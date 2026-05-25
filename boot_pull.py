#!/usr/bin/env python3
# ============================================
#  Shadow Core Boot Puller v2
#  Device: OPPO Reno 5 CPH2159 | ColorOS
#  Platform: Termux (Android)
# ============================================

import subprocess
import sys
import os
import time
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
{R}╔══════════════════════════════════════╗
║  {W}Shadow Core Boot Puller  v2{R}        ║
║  {B}OPPO Reno 5 CPH2159 | ColorOS{R}     ║
╚══════════════════════════════════════╝{RESET}
"""

OUTPUT_DIR = os.path.expanduser("~/boot_images")

def success(msg): print(f"{G}[✓] {msg}{RESET}")
def error(msg):   print(f"{R}[✗] {msg}{RESET}")
def warn(msg):    print(f"{Y}[!] {msg}{RESET}")
def info(msg):    print(f"{C}[*] {msg}{RESET}")

def run_su(cmd):
    """تشغيل أمر بصلاحية root وإرجاع (stdout, stderr, returncode)"""
    try:
        result = subprocess.run(
            ["su", "-c", cmd],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except FileNotFoundError:
        return "", "su not found", 127
    except subprocess.TimeoutExpired:
        return "", "timeout", 1

def check_root():
    info("فحص صلاحيات Root...")
    stdout, stderr, code = run_su("id")

    # تحقق حقيقي: الـ output يجب أن يحتوي uid=0
    if code == 0 and "uid=0" in stdout:
        success(f"Root متاح! ({stdout.split()[0]})")
        return True
    else:
        error("Root غير متاح!")
        if "No su program" in stderr or "su not found" in stderr:
            print(f"\n{Y}الجهاز غير مفتوح (Not Rooted){RESET}")
            print(f"{W}لتفعيل Root على CPH2159 تحتاج:{RESET}")
            print(f"  1. فتح bootloader (Unlock OEM)")
            print(f"  2. تثبيت Magisk عبر Recovery")
            print(f"  3. تفعيل Magisk في الإعدادات\n")
        else:
            error(f"خطأ: {stderr[:100]}")
        return False

def check_dependencies():
    info("فحص الأدوات المطلوبة...")
    tools = ["dd", "ls", "blockdev", "stat"]
    missing = []

    for tool in tools:
        stdout, _, code = run_su(f"which {tool} 2>/dev/null || command -v {tool} 2>/dev/null")
        if code == 0 and stdout:
            success(f"{tool} ✓")
        else:
            missing.append(tool)
            warn(f"{tool} مفقود")

    if "dd" in missing:
        print(f"\n{Y}لتثبيت الأدوات:{RESET}")
        print(f"  {B}pkg install coreutils{RESET}\n")
        return False

    return True

def find_boot_partition():
    info("البحث عن boot partition للـ CPH2159...")

    # مسارات محتملة لـ MediaTek Helio P95
    candidates = [
        "/dev/block/by-name/boot",
        "/dev/block/by-name/boot_a",
        "/dev/block/by-name/boot_b",
        "/dev/block/bootdevice/by-name/boot",
        "/dev/block/platform/bootdevice/by-name/boot",
        "/dev/block/mmcblk0p34",
        "/dev/block/mmcblk0p35",
    ]

    for path in candidates:
        stdout, stderr, code = run_su(f"test -e {path} && echo EXISTS")
        if code == 0 and "EXISTS" in stdout:
            success(f"تم العثور على: {path}")
            return path

    # بحث عبر ls فقط في المجلد الصحيح
    info("بحث متعمق في /dev/block/by-name/...")
    stdout, stderr, code = run_su("ls /dev/block/by-name/ 2>/dev/null")

    if code != 0 or not stdout or "No su" in stdout or "not found" in stdout.lower():
        return None

    # فلترة: فقط أسماء صالحة تحتوي كلمة boot
    valid_partitions = []
    for line in stdout.splitlines():
        line = line.strip()
        # اسم partition صالح: حروف وأرقام و _ و - فقط، وقصير
        if "boot" in line.lower() and len(line) < 30 and " " not in line:
            valid_partitions.append(line)

    for name in valid_partitions:
        full_path = f"/dev/block/by-name/{name}"
        success(f"وجدت partition: {full_path}")

    if valid_partitions:
        chosen = f"/dev/block/by-name/{valid_partitions[0]}"
        info(f"سيتم استخدام: {chosen}")
        return chosen

    return None

def get_partition_size(partition):
    stdout, _, code = run_su(f"blockdev --getsize64 {partition} 2>/dev/null")
    if code == 0 and stdout.isdigit():
        return int(stdout)
    return 67108864  # 64MB افتراضي

def pull_boot(partition):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(OUTPUT_DIR, f"boot_CPH2159_{timestamp}.img")

    size = get_partition_size(partition)
    size_mb = size / (1024 * 1024)

    info(f"جاري سحب boot.img من: {partition}")
    info(f"الحجم التقريبي: {size_mb:.1f} MB")
    info(f"مسار الحفظ: {output_file}")

    print(f"\n{Y}{'═'*42}{RESET}")

    start = time.time()
    stdout, stderr, code = run_su(
        f"dd if={partition} of={output_file} bs=4096"
    )
    elapsed = time.time() - start

    print(f"{Y}{'═'*42}{RESET}\n")

    if not os.path.exists(output_file) or os.path.getsize(output_file) == 0:
        error("فشل السحب — الملف غير موجود أو فارغ")
        if stderr:
            error(f"تفاصيل: {stderr[:200]}")
        return None

    file_size = os.path.getsize(output_file)
    success(f"تم السحب بنجاح!")
    success(f"الملف: {output_file}")
    success(f"الحجم: {file_size / (1024*1024):.2f} MB")
    success(f"الوقت: {elapsed:.1f} ثانية")

    verify_boot_image(output_file)
    return output_file

def verify_boot_image(filepath):
    info("التحقق من صحة الملف...")
    try:
        with open(filepath, 'rb') as f:
            magic = f.read(8)
        if magic[:8] == b'ANDROID!':
            success("ملف boot.img صحيح ✅ (Magic: ANDROID!)")
        elif magic[:3] == b'\x1f\x8b\x08':
            warn("الملف مضغوط gzip")
        else:
            warn(f"Magic غير معروف: {magic.hex()} — قد يكون صحيحاً")
    except Exception as e:
        warn(f"تعذر التحقق: {e}")

def show_next_steps(output_file):
    print(f"\n{C}{'═'*42}")
    print(f"  الخطوات التالية")
    print(f"{'═'*42}{RESET}")
    print(f"{W}نقل للكمبيوتر:{RESET}")
    print(f"  {B}adb pull {output_file}{RESET}")
    print(f"{W}فك تشفير الـ boot.img:{RESET}")
    print(f"  {B}magiskboot unpack boot.img{RESET}")
    print(f"{W}التحقق من نوع الملف:{RESET}")
    print(f"  {B}file {output_file}{RESET}")
    print(f"{C}{'═'*42}{RESET}\n")

def main():
    print(BANNER)
    print(f"{B}الجهاز: OPPO Reno 5 CPH2159 | ColorOS | Helio P95{RESET}\n")

    # 1. تحقق من Root
    if not check_root():
        sys.exit(1)

    print()

    # 2. تحقق من الأدوات
    if not check_dependencies():
        sys.exit(1)

    print()

    # 3. ابحث عن الـ partition
    partition = find_boot_partition()
    if not partition:
        error("لم يتم العثور على boot partition!")
        error("تأكد من أن Root يعمل بشكل كامل")
        sys.exit(1)

    print()

    # 4. تأكيد المستخدم
    print(f"{Y}سيتم سحب boot.img من: {partition}{RESET}")
    try:
        confirm = input(f"{W}هل تريد المتابعة؟ (y/n): {RESET}").strip().lower()
    except KeyboardInterrupt:
        print()
        warn("تم الإلغاء.")
        sys.exit(0)

    if confirm not in ['y', 'yes', 'نعم', 'ي']:
        warn("تم الإلغاء.")
        sys.exit(0)

    print()

    # 5. سحب الـ boot
    output = pull_boot(partition)

    if output:
        show_next_steps(output)
        success("🖤 Shadow Core — مهمة مكتملة")
    else:
        error("فشلت العملية.")
        sys.exit(1)

if __name__ == "__main__":
    main()
