#!/usr/bin/env python3
# ============================================
#  Shadow Core Boot Puller
#  Device: OPPO Reno 5 CPH2159 | ColorOS
#  Platform: Termux (Android)
# ============================================

import subprocess
import sys
import os
import time
from datetime import datetime

# ─── Colors ───────────────────────────────
R = "\033[31m"
G = "\033[32m"
Y = "\033[33m"
C = "\033[36m"
W = "\033[97m"
B = "\033[90m"
RESET = "\033[0m"
BOLD = "\033[1m"

BANNER = f"""
{R}╔══════════════════════════════════════╗
║   {W}Shadow Core Boot Puller{R}            ║
║   {B}OPPO Reno 5 CPH2159 | ColorOS{R}     ║
╚══════════════════════════════════════╝{RESET}
"""

# ─── Boot partitions (CPH2159 MediaTek) ───
BOOT_PARTITIONS = [
    "/dev/block/by-name/boot",
    "/dev/block/by-name/boot_a",
    "/dev/block/by-name/boot_b",
    "/dev/block/bootdevice/by-name/boot",
    "/dev/block/platform/bootdevice/by-name/boot",
]

OUTPUT_DIR = os.path.expanduser("~/boot_images")

def log(msg, color=W):
    print(f"{color}[{datetime.now().strftime('%H:%M:%S')}] {msg}{RESET}")

def success(msg):
    print(f"{G}[✓] {msg}{RESET}")

def error(msg):
    print(f"{R}[✗] {msg}{RESET}")

def warn(msg):
    print(f"{Y}[!] {msg}{RESET}")

def info(msg):
    print(f"{C}[*] {msg}{RESET}")

def run(cmd, shell=True, capture=True):
    try:
        result = subprocess.run(
            cmd, shell=shell,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return result
    except Exception as e:
        return None

def check_root():
    info("فحص صلاحيات Root...")
    result = run("su -c 'id'")
    if result and "root" in result.stdout:
        success("Root متاح!")
        return True
    else:
        error("Root غير متاح! تأكد من تفعيل Magisk أو SuperSU")
        return False

def check_dependencies():
    info("فحص الأدوات المطلوبة...")
    tools = ["dd", "ls", "stat"]
    missing = []
    for tool in tools:
        r = run(f"which {tool}")
        if r and r.returncode == 0:
            success(f"{tool} موجود")
        else:
            missing.append(tool)
            warn(f"{tool} غير موجود")
    
    if missing:
        warn(f"أدوات مفقودة: {', '.join(missing)}")
        warn("جرب: pkg install coreutils")
        return False
    return True

def find_boot_partition():
    info("البحث عن boot partition...")
    
    for partition in BOOT_PARTITIONS:
        result = run(f"su -c 'ls -la {partition} 2>/dev/null'")
        if result and result.returncode == 0 and partition in result.stdout:
            success(f"تم العثور على: {partition}")
            return partition
    
    # بحث إضافي
    info("جاري البحث المتعمق...")
    result = run("su -c 'ls /dev/block/by-name/ 2>/dev/null | grep boot'")
    if result and result.stdout.strip():
        partitions = result.stdout.strip().split('\n')
        for p in partitions:
            full_path = f"/dev/block/by-name/{p.strip()}"
            warn(f"وجدت: {full_path}")
        
        # نأخذ الأول
        first = partitions[0].strip()
        chosen = f"/dev/block/by-name/{first}"
        info(f"سيتم استخدام: {chosen}")
        return chosen
    
    return None

def get_partition_size(partition):
    result = run(f"su -c 'blockdev --getsize64 {partition} 2>/dev/null'")
    if result and result.stdout.strip().isdigit():
        size = int(result.stdout.strip())
        return size
    # تقدير افتراضي لـ CPH2159
    return 67108864  # 64MB

def pull_boot(partition):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(OUTPUT_DIR, f"boot_CPH2159_{timestamp}.img")
    
    info(f"جاري سحب boot.img من {partition}")
    info(f"سيتم الحفظ في: {output_file}")
    
    size = get_partition_size(partition)
    size_mb = size / (1024 * 1024)
    info(f"حجم الـ partition: ~{size_mb:.1f} MB")
    
    print(f"\n{Y}{'═'*42}{RESET}")
    
    cmd = f"su -c 'dd if={partition} of={output_file} bs=4096 2>&1'"
    
    start_time = time.time()
    result = run(cmd)
    elapsed = time.time() - start_time
    
    print(f"{Y}{'═'*42}{RESET}\n")
    
    if result and os.path.exists(output_file):
        file_size = os.path.getsize(output_file)
        if file_size > 0:
            success(f"تم السحب بنجاح!")
            success(f"الملف: {output_file}")
            success(f"الحجم: {file_size / (1024*1024):.2f} MB")
            success(f"الوقت: {elapsed:.1f} ثانية")
            
            # تحقق من magic bytes
            verify_boot_image(output_file)
            return output_file
        else:
            error("الملف فارغ! فشل السحب.")
            return None
    else:
        error("فشل السحب!")
        if result:
            error(f"الخطأ: {result.stderr[:200]}")
        return None

def verify_boot_image(filepath):
    info("التحقق من صحة الملف...")
    with open(filepath, 'rb') as f:
        magic = f.read(8)
    
    # Android boot magic: ANDROID!
    if magic[:8] == b'ANDROID!':
        success("✅ ملف boot.img صحيح! (Magic: ANDROID!)")
    elif magic[:3] == b'\x1f\x8b\x08':
        warn("الملف مضغوط (gzip) — قد يكون boot kernel مباشرة")
    else:
        warn(f"Magic bytes غير معروفة: {magic.hex()}")
        warn("قد يكون الملف صحيحاً لكن بصيغة مختلفة")

def show_next_steps(output_file):
    print(f"\n{C}{'═'*42}")
    print(f"  الخطوات التالية:")
    print(f"{'═'*42}{RESET}")
    print(f"{W}1. نقل الملف للكمبيوتر:{RESET}")
    print(f"   {B}adb pull {output_file}{RESET}")
    print(f"{W}2. فك تشفير الـ boot.img:{RESET}")
    print(f"   {B}magiskboot unpack boot.img{RESET}")
    print(f"{W}3. التحقق من الملف:{RESET}")
    print(f"   {B}file {output_file}{RESET}")
    print(f"{C}{'═'*42}{RESET}\n")

def main():
    print(BANNER)
    
    print(f"{B}الجهاز المستهدف: OPPO Reno 5 CPH2159{RESET}")
    print(f"{B}النظام: ColorOS | المعالج: MediaTek Helio P95{RESET}\n")
    
    # فحص Root
    if not check_root():
        sys.exit(1)
    
    # فحص الأدوات
    check_dependencies()
    
    print()
    
    # إيجاد partition
    partition = find_boot_partition()
    if not partition:
        error("لم يتم العثور على boot partition!")
        error("تأكد من أن الجهاز لديه صلاحيات root كاملة")
        sys.exit(1)
    
    print()
    
    # تأكيد
    print(f"{Y}سيتم سحب boot.img من: {partition}{RESET}")
    confirm = input(f"{W}هل تريد المتابعة؟ (y/n): {RESET}").strip().lower()
    
    if confirm not in ['y', 'yes', 'نعم', 'ي']:
        warn("تم الإلغاء.")
        sys.exit(0)
    
    print()
    
    # السحب
    output = pull_boot(partition)
    
    if output:
        show_next_steps(output)
        success("🖤 Shadow Core — مهمة مكتملة")
    else:
        error("فشلت العملية. تحقق من صلاحيات Root")
        sys.exit(1)

if __name__ == "__main__":
    main()
