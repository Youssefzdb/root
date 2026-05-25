#!/usr/bin/env python3
# ============================================
#  Shadow Core Boot Puller v11
#  Device: OPPO Reno 5 CPH2159 | Helio P95
#
#  Method Chain (Auto Fallback):
#    1. Root/KernelSU   → dd partition
#    2. PHH-GSI via DSU → su → dd partition
#    3. MTK DA Bypass   → dump via preloader
#
#  CPH2159 supports Project Treble → DSU works
# ============================================

import subprocess, sys, os, re, shutil, time, json
import urllib.request, urllib.error
from datetime import datetime

R="\033[31m"; G="\033[32m"; Y="\033[33m"
C="\033[36m"; W="\033[97m"; B="\033[90m"; RESET="\033[0m"

BANNER = f"""
{R}╔══════════════════════════════════════════════╗
║  {W}Shadow Core Boot Puller  v11{R}              ║
║  {B}OPPO Reno 5 CPH2159 | Helio P95{R}          ║
║  {B}3-Method Chain | Auto Fallback{R}            ║
╚══════════════════════════════════════════════╝{RESET}
"""

OUTPUT_DIR = os.path.expanduser("~/boot_images")

def success(m): print(f"{G}[✓] {m}{RESET}")
def error(m):   print(f"{R}[✗] {m}{RESET}")
def warn(m):    print(f"{Y}[!] {m}{RESET}")
def info(m):    print(f"{C}[*] {m}{RESET}")
def step(n, m): print(f"\n{W}━━[{n}] {m}━━{RESET}")
def banner2(m): print(f"\n{R}──────────────────────────────────────────\n  {W}{m}{R}\n──────────────────────────────────────────{RESET}")

def run(cmd, timeout=15):
    try:
        r = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, text=True, timeout=timeout)
        return r.stdout.strip(), r.stderr.strip(), r.returncode
    except subprocess.TimeoutExpired:
        return "", "timeout", 1
    except Exception as e:
        return "", str(e), 1

def exists_bin(b): return shutil.which(b) is not None

# ─── Shared Utils ──────────────────────────────────
def find_boot_partition(use_su=False):
    pfx = "su -c " if use_su else ""
    for path in [
        "/dev/block/by-name/boot",
        "/dev/block/bootdevice/by-name/boot",
        "/dev/block/platform/bootdevice/by-name/boot",
        "/dev/block/platform/11270000.ufshci/by-name/boot",
    ]:
        out, _, rc = run(f"{pfx}readlink -f {path} 2>/dev/null")
        if rc == 0 and out.startswith("/dev/"):
            return out

    # scan by-name
    out, _, _ = run(f"{pfx}ls -la /dev/block/by-name/ 2>/dev/null")
    for line in out.split("\n"):
        if re.search(r'\bboot\b', line, re.I) and '->' in line:
            t = line.split('->')[-1].strip()
            return t if t.startswith('/dev/') else f"/dev/block/{t.split('/')[-1]}"

    # bash find (from XDA guide)
    cmd = r"""for P in boot boot_a boot_b; do B=$(find /dev/block \( -type b -o -type c -o -type l \) -iname "$P" -print -quit 2>/dev/null); [ -n "$B" ] && echo "$P=$(readlink -f $B)"; done"""
    out, _, _ = run(f"{pfx}sh -c '{cmd}'")
    for line in out.split("\n"):
        if '=' in line:
            part, path = line.split('=', 1)
            if path.strip().startswith('/dev/'):
                return path.strip()
    return None

def dd_extract(partition, outfile, use_su=False):
    os.makedirs(os.path.dirname(outfile), exist_ok=True)
    pfx = "su -c " if use_su else ""
    cmd = f"{pfx}dd if={partition} of={outfile} bs=4096"
    info(f"تشغيل: {cmd}")
    out, err, rc = run(cmd, timeout=180)
    combined = (out + " " + err).strip()
    info(f"نتيجة: {combined[:120]}")
    return os.path.exists(outfile) and os.path.getsize(outfile) > 512*1024

def verify(f):
    try:
        with open(f,'rb') as fp: magic = fp.read(8)
        if magic[:8] == b'ANDROID!':
            success(f"boot.img صحيح ✅  — {os.path.getsize(f)//1024//1024} MB")
            return True
        warn(f"Magic غير معروف: {magic.hex()}")
        return True
    except: return False


# ══════════════════════════════════════════════════
#  METHOD 1 — Root / KernelSU / su
# ══════════════════════════════════════════════════
def method1_root(outfile):
    banner2("الطريقة 1: KernelSU / Root → dd partition")

    # هل نحن root؟
    uid_out, _, _ = run("id")
    is_root = "uid=0" in uid_out

    # هل su متاح؟
    su_out, _, su_rc = run("su -c id", timeout=8)
    has_su = "uid=0" in su_out

    if not is_root and not has_su:
        warn("لا root ولا su → الانتقال للطريقة 2")
        return False

    use_su = not is_root
    success(f"{'su متاح' if use_su else 'root مباشر'}!")

    partition = find_boot_partition(use_su=use_su)
    if not partition:
        # جرب active slot
        slot, _, _ = run("getprop ro.boot.slot_suffix")
        if slot:
            pfx = "su -c " if use_su else ""
            out, _, _ = run(f"{pfx}readlink -f /dev/block/by-name/boot{slot} 2>/dev/null")
            if out.startswith('/dev/'): partition = out
    if not partition:
        warn("لم يُعثر على boot partition")
        return False

    success(f"Boot partition: {partition}")
    return dd_extract(partition, outfile, use_su=use_su)


# ══════════════════════════════════════════════════
#  METHOD 2 — PHH GSI via DSU → su → dd
# ══════════════════════════════════════════════════
def method2_gsi_dsu(outfile):
    banner2("الطريقة 2: PHH GSI عبر DSU → su → dd")

    info("فحص Project Treble...")
    treble, _, _ = run("getprop ro.treble.enabled")
    vndk, _, _   = run("getprop ro.vndk.version")
    ab_update, _, _ = run("getprop ro.build.ab_update")
    slot, _, _   = run("getprop ro.boot.slot_suffix")
    arch, _, _   = run("uname -m")

    info(f"Treble: {treble} | VNDK: {vndk} | A/B: {ab_update} | Slot: {slot} | Arch: {arch}")

    if treble != "true":
        warn("Treble غير مدعوم على هذا الجهاز → الانتقال للطريقة 3")
        return False

    # CPH2159 = arm64, A/B = true
    is_ab = ab_update == "true" or bool(slot)
    part_type = "b" if is_ab else "a"
    gsi_name = f"arm64_{part_type}vS"  # arm64 + partition_type + vanilla + Superuser

    # PHH GSI releases API
    info("جلب أحدث PHH GSI release...")
    try:
        url = "https://api.github.com/repos/phhusson/treble_experimentations/releases/latest"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
        assets = data.get("assets", [])
        tag    = data.get("tag_name", "?")
        info(f"أحدث release: {tag} ({len(assets)} ملف)")

        # ابحث عن arm64_bvS (vanilla + Superuser + A/B)
        gsi_asset = None
        for a in assets:
            n = a["name"].lower()
            if "arm64" in n and "vs" in n and a["name"].endswith(".img.xz"):
                gsi_asset = a
                break
        if not gsi_asset:
            for a in assets:
                n = a["name"].lower()
                if "arm64" in n and n.endswith(".img.xz"):
                    gsi_asset = a
                    break

        if not gsi_asset:
            warn("لم يُعثر على GSI مناسب في الـ release")
        else:
            info(f"GSI: {gsi_asset['name']} ({gsi_asset['size']//1024//1024} MB)")
    except Exception as e:
        warn(f"فشل جلب GSI releases: {e}")
        gsi_asset = None

    # ─── طباعة التعليمات الكاملة بدلاً من التنزيل التلقائي ───
    # (الـ GSI حجمه ~800MB — أثقل من أن ينزله السكريبت)
    print(f"""
{Y}{'═'*54}
  ► الطريقة 2 تحتاج خطوة يدوية واحدة (5 دقائق)
{'═'*54}{RESET}

{W}الخطوة 1 — تحقق من Treble:{RESET}
  {G}✓ جهازك يدعم Project Treble (مؤكد){RESET}

{W}الخطوة 2 — ثبّت DSU Sideloader:{RESET}
  {B}https://play.google.com/store/apps/details?id=vegabobo.dsusideloader{RESET}
  أو حمّله من هنا مباشرة (بدون Play Store):
  {B}https://github.com/VegaBobo/DSU-Sideloader/releases/latest{RESET}

{W}الخطوة 3 — حمّل PHH GSI (arm64 + Superuser):{RESET}""")

    if gsi_asset:
        print(f"  {B}{gsi_asset['browser_download_url']}{RESET}")
        print(f"  الحجم: {gsi_asset['size']//1024//1024} MB")
    else:
        print(f"  {B}https://github.com/phhusson/treble_experimentations/releases/latest{RESET}")
        print(f"  اختر: arm64_bvS-*.img.xz")

    print(f"""
{W}الخطوة 4 — ثبّت GSI عبر DSU Sideloader:{RESET}
  • افتح DSU Sideloader
  • اختر الـ .img.xz
  • اضغط Install → الجهاز يُعيد التشغيل في GSI مؤقتاً

{W}الخطوة 5 — بعد التشغيل في GSI:{RESET}
  {G}pkg update && git pull{RESET}
  {G}python boot_pull.py{RESET}
  (الآن الطريقة 1 ستنجح تلقائياً بـ su من PHH)

{Y}ملاحظة: GSI مؤقت — الجهاز يعود لـ ColorOS عند الإقلاع العادي{RESET}
""")

    # هل نحن الآن داخل GSI؟
    flavor, _, _ = run("getprop ro.system.build.flavor")
    treble_ver, _, _ = run("getprop ro.product.system.brand")
    info(f"system.brand: {treble_ver}")
    if "phh" in flavor.lower() or "treble" in flavor.lower():
        success("أنت الآن داخل PHH GSI!")
        # جرب su
        su_test, _, _ = run("su -c id", timeout=8)
        if "uid=0" in su_test:
            success("su يعمل! جاري الاستخراج...")
            partition = find_boot_partition(use_su=True)
            if partition:
                return dd_extract(partition, outfile, use_su=True)

    return False


# ══════════════════════════════════════════════════
#  METHOD 3 — MTK DA Bypass (Preloader exploit)
#  MT6779 / Helio P95
# ══════════════════════════════════════════════════
def method3_mtk_bypass(outfile):
    banner2("الطريقة 3: MTK DA Bypass (Helio P95 / MT6779)")

    info("هذه الطريقة تحتاج PC متصل بالجهاز عبر USB.")
    info("لكن يمكن تحضير الأداة من Termux الآن.")

    # فحص هل mtkclient متاح
    if not exists_bin("mtkclient"):
        info("تحضير mtkclient...")
        # جرب pip
        out, err, rc = run("pip install mtkclient 2>&1 | tail -3", timeout=60)
        info(f"pip: {out[-100:]}")

    # فحص /dev/ttyUSB أو /dev/ttyACM (لو كان في PC متصل)
    tty_devs = [d for d in ["/dev/ttyUSB0","/dev/ttyUSB1","/dev/ttyACM0"] if os.path.exists(d)]
    if tty_devs:
        success(f"وجد USB serial: {tty_devs}")
    else:
        info("لا يوجد USB serial device (متوقع في Termux بدون PC)")

    print(f"""
{R}{'═'*54}
  الطريقة 3: MTK DA Bypass — يحتاج PC
{'═'*54}{RESET}

{W}هذه الطريقة هي الأقوى لكنها تحتاج PC:{RESET}

{W}الخطوة 1 — على الـ PC:{RESET}
  {B}pip install mtkclient{RESET}

{W}الخطوة 2 — أدخل الجهاز في BROM mode:{RESET}
  • أطفئ الجهاز تماماً
  • اضغط Volume Down واحتفظ به
  • وصّل USB بالـ PC

{W}الخطوة 3 — من PC terminal:{RESET}
  {B}python -m mtk r boot boot.img{RESET}

{W}الخطوة 4 — انقل boot.img للجهاز:{RESET}
  {B}adb push boot.img /sdcard/Download/{RESET}

{G}MT6779 (Helio P95) = مدعوم في mtkclient ✓{RESET}
{B}https://github.com/bkerler/mtkclient{RESET}
""")

    return False


# ══════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════
def main():
    print(BANNER)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # معلومات سريعة
    info("جمع معلومات الجهاز...")
    for prop in ["ro.product.name", "ro.build.version.ota", "ro.boot.slot_suffix",
                 "ro.treble.enabled", "ro.boot.flash.locked"]:
        val, _, _ = run(f"getprop {prop}")
        info(f"  {prop}: {val}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = os.path.join(OUTPUT_DIR, f"boot_CPH2159_{ts}.img")

    methods = [
        ("Root / KernelSU + dd",   method1_root),
        ("PHH GSI via DSU + su",   method2_gsi_dsu),
        ("MTK DA Bypass (PC)",     method3_mtk_bypass),
    ]

    for i, (name, func) in enumerate(methods, 1):
        step(i, name)
        try:
            ok = func(outfile)
        except Exception as e:
            warn(f"استثناء: {e}")
            ok = False

        if ok and os.path.exists(outfile) and os.path.getsize(outfile) > 512*1024:
            print()
            success(f"✅ نجحت: {name}")
            success(f"الملف: {outfile}")
            success(f"الحجم: {os.path.getsize(outfile)/1024/1024:.2f} MB")
            verify(outfile)
            print(f"""
{C}{'═'*50}
  🖤 الخطوات التالية — Root بـ Magisk
{'═'*50}{RESET}
{W}1. ثبّت Magisk:{RESET}
   {B}https://github.com/topjohnwu/Magisk/releases{RESET}
{W}2. Magisk → Install → Patch a File → {B}{outfile}{RESET}
{W}3. فلّش الناتج:{RESET}
   {B}fastboot flash boot magisk_patched.img{RESET}
{C}{'═'*50}{RESET}
""")
            success("🖤 Shadow Core — مهمة مكتملة")
            return

        if i < len(methods):
            warn(f"الطريقة {i} فشلت → جاري تجربة الطريقة {i+1}...")
            time.sleep(0.3)

    print(f"\n{R}[✗] جميع الطرق الثلاث فشلت تلقائياً.{RESET}")
    print(f"{W}اتبع تعليمات الطريقة 2 (DSU) أو الطريقة 3 (PC+mtkclient){RESET}\n")

if __name__ == "__main__":
    main()
