#!/usr/bin/env python3
# ============================================
#  Shadow Core Boot Puller v3
#  Device: OPPO Reno 5 CPH2159 | ColorOS
#  Platform: Termux (Android) — No Root needed
#  Method: Extract boot.img from OFP/ZIP ROM
# ============================================

import subprocess
import sys
import os
import zipfile
import shutil
import struct
import tempfile
from datetime import datetime

# ─── Colors ───────────────────────────────
R  = "\033[31m"
G  = "\033[32m"
Y  = "\033[33m"
C  = "\033[36m"
W  = "\033[97m"
B  = "\033[90m"
RESET = "\033[0m"

BANNER = f"""
{R}╔══════════════════════════════════════════╗
║  {W}Shadow Core Boot Puller  v3{R}           ║
║  {B}OPPO Reno 5 CPH2159 | No Root Needed{R} ║
╚══════════════════════════════════════════╝{RESET}
"""

OUTPUT_DIR = os.path.expanduser("~/boot_images")

def success(msg): print(f"{G}[✓] {msg}{RESET}")
def error(msg):   print(f"{R}[✗] {msg}{RESET}")
def warn(msg):    print(f"{Y}[!] {msg}{RESET}")
def info(msg):    print(f"{C}[*] {msg}{RESET}")
def step(msg):    print(f"\n{W}━━ {msg} ━━{RESET}")

# ─── OFP Decrypt (Qualcomm / CPH2159) ────
# Based on bkerler/oppo_decrypt (ofp_qc_decrypt.py)
OFP_MAGIC = b"OPPOENCRYPT!"

def is_ofp_encrypted(filepath):
    """تحقق إذا كان الملف OFP مشفر"""
    with open(filepath, 'rb') as f:
        magic = f.read(12)
    return magic == OFP_MAGIC

def ofp_qc_decrypt(ofp_path, out_dir):
    """فك تشفير OFP لـ Qualcomm (CPH2159)"""
    info(f"فك تشفير OFP: {os.path.basename(ofp_path)}")
    os.makedirs(out_dir, exist_ok=True)

    with open(ofp_path, 'rb') as f:
        magic = f.read(12)
        if magic != OFP_MAGIC:
            warn("الملف غير مشفر أو صيغة مختلفة — سنحاول كـ ZIP مباشرة")
            return False

        # قراءة header
        f.seek(0)
        data = f.read()

    # OFP = ZIP مشفر بـ XOR مع key ثابت لـ Qualcomm
    # Key الـ Qualcomm OPPO
    key = bytearray([
        0x6F, 0x70, 0x70, 0x6F, 0x71, 0x63, 0x6F, 0x6D,
        0x6D, 0x75, 0x6E, 0x69, 0x63, 0x61, 0x74, 0x69
    ])

    decrypted = bytearray(len(data))
    for i in range(len(data)):
        decrypted[i] = data[i] ^ key[i % len(key)]

    # احفظ كـ zip مؤقت
    tmp_zip = os.path.join(out_dir, "_decrypted.zip")
    with open(tmp_zip, 'wb') as f:
        f.write(decrypted)

    # تحقق من magic ZIP
    with open(tmp_zip, 'rb') as f:
        zip_magic = f.read(4)

    if zip_magic != b'PK\x03\x04':
        warn("فك التشفير لم يعمل بالـ XOR القياسي — الملف قد يكون MTK أو بصيغة مختلفة")
        os.remove(tmp_zip)
        return False

    success("تم فك التشفير بنجاح!")
    return tmp_zip

def extract_from_zip(zip_path, out_dir):
    """استخراج boot.img من ZIP/OFP"""
    os.makedirs(out_dir, exist_ok=True)
    boot_targets = ['boot.img', 'boot_a.img', 'boot_b.img', 'BOOT.IMG']

    info(f"فحص محتوى الملف...")

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            all_files = zf.namelist()

            # اطبع ملفات IMG الموجودة
            img_files = [f for f in all_files if f.lower().endswith('.img')]
            if img_files:
                info(f"ملفات IMG موجودة في الأرشيف:")
                for img in img_files[:15]:
                    print(f"   {B}{img}{RESET}")
                if len(img_files) > 15:
                    print(f"   {B}... و {len(img_files)-15} ملفات أخرى{RESET}")
            else:
                warn("لا توجد ملفات .img مباشرة — قد تكون داخل ZIP فرعي")

            # ابحث عن boot.img
            found = None
            for target in boot_targets:
                for f in all_files:
                    if os.path.basename(f).lower() == target.lower():
                        found = f
                        break
                if found:
                    break

            if not found:
                # بحث أعمق — zip داخل zip
                warn("boot.img غير موجود مباشرة — أبحث داخل ZIPs الفرعية...")
                for f in all_files:
                    if f.lower().endswith('.zip') or f.lower().endswith('.ofp'):
                        info(f"ZIP فرعي: {f}")
                        sub_zip_data = zf.read(f)
                        sub_path = os.path.join(out_dir, os.path.basename(f))
                        with open(sub_path, 'wb') as sf:
                            sf.write(sub_zip_data)
                        result = extract_from_zip(sub_path, out_dir)
                        os.remove(sub_path)
                        if result:
                            return result
                return None

            # استخرج boot.img
            info(f"جاري استخراج: {found}")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_file = os.path.join(out_dir, f"boot_CPH2159_{timestamp}.img")

            with zf.open(found) as src, open(out_file, 'wb') as dst:
                shutil.copyfileobj(src, dst)

            return out_file

    except zipfile.BadZipFile:
        error("الملف ليس ZIP صحيح")
        return None
    except Exception as e:
        error(f"خطأ أثناء الاستخراج: {e}")
        return None

def verify_boot_image(filepath):
    """تحقق من صحة boot.img"""
    info("التحقق من صحة الملف...")
    try:
        with open(filepath, 'rb') as f:
            magic = f.read(8)
        if magic[:8] == b'ANDROID!':
            success("ملف boot.img صحيح ✅ (Magic: ANDROID!)")
            return True
        elif magic[:3] == b'\x1f\x8b\x08':
            warn("الملف مضغوط gzip — قد يكون kernel مباشرة")
            return True
        else:
            warn(f"Magic: {magic.hex()} — قد يكون صحيحاً بصيغة مختلفة")
            return True
    except Exception as e:
        warn(f"تعذر التحقق: {e}")
        return False

def check_dependencies():
    """تحقق من وجود Python packages"""
    info("فحص المتطلبات...")
    try:
        import zipfile
        success("zipfile ✓")
    except:
        error("zipfile غير موجود")
        return False
    return True

def find_rom_file():
    """ابحث عن ملف ROM في مجلدات شائعة"""
    search_dirs = [
        os.path.expanduser("~/storage/downloads"),
        os.path.expanduser("~/storage/shared/Download"),
        "/sdcard/Download",
        "/sdcard/Downloads",
        os.path.expanduser("~"),
    ]

    found_files = []
    extensions = ['.ofp', '.zip', '.OFP', '.ZIP']

    for d in search_dirs:
        if os.path.exists(d):
            try:
                for f in os.listdir(d):
                    if any(f.endswith(ext) for ext in extensions):
                        full = os.path.join(d, f)
                        size_mb = os.path.getsize(full) / (1024*1024)
                        # فقط ملفات أكبر من 50MB (ROM حقيقي)
                        if size_mb > 50:
                            found_files.append((full, size_mb))
            except:
                pass

    return found_files

def show_next_steps(output_file):
    print(f"\n{C}{'═'*44}")
    print(f"  الخطوات التالية — تثبيت Magisk Root")
    print(f"{'═'*44}{RESET}")
    print(f"{W}1. ثبّت تطبيق Magisk من:{RESET}")
    print(f"   {B}https://github.com/topjohnwu/Magisk/releases{RESET}")
    print(f"{W}2. افتح Magisk → Install → Select and Patch a File{RESET}")
    print(f"{W}3. اختر الملف:{RESET}")
    print(f"   {B}{output_file}{RESET}")
    print(f"{W}4. سيُنشئ Magisk ملف:{RESET}")
    print(f"   {B}magisk_patched_xxxx.img{RESET}")
    print(f"{W}5. فلّش الملف عبر fastboot:{RESET}")
    print(f"   {B}fastboot flash boot magisk_patched.img{RESET}")
    print(f"{C}{'═'*44}{RESET}\n")

def main():
    print(BANNER)
    print(f"{B}الجهاز: OPPO Reno 5 CPH2159 | ColorOS | Helio P95{RESET}")
    print(f"{B}الوضع: استخراج boot.img من ROM بدون Root{RESET}\n")

    if not check_dependencies():
        sys.exit(1)

    step("البحث عن ملف ROM")

    rom_file = None
    found_files = find_rom_file()

    if found_files:
        info(f"تم العثور على {len(found_files)} ملف ROM محتمل:")
        for i, (path, size) in enumerate(found_files):
            print(f"  {Y}[{i+1}]{RESET} {os.path.basename(path)} {B}({size:.0f} MB){RESET}")

        print(f"\n{W}اختر رقم الملف، أو اضغط 0 لإدخال مسار يدوي: {RESET}", end="")
        try:
            choice = input().strip()
            if choice == '0' or not choice:
                rom_file = None
            else:
                idx = int(choice) - 1
                if 0 <= idx < len(found_files):
                    rom_file, _ = found_files[idx]
        except (ValueError, KeyboardInterrupt):
            pass

    if not rom_file:
        print(f"\n{W}أدخل المسار الكامل لملف OFP أو ZIP:{RESET}")
        print(f"{B}مثال: /sdcard/Download/CPH2159_firmware.ofp{RESET}")
        print(f"{W}المسار: {RESET}", end="")
        try:
            rom_file = input().strip().strip("'\"")
        except KeyboardInterrupt:
            print()
            warn("تم الإلغاء.")
            sys.exit(0)

    if not rom_file or not os.path.exists(rom_file):
        error(f"الملف غير موجود: {rom_file}")
        print(f"\n{Y}كيف تحصل على ملف ROM للـ CPH2159:{RESET}")
        print(f"  1. ابحث عن: {W}CPH2159 OFP firmware download{RESET}")
        print(f"  2. مواقع موثوقة: {B}oppoflash.com, androidfilehost.com{RESET}")
        print(f"  3. حجم الملف عادة: {B}500MB - 3GB{RESET}")
        sys.exit(1)

    file_size = os.path.getsize(rom_file) / (1024*1024)
    success(f"الملف: {os.path.basename(rom_file)} ({file_size:.0f} MB)")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    step("تحليل الملف")

    ext = os.path.splitext(rom_file)[1].lower()
    extracted_boot = None

    if ext == '.ofp':
        info("صيغة OFP مكتشفة — جاري فك التشفير...")
        if is_ofp_encrypted(rom_file):
            decrypted = ofp_qc_decrypt(rom_file, OUTPUT_DIR)
            if decrypted:
                step("استخراج boot.img من OFP")
                extracted_boot = extract_from_zip(decrypted, OUTPUT_DIR)
                os.remove(decrypted)
            else:
                # جرب مباشرة كـ ZIP
                warn("جاري المحاولة كـ ZIP مباشرة...")
                extracted_boot = extract_from_zip(rom_file, OUTPUT_DIR)
        else:
            info("OFP غير مشفر — استخراج مباشر...")
            extracted_boot = extract_from_zip(rom_file, OUTPUT_DIR)

    elif ext == '.zip':
        step("استخراج boot.img من ZIP")
        extracted_boot = extract_from_zip(rom_file, OUTPUT_DIR)

    else:
        error(f"صيغة غير مدعومة: {ext}")
        error("الصيغ المدعومة: .ofp .zip")
        sys.exit(1)

    print()

    if extracted_boot and os.path.exists(extracted_boot):
        size = os.path.getsize(extracted_boot) / (1024*1024)
        success(f"تم استخراج boot.img!")
        success(f"الملف: {extracted_boot}")
        success(f"الحجم: {size:.2f} MB")
        verify_boot_image(extracted_boot)
        show_next_steps(extracted_boot)
        success("🖤 Shadow Core — مهمة مكتملة")
    else:
        error("لم يتم العثور على boot.img في الملف المحدد")
        print(f"\n{Y}تأكد من:{RESET}")
        print(f"  - أن الملف هو ROM خاص بـ CPH2159")
        print(f"  - أن الملف لم يتلف أثناء التحميل")
        print(f"  - جرب ملف ROM من مصدر آخر")
        sys.exit(1)

if __name__ == "__main__":
    main()
