#!/usr/bin/env python3
# ============================================
#  Shadow Core Boot Puller v13
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
║  {W}Shadow Core Boot Puller  v13{R}              ║
║  {B}OPPO Reno 5 CPH2159 | Helio P95{R}          ║
║  {B}3-Method Chain | Auto Fallback{R}            ║
╚══════════════════════════════════════════════╝{RESET}
"""

TERMUX_HOME = os.path.expanduser("~")
OUTPUT_DIR  = os.path.join(TERMUX_HOME, "boot_images")
TOOLS_DIR   = os.path.join(TERMUX_HOME, "boot_images", "tools")

# مسارات sdcard المحتملة
SDCARD_CANDIDATES = [
    "/sdcard/Download",
    "/storage/emulated/0/Download",
    os.path.join(TERMUX_HOME, "storage/downloads"),
    os.path.join(TERMUX_HOME, "storage/shared/Download"),
]

DSU_APK_URL  = "https://github.com/VegaBobo/DSU-Sideloader/releases/download/2.03/app-release.apk"
DSU_APK_NAME = "DSU-Sideloader-2.03.apk"

GSI_URL      = "https://github.com/phhusson/treble_experimentations/releases/download/v416/system-squeak-arm64-ab-floss.img.xz"
GSI_NAME     = "phh-gsi-arm64-ab-floss-v416.img.xz"
GSI_SIZE_MB  = 842

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

# ─── sdcard resolver ────────────────────────────
def get_sdcard_download():
    """يجد مسار Download المتاح للكتابة"""
    for path in SDCARD_CANDIDATES:
        if os.path.isdir(path):
            # اختبر الكتابة
            test = os.path.join(path, ".sc_test")
            try:
                with open(test, 'w') as f: f.write("1")
                os.remove(test)
                return path
            except:
                continue
    return None

def setup_termux_storage():
    """يطلب إذن storage من Termux"""
    sdcard = get_sdcard_download()
    if sdcard:
        return sdcard

    info("إذن storage غير ممنوح — طلب الإذن...")
    print(f"\n{Y}سيظهر لك dialog لمنح إذن الوصول للـ storage.{RESET}")
    print(f"{W}اضغط Allow عندما يظهر. انتظر 5 ثوان...{RESET}\n")

    run("termux-setup-storage", timeout=30)
    time.sleep(5)

    # انتظر حتى يظهر الـ storage
    for _ in range(6):
        sdcard = get_sdcard_download()
        if sdcard:
            success(f"Storage متاح: {sdcard}")
            return sdcard
        time.sleep(2)

    warn("storage غير متاح بعد الإذن — سنحفظ في Termux home فقط")
    return None

# ─── Download with progress ─────────────────────
def download_file(url, dest, label=""):
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
                        print(f"\r  {C}[{bar}] {pct:.0f}%  {done//1024//1024}/{total//1024//1024} MB{RESET}",
                              end="", flush=True)
        print()
        success(f"تم: {os.path.getsize(dest)//1024//1024} MB → {dest}")
        return True
    except Exception as e:
        print()
        error(f"فشل التحميل: {e}")
        return False

def copy_to_sdcard(src, sdcard_dir, name):
    """ينسخ ملف للـ sdcard مع معالجة الأخطاء"""
    if not sdcard_dir or not os.path.exists(src):
        return None
    dest = os.path.join(sdcard_dir, name)
    try:
        shutil.copy2(src, dest)
        success(f"نُسخ إلى: {dest}")
        return dest
    except PermissionError:
        # جرب cp بدلاً من shutil
        _, err, rc = run(f"cp '{src}' '{dest}'")
        if rc == 0:
            success(f"نُسخ (cp) إلى: {dest}")
            return dest
        warn(f"لا يمكن النسخ إلى sdcard: {err}")
        return None
    except Exception as e:
        warn(f"نسخ فشل: {e}")
        return None

# ─── Boot utils ─────────────────────────────────
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
    return os.path.exists(outfile) and os.path.getsize(outfile) > 512*1024

def verify(f):
    try:
        with open(f, 'rb') as fp: magic = fp.read(8)
        if magic[:8] == b'ANDROID!':
            success(f"boot.img صحيح ✅  Magic: ANDROID! — {os.path.getsize(f)//1024//1024} MB")
        else:
            warn(f"Magic: {magic.hex()} — تحقق يدوياً")
    except: pass


# ══════════════════════════════════════════════════
#  METHOD 1 — Root / KernelSU
# ══════════════════════════════════════════════════
def method1_root(outfile):
    banner2("الطريقة 1: Root / KernelSU → dd partition")

    uid_out, _, _ = run("id")
    is_root = "uid=0" in uid_out
    su_out, _, _  = run("su -c id", timeout=8)
    has_su  = "uid=0" in su_out

    if not is_root and not has_su:
        warn("لا root ولا su → الانتقال للطريقة 2")
        return False

    use_su = not is_root
    success(f"{'su متاح' if use_su else 'root مباشر'}!")

    slot, _, _ = run("getprop ro.boot.slot_suffix")
    partition  = find_boot_partition(use_su=use_su)

    if not partition and slot:
        pfx = "su -c " if use_su else ""
        out, _, _ = run(f"{pfx}readlink -f /dev/block/by-name/boot{slot} 2>/dev/null")
        if out.startswith('/dev/'): partition = out

    if not partition:
        warn("لم يُعثر على boot partition")
        return False

    success(f"Boot partition: {partition}")
    return dd_extract(partition, outfile, use_su=use_su)


# ══════════════════════════════════════════════════
#  METHOD 2 — DSU Sideloader + PHH GSI
# ══════════════════════════════════════════════════
def method2_dsu(outfile):
    banner2("الطريقة 2: DSU Sideloader + PHH GSI → su → dd")

    os.makedirs(TOOLS_DIR, exist_ok=True)

    # ─── هل نحن داخل GSI؟ ───
    flavor, _, _ = run("getprop ro.system.build.flavor")
    phh_pkg, _, _ = run("pm list packages 2>/dev/null | grep me.phh.superuser")
    if "phh" in flavor.lower() or "treble" in flavor.lower() or phh_pkg:
        success("✅ أنت داخل PHH GSI الآن!")
        su_test, _, _ = run("su -c id", timeout=8)
        if "uid=0" in su_test:
            success("su يعمل! جاري الاستخراج...")
            partition = find_boot_partition(use_su=True)
            if partition:
                success(f"Boot partition: {partition}")
                return dd_extract(partition, outfile, use_su=True)
        else:
            warn("افتح PHH Superuser app وامنح إذن su لـ Termux، ثم أعد تشغيل الأداة")
        return False

    # ─── فحص Treble ───
    treble, _, _ = run("getprop ro.treble.enabled")
    sdk, _, _    = run("getprop ro.build.version.sdk")

    if treble != "true":
        warn("جهازك لا يدعم Treble → الانتقال للطريقة 3")
        return False

    success(f"Treble=true | SDK={sdk}")

    # ─── حل مشكلة storage ───
    info("فحص صلاحيات storage...")
    sdcard = get_sdcard_download()
    if not sdcard:
        info("طلب إذن storage من Termux...")
        sdcard = setup_termux_storage()

    if sdcard:
        success(f"storage متاح: {sdcard}")
    else:
        warn(f"storage غير متاح — سيُحفظ APK في: {TOOLS_DIR}")
        info("يمكنك تشغيل: termux-setup-storage  ثم إعادة تشغيل الأداة")

    # ─── DSU APK ───
    apk_local   = os.path.join(TOOLS_DIR, DSU_APK_NAME)
    apk_sdcard  = os.path.join(sdcard, DSU_APK_NAME) if sdcard else None

    # ابحث هل موجود مسبقاً
    apk_exists = None
    for p in filter(None, [apk_sdcard, apk_local]):
        if os.path.exists(p) and os.path.getsize(p) > 1024*1024:
            apk_exists = p
            success(f"DSU APK موجود: {p}")
            break

    if not apk_exists:
        if download_file(DSU_APK_URL, apk_local, "DSU Sideloader v2.03 APK (~5 MB)"):
            apk_exists = apk_local
            # انسخ للـ sdcard
            if sdcard:
                copied = copy_to_sdcard(apk_local, sdcard, DSU_APK_NAME)
                if copied:
                    apk_exists = copied  # اجعل المرجع الرئيسي هو sdcard
        else:
            warn("فشل تحميل DSU APK")

    # ─── تثبيت APK تلقائياً ───
    if apk_exists:
        info("تثبيت DSU Sideloader APK...")
        out, err, rc = run(f"pm install -r \"{apk_exists}\"", timeout=45)
        combined = (out + " " + err).lower()
        if "success" in combined:
            success("DSU Sideloader مُثبَّت تلقائياً! ✅")
        elif "already" in combined or "downgrade" in combined:
            success("DSU Sideloader مُثبَّت مسبقاً ✅")
        else:
            warn(f"pm install: {(out or err)[:80]}")
            info(f"ثبّته يدوياً: افتح مدير الملفات → {apk_exists}")

    # ─── PHH GSI ───
    gsi_local   = os.path.join(TOOLS_DIR, GSI_NAME)
    gsi_sdcard  = os.path.join(sdcard, GSI_NAME) if sdcard else None

    gsi_exists = None
    for p in filter(None, [gsi_sdcard, gsi_local]):
        if os.path.exists(p) and os.path.getsize(p) > 100*1024*1024:
            gsi_exists = p
            success(f"PHH GSI موجود: {p}")
            break

    if not gsi_exists:
        # حساب المساحة المتاحة
        stat = shutil.disk_usage(TERMUX_HOME)
        free_gb = stat.free / 1024**3
        info(f"مساحة متاحة في Termux home: {free_gb:.1f} GB")
        if sdcard:
            try:
                stat_sd = shutil.disk_usage(sdcard)
                free_sd = stat_sd.free / 1024**3
                info(f"مساحة متاحة في sdcard: {free_sd:.1f} GB")
            except: free_sd = 0
        else:
            free_sd = 0

        print(f"\n{Y}PHH GSI حجمه ~{GSI_SIZE_MB} MB.{RESET}")
        print(f"{W}هل تريد تحميله الآن؟ (y/n): {RESET}", end="", flush=True)
        try:
            choice = input().strip().lower()
        except (KeyboardInterrupt, EOFError):
            choice = 'n'

        if choice == 'y':
            # اختر أفضل مكان للحفظ
            if sdcard and free_sd > 1.0:
                save_to = os.path.join(sdcard, GSI_NAME)
            elif free_gb > 1.0:
                save_to = gsi_local
            else:
                error(f"لا توجد مساحة كافية (متاح: {free_gb:.1f} GB في Termux, {free_sd:.1f} GB في sdcard)")
                save_to = None

            if save_to and download_file(GSI_URL, save_to, f"PHH GSI v416 ({GSI_SIZE_MB} MB)"):
                gsi_exists = save_to
                # انسخ للـ sdcard إذا لزم
                if save_to == gsi_local and sdcard:
                    copy_to_sdcard(gsi_local, sdcard, GSI_NAME)

    # ─── ملخص التعليمات ───
    print(f"""
{C}{'═'*54}
  خطوات DSU + PHH GSI
{'═'*54}{RESET}

{W}الملفات:{RESET}""")

    dsu_display = apk_exists or f"{Y}لم يُحمَّل ← شغّل الأداة مرة أخرى{RESET}"
    gsi_display = gsi_exists or f"{Y}لم يُحمَّل ← أجب بـ y عند السؤال{RESET}"

    print(f"  DSU APK : {G if apk_exists else Y}{apk_exists or 'غير موجود'}{RESET}")
    print(f"  PHH GSI : {G if gsi_exists else Y}{gsi_exists or 'غير موجود'}{RESET}")

    print(f"""
{W}الخطوات:{RESET}

{W}1.{RESET} ثبّت DSU Sideloader:""")
    if apk_exists:
        print(f"   {G}APK مُثبَّت تلقائياً ✅ — أو افتح الملف يدوياً:{RESET}")
        print(f"   {B}{apk_exists}{RESET}")
    else:
        print(f"   {B}{DSU_APK_URL}{RESET}")

    print(f"""
{W}2.{RESET} افتح DSU Sideloader → اختر الـ GSI:""")
    if gsi_exists:
        print(f"   {B}{gsi_exists}{RESET}")
    else:
        print(f"   {B}{GSI_URL}{RESET}")

    print(f"""   اضغط Install — الجهاز يُقلع في GSI مؤقتاً

{W}3.{RESET} بعد الإقلاع في GSI، شغّل:
   {G}cd ~/root-cli && git pull && python boot_pull.py{RESET}
   {B}← الطريقة 1 ستنجح تلقائياً بـ su{RESET}

{Y}GSI مؤقت 100% — ColorOS يعود عند الإقلاع العادي{RESET}
""")

    return False


# ══════════════════════════════════════════════════
#  METHOD 3 — MTK DA Bypass
# ══════════════════════════════════════════════════
def method3_mtk(outfile):
    banner2("الطريقة 3: MTK DA Bypass — Helio P95 (MT6779)")

    if exists_bin("mtk") or exists_bin("mtkclient"):
        success("mtkclient موجود!")
        tty_devs = [d for d in ["/dev/ttyUSB0","/dev/ttyUSB1","/dev/ttyACM0"] if os.path.exists(d)]
        if tty_devs:
            success(f"USB serial: {tty_devs[0]}")
            out, err, rc = run(f"mtk r boot {outfile}", timeout=120)
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

{G}✓ MT6779 / Helio P95 = مدعوم{RESET}
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
    for prop in ["ro.product.name", "ro.build.version.ota", "ro.boot.slot_suffix",
                 "ro.treble.enabled", "ro.boot.flash.locked",
                 "ro.build.ab_update", "ro.build.version.sdk"]:
        val, _, _ = run(f"getprop {prop}")
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
{W}2. Magisk → Install → Patch a File → اختر:{RESET}
   {B}{outfile}{RESET}
{W}3. فلّش الناتج:{RESET}
   {B}fastboot flash boot magisk_patched.img{RESET}
{C}{'═'*52}{RESET}
""")
            success("🖤 Shadow Core — مهمة مكتملة")
            return

        if i < len(methods):
            warn(f"الطريقة {i} فشلت → جاري تجربة الطريقة {i+1}...")
            time.sleep(0.3)

    print(f"\n{R}[✗] لم تنجح الطرق الثلاث تلقائياً.{RESET}")
    print(f"{W}اتبع خطوات الطريقة 2 (DSU) أعلاه — APK جاهز ✓{RESET}\n")


if __name__ == "__main__":
    main()
