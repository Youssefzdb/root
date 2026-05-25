#!/usr/bin/env python3
# ============================================
#  Shadow Core Boot Puller v8
#  Device: OPPO Reno 5 CPH2159 | ColorOS
#  Platform: Termux — No Root, No PC
# ============================================

import subprocess, sys, os, json, zipfile, shutil
import re, hashlib, base64, string, time as _time
import urllib.request, urllib.error
from datetime import datetime
from random import randint, choices

R="\033[31m"; G="\033[32m"; Y="\033[33m"
C="\033[36m"; W="\033[97m"; B="\033[90m"; RESET="\033[0m"

BANNER = f"""
{R}╔══════════════════════════════════════════════╗
║  {W}Shadow Core Boot Puller  v8{R}               ║
║  {B}OPPO Reno 5 CPH2159 | No Root | No PC{R}    ║
╚══════════════════════════════════════════════╝{RESET}
"""

OUTPUT_DIR = os.path.expanduser("~/boot_images")
TEMP_DIR   = os.path.expanduser("~/boot_images/.tmp")

def success(m): print(f"{G}[✓] {m}{RESET}")
def error(m):   print(f"{R}[✗] {m}{RESET}")
def warn(m):    print(f"{Y}[!] {m}{RESET}")
def info(m):    print(f"{C}[*] {m}{RESET}")
def step(n, m): print(f"\n{W}━━[{n}] {m}━━{RESET}")

# ─── Crypto (exact from realme-ota/utils/crypto.py) ───
KEYS = ["oppo1997","baed2017","java7865","231uiedn","09e32ji6",
        "0oiu3jdy","0pej387l","2dkliuyt","20odiuye","87j3id7w"]

def ensure_pycrypto():
    try:
        from Crypto.Cipher import AES; return True
    except ImportError:
        info("تثبيت pycryptodome...")
        subprocess.run([sys.executable,"-m","pip","install","--quiet","pycryptodome"],
                       timeout=90, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            from Crypto.Cipher import AES; success("pycryptodome جاهز"); return True
        except: return False

def get_key(key_pseudo):
    return (KEYS[int(key_pseudo[0])] + key_pseudo[4:12]).encode('utf-8')

def enc_ecb(data_bytes, key_bytes):
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad
    return AES.new(key_bytes, AES.MODE_ECB).encrypt(pad(data_bytes, 16))

def dec_ecb(data_bytes, key_bytes):
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
    return unpad(AES.new(key_bytes, AES.MODE_ECB).decrypt(data_bytes), 16)

def enc_ctr(data_bytes, key_bytes, iv_bytes):
    from Crypto.Cipher import AES
    from Crypto.Util import Counter
    ctr = Counter.new(128, initial_value=int.from_bytes(iv_bytes, 'big'))
    return AES.new(key_bytes, AES.MODE_CTR, counter=ctr).encrypt(data_bytes)

def dec_ctr(data_bytes, key_bytes, iv_bytes):
    from Crypto.Cipher import AES
    from Crypto.Util import Counter
    ctr = Counter.new(128, initial_value=int.from_bytes(iv_bytes, 'big'))
    return AES.new(key_bytes, AES.MODE_CTR, counter=ctr).decrypt(data_bytes)

def encrypt_ecb(buf):
    kp = str(randint(0,9)) + ''.join(choices(string.ascii_letters+string.digits, k=14))
    kr = get_key(kp)
    return base64.b64encode(enc_ecb(buf.encode('utf-8'), kr)).decode() + kp

def decrypt_ecb(buf):
    data = base64.b64decode(buf[:-15])
    key  = get_key(buf[-15:])
    return dec_ecb(data, key).decode('utf-8')

def encrypt_ctr(buf):
    kp = str(randint(0,9)) + ''.join(choices(string.digits, k=14))
    kr = get_key(kp)
    iv = hashlib.md5(kr).digest()
    return base64.b64encode(enc_ctr(buf.encode('utf-8'), kr, iv)).decode() + kp

def decrypt_ctr(buf):
    data = base64.b64decode(buf[:-15])
    key  = get_key(buf[-15:])
    iv   = hashlib.md5(key).digest()
    return dec_ctr(data, key, iv).decode('utf-8')

def sha256u(s):
    return hashlib.sha256(s.encode()).hexdigest().upper()

# ─── Build request ─────────────────────────────────────
def build_body(device):
    ota = device['ota_version']
    parts = ota.split('_')
    prefix = '_'.join(parts[:2]) if len(parts) >= 2 else ota
    rui = device['rui_version']
    nv  = device['nv_id']
    nvc = nv if (nv and nv != '0') else '00011011'
    return {
        "language": "en-EN", "romVersion": ota, "otaVersion": ota,
        "androidVersion": f"Android{10+rui-1}.0",
        "colorOSVersion": f"ColorOS{rui}",
        "model": device['product_name'], "productName": device['product_name'],
        "operator": device['product_name'],
        "uRegion": "GL", "trackRegion": "GL",
        "imei": "000000000000000", "imei1": "000000000000000",
        "mode": "0", "registrationId": "unknown",
        "deviceId": sha256u("000000000000000"),
        "version": "3", "type": "1",
        "otaPrefix": prefix, "romPrefix": prefix, "isRealme": "0",
        "time": str(int(_time.time()*1000)), "canCheckSelf": "0",
        "nvId": nv, "nvCarrier": nvc, "partCarrier": nvc, "localCarrier": nvc,
    }

def build_headers(device):
    ota = device['ota_version']; rui = device['rui_version']
    nv  = device['nv_id']
    nvc = nv if (nv and nv != '0') else '00011011'
    return {
        'language': 'en-EN', 'romVersion': ota, 'otaVersion': ota,
        'androidVersion': f"Android{10+rui-1}.0",
        'colorOSVersion': f"ColorOS{rui}",
        'model': device['product_name'], 'infVersion': '1',
        'operator': device['product_name'], 'nvCarrier': nvc,
        'uRegion': 'GL', 'trackRegion': 'GL',
        'imei': '000000000000000', 'imei1': '000000000000000',
        'deviceId': sha256u("000000000000000"),
        'mode': 'client_auto', 'channel': 'pc', 'version': '1',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'User-Agent': 'NULL',
    }

def post_ota(url, device, use_ecb=True):
    body_plain = build_body(device)
    cipher = encrypt_ecb(json.dumps(body_plain)) if use_ecb else encrypt_ctr(json.dumps(body_plain))
    payload = json.dumps({"params": cipher}).encode('utf-8')
    headers = build_headers(device)
    info(f"POST → {url}  [{'ECB' if use_ecb else 'CTR'}]")
    try:
        req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            info(f"HTTP {resp.status} | {len(raw)} bytes")
            if not raw.strip():
                warn("Response فارغ"); return None, None
            # طبع raw للـ debug
            info(f"Raw: {raw[:200]}")
            return json.loads(raw), use_ecb
    except urllib.error.HTTPError as e:
        body = b""
        try: body = e.read()
        except: pass
        warn(f"HTTP {e.code} | body: {body[:150]}")
        return None, None
    except Exception as e:
        warn(f"خطأ: {e}"); return None, None

def parse_response(resp_json, use_ecb):
    if not resp_json: return None
    # طبع كل الـ keys
    info(f"JSON keys: {list(resp_json.keys())}")
    code = resp_json.get('responseCode', resp_json.get('code', resp_json.get('status','?')))
    info(f"responseCode: {code}")
    if code != 200:
        warn(f"errMsg: {resp_json.get('errMsg','')}")
        return None
    # جرب كل مفاتيح الـ response المشفر
    for enc_key in ['resps', 'body', 'data', 'result']:
        enc = resp_json.get(enc_key)
        if enc:
            try:
                dec = decrypt_ecb(enc) if use_ecb else decrypt_ctr(enc)
                info(f"فك تشفير '{enc_key}' نجح ✓")
                return json.loads(dec)
            except Exception as e:
                warn(f"فشل فك '{enc_key}': {e}")
    info(f"Response كامل: {json.dumps(resp_json, ensure_ascii=False)[:400]}")
    return None

def find_dl_url(content):
    if not isinstance(content, dict): return None
    info(f"Content: {json.dumps(content, indent=2, ensure_ascii=False)[:600]}")
    for k in ["dlUrl","url","componentUrl","fileUrl","downloadUrl","fullDlUrl"]:
        if content.get(k): return content[k]
    for ck in ["components","component","list"]:
        for comp in (content.get(ck) or []):
            if isinstance(comp, dict):
                for k in ["dlUrl","url","componentUrl","fileUrl"]:
                    if comp.get(k): return comp[k]
    return None

# ─── Search OTA ────────────────────────────────────────
# جهازك F.42 = أحدث إصدار → نرسل إصدار قديم جداً عشان يرد بـ update
OLD_OTAS = [
    # إصدارات قديمة جداً لـ CPH2159 — السيرفر سيرد بالأحدث
    ("CPH2159_11.A.21_2420_202101270001_000000000001", 1),
    ("CPH2159_11_A.21_0001_000000000001",              1),
    ("CPH2159EX_11_A.01_0001_000000000001",            1),
    ("CPH2159_11.A.01_2420_202001010001_000000000001", 1),
    # v2 endpoint format
    ("CPH2159_11.A.21_2420_202101270001_000000000001", 13),
]

URLS_V1 = [
    'https://iota.coloros.com/post/Query_Update',
    'https://ifota.realmemobile.com/post/Query_Update',
]
URLS_V2 = [
    'https://component-ota-f.coloros.com/update/v3',
    'https://component-otapc-sg.allawnos.com/update/v3',
]

def search_ota(device):
    # 1. جرب v2 endpoints مع الإصدار الحالي وإصدارات قديمة
    info("جاري تجربة v2 endpoints...")
    for url in URLS_V2:
        for ota, rui in OLD_OTAS:
            d = dict(device); d['ota_version'] = ota; d['rui_version'] = rui
            resp, enc = post_ota(url, d, use_ecb=False)
            content = parse_response(resp, False)
            dl = find_dl_url(content)
            if dl: return dl

    # 2. جرب v1 endpoints مع إصدارات قديمة جداً
    info("جاري تجربة v1 endpoints مع OTA قديمة...")
    for url in URLS_V1:
        for ota, rui in OLD_OTAS:
            d = dict(device); d['ota_version'] = ota; d['rui_version'] = rui if rui == 1 else 1
            resp, enc = post_ota(url, d, use_ecb=True)
            content = parse_response(resp, True)
            dl = find_dl_url(content)
            if dl: return dl

    return None

# ─── Read device ───────────────────────────────────────
def get_prop(k):
    try:
        r = subprocess.run(["getprop",k], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, text=True, timeout=5)
        v = r.stdout.strip(); return v or None
    except: return None

def read_device():
    info("قراءة معلومات الجهاز...")
    pn  = get_prop("ro.product.name") or "CPH2159"
    ota = get_prop("ro.build.version.ota") or "CPH2159_11.F.42_2420_202510271432"
    rui_raw = get_prop("ro.build.version.realmeui") or get_prop("ro.build.version.oplusrom") or "13"
    nv  = get_prop("ro.build.oplus_nv_id") or "00011011"
    m   = re.search(r'\d+', rui_raw); rui = int(m.group()) if m else 13
    for k,v in [("product_name",pn),("ota_version",ota),("rui_version",rui),("nv_id",nv)]:
        success(f"{k}: {v}")
    return {"product_name":pn,"ota_version":ota,"rui_version":rui,"nv_id":nv}

# ─── Download ──────────────────────────────────────────
def download(url, dest):
    info(f"تحميل: {url[:80]}...")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            total = int(resp.headers.get("Content-Length",0))
            info(f"الحجم: {total/1024/1024:.0f} MB")
            done = 0
            with open(dest,'wb') as f:
                while True:
                    buf = resp.read(1024*1024)
                    if not buf: break
                    f.write(buf); done+=len(buf)
                    if total:
                        print(f"\r{C}  [{done/total*100:5.1f}%] {done//1024//1024}/{total//1024//1024} MB{RESET}",
                              end="", flush=True)
        print(); success(f"تم: {os.path.getsize(dest)/1024/1024:.1f} MB"); return True
    except Exception as e:
        print(); error(f"فشل: {e}"); return False

# ─── Extract boot.img ──────────────────────────────────
def extract_boot(zip_path, out_dir):
    info(f"فحص: {os.path.basename(zip_path)}")
    os.makedirs(out_dir, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path,'r') as zf:
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
            with zf.open(found) as s, open(out,'wb') as d: shutil.copyfileobj(s,d)
            return out
    except zipfile.BadZipFile: error("ZIP تالف"); return None
    except Exception as e: error(f"خطأ: {e}"); return None

def verify(f):
    try:
        with open(f,'rb') as fp: magic=fp.read(8)
        success("boot.img صحيح ✅") if magic[:8]==b'ANDROID!' else warn(f"Magic: {magic.hex()}")
    except: pass

def next_steps(f):
    print(f"\n{C}{'═'*46}")
    print(f"  الخطوات التالية — Root بـ Magisk")
    print(f"{'═'*46}{RESET}")
    print(f"{W}1. ثبّت Magisk: github.com/topjohnwu/Magisk/releases{RESET}")
    print(f"{W}2. Magisk → Install → Patch a File → {B}{f}{RESET}")
    print(f"{W}3. fastboot flash boot magisk_patched.img{RESET}")
    print(f"{C}{'═'*46}{RESET}\n")

# ─── Main ──────────────────────────────────────────────
def main():
    print(BANNER)
    os.makedirs(OUTPUT_DIR, exist_ok=True); os.makedirs(TEMP_DIR, exist_ok=True)

    step(1, "قراءة معلومات الجهاز")
    device = read_device()

    print(f"\n{W}Enter=تأكيد / n=تعديل OTA version: {RESET}", end="")
    try:
        if input().strip().lower() == 'n':
            print(f"{W}OTA version: {RESET}", end="")
            v = input().strip()
            if v: device['ota_version'] = v
    except KeyboardInterrupt:
        print(); sys.exit(0)

    step(2, "تجهيز التشفير")
    if not ensure_pycrypto():
        error("pip install pycryptodome"); sys.exit(1)

    step(3, "الاستعلام عن OTA من OPPO")
    dl_url = search_ota(device)

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
        success(f"الملف: {boot}"); success(f"الحجم: {os.path.getsize(boot)/1024/1024:.2f} MB")
        verify(boot); next_steps(boot); success("🖤 Shadow Core — مهمة مكتملة")
    else:
        error("لم يتم العثور على boot.img في الـ OTA"); sys.exit(1)

if __name__ == "__main__":
    main()
