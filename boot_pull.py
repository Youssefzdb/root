#!/usr/bin/env python3
# ============================================
#  Shadow Core Boot Puller v5
#  Device: OPPO Reno 5 CPH2159 | ColorOS
#  Platform: Termux — No Root, No PC
#  Method: OPPO OTA API (built-in) → boot.img
# ============================================

import subprocess, sys, os, json, zipfile, shutil
import re, struct, hashlib, base64, time
import urllib.request, urllib.error
from datetime import datetime

# ─── Colors ───────────────────────────────
R="\033[31m"; G="\033[32m"; Y="\033[33m"
C="\033[36m"; W="\033[97m"; B="\033[90m"; RESET="\033[0m"

BANNER = f"""
{R}╔══════════════════════════════════════════════╗
║  {W}Shadow Core Boot Puller  v5{R}               ║
║  {B}OPPO Reno 5 CPH2159 | No Root | No PC{R}    ║
║  {B}Method: OPPO OTA API → boot.img{R}          ║
╚══════════════════════════════════════════════╝{RESET}
"""

OUTPUT_DIR = os.path.expanduser("~/boot_images")
TEMP_DIR   = os.path.expanduser("~/boot_images/.tmp")

def success(m): print(f"{G}[✓] {m}{RESET}")
def error(m):   print(f"{R}[✗] {m}{RESET}")
def warn(m):    print(f"{Y}[!] {m}{RESET}")
def info(m):    print(f"{C}[*] {m}{RESET}")
def step(n, m): print(f"\n{W}━━[{n}] {m}━━{RESET}")

# ─── Crypto helpers (ECB for RUI v1, CTR for v2+) ────
def install_pycrypto():
    try:
        from Crypto.Cipher import AES
        return True
    except ImportError:
        info("تثبيت pycryptodome...")
        r = subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "pycryptodome"],
            timeout=60, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        try:
            from Crypto.Cipher import AES
            success("pycryptodome جاهز")
            return True
        except:
            error("فشل تثبيت pycryptodome")
            return False

# AES-ECB (RUI 1)
ECB_KEY = b'\xd8\x99&\xf3\x00D\xa2\x89\xb4\x8e\x96\xe0]\xa6\x1fJ'

def encrypt_ecb(data_str):
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad
    cipher = AES.new(ECB_KEY, AES.MODE_ECB)
    return base64.b64encode(cipher.encrypt(pad(data_str.encode(), 16))).decode()

def decrypt_ecb(data_b64):
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
    cipher = AES.new(ECB_KEY, AES.MODE_ECB)
    return unpad(cipher.decrypt(base64.b64decode(data_b64)), 16).decode()

# sha256 helper
def sha256(s):
    return hashlib.sha256(s.encode()).hexdigest()

# ─── OPPO OTA Request (RUI v1 — for CPH2159) ─────────
OPPO_URL_V1 = "https://ifota.realmemobile.com/post/Query_Update"

DEFAULT_HEADERS = {
    "plateform":    "android",
    "language":     "en-EN",
    "version":      "1",
    "Accept":       "application/json",
    "Content-Type": "application/json; charset=UTF-8",
    "imei":         "000000000000000",
}

DEFAULT_BODY = {
    "androidVersion":   "Android11.0",
    "colorOSVersion":   "ColorOS7",
    "model":            "CPH2159",
    "productName":      "CPH2159",
    "otaVersion":       "",
    "romVersion":       "",
    "romPrefix":        "",
    "otaPrefix":        "",
    "nvCarrier":        "00011011",
    "partCarrier":      "00011011",
    "localCarrier":     "00011011",
    "nvId":             "0",
    "trackRegion":      "GL",
    "uRegion":          "GL",
    "isRealme":         "0",
    "mode":             "0",
    "time":             "",
    "deviceId":         "",
}

def build_ota_request(device):
    body = dict(DEFAULT_BODY)
    body["model"]        = device["product_name"]
    body["productName"]  = device["product_name"]
    body["otaVersion"]   = device["ota_version"]
    body["nvId"]         = device["nv_id"]
    body["nvCarrier"]    = body["partCarrier"] = body["localCarrier"] = device["nv_id"]
    body["time"]         = str(int(time.time() * 1000))
    body["deviceId"]     = sha256(DEFAULT_HEADERS["imei"])

    # romPrefix = first 2 parts of ota_version
    parts = device["ota_version"].split("_")
    prefix = "_".join(parts[:2]) if len(parts) >= 2 else device["ota_version"]
    body["romVersion"] = body["romPrefix"] = body["otaPrefix"] = prefix

    # Encrypt body with ECB
    encrypted = encrypt_ecb(json.dumps(body))
    req_body = json.dumps({"params": encrypted})
    return req_body, DEFAULT_HEADERS

def query_oppo_server(device):
    info("الاتصال بسيرفر OPPO OTA...")
    try:
        req_body, headers = build_ota_request(device)
        req = urllib.request.Request(
            OPPO_URL_V1,
            data=req_body.encode("utf-8"),
            headers=headers,
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
        data_json = json.loads(raw)
        info(f"Response code: {data_json.get('responseCode')}")

        if data_json.get("responseCode") != 200:
            warn(f"Server: {data_json.get('errMsg','unknown error')}")
            return None

        # Decrypt response
        encrypted_resp = data_json.get("resps")
        if not encrypted_resp:
            warn("لا يوجد 'resps' في الرد")
            return None

        decrypted = decrypt_ecb(encrypted_resp)
        content = json.loads(decrypted)
        return content

    except Exception as e:
        warn(f"OPPO server error: {e}")
        return None

def extract_download_url(content):
    """استخراج رابط التحميل من response"""
    if not content:
        return None

    info(f"Response keys: {list(content.keys()) if isinstance(content, dict) else type(content)}")

    # بحث مباشر
    for key in ["dlUrl", "url", "componentUrl", "fileUrl", "downloadUrl"]:
        if key in content and content[key]:
            return content[key]

    # في RUI v1 قد تكون داخل component
    if "components" in content:
        for comp in content["components"]:
            for key in ["dlUrl", "url", "componentUrl"]:
                if key in comp and comp[key]:
                    return comp[key]

    # اطبع الـ response كاملاً لنرى ماذا فيه
    info(f"Full response:\n{json.dumps(content, indent=2, ensure_ascii=False)[:800]}")
    return None

# ─── Fallback: try older OTA version to get a URL ────
def try_older_ota(device):
    info("جاري تجربة إصدار OTA أقدم للحصول على رابط...")
    # جرب إصدارات أقدم معروفة لـ CPH2159
    older_versions = [
        "CPH2159EX_11_A.21_210127",
        "CPH2159EX_11_A.23_210223",
        "CPH2159_11_A.21_210127",
        "CPH2159_11.A.21_2420_202101271432",
    ]
    for v in older_versions:
        info(f"جاري تجربة: {v}")
        device_copy = dict(device)
        device_copy["ota_version"] = v
        result = query_oppo_server(device_copy)
        if result:
            url = extract_download_url(result)
            if url:
                return url, result
    return None, None

# ─── Read device props ────────────────────
def get_prop(key):
    try:
        r = subprocess.run(["getprop", key],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        v = r.stdout.strip()
        return v if v else None
    except:
        return None

def read_device_info():
    info("قراءة معلومات الجهاز...")
    props = {
        "product_name": get_prop("ro.product.name"),
        "ota_version":  get_prop("ro.build.version.ota"),
        "rui_raw":      get_prop("ro.build.version.realmeui") or get_prop("ro.build.version.oplusrom"),
        "nv_id":        get_prop("ro.build.oplus_nv_id") or "0",
    }
    for k, v in props.items():
        if v: success(f"{k}: {v}")
        else: warn(f"{k}: غير متاح")

    rui_raw = props["rui_raw"] or "1"
    m = re.search(r'\d+', rui_raw)
    rui_version = int(m.group()) if m else 1

    return {
        "product_name": props["product_name"] or "CPH2159",
        "ota_version":  props["ota_version"]  or "CPH2159EX_11_A.21_210127",
        "rui_version":  rui_version,
        "nv_id":        props["nv_id"] or "0",
    }

# ─── Download with progress ───────────────
def download_file(url, dest_path):
    info(f"جاري التحميل...")
    info(f"URL: {url[:90]}...")
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Linux; Android 11) AppleWebKit/537.36"
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            total_mb = total / (1024*1024)
            info(f"حجم الملف: {total_mb:.0f} MB")
            downloaded = 0
            with open(dest_path, 'wb') as f:
                while True:
                    buf = resp.read(1024*1024)
                    if not buf: break
                    f.write(buf)
                    downloaded += len(buf)
                    if total > 0:
                        pct = downloaded/total*100
                        print(f"\r{C}  [{pct:5.1f}%] {downloaded/1024/1024:.0f}/{total_mb:.0f} MB{RESET}", end="", flush=True)
        print()
        success(f"تم التحميل: {os.path.getsize(dest_path)/1024/1024:.1f} MB")
        return True
    except Exception as e:
        print()
        error(f"فشل التحميل: {e}")
        return False

# ─── Extract boot.img from zip ────────────
def extract_boot(zip_path, out_dir):
    info(f"استخراج boot.img من: {os.path.basename(zip_path)}")
    os.makedirs(out_dir, exist_ok=True)
    boot_names = ['boot.img','boot_a.img','boot_b.img','BOOT.IMG']
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            all_files = zf.namelist()
            imgs = [f for f in all_files if f.lower().endswith('.img')]
            if imgs:
                info(f"ملفات IMG ({len(imgs)}):")
                for img in imgs[:10]: print(f"   {B}• {img}{RESET}")

            found = None
            for name in boot_names:
                for f in all_files:
                    if os.path.basename(f).lower() == name.lower():
                        found = f; break
                if found: break

            if not found:
                warn("boot.img غير موجود مباشرة — فحص ZIPs الفرعية...")
                for f in all_files:
                    if f.lower().endswith('.zip'):
                        sub_data = zf.read(f)
                        sub_path = os.path.join(TEMP_DIR, os.path.basename(f))
                        with open(sub_path, 'wb') as sf: sf.write(sub_data)
                        result = extract_boot(sub_path, out_dir)
                        if result: return result
                return None

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_file = os.path.join(out_dir, f"boot_CPH2159_{ts}.img")
            info(f"استخراج: {found}")
            with zf.open(found) as src, open(out_file, 'wb') as dst:
                shutil.copyfileobj(src, dst)
            return out_file

    except zipfile.BadZipFile:
        error("ملف ZIP تالف")
        return None
    except Exception as e:
        error(f"خطأ: {e}")
        return None

def verify_boot(filepath):
    try:
        with open(filepath, 'rb') as f: magic = f.read(8)
        if magic[:8] == b'ANDROID!': success("boot.img صحيح ✅ (ANDROID!)")
        else: warn(f"Magic: {magic.hex()}")
    except: pass

def show_next_steps(f):
    print(f"\n{C}{'═'*46}")
    print(f"  الخطوات التالية — Root بـ Magisk")
    print(f"{'═'*46}{RESET}")
    print(f"{W}1. ثبّت Magisk: github.com/topjohnwu/Magisk/releases{RESET}")
    print(f"{W}2. Magisk → Install → Patch a File{RESET}")
    print(f"{W}3. اختر: {B}{f}{RESET}")
    print(f"{W}4. fastboot flash boot magisk_patched.img{RESET}")
    print(f"{C}{'═'*46}{RESET}\n")

# ─── Main ─────────────────────────────────
def main():
    print(BANNER)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR, exist_ok=True)

    step(1, "قراءة معلومات الجهاز")
    device = read_device_info()
    print(f"\n{Y}معلومات الجهاز:{RESET}")
    for k,v in device.items(): print(f"  {B}{k}:{RESET} {W}{v}{RESET}")

    print(f"\n{W}هل المعلومات صحيحة؟ Enter للتأكيد أو n للتعديل: {RESET}", end="")
    try:
        if input().strip().lower() == 'n':
            print(f"{W}OTA version يدوي: {RESET}", end="")
            v = input().strip()
            if v: device["ota_version"] = v
    except KeyboardInterrupt:
        print(); sys.exit(0)

    step(2, "تثبيت متطلبات التشفير")
    if not install_pycrypto():
        error("pycryptodome مطلوب — شغّل: pip install pycryptodome")
        sys.exit(1)

    step(3, "الاستعلام عن OTA من سيرفر OPPO")
    result = query_oppo_server(device)
    download_url = extract_download_url(result) if result else None

    if not download_url:
        warn("لم يُعثر على رابط — جاري تجربة إصدارات أقدم...")
        download_url, result = try_older_ota(device)

    if not download_url:
        error("لم يتم العثور على OTA لهذا الجهاز")
        print(f"\n{Y}هل تريد إدخال رابط يدوياً؟ (y/n): {RESET}", end="")
        try:
            if input().strip().lower() == 'y':
                print(f"{W}الرابط: {RESET}", end="")
                download_url = input().strip()
        except: pass
        if not download_url: sys.exit(1)

    success(f"OTA URL: {download_url[:80]}...")

    step(4, "تحميل OTA package")
    ext = ".ozip" if ".ozip" in download_url else ".zip"
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    dl_path = os.path.join(TEMP_DIR, f"CPH2159_OTA_{ts}{ext}")

    if not download_file(download_url, dl_path): sys.exit(1)

    step(5, "استخراج boot.img")
    boot_file = extract_boot(dl_path, OUTPUT_DIR)

    try: shutil.rmtree(TEMP_DIR)
    except: pass

    print()
    if boot_file and os.path.exists(boot_file):
        size = os.path.getsize(boot_file)/1024/1024
        success(f"تم استخراج boot.img!")
        success(f"الملف: {boot_file}")
        success(f"الحجم: {size:.2f} MB")
        verify_boot(boot_file)
        show_next_steps(boot_file)
        success("🖤 Shadow Core — مهمة مكتملة")
    else:
        error("لم يتم العثور على boot.img في الـ OTA")
        sys.exit(1)

if __name__ == "__main__":
    main()
