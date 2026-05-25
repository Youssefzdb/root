#!/usr/bin/env python3
# ============================================
#  Shadow Core Boot Puller v7
#  Device: OPPO Reno 5 CPH2159 | ColorOS
#  Platform: Termux — No Root, No PC
#  Crypto: Exact match of realme-ota source
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
║  {W}Shadow Core Boot Puller  v7{R}               ║
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

# ─── Crypto (exact copy from realme-ota/utils/crypto.py) ──────────
KEYS = ["oppo1997","baed2017","java7865","231uiedn","09e32ji6",
        "0oiu3jdy","0pej387l","2dkliuyt","20odiuye","87j3id7w"]

def ensure_pycrypto():
    try:
        from Crypto.Cipher import AES
        return True
    except ImportError:
        info("تثبيت pycryptodome...")
        subprocess.run([sys.executable,"-m","pip","install","--quiet","pycryptodome"],
                       timeout=90, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            from Crypto.Cipher import AES
            success("pycryptodome جاهز")
            return True
        except:
            return False

def get_key(key_pseudo):
    return (KEYS[int(key_pseudo[0])] + key_pseudo[4:12]).encode('utf-8')

def enc_aes_ecb(data_bytes, key_bytes):
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import pad
    cipher = AES.new(key_bytes, AES.MODE_ECB)
    return cipher.encrypt(pad(data_bytes, AES.block_size))

def dec_aes_ecb(data_bytes, key_bytes):
    from Crypto.Cipher import AES
    from Crypto.Util.Padding import unpad
    cipher = AES.new(key_bytes, AES.MODE_ECB)
    return unpad(cipher.decrypt(data_bytes), AES.block_size)

def enc_aes_ctr(data_bytes, key_bytes, iv_bytes):
    from Crypto.Cipher import AES
    from Crypto.Util import Counter
    ctr = Counter.new(128, initial_value=int.from_bytes(iv_bytes, 'big'))
    cipher = AES.new(key_bytes, AES.MODE_CTR, counter=ctr)
    return cipher.encrypt(data_bytes)

def dec_aes_ctr(data_bytes, key_bytes, iv_bytes):
    from Crypto.Cipher import AES
    from Crypto.Util import Counter
    ctr = Counter.new(128, initial_value=int.from_bytes(iv_bytes, 'big'))
    cipher = AES.new(key_bytes, AES.MODE_CTR, counter=ctr)
    return cipher.decrypt(data_bytes)

# RUI v1: ECB with derived key
def encrypt_ecb(buf):
    key_pseudo = str(randint(0,9)) + ''.join(choices(string.ascii_letters+string.digits, k=14))
    key_real = get_key(key_pseudo)
    encrypted = enc_aes_ecb(buf.encode('utf-8'), key_real)
    return base64.b64encode(encrypted).decode('utf-8') + key_pseudo

def decrypt_ecb(buf):
    data = base64.b64decode(buf[:-15])
    key  = get_key(buf[-15:])
    return dec_aes_ecb(data, key).decode('utf-8')

# RUI v2+: CTR with derived key
def encrypt_ctr(buf):
    key_pseudo = str(randint(0,9)) + ''.join(choices(string.digits, k=14))
    key_real = get_key(key_pseudo)
    iv = hashlib.md5(key_real).digest()
    encrypted = enc_aes_ctr(buf.encode('utf-8'), key_real, iv)
    return base64.b64encode(encrypted).decode('utf-8') + key_pseudo

def decrypt_ctr(buf):
    data = base64.b64decode(buf[:-15])
    key  = get_key(buf[-15:])
    iv   = hashlib.md5(key).digest()
    return dec_aes_ctr(data, key, iv).decode('utf-8')

def sha256_upper(s):
    return hashlib.sha256(s.encode('utf-8')).hexdigest().upper()

# ─── Endpoints ────────────────────────────────────────
# RUI 1 → ECB → /post/Query_Update
# RUI 2+ → CTR → /update/v3
URLS = {
    'v1_gl': 'https://ifota.realmemobile.com/post/Query_Update',
    'v1_oppo': 'https://iota.coloros.com/post/Query_Update',
    'v1_eu': 'https://ifota-eu.realmemobile.com/post/Query_Update',
    'v1_in': 'https://ifota-in.realmemobile.com/post/Query_Update',
    'v2_gl': 'https://component-ota-f.coloros.com/update/v3',
    'v2_sg': 'https://component-otapc-sg.allawnos.com/update/v3',
}

# ─── Build body (matches default_body in data.py exactly) ─────────
def build_body(device):
    ota = device['ota_version']
    parts = ota.split('_')
    prefix = '_'.join(parts[:2]) if len(parts) >= 2 else ota
    rui = device['rui_version']
    nv  = device['nv_id']
    nv_carrier = nv if nv != '0' else ('10010111' if False else '00011011')

    return {
        "language":       "en-EN",
        "romVersion":     ota,
        "otaVersion":     ota,
        "androidVersion": f"Android{10 + rui - 1}.0",
        "colorOSVersion": f"ColorOS{rui}",
        "model":          device['product_name'],
        "productName":    device['product_name'],
        "operator":       device['product_name'],
        "uRegion":        "GL",
        "trackRegion":    "GL",
        "imei":           "000000000000000",
        "imei1":          "000000000000000",
        "mode":           "0",
        "registrationId": "unknown",
        "deviceId":       sha256_upper("000000000000000"),
        "version":        "3",
        "type":           "1",
        "otaPrefix":      prefix,
        "romPrefix":      prefix,
        "isRealme":       "0",
        "time":           str(int(_time.time() * 1000)),
        "canCheckSelf":   "0",
        "nvId":           nv,
        "nvCarrier":      nv_carrier,
        "partCarrier":    nv_carrier,
        "localCarrier":   nv_carrier,
    }

def build_headers(device):
    ota = device['ota_version']
    rui = device['rui_version']
    nv  = device['nv_id']
    return {
        'language':       'en-EN',
        'romVersion':     ota,
        'otaVersion':     ota,
        'androidVersion': f"Android{10 + rui - 1}.0",
        'colorOSVersion': f"ColorOS{rui}",
        'model':          device['product_name'],
        'infVersion':     '1',
        'operator':       device['product_name'],
        'nvCarrier':      nv if nv != '0' else '00011011',
        'uRegion':        'GL',
        'trackRegion':    'GL',
        'imei':           '000000000000000',
        'imei1':          '000000000000000',
        'deviceId':       sha256_upper("000000000000000"),
        'mode':           'client_auto',
        'channel':        'pc',
        'version':        '1',
        'Accept':         'application/json',
        'Content-Type':   'application/json',
        'User-Agent':     'NULL',
    }

# ─── Send request ─────────────────────────────────────
def post_ota(url, device, use_ecb=True):
    body_plain = build_body(device)
    body_str   = json.dumps(body_plain)

    if use_ecb:
        cipher_text = encrypt_ecb(body_str)
        payload = json.dumps({"params": cipher_text}).encode('utf-8')
    else:
        cipher_text = encrypt_ctr(body_str)
        payload = json.dumps({"params": cipher_text}).encode('utf-8')

    headers = build_headers(device)
    info(f"POST → {url}")
    try:
        req = urllib.request.Request(url, data=payload, headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            info(f"HTTP {resp.status} | {len(raw)} bytes")
            if not raw.strip():
                warn("Response فارغ (204/empty)")
                return None
            return json.loads(raw)
    except urllib.error.HTTPError as e:
        body = b""
        try: body = e.read()
        except: pass
        warn(f"HTTP {e.code} | {len(body)} bytes")
        if body:
            info(f"Error body: {body[:300]}")
        return None
    except Exception as e:
        warn(f"خطأ: {e}")
        return None

def parse_and_decrypt(resp_json, use_ecb=True):
    if not resp_json:
        return None
    code = resp_json.get('responseCode', resp_json.get('code', '?'))
    info(f"responseCode: {code}")
    if code != 200:
        warn(f"errMsg: {resp_json.get('errMsg','')}")
        return None
    enc = resp_json.get('resps') or resp_json.get('body')
    if not enc:
        info(f"Keys في response: {list(resp_json.keys())}")
        return None
    try:
        decrypted = decrypt_ecb(enc) if use_ecb else decrypt_ctr(enc)
        return json.loads(decrypted)
    except Exception as e:
        warn(f"فشل فك التشفير: {e}")
        return None

def find_dl_url(content):
    if not isinstance(content, dict):
        return None
    # اطبع كل الـ response
    print(f"{B}{json.dumps(content, indent=2, ensure_ascii=False)[:800]}{RESET}")
    for k in ["dlUrl","url","componentUrl","fileUrl","downloadUrl","fullDlUrl"]:
        if content.get(k): return content[k]
    for comp_key in ["components","component"]:
        for comp in (content.get(comp_key) or []):
            for k in ["dlUrl","url","componentUrl","fileUrl"]:
                if comp.get(k): return comp[k]
    return None

# ─── Main OTA search ──────────────────────────────────
def search_ota(device):
    rui = device['rui_version']

    # RUI 1 → ECB
    # RUI 2+ → CTR  (جهازك على RUI 13 فنجرب الاثنين)
    trials = [
        (URLS['v1_oppo'],  True),
        (URLS['v1_gl'],    True),
        (URLS['v1_eu'],    True),
        (URLS['v2_gl'],    False),
        (URLS['v2_sg'],    False),
    ]

    for url, use_ecb in trials:
        resp = post_ota(url, device, use_ecb)
        content = parse_and_decrypt(resp, use_ecb)
        dl = find_dl_url(content)
        if dl: return dl

    # جرب OTA versions أقدم
    warn("جاري تجربة OTA versions أقدم مع OPPO URL...")
    old_otas = [
        "CPH2159_11.A.21_2420_202101270001_000000000001",
        "CPH2159EX_11_A.21_210127",
    ]
    for ota in old_otas:
        d2 = dict(device); d2['ota_version'] = ota; d2['rui_version'] = 1
        for url, ecb in [(URLS['v1_oppo'], True), (URLS['v1_gl'], True)]:
            resp = post_ota(url, d2, ecb)
            content = parse_and_decrypt(resp, ecb)
            dl = find_dl_url(content)
            if dl: return dl

    return None

# ─── Read device ──────────────────────────────────────
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

# ─── Download ─────────────────────────────────────────
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

# ─── Extract boot.img ─────────────────────────────────
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

# ─── Main ─────────────────────────────────────────────
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
        error("pycryptodome مطلوب — pip install pycryptodome"); sys.exit(1)

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
