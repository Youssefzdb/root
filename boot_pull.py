#!/usr/bin/env python3
# ============================================
#  Shadow Core Boot Puller v12
#  Device: OPPO Reno 5 CPH2159 | Helio P95
#
#  Method Chain (Auto Fallback):
#    1. Root / KernelSU  → dd partition
#    2. DSU Sideloader   → PHH GSI → su → dd
#    3. MTK DA Bypass    → PC guide
# ============================================

import subprocess, sys, os, re, shutil, time, json
import urllib.request, urllib.error
from datetime import datetime

R="\033[31m"; G="\033[32m"; Y="\033[33m"
C="\033[36m"; W="\033[97m"; B="\033[90m"; RESET="\033[0m"

BANNER = f"""
{R}╔══════════════════════════════════════════════╗
║  {W}Shadow Core Boot Puller  v12{R}              ║
║  {B}OPPO Reno 5 CPH2159 | Helio P95{R}          ║
║  {B}3-Method Chain | Auto Fallback{R}            ║
╚══════════════════════════════════════════════╝{RESET}
"""

OUTPUT_DIR  = os.path.expanduser("~/boot_images")
TOOLS_DIR   = os.path.expanduser("~/boot_images/tools")
STORAGE_DIR = os.path.expanduser("/sdcard/Download")

DSU_APK_URL = "https://github.com/VegaBobo/DSU-Sideloader/releases/download/2.03/app-release.apk"
DSU_MOD_URL = "https://github.com/VegaBobo/DSU-Sideloader/releases/download/2.03/module_DSU_Sideloader.zip"
DSU_APK_NAME = "DSU-Sideloader-2.03.apk"
DSU_MOD_NAME = "DSU-Sideloader-module.zip"

# أفضل GSI لـ CPH2159: arm64 + A/B + vanilla (أصغر) + بدون secure (له su)
# system-squeak-arm64-ab-vanilla = 578MB ← لا يحتوي su!
# نحتاج floss (= free software = له su بداخله)
GSI_URL  = "https://github.com/phhusson/treble_experimentations/releases/download/v416/system-squeak-arm64-ab-floss.img.xz"
GSI_NAME = "phh-gsi-arm64-ab-floss-v416.img.xz"
GSI_SIZE_MB = 842

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

def download_file(url, dest, label=""):
    """تحميل ملف مع progress bar"""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    info(f"تحميل {label or os.path.basename(dest)}...")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            done  = 0
            with open(dest, 'wb') as f:
                while True:
                    buf = resp.read(512 * 1024)
                    if not buf: break
                    f.write(buf)
                    done += len(buf)
                    if total:
                        pct = done / total * 100
                        bar = "█" * int(pct/5) + "░" * (20 - int(pct/5))
                        print(f"\r  {C}[{bar}] {pct:.0f}% — {done//1024//1024}/{total//1024//1024} MB{RESET}",
                              end="", flush=True)
        print()
        size = os.path.getsize(dest)
        success(f"تم: {size//1024//1024} MB → {dest}")
        return True
    except Exception as e:
        print()
        error(f"فشل التحميل: {e}")
        return False

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

    # bash find (XDA method)
    cmd = (r'for P in boot boot_a boot_b; do '
           r'B=$(find /dev/block \( -type b -o -type c -o -type l \) '
           r'-iname "$P" -print -quit 2>/dev/null); '
           r'[ -n "$B" ] && echo "$P=$(readlink -f $B)"; done')
    out, _, _ = run(f"{pfx}sh -c '{cmd}'")
    for line in out.split("\n"):
        if '=' in line:
            _, path = line.split('=', 1)
            if path.strip().startswith('/dev/'):
                return path.strip()

    # ls -la by-name fallback
    out, _, _ = run(f"{pfx}ls -la /dev/block/by-name/ 2>/dev/null")
    for line in out.split("\n"):
        if re.search(r'\bboot\b', line, re.I) and '->' in line:
            t = line.split('->')[-1].strip()
            return t if t.startswith('/dev/') else f"/dev/block/{t.split('/')[-1]}"
    return None

def dd_extract(partition, outfile, use_su=False):
    os.makedirs(os.path.dirname(outfile), exist_ok=True)
    pfx = "su -c " if use_su else ""
    cmd = f"{pfx}dd if={partition} of={outfile} bs=4096"
    info(f"تشغيل: {cmd}")
    _, _, _ = run(cmd, timeout=180)
    if os.path.exists(outfile) and os.path.getsize(outfile) > 512*1024:
        return True
    # جرب حفظ في /sdcard أيضاً
    sdcard_out = os.path.join(STORAGE_DIR, os.path.basename(outfile))
    cmd2 = f"{pfx}dd if={partition} of={sdcard_out} bs=4096"
    _, _, _ = run(cmd2, timeout=180)
    if os.path.exists(sdcard_out) and os.path.getsize(sdcard_out) > 512*1024:
        shutil.copy2(sdcard_out, outfile)
        return True
    return False

def verify(f):
    try:
        with open(f, 'rb') as fp:
            magic = fp.read(8)
        if magic[:8] == b'ANDROID!':
            success(f"boot.img صحيح ✅  Magic: ANDROID! — {os.path.getsize(f)//1024//1024} MB")
            return True
        warn(f"Magic: {magic.hex()} — تحقق يدوياً")
        return True
    except: return False


# ══════════════════════════════════════════════════
#  METHOD 1 — Root / KernelSU / su
# ══════════════════════════════════════════════════
def method1_root(outfile):
    banner2("الطريقة 1: Root / KernelSU → dd partition")

    uid_out, _, _ = run("id")
    is_root = "uid=0" in uid_out
    su_out, _, _ = run("su -c id", timeout=8)
    has_su = "uid=0" in su_out

    if not is_root and not has_su:
        warn("لا root ولا su → الانتقال للطريقة 2")
        return False

    use_su = not is_root
    success(f"{'su متاح' if use_su else 'root مباشر'}!")

    # active slot
    slot, _, _ = run("getprop ro.boot.slot_suffix")
    info(f"Active slot: {slot or 'A-only'}")

    partition = find_boot_partition(use_su=use_su)
    if not partition and slot:
        pfx = "su -c " if use_su else ""
        out, _, _ = run(f"{pfx}readlink -f /dev/block/by-name/boot{slot} 2>/dev/null")
        if out.startswith('/dev/'): partition = out

    if not partition:
        warn("لم يُعثر على boot partition")
        return False

    success(f"Boot partition: {partition}")
    if dd_extract(partition, outfile, use_su=use_su):
        return True
    warn("dd فشل")
    return False


# ══════════════════════════════════════════════════
#  METHOD 2 — DSU Sideloader + PHH GSI → su → dd
# ══════════════════════════════════════════════════
def method2_dsu(outfile):
    banner2("الطريقة 2: DSU Sideloader + PHH GSI → su → dd")

    os.makedirs(TOOLS_DIR, exist_ok=True)

    # ─── فحص Treble ───
    info("فحص Project Treble...")
    treble, _, _  = run("getprop ro.treble.enabled")
    ab_update, _, _ = run("getprop ro.build.ab_update")
    slot, _, _    = run("getprop ro.boot.slot_suffix")
    sdk, _, _     = run("getprop ro.build.version.sdk")
    brand, _, _   = run("getprop ro.product.system.brand")

    info(f"Treble={treble} | A/B={ab_update} | slot={slot} | SDK={sdk} | brand={brand}")

    # ─── هل نحن الآن داخل PHH GSI؟ ───
    flavor, _, _ = run("getprop ro.system.build.flavor")
    phh_app, _, _ = run("pm list packages 2>/dev/null | grep me.phh.superuser")

    if "phh" in flavor.lower() or "treble" in flavor.lower() or phh_app:
        success("✅ أنت داخل PHH GSI!")
        su_test, _, _ = run("su -c id", timeout=8)
        if "uid=0" in su_test:
            success("su يعمل! جاري الاستخراج...")
            partition = find_boot_partition(use_su=True)
            if partition:
                success(f"Boot partition: {partition}")
                return dd_extract(partition, outfile, use_su=True)
            else:
                error("لم يُعثر على boot partition حتى داخل GSI")
                return False
        else:
            warn("su غير متاح داخل GSI — تحقق من PHH Superuser app")
            return False

    # ─── لم نكن في GSI بعد → نُحضّر الملفات ───
    if treble != "true":
        warn("جهازك لا يدعم Project Treble — DSU لن يعمل")
        return False

    success(f"Treble مدعوم! SDK={sdk}")

    # ─── تحميل DSU Sideloader APK ───
    apk_path = os.path.join(TOOLS_DIR, DSU_APK_NAME)
    apk_sdcard = os.path.join(STORAGE_DIR, DSU_APK_NAME)

    if not os.path.exists(apk_path) and not os.path.exists(apk_sdcard):
        info("تحميل DSU Sideloader APK...")
        if not download_file(DSU_APK_URL, apk_path, "DSU Sideloader v2.03 APK"):
            warn("فشل تحميل DSU APK")
    else:
        success(f"DSU APK موجود مسبقاً")
        apk_path = apk_path if os.path.exists(apk_path) else apk_sdcard

    # انسخ APK للـ sdcard
    sdcard_apk = os.path.join(STORAGE_DIR, DSU_APK_NAME)
    if os.path.exists(apk_path) and not os.path.exists(sdcard_apk):
        try:
            shutil.copy2(apk_path, sdcard_apk)
            success(f"APK في: {sdcard_apk}")
        except Exception as e:
            warn(f"نسخ APK: {e}")

    # ─── تحميل PHH GSI ───
    gsi_path    = os.path.join(TOOLS_DIR, GSI_NAME)
    gsi_sdcard  = os.path.join(STORAGE_DIR, GSI_NAME)

    if os.path.exists(gsi_path):
        success(f"PHH GSI موجود: {gsi_path}")
    elif os.path.exists(gsi_sdcard):
        success(f"PHH GSI موجود: {gsi_sdcard}")
        gsi_path = gsi_sdcard
    else:
        print(f"\n{Y}PHH GSI حجمه {GSI_SIZE_MB} MB.{RESET}")
        print(f"{W}هل تريد تحميله الآن؟ (y/n) [n=تخطي وأرى التعليمات]: {RESET}", end="", flush=True)
        try:
            choice = input().strip().lower()
        except (KeyboardInterrupt, EOFError):
            choice = 'n'

        if choice == 'y':
            # حاول الحفظ في sdcard أولاً (مساحة أكبر)
            save_to = gsi_sdcard if os.path.exists(STORAGE_DIR) else gsi_path
            if not download_file(GSI_URL, save_to, f"PHH GSI v416 arm64-ab-floss ({GSI_SIZE_MB} MB)"):
                warn("فشل تحميل GSI")
            else:
                gsi_path = save_to

    # ─── تعليمات التثبيت ───
    print(f"""
{C}{'═'*54}
  خطوات تثبيت DSU + PHH GSI
{'═'*54}{RESET}

{W}الملفات المُحمّلة:{RESET}""")

    if os.path.exists(sdcard_apk):
        print(f"  {G}✓ DSU Sideloader APK:{RESET} {B}{sdcard_apk}{RESET}")
    else:
        print(f"  {Y}⚠ DSU APK لم يُحمَّل — نزّله من:{RESET}")
        print(f"    {B}{DSU_APK_URL}{RESET}")

    if os.path.exists(gsi_path):
        print(f"  {G}✓ PHH GSI:{RESET} {B}{gsi_path}{RESET}")
    else:
        print(f"  {Y}⚠ PHH GSI لم يُحمَّل — نزّله من:{RESET}")
        print(f"    {B}{GSI_URL}{RESET}")

    # تثبيت APK تلقائياً
    if os.path.exists(sdcard_apk):
        info("محاولة تثبيت DSU APK تلقائياً...")
        out, err, rc = run(f"pm install -r {sdcard_apk}", timeout=30)
        if rc == 0 or "success" in out.lower():
            success("DSU Sideloader مُثبَّت! ✅")
        else:
            info(f"pm install: {out or err}")

    print(f"""
{W}الخطوات اليدوية (مرة واحدة فقط):{RESET}

{W}1. ثبّت DSU Sideloader APK:{RESET}
   {B}• افتح مدير الملفات → {sdcard_apk if os.path.exists(sdcard_apk) else 'Download/'+DSU_APK_NAME}{RESET}
   {B}• اضغط على الملف وثبّته (قد تحتاج تفعيل "مصادر غير معروفة"){RESET}

{W}2. افتح DSU Sideloader وحدد الـ GSI:{RESET}
   {B}• اختر الملف: {gsi_path if os.path.exists(gsi_path) else 'PHH GSI .img.xz'}{RESET}
   {B}• اضغط Install (سيأخذ وقتاً){RESET}
   {B}• الجهاز سيُعيد التشغيل في GSI مؤقتاً{RESET}

{W}3. بعد الإقلاع في GSI — شغّل هذه الأداة مجدداً:{RESET}
   {B}cd ~/root-cli && git pull && python boot_pull.py{RESET}
   {G}← الطريقة 1 ستنجح تلقائياً بـ su من PHH{RESET}

{Y}ملاحظة: GSI مؤقت 100% — الجهاز يعود لـ ColorOS عند الإقلاع العادي{RESET}
""")

    return False  # لن ننجح الآن، لكن الملفات جاهزة


# ══════════════════════════════════════════════════
#  METHOD 3 — MTK DA Bypass (PC required)
# ══════════════════════════════════════════════════
def method3_mtk(outfile):
    banner2("الطريقة 3: MTK DA Bypass — Helio P95 (MT6779)")

    # فحص هل mtkclient متاح محلياً (لو شغّلها من PC)
    if exists_bin("mtk") or exists_bin("mtkclient"):
        success("mtkclient موجود!")
        # فحص USB device
        tty_devs = [d for d in ["/dev/ttyUSB0","/dev/ttyUSB1","/dev/ttyACM0"] if os.path.exists(d)]
        if tty_devs:
            success(f"USB serial: {tty_devs[0]}")
            info("جاري محاولة dump boot...")
            out, err, rc = run(f"mtk r boot {outfile}", timeout=120)
            info(f"mtkclient: {(out+err)[:150]}")
            if os.path.exists(outfile) and os.path.getsize(outfile) > 512*1024:
                return True

    print(f"""
{R}{'═'*54}
  الطريقة 3: MTK DA Bypass — يحتاج PC
{'═'*54}{RESET}

{W}على الـ PC:{RESET}
  {B}pip install mtkclient{RESET}

{W}أدخل الجهاز في BROM mode:{RESET}
  {Y}• أطفئ الجهاز تماماً{RESET}
  {Y}• اضغط Volume Down واحتفظ به{RESET}
  {Y}• وصّل USB بالـ PC{RESET}

{W}من PC terminal:{RESET}
  {B}python -m mtk r boot boot.img{RESET}

{W}انقل boot.img للجهاز:{RESET}
  {B}adb push boot.img /sdcard/Download/{RESET}

{G}✓ MT6779 / Helio P95 = مدعوم في mtkclient{RESET}
{B}https://github.com/bkerler/mtkclient{RESET}
""")
    return False


# ══════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════
def main():
    print(BANNER)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(TOOLS_DIR, exist_ok=True)

    step(0, "معلومات الجهاز")
    props = {}
    for prop in ["ro.product.name", "ro.build.version.ota", "ro.boot.slot_suffix",
                 "ro.treble.enabled", "ro.boot.flash.locked", "ro.build.ab_update",
                 "ro.build.version.sdk"]:
        val, _, _ = run(f"getprop {prop}")
        props[prop] = val
        info(f"  {prop.split('.')[-1]}: {val}")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    outfile = os.path.join(OUTPUT_DIR, f"boot_CPH2159_{ts}.img")

    methods = [
        ("Root / KernelSU + dd",          method1_root),
        ("DSU Sideloader + PHH GSI + su",  method2_dsu),
        ("MTK DA Bypass (PC)",             method3_mtk),
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
{C}{'═'*52}
  🖤 الخطوات التالية — Root بـ Magisk
{'═'*52}{RESET}
{W}1. ثبّت Magisk:{RESET}
   {B}https://github.com/topjohnwu/Magisk/releases{RESET}
{W}2. Magisk → Install → Patch a File → اختر boot.img{RESET}
{W}3. فلّش:{RESET}
   {B}fastboot flash boot magisk_patched.img{RESET}
{C}{'═'*52}{RESET}
""")
            success("🖤 Shadow Core — مهمة مكتملة")
            return

        if i < len(methods):
            warn(f"الطريقة {i} فشلت → جاري تجربة الطريقة {i+1}...")
            time.sleep(0.3)

    print(f"\n{R}[✗] لم تنجح الطرق الثلاث تلقائياً.{RESET}")
    print(f"{W}اتبع تعليمات الطريقة 2 (DSU) الموضحة أعلاه — الخطوات بسيطة{RESET}\n")


if __name__ == "__main__":
    main()
