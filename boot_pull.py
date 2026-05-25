#!/usr/bin/env python3
# ============================================
#  Shadow Core Boot Puller v9
#  Device: OPPO Reno 5 CPH2159
#  Method: dd from partition (needs root)
#       OR adb backup trick
#       OR fastboot (if bootloader unlocked)
# ============================================

import subprocess, sys, os, re
from datetime import datetime

R="\033[31m"; G="\033[32m"; Y="\033[33m"
C="\033[36m"; W="\033[97m"; B="\033[90m"; RESET="\033[0m"

BANNER = f"""
{R}╔══════════════════════════════════════════════╗
║  {W}Shadow Core Boot Puller  v9{R}               ║
║  {B}OPPO Reno 5 CPH2159{R}                       ║
║  {B}Method: dd partition → boot.img{R}           ║
╚══════════════════════════════════════════════╝{RESET}
"""

OUTPUT_DIR = os.path.expanduser("~/boot_images")

def success(m): print(f"{G}[✓] {m}{RESET}")
def error(m):   print(f"{R}[✗] {m}{RESET}")
def warn(m):    print(f"{Y}[!] {m}{RESET}")
def info(m):    print(f"{C}[*] {m}{RESET}")
def step(n, m): print(f"\n{W}━━[{n}] {m}━━{RESET}")

def run(cmd, timeout=10):
    try:
        r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, text=True, timeout=timeout)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", 1

# ─── Check root ─────────────────────────────────────
def check_root():
    out, _, rc = run("id")
    return "uid=0" in out

# ─── Find boot partition ─────────────────────────────
def find_boot_partition():
    # طريقة 1: by-name
    candidates = []
    for pattern in ["/dev/block/by-name/boot", "/dev/block/bootdevice/by-name/boot",
                    "/dev/block/platform/bootdevice/by-name/boot"]:
        if os.path.exists(pattern):
            candidates.append(pattern)

    # طريقة 2: scan /dev/block
    out, _, _ = run("ls /dev/block/")
    for name in out.split():
        if re.match(r'^(mmcblk\d+p\d+|sda\d+|sdc\d+)$', name):
            full = f"/dev/block/{name}"
            candidates.append(full)

    # طريقة 3: ls -la by-name
    out, _, _ = run("ls -la /dev/block/by-name/ 2>/dev/null || ls -la /dev/block/bootdevice/by-name/ 2>/dev/null")
    for line in out.split('\n'):
        if 'boot' in line.lower() and '->' in line:
            target = line.split('->')[-1].strip()
            if target:
                candidates.append(target)

    return candidates

def detect_boot_partition():
    """اكتشاف partition الـ boot"""
    # by-name (الأفضل)
    for path in [
        "/dev/block/by-name/boot",
        "/dev/block/bootdevice/by-name/boot",
        "/dev/block/platform/bootdevice/by-name/boot",
        "/dev/block/platform/11270000.ufshci/by-name/boot",  # MediaTek
        "/dev/block/platform/11230000.ufs/by-name/boot",
    ]:
        if os.path.exists(path):
            return path

    # resolve symlink
    out, _, rc = run("readlink -f /dev/block/by-name/boot 2>/dev/null")
    if rc == 0 and out and "/dev/block/" in out:
        return out

    out, _, rc = run("ls -la /dev/block/by-name/boot 2>/dev/null")
    if rc == 0 and '->' in out:
        target = out.split('->')[-1].strip()
        if target.startswith('/dev/'):
            return target
        return f"/dev/block/{target.split('/')[-1]}"

    # fallback: scan all partitions
    out, _, _ = run("cat /proc/partitions 2>/dev/null")
    for line in out.split('\n'):
        parts = line.split()
        if len(parts) >= 4:
            name = parts[3]
            if re.match(r'^mmcblk\dp\d+$', name) or re.match(r'^sd[a-z]\d+$', name):
                # جرب قراءة magic
                dev = f"/dev/block/{name}"
                magic, _, _ = run(f"dd if={dev} bs=8 count=1 2>/dev/null | xxd -p 2>/dev/null")
                if magic.startswith('414e44524f4944'):  # ANDROID!
                    return dev

    return None

# ─── Extract boot.img ────────────────────────────────
def extract_boot(partition, output_file):
    info(f"استخراج من: {partition}")
    info(f"إلى: {output_file}")

    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # dd بدون su (نفترض أننا نعمل كـ root في Termux)
    cmd = f"dd if={partition} of={output_file} bs=4096 2>&1"
    info(f"تشغيل: {cmd}")

    proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    output = proc.communicate(timeout=120)[0]
    rc = proc.returncode

    info(f"dd output: {output.strip()}")

    if rc != 0:
        error(f"فشل dd: {output}")
        return False

    if os.path.exists(output_file) and os.path.getsize(output_file) > 0:
        return True
    return False

def verify(f):
    try:
        with open(f,'rb') as fp: magic=fp.read(8)
        if magic[:8]==b'ANDROID!':
            success("boot.img صحيح ✅ (ANDROID! magic)")
        elif magic[:4]==b'\x1f\x8b\x08\x00':
            warn("gzip compressed — قد يحتاج unpack")
        else:
            warn(f"Magic: {magic.hex()} — تحقق يدوياً")
    except Exception as e:
        warn(f"تحقق يدوي مطلوب: {e}")

def next_steps(f):
    print(f"\n{C}{'═'*50}")
    print(f"  الخطوات التالية — Root بـ Magisk")
    print(f"{'═'*50}{RESET}")
    print(f"{W}1. انقل boot.img إلى هاتفك أو PC:{RESET}")
    print(f"   {B}adb pull {f}{RESET}")
    print(f"{W}2. ثبّت Magisk: {B}github.com/topjohnwu/Magisk/releases{RESET}")
    print(f"{W}3. Magisk → Install → Patch a File → اختر boot.img{RESET}")
    print(f"{W}4. فلّش الملف الناتج:{RESET}")
    print(f"   {B}fastboot flash boot magisk_patched.img{RESET}")
    print(f"{C}{'═'*50}{RESET}\n")

# ─── Main ────────────────────────────────────────────
def main():
    print(BANNER)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    step(1, "التحقق من الصلاحيات")
    if not check_root():
        error("هذه الأداة تحتاج صلاحيات root!")
        print(f"""
{Y}الخيارات المتاحة لك:{RESET}

{W}الخيار 1 — تثبيت KernelSU (بدون فتح bootloader):{RESET}
  • نزّل KernelSU Manager: {B}github.com/tiann/KernelSU/releases{RESET}
  • ابحث عن GKI kernel لـ CPH2159

{W}الخيار 2 — استخدام Magisk Patched Boot عبر PC:{RESET}
  • سجّل الـ IMEI من: الإعدادات → عن الهاتف
  • حمّل Stock ROM من: {B}firmwarefile.com/oppo-reno-5-4g-cph2159{RESET}
  • افتح على PC واستخرج boot.img
  • فلّش بـ fastboot

{W}الخيار 3 — طلب OTA مباشرة من داخل الهاتف:{RESET}
  • الإعدادات → عن الهاتف → تحديث → ابحث عن تحديث
  • إذا وجد → حمّله وقبل التثبيت استخرج boot.img

{R}السبب: OPPO لا يسمح بـ OTA download عبر الـ API العام (مخصص لـ Realme فقط){RESET}
""")
        sys.exit(1)

    success("root متاح!")

    step(2, "البحث عن boot partition")
    partition = detect_boot_partition()

    if not partition:
        warn("لم يتم اكتشاف boot partition تلقائياً")
        print(f"\n{W}قائمة الـ partitions المتاحة:{RESET}")
        out, _, _ = run("ls -la /dev/block/by-name/ 2>/dev/null || ls /dev/block/ 2>/dev/null | head -30")
        print(f"{B}{out}{RESET}")
        print(f"\n{W}أدخل مسار الـ partition يدوياً: {RESET}", end="")
        try:
            partition = input().strip()
        except KeyboardInterrupt:
            print(); sys.exit(0)
        if not partition:
            sys.exit(1)

    success(f"Boot partition: {partition}")

    step(3, "استخراج boot.img")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = os.path.join(OUTPUT_DIR, f"boot_CPH2159_{ts}.img")

    if not extract_boot(partition, output_file):
        error("فشل الاستخراج")
        sys.exit(1)

    size = os.path.getsize(output_file) / (1024*1024)
    success(f"تم! الملف: {output_file}")
    success(f"الحجم: {size:.2f} MB")
    verify(output_file)
    next_steps(output_file)
    success("🖤 Shadow Core — مهمة مكتملة")

if __name__ == "__main__":
    main()
