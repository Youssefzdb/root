#!/usr/bin/env python3
# ============================================
#  Shadow Core Boot Puller v6
#  Device: OPPO Reno 5 CPH2159 | ColorOS
#  Platform: Termux — No Root, No PC
#  Method: OPPO OTA API v1+v2 → boot.img
# ============================================

import subprocess, sys, os, json, zipfile, shutil
import re, hashlib, base64, time as _time
import urllib.request, urllib.error
from datetime import datetime

R="\033[31m"; G="\033[32m"; Y="\033[33m"
C="\033[36m"; W="\033[97m"; B="\033[90m"; RESET="\033[0m"

BANNER = f"""
{R}╔══════════════════════════════════════════════╗
║  {W}Shadow Core Boot Puller  v6{R}               ║
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

# ─── Crypto ───────────────────────────────────────────
def ensure_pycrypto():
    try:
        from Crypto.Cipher import AES
        return True
    except ImportError:
        info("تثبيت pycryptodome...")
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "pycryptodome"],
                       timeout=90, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            from Crypto.Cipher import AES
            success("pycryptodome جاهز")
            return True
        except:
            return False

# AES-ECB key (RUI v1)
ECB_KEY = bytes([0xd8,0x99,0x26,0xf3,0x00,0x44,0xa2,0x89,
                 0xb4,0x8e,0x96,0xe0,0x5d,0xa6,0x1f,0x4a])

def _pad(s):
    n = 16 - len(s) % 16
    return s + chr(n) * n

def _unpad(s):
    return s[:-ord(s[-1])]

def ecb_encrypt(plaintext):
    from Crypto.Cipher import AES
    data = _pad(plaintext).encode('utf-8')
    cipher = AES.new(ECB_KEY, AES.MODE_ECB)
    return base64.b64encode(cipher.encrypt(data)).decode()

def ecb_decrypt(ciphertext_b64):
    from Crypto.Cipher import AES
    cipher = AES.new(ECB_KEY, AES.MODE_ECB)
    dec = cipher.decrypt(base64.b64decode(ciphertext_b64))
    return _unpad(dec.decode('utf-8'))

def sha256(s):
    return hashlib.sha256(s.encode()).hexdigest()

# ─── OTA Endpoints ────────────────────────────────────
# RUI v1  → ECB , URL v1
# RUI v2+ → CTR , URL v2 (component-ota)
URLS_V1 = {
    0: 'https://ifota.realmemobile.com/post/Query_Update',   # GL (Realme)
    'oppo_gl': 'https://iota.coloros.com/post/Query_Update', # GL (OPPO)
}
URLS_V2_GL = 'https://component-ota-f.coloros.com/update/v3'

# ─── Build request body ───────────────────────────────
def make_body_v1(device):
    ts = str(int(_time.time() * 1000))
    ota = device['ota_version']
    parts = ota.split('_')
    prefix = '_'.join(parts[:2]) if len(parts) >= 2 else ota

    body = {
        "language":       "en-EN",
        "romVersion":     ota,
        "otaVersion":     ota,
        "androidVersion": f"Android{10 + device['rui_version'] - 1}.0",
        "colorOSVersion": f"ColorOS{device['rui_version']}",
        "model":          device['product_name'],
        "productName":    device['product_name'],
        "operator":       device['product_name'],
        "uRegion":        "GL",
        "trackRegion":    "GL",
        "imei":           "000000000000000",
        "imei1":          "000000000000000",
        "mode":           "0",
        "registrationId": "unknown",
        "deviceId":       sha256("000000000000000"),
        "version":        "3",
        "type":           "1",
        "otaPrefix":      prefix,
        "romPrefix":      prefix,
        "isRealme":       "0",
        "time":           ts,
        "canCheckSelf":   "0",
        "nvId":           device['nv_id'],
        "nvCarrier":      device['nv_id'] if device['nv_id'] != '0' else "00011011",
        "partCarrier":    device['nv_id'] if device['nv_id'] != '0' else "00011011",
        "localCarrier":   device['nv_id'] if device['nv_id'] != '0' else "00011011",
    }
    return body

def make_headers_v1(device):
    ota = device['ota_version']
    parts = ota.split('_')
    prefix = '_'.join(parts[:2]) if len(parts) >= 2 else ota
    return {
        'language':       'en-EN',
        'romVersion':     ota,
        'otaVersion':     ota,
        'androidVersion': f"Android{10 + device['rui_version'] - 1}.0",
        'colorOSVersion': f"ColorOS{device['rui_version']}",
        'model':          device['product_name'],
        'infVersion':     '1',
        'operator':       device['product_name'],
        'nvCarrier':      device['nv_id'] if device['nv_id'] != '0' else "00011011",
        'uRegion':        'GL',
        'trackRegion':    'GL',
        'imei':           '000000000000000',
        'imei1':          '000000000000000',
        'deviceId':       sha256("000000000000000"),
        'mode':           'client_auto',
        'channel':        'pc',
        'version':        '1',
        'Accept':         'application/json',
        'Content-Type':   'application/json',
        'User-Agent':     'NULL',
    }

# ─── Query OPPO OTA server ────────────────────────────
def query_v1(device, url):
    body_plain = make_body_v1(device)
    body_enc   = ecb_encrypt(json.dumps(body_plain))
    payload    = json.dumps({"params": body_enc}).encode('utf-8')
    headers    = make_headers_v1(device)

    info(f"POST → {url}")
    try:
        req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            info(f"HTTP {resp.status} | {len(raw)} bytes")
            if not raw.strip():
                warn("Response فارغ")
                return None
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        warn(f"HTTP {e.code}: {e.reason}")
        try:
            body = e.read()
            info(f"Error body: {body[:200]}")
        except: pass
        return None
    except Exception as e:
        warn(f"Error: {e}")
        return None

def parse_response_v1(data_json):
    if not data_json:
        return None
    code = data_json.get('responseCode', data_json.get('code'))
    info(f"responseCode: {code}")
    if code != 200:
        warn(f"errMsg: {data_json.get('errMsg','')}")
        return None
    enc = data_json.get('resps')
    if not enc:
        info(f"Keys: {list(data_json.keys())}")
        return None
    try:
        return json.loads(ecb_decrypt(enc))
    except Exception as e:
        warn(f"فشل فك التشفير: {e}")
        return None

def extract_url(content):
    if not content:
        return None
    info(f"Content keys: {list(content.keys()) if isinstance(content, dict) else '?'}")
    # طبع المحتوى كاملاً لنرى ماذا يحتوي
    print(f"{B}{json.dumps(content, indent=2, ensure_ascii=False)[:600]}{RESET}")

    for key in ["dlUrl", "url", "componentUrl", "fileUrl", "downloadUrl", "fullDlUrl"]:
        if content.get(key):
            return content[key]

    # داخل components (RUI v2+)
    for comp_key in ["components", "component"]:
        for comp in (content.get(comp_key) or []):
            for key in ["dlUrl", "url", "componentUrl"]:
                if comp.get(key):
                    return comp[key]
    return None

# ─── Try all endpoints ────────────────────────────────
def find_ota_url(device):
    # جرب OPPO GL URL أولاً
    for url in [
        'https://iota.coloros.com/post/Query_Update',
        'https://ifota.realmemobile.com/post/Query_Update',
        'https://ifota-eu.realmemobile.com/post/Query_Update',
    ]:
        info(f"جاري تجربة: {url}")
        resp = query_v1(device, url)
        content = parse_response_v1(resp)
        dl_url = extract_url(content)
        if dl_url:
            return dl_url

    # جرب إصدارات OTA أقدم
    warn("جاري تجربة OTA versions أقدم...")
    old_versions = [
        "CPH2159_11.A.21_2420_202101270001_000000000001",
        "CPH2159_11.A.21_2420_202101271432",
        "CPH2159EX_11_A.21_210127",
        "CPH2159_11_A.21_210127",
    ]
    for v in old_versions:
        info(f"OTA: {v}")
        d2 = dict(device); d2['ota_version'] = v
        for url in ['https://iota.coloros.com/post/Query_Update']:
            resp = query_v1(d2, url)
            content = parse_response_v1(resp)
            dl_url = extract_url(content)
            if dl_url:
                return dl_url
    return None

# ─── Read device props ────────────────────────────────
def get_prop(k):
    try:
        r = subprocess.run(["getprop", k], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, text=True, timeout=5)
        v = r.stdout.strip()
        return v or None
    except: return None

def read_device():
    info("قراءة معلومات الجهاز...")
    pn  = get_prop("ro.product.name") or "CPH2159"
    ota = get_prop("ro.build.version.ota") or "CPH2159_11.A.21_2420_202101271432"
    rui_raw = get_prop("ro.build.version.realmeui") or get_prop("ro.build.version.oplusrom") or "13"
    nv  = get_prop("ro.build.oplus_nv_id") or "00011011"
    m   = re.search(r'\d+', rui_raw)
    rui = int(m.group()) if m else 13

    for k, v in [("product_name", pn), ("ota_version", ota),
                 ("rui_version", rui), ("nv_id", nv)]:
        success(f"{k}: {v}")
    return {"product_name": pn, "ota_version": ota, "rui_version": rui, "nv_id": nv}

# ─── Download ─────────────────────────────────────────
def download(url, dest):
    info(f"تحميل: {url[:80]}...")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            info(f"الحجم: {total/1024/1024:.0f} MB")
            done = 0
            with open(dest, 'wb') as f:
                while True:
                    buf = resp.read(1024*1024)
                    if not buf: break
                    f.write(buf); done += len(buf)
                    if total:
                        print(f"\r{C}  [{done/total*100:5.1f}%] {done//1024//1024}/{total//1024//1024} MB{RESET}",
                              end="", flush=True)
        print()
        success(f"تم: {os.path.getsize(dest)/1024/1024:.1f} MB")
        return True
    except Exception as e:
        print(); error(f"فشل: {e}"); return False

# ─── Extract boot.img ─────────────────────────────────
def extract_boot(zip_path, out_dir):
    info(f"فحص: {os.path.basename(zip_path)}")
    os.makedirs(out_dir, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            all_f = zf.namelist()
            imgs = [f for f in all_f if f.lower().endswith('.img')]
            if imgs:
                info(f"ملفات IMG ({len(imgs)}):")
                for f in imgs[:10]: print(f"   {B}• {f}{RESET}")

            found = next((f for f in all_f if os.path.basename(f).lower() in
                          ['boot.img','boot_a.img','boot_b.img']), None)

            if not found:
                for f in all_f:
                    if f.lower().endswith('.zip'):
                        sub = os.path.join(TEMP_DIR, os.path.basename(f))
                        with open(sub,'wb') as sf: sf.write(zf.read(f))
                        r = extract_boot(sub, out_dir)
                        if r: return r
                return None

            ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
            out = os.path.join(out_dir, f"boot_CPH2159_{ts}.img")
            with zf.open(found) as s, open(out,'wb') as d: shutil.copyfileobj(s, d)
            return out
    except zipfile.BadZipFile:
        error("ZIP تالف"); return None
    except Exception as e:
        error(f"خطأ: {e}"); return None

def verify(f):
    try:
        with open(f,'rb') as fp: magic = fp.read(8)
        success("boot.img صحيح ✅") if magic[:8]==b'ANDROID!' else warn(f"Magic: {magic.hex()}")
    except: pass

def next_steps(f):
    print(f"\n{C}{'═'*46}")
    print(f"  الخطوات التالية — Root بـ Magisk")
    print(f"{'═'*46}{RESET}")
    print(f"{W}1. ثبّت Magisk: github.com/topjohnwu/Magisk/releases{RESET}")
    print(f"{W}2. Magisk → Install → Patch a File → اختر:{RESET}")
    print(f"   {B}{f}{RESET}")
    print(f"{W}3. fastboot flash boot magisk_patched.img{RESET}")
    print(f"{C}{'═'*46}{RESET}\n")

# ─── Main ─────────────────────────────────────────────
def main():
    print(BANNER)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(TEMP_DIR,   exist_ok=True)

    step(1, "قراءة معلومات الجهاز")
    device = read_device()

    print(f"\n{W}تأكيد أو تعديل OTA version؟ Enter=تأكيد / n=تعديل: {RESET}", end="")
    try:
        if input().strip().lower() == 'n':
            print(f"{W}OTA version: {RESET}", end="")
            v = input().strip()
            if v: device['ota_version'] = v
    except KeyboardInterrupt:
        print(); sys.exit(0)

    step(2, "تجهيز التشفير")
    if not ensure_pycrypto():
        error("pycryptodome مطلوب — شغّل: pip install pycryptodome")
        sys.exit(1)

    step(3, "الاستعلام عن OTA من OPPO")
    dl_url = find_ota_url(device)

    if not dl_url:
        error("لم يُعثر على رابط OTA")
        print(f"\n{W}أدخل رابطاً يدوياً؟ (y/n): {RESET}", end="")
        try:
            if input().strip().lower() == 'y':
                print(f"{W}الرابط: {RESET}", end="")
                dl_url = input().strip()
        except: pass
        if not dl_url: sys.exit(1)

    success(f"URL: {dl_url[:80]}...")

    step(4, "تحميل OTA")
    ext  = ".ozip" if ".ozip" in dl_url else ".zip"
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(TEMP_DIR, f"CPH2159_OTA_{ts}{ext}")
    if not download(dl_url, dest): sys.exit(1)

    step(5, "استخراج boot.img")
    boot = extract_boot(dest, OUTPUT_DIR)
    try: shutil.rmtree(TEMP_DIR)
    except: pass

    print()
    if boot and os.path.exists(boot):
        success(f"الملف: {boot}")
        success(f"الحجم: {os.path.getsize(boot)/1024/1024:.2f} MB")
        verify(boot); next_steps(boot)
        success("🖤 Shadow Core — مهمة مكتملة")
    else:
        error("لم يتم العثور على boot.img في الـ OTA")
        sys.exit(1)

if __name__ == "__main__":
    main()
