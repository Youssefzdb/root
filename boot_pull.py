#!/usr/bin/env python3
# ============================================
#  Shadow Core Boot Puller v4
#  Device: OPPO Reno 5 CPH2159 | ColorOS
#  Platform: Termux — No Root, No PC
#  Method: Download OTA from OPPO servers
#          + Extract boot.img automatically
# ============================================

import subprocess
import sys
import os
import json
import zipfile
import shutil
import struct
import hashlib
import urllib.request
import urllib.error
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
{R}╔══════════════════════════════════════════════╗
║  {W}Shadow Core Boot Puller  v4{R}               ║
║  {B}OPPO Reno 5 CPH2159 | No Root | No PC{R}    ║
║  {B}Method: OPPO OTA Server → boot.img{R}       ║
╚══════════════════════════════════════════════╝{RESET}
"""

OUTPUT_DIR = os.path.expanduser("~/boot_images")
TEMP_DIR   = os.path.expanduser("~/boot_images/.tmp")

# ─── CPH2159 Device Info ──────────────────
DEVICE_INFO = {
    "product_name": "CPH2159EX",        # ro.product.name
    "ota_version":  "CPH2159EX_11_A.21_210127",  # ro.build.version.ota (مثال)
    "rui_version":  1,                   # ColorOS = 1
    "nv_id":        "0",
    "region":       0,                   # GL=0, CN=1, IN=2, EU=3
}

def success(msg): print(f"{G}[✓] {msg}{RESET}")
def error(msg):   print(f"{R}[✗] {msg}{RESET}")
def warn(msg):    print(f"{Y}[!] {msg}{RESET}")
def info(msg):    print(f"{C}[*] {msg}{RESET}")
def step(n, msg): print(f"\n{W}━━[{n}] {msg}━━{RESET}")

# ─── Read device props ────────────────────
def get_prop(key):
    try:
        r = subprocess.run(
            ["getprop", key],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5
        )
        val = r.stdout.strip()
        return val if val else None
    except:
        return None

def read_device_info():
    info("قراءة معلومات الجهاز...")
    props = {
        "product_name": get_prop("ro.product.name"),
        "ota_version":  get_prop("ro.build.version.ota"),
        "rui_version":  get_prop("ro.build.version.realmeui") or get_prop("ro.build.version.oplusrom"),
        "nv_id":        get_prop("ro.build.oplus_nv_id") or "0",
    }

    for k, v in props.items():
        if v:
            success(f"{k}: {v}")
        else:
            warn(f"{k}: غير متاح — سيُستخدم الافتراضي")

    # استخدم الافتراضي لـ CPH2159 إذا ما قرأنا البيانات
    final = {}
    final["product_name"] = props["product_name"] or DEVICE_INFO["product_name"]
    final["ota_version"]  = props["ota_version"]  or DEVICE_INFO["ota_version"]
    final["rui_version"]  = int(props["rui_version"] or DEVICE_INFO["rui_version"])
    final["nv_id"]        = props["nv_id"] or DEVICE_INFO["nv_id"]
    final["region"]       = DEVICE_INFO["region"]

    return final

# ─── Install realme-ota ───────────────────
def install_realme_ota():
    info("التحقق من realme-ota...")
    try:
        r = subprocess.run(
            [sys.executable, "-m", "realme_ota", "--help"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10
        )
        if r.returncode == 0 or "usage" in r.stdout.lower() or "usage" in r.stderr.lower():
            success("realme-ota مثبت مسبقاً")
            return True
    except:
        pass

    info("تثبيت realme-ota من GitHub...")
    try:
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet",
             "git+https://github.com/R0rt1z2/realme-ota"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=120
        )
        if r.returncode == 0:
            success("تم تثبيت realme-ota!")
            return True
        else:
            # جرب pip install requests أولاً
            warn("فشل التثبيت من git — جاري تجربة طريقة بديلة...")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--quiet", "requests", "pycryptodome"],
                timeout=60
            )
            return install_realme_ota_manual()
    except Exception as e:
        error(f"فشل التثبيت: {e}")
        return False

def install_realme_ota_manual():
    """تحميل realme-ota مباشرة بدون git"""
    try:
        url = "https://raw.githubusercontent.com/R0rt1z2/realme-ota/master/realme_ota/main.py"
        os.makedirs(TEMP_DIR, exist_ok=True)
        dst = os.path.join(TEMP_DIR, "realme_ota_main.py")
        urllib.request.urlretrieve(url, dst)
        success("تم تحميل realme-ota يدوياً")
        return True
    except Exception as e:
        error(f"فشل التحميل: {e}")
        return False

# ─── Query OPPO OTA server ────────────────
def query_ota_server(device):
    info("الاتصال بسيرفر OPPO للبحث عن OTA...")

    cmd = [
        sys.executable, "-m", "realme_ota",
        "-s",  # silent
        "-d", os.path.join(TEMP_DIR, "ota_response.json"),
        device["product_name"],
        device["ota_version"],
        str(device["rui_version"]),
        device["nv_id"],
        "-r", str(device["region"])
    ]

    try:
        os.makedirs(TEMP_DIR, exist_ok=True)
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           text=True, timeout=60)
        output = r.stdout + r.stderr

        # ابحث عن URL في الـ output
        download_url = extract_url_from_output(output)
        if download_url:
            return {"url": download_url, "source": "realme-ota"}

        # جرب قراءة الـ dump file
        dump_file = os.path.join(TEMP_DIR, "ota_response.json")
        if os.path.exists(dump_file):
            with open(dump_file) as f:
                data = json.load(f)
            url = extract_url_from_json(data)
            if url:
                return {"url": url, "source": "realme-ota", "data": data}

        warn(f"output: {output[:300]}")
        return None

    except subprocess.TimeoutExpired:
        error("انتهى الوقت — السيرفر لا يستجيب")
        return None
    except Exception as e:
        error(f"خطأ: {e}")
        return None

def extract_url_from_output(text):
    import re
    patterns = [
        r'https?://[^\s\'"]+\.(?:zip|ozip|ofp)',
        r'https?://[^\s\'"]+download[^\s\'"]+',
        r'componentUrl[\'"]?\s*[=:]\s*[\'"]?(https?://[^\s\'"]+)',
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return m.group(0).strip("'\",")
    return None

def extract_url_from_json(data):
    """استخرج URL من JSON response"""
    if isinstance(data, dict):
        for key in ["url", "dlUrl", "componentUrl", "download_url", "fileUrl"]:
            if key in data and data[key]:
                return data[key]
        # بحث عميق
        for v in data.values():
            result = extract_url_from_json(v)
            if result:
                return result
    elif isinstance(data, list):
        for item in data:
            result = extract_url_from_json(item)
            if result:
                return result
    elif isinstance(data, str) and data.startswith("http"):
        return data
    return None

# ─── Alternative: danielspringer backend ─
def query_danielspringer(device):
    info("جاري الاستعلام من danielspringer.at...")
    try:
        url = f"https://roms.danielspringer.at/index.php?view=ota&device={device['product_name']}&region=global&version_index=0"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        dl_url = extract_url_from_json(data)
        if dl_url:
            return {"url": dl_url, "source": "danielspringer"}
    except Exception as e:
        warn(f"danielspringer: {e}")
    return None

# ─── Download file ────────────────────────
def download_file(url, dest_path):
    info(f"جاري التحميل...")
    info(f"URL: {url[:80]}...")

    os.makedirs(os.path.dirname(dest_path), exist_ok=True)

    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36"
        })

        with urllib.request.urlopen(req, timeout=30) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            total_mb = total / (1024*1024)
            info(f"حجم الملف: {total_mb:.0f} MB")

            if total_mb > 3000:
                warn(f"الملف كبير جداً ({total_mb:.0f} MB) — قد يستغرق وقتاً طويلاً")

            downloaded = 0
            chunk = 1024 * 1024  # 1MB chunks
            with open(dest_path, 'wb') as f:
                while True:
                    buf = resp.read(chunk)
                    if not buf:
                        break
                    f.write(buf)
                    downloaded += len(buf)
                    if total > 0:
                        pct = downloaded / total * 100
                        done_mb = downloaded / (1024*1024)
                        print(f"\r{C}  [{pct:5.1f}%] {done_mb:.0f}/{total_mb:.0f} MB{RESET}", end="", flush=True)

        print()
        size = os.path.getsize(dest_path)
        if size > 0:
            success(f"تم التحميل: {size/(1024*1024):.1f} MB")
            return True
        else:
            error("الملف فارغ!")
            return False

    except Exception as e:
        print()
        error(f"فشل التحميل: {e}")
        return False

# ─── OTA Decrypt (.ozip) ─────────────────
def decrypt_ozip(ozip_path, out_dir):
    """فك تشفير .ozip باستخدام bkerler/oppo_ozip_decrypt"""
    info("فك تشفير .ozip...")

    # حاول تثبيت pycryptodome
    subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "pycryptodome"], timeout=60)

    # حمّل سكريبت الفك مباشرة
    script_url = "https://raw.githubusercontent.com/bkerler/oppo_ozip_decrypt/master/ozipdecrypt.py"
    script_path = os.path.join(TEMP_DIR, "ozipdecrypt.py")

    try:
        urllib.request.urlretrieve(script_url, script_path)
    except Exception as e:
        error(f"فشل تحميل أداة الفك: {e}")
        return None

    r = subprocess.run(
        [sys.executable, script_path, ozip_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, cwd=out_dir, timeout=300
    )

    # ابحث عن الملف المفكوك
    for f in os.listdir(out_dir):
        if f.endswith(".zip") and "ozip" not in f.lower():
            return os.path.join(out_dir, f)

    # أحياناً يُنشئ نفس الاسم بـ .zip
    zip_path = ozip_path.replace(".ozip", ".zip")
    if os.path.exists(zip_path):
        return zip_path

    warn(f"stdout: {r.stdout[:200]}")
    warn(f"stderr: {r.stderr[:200]}")
    return None

# ─── Extract boot.img ─────────────────────
def extract_boot_from_zip(zip_path, out_dir):
    info(f"استخراج boot.img من: {os.path.basename(zip_path)}")
    os.makedirs(out_dir, exist_ok=True)

    boot_names = ['boot.img', 'boot_a.img', 'boot_b.img', 'BOOT.IMG']

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            all_files = zf.namelist()

            # اعرض ملفات IMG
            imgs = [f for f in all_files if f.lower().endswith('.img')]
            if imgs:
                info(f"ملفات IMG في الأرشيف ({len(imgs)} ملف):")
                for img in imgs[:10]:
                    print(f"   {B}• {img}{RESET}")

            # ابحث عن boot.img
            found = None
            for name in boot_names:
                for f in all_files:
                    if os.path.basename(f).lower() == name.lower():
                        found = f
                        break
                if found:
                    break

            if not found:
                # بحث في ZIPs الفرعية
                warn("boot.img غير موجود مباشرة — فحص ZIPs الفرعية...")
                for f in all_files:
                    if f.lower().endswith('.zip'):
                        sub_data = zf.read(f)
                        sub_path = os.path.join(TEMP_DIR, os.path.basename(f))
                        with open(sub_path, 'wb') as sf:
                            sf.write(sub_data)
                        result = extract_boot_from_zip(sub_path, out_dir)
                        if result:
                            return result
                return None

            # استخراج
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_file = os.path.join(out_dir, f"boot_CPH2159_{ts}.img")

            info(f"استخراج: {found} → {os.path.basename(out_file)}")
            with zf.open(found) as src, open(out_file, 'wb') as dst:
                shutil.copyfileobj(src, dst)

            return out_file

    except zipfile.BadZipFile:
        error("ملف ZIP تالف")
        return None
    except Exception as e:
        error(f"خطأ: {e}")
        return None

# ─── Verify boot.img ──────────────────────
def verify_boot(filepath):
    info("التحقق من صحة boot.img...")
    try:
        with open(filepath, 'rb') as f:
            magic = f.read(8)
        if magic[:8] == b'ANDROID!':
            success("boot.img صحيح ✅ (ANDROID! magic)")
        elif magic[:3] == b'\x1f\x8b\x08':
            warn("ملف gzip — قد يكون kernel مباشرة")
        else:
            warn(f"Magic: {magic.hex()} — قد يكون صحيحاً")
    except Exception as e:
        warn(f"تعذر التحقق: {e}")

def show_next_steps(output_file):
    print(f"\n{C}{'═'*46}")
    print(f"  الخطوات التالية — Root بـ Magisk")
    print(f"{'═'*46}{RESET}")
    print(f"{W}1. ثبّت Magisk APK:{RESET}")
    print(f"   {B}github.com/topjohnwu/Magisk/releases{RESET}")
    print(f"{W}2. Magisk → Install → Patch a File{RESET}")
    print(f"{W}3. اختر: {B}{output_file}{RESET}")
    print(f"{W}4. فلّش الملف الناتج:{RESET}")
    print(f"   {B}fastboot flash boot magisk_patched.img{RESET}")
    print(f"{C}{'═'*46}{RESET}\n")

# ─── Main ─────────────────────────────────
def main():
    print(BANNER)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)

    # ─ 1. قراءة معلومات الجهاز ─
    step(1, "قراءة معلومات الجهاز")
    device = read_device_info()

    print(f"\n{Y}معلومات الجهاز المستخدمة:{RESET}")
    for k, v in device.items():
        print(f"  {B}{k}:{RESET} {W}{v}{RESET}")

    print(f"\n{W}هل المعلومات صحيحة؟ (y/n) أو اضغط Enter للتأكيد: {RESET}", end="")
    try:
        confirm = input().strip().lower()
        if confirm == 'n':
            print(f"{W}أدخل OTA version يدوياً (مثال: CPH2159EX_11_A.21_210127): {RESET}", end="")
            device["ota_version"] = input().strip() or device["ota_version"]
    except KeyboardInterrupt:
        print()
        sys.exit(0)

    # ─ 2. تثبيت realme-ota ─
    step(2, "تجهيز أداة الاستعلام")
    ota_tool_ok = install_realme_ota()

    # ─ 3. استعلام OTA ─
    step(3, "الاستعلام عن OTA من OPPO")
    ota_result = None

    if ota_tool_ok:
        ota_result = query_ota_server(device)

    if not ota_result:
        warn("realme-ota لم تُرجع نتيجة — جاري تجربة danielspringer...")
        ota_result = query_danielspringer(device)

    if not ota_result:
        error("لم يتم العثور على OTA لهذا الجهاز")
        print(f"\n{Y}الأسباب المحتملة:{RESET}")
        print(f"  • الجهاز على أحدث إصدار (لا يوجد OTA جديد)")
        print(f"  • السيرفر يحتاج IMEI للتحقق")
        print(f"  • جرب تحديث ota_version في الكود")
        print(f"\n{W}هل تريد إدخال رابط OTA يدوياً؟ (y/n): {RESET}", end="")
        try:
            if input().strip().lower() == 'y':
                print(f"{W}الرابط: {RESET}", end="")
                manual_url = input().strip()
                if manual_url:
                    ota_result = {"url": manual_url, "source": "manual"}
        except:
            pass

        if not ota_result:
            sys.exit(1)

    download_url = ota_result["url"]
    success(f"OTA URL: {download_url[:80]}...")

    # ─ 4. تحميل الملف ─
    step(4, "تحميل OTA package")

    ext = ".ozip" if ".ozip" in download_url else ".zip"
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    dl_path = os.path.join(TEMP_DIR, f"CPH2159_OTA_{ts}{ext}")

    if not download_file(download_url, dl_path):
        sys.exit(1)

    # ─ 5. فك التشفير (إذا .ozip) ─
    step(5, "معالجة الملف")

    zip_path = dl_path
    if dl_path.endswith(".ozip"):
        decrypted = decrypt_ozip(dl_path, TEMP_DIR)
        if decrypted:
            zip_path = decrypted
            success(f"تم فك التشفير: {os.path.basename(zip_path)}")
        else:
            warn("فشل فك التشفير — سنحاول مباشرة كـ ZIP")

    # ─ 6. استخراج boot.img ─
    step(6, "استخراج boot.img")
    boot_file = extract_boot_from_zip(zip_path, OUTPUT_DIR)

    # نظّف الملفات المؤقتة
    try:
        shutil.rmtree(TEMP_DIR)
    except:
        pass

    print()

    if boot_file and os.path.exists(boot_file):
        size = os.path.getsize(boot_file) / (1024*1024)
        success(f"تم استخراج boot.img!")
        success(f"الملف: {boot_file}")
        success(f"الحجم: {size:.2f} MB")
        verify_boot(boot_file)
        show_next_steps(boot_file)
        success("🖤 Shadow Core — مهمة مكتملة")
    else:
        error("لم يتم العثور على boot.img في الـ OTA package")
        sys.exit(1)

if __name__ == "__main__":
    main()
