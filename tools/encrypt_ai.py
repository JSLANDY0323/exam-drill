"""把 AI應用規劃師 題庫加密後放到 data/（明文只留在 private/，不要上傳）。

用法（在專案資料夾執行）：
    py tools/encrypt_ai.py            加密 private/ 裡的題庫，輸入兩次密碼
    py tools/encrypt_ai.py --check    用密碼試解 data/ 裡的加密檔，確認密碼正確

加密方式：密碼經 PBKDF2-SHA256（600,000 次）導出 256 位元金鑰，題庫 gzip 壓縮後用 AES-256-GCM 加密。
網頁（index.html 的 AILock）用瀏覽器內建的 Web Crypto 以同樣方式解密。
需要套件：py -m pip install cryptography
"""
import base64, getpass, gzip, hashlib, json, os, sys

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRIVATE = os.path.join(ROOT, 'private')
DATA = os.path.join(ROOT, 'data')
MEDIA_OUT = os.path.join(DATA, 'media')
RB_DIR = os.path.join(ROOT, 'private', 'TOEIC', 'TOEIC紅藍本')
IMG_SRC = os.path.join(RB_DIR, 'kb', 'img')
AUDIO_64K = os.path.join(RB_DIR, 'kb', '_work', 'audio_64k')
AUDIO_RAW = os.path.join(RB_DIR, '聽力')
T10_MEDIA = os.path.join(ROOT, 'private', 'toeic_md', 'listening', 'media')   # 各 10 回聽力：build_toeic10_listening.py 產生
SOURCES = ['ai_jr.json', 'ai_sr_common.json', 'ai_sr_ml.json', 'ai_sr_bd.json', 'toeic_listening.json', 'toeic_reading_mock.json', 'toeic10_reading.json',
           'toeic10_listening.json']
LISTENING = ['toeic_listening.json', 'toeic10_listening.json']
ITER = 600_000
b64 = lambda b: base64.b64encode(b).decode('ascii')


def media_id(media_key: str) -> str:
    return hashlib.sha256(media_key.encode('utf-8')).hexdigest()[:16]


def media_src(kind, rel):
    """媒體鍵（img/… 或 audio/…）對應的本機檔案；t10/ 開頭是各 10 回聽力。"""
    if rel.startswith('t10/'):
        return os.path.join(T10_MEDIA, rel[4:])
    if kind == 'img':
        return os.path.join(IMG_SRC, rel)
    src64 = os.path.join(AUDIO_64K, rel)
    return src64 if os.path.exists(src64) else os.path.join(AUDIO_RAW, rel)


def collect_listening_media():
    imgs, audios = set(), set()
    exams = []
    for name in LISTENING:
        p = os.path.join(PRIVATE, name)
        if os.path.exists(p):
            exams += json.load(open(p, encoding='utf-8')).get('exams', [])
    for e in exams:
        if e.get('audio'):
            audios.add(e['audio'])
        if e.get('audioAlt'):
            audios.add(e['audioAlt'])
        for pt in e.get('parts', []):
            if pt.get('audio'):
                audios.add(pt['audio'])
        for q in e.get('qs', []):
            if q.get('img'):
                imgs.add(q['img'])
        for s in e.get('sets', []):
            if s.get('img'):
                imgs.add(s['img'])
    return sorted(imgs), sorted(audios)


def derive(password, salt, it=ITER):
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=it)
    return kdf.derive(password.encode('utf-8'))


def enc_name(name):
    return name[:-5] + '.enc.json'


def check():
    password = getpass.getpass('密碼：')
    keys = {}
    for name in SOURCES:
        p = os.path.join(DATA, enc_name(name))
        env = json.load(open(p, encoding='utf-8'))
        salt = base64.b64decode(env['salt'])
        k = keys.setdefault(env['salt'], derive(password, salt, env['iter']))
        try:
            raw = AESGCM(k).decrypt(base64.b64decode(env['iv']), base64.b64decode(env['data']), None)
        except Exception:
            sys.exit(f'密碼不正確（{enc_name(name)} 無法解密）')
        d = json.loads(gzip.decompress(raw).decode('utf-8'))
        print(f"OK {enc_name(name)}：{len(d['exams'])} 份題組、{sum(len(e['qs']) for e in d['exams'])} 題")
    imgs, audios = collect_listening_media()
    if imgs or audios:
        k = next(iter(keys.values()))
        ok_cnt = 0
        for mkey in [f'img/{x}' for x in imgs] + [f'audio/{x}' for x in audios]:
            mp_enc = os.path.join(MEDIA_OUT, f'{media_id(mkey)}.enc')
            if not os.path.exists(mp_enc):
                sys.exit(f'找不到加密媒體檔：{mp_enc}（對應 {mkey}）')
            blob = open(mp_enc, 'rb').read()
            try:
                AESGCM(k).decrypt(blob[:12], blob[12:], None)
                ok_cnt += 1
            except Exception:
                sys.exit(f'媒體檔解密失敗：{mp_enc}（{mkey}）')
        print(f'OK data/media/*.enc：{ok_cnt} 個加密媒體檔（圖片 {len(imgs)}、音檔 {len(audios)}）全數驗證通過')


def encrypt():
    missing = [n for n in SOURCES if not os.path.exists(os.path.join(PRIVATE, n))]
    if missing:
        sys.exit('private/ 找不到：' + '、'.join(missing))
    password = getpass.getpass('設定密碼（輸入時不會顯示）：')
    if len(password) < 12:
        sys.exit('密碼太短。加密檔是公開的，請用至少 12 個字元、最好是一句好記的長句子。')
    if getpass.getpass('再輸入一次：') != password:
        sys.exit('兩次輸入的密碼不同，沒有變更任何檔案。')
    salt = os.urandom(16)
    key = derive(password, salt)
    mp = os.path.join(DATA, 'manifest.json')
    m = json.load(open(mp, encoding='utf-8-sig'))
    for name in SOURCES:
        txt = open(os.path.join(PRIVATE, name), 'rb').read()
        d = json.loads(txt.decode('utf-8-sig'))
        iv = os.urandom(12)
        ct = AESGCM(key).encrypt(iv, gzip.compress(txt, 9), None)
        env = {'enc': 'AES-256-GCM', 'kdf': 'PBKDF2-SHA256', 'iter': ITER, 'salt': b64(salt), 'iv': b64(iv), 'gz': 1, 'data': b64(ct)}
        out = json.dumps(env, separators=(',', ':')) + '\n'
        open(os.path.join(DATA, enc_name(name)), 'w', encoding='utf-8', newline='\n').write(out)
        entry = next((f for f in m['files'] if f['path'] in (name, enc_name(name))), None)
        if entry is None:
            entry = {'path': enc_name(name), 'title': d.get('about', name)}
            m['files'].append(entry)
        entry['path'] = enc_name(name)
        entry['enc'] = 1
        entry['v'] = hashlib.md5(out.encode('utf-8')).hexdigest()[:8]
        entry['exams'] = [e['id'] for e in d['exams']]
        print(f"已加密 {name} → data/{enc_name(name)}（{len(out) // 1024} KB）")
        if os.path.exists(os.path.join(DATA, name)):
            print(f'  注意：data/{name} 是明文，請刪除或移到 private/，不要上傳。')

    # 加密 TOEIC 聽力圖片與音檔至 data/media/<sha256[:16]>.enc
    imgs, audios = collect_listening_media()
    if imgs or audios:
        os.makedirs(MEDIA_OUT, exist_ok=True)
        aes = AESGCM(key)
        img_bytes = 0
        for img in imgs:
            raw = open(media_src('img', img), 'rb').read()
            iv = os.urandom(12)
            enc_blob = iv + aes.encrypt(iv, raw, None)
            dst = os.path.join(MEDIA_OUT, f"{media_id('img/' + img)}.enc")
            open(dst, 'wb').write(enc_blob)
            img_bytes += len(enc_blob)
        aud_bytes = 0
        for aud in audios:
            raw = open(media_src('audio', aud), 'rb').read()
            iv = os.urandom(12)
            enc_blob = iv + aes.encrypt(iv, raw, None)
            dst = os.path.join(MEDIA_OUT, f"{media_id('audio/' + aud)}.enc")
            open(dst, 'wb').write(enc_blob)
            aud_bytes += len(enc_blob)
        print(f"已加密聽力圖片 {len(imgs)} 張（{img_bytes / 1024 / 1024:.1f} MB）與音檔 {len(audios)} 個（{aud_bytes / 1024 / 1024:.1f} MB）→ data/media/*.enc")
    lines = ['{', f' "about":{json.dumps(m["about"], ensure_ascii=False)},', ' "files":[']
    lines.append(',\n'.join('  ' + json.dumps(f, ensure_ascii=False, separators=(',', ':')) for f in m['files']))
    lines += [' ]', '}']
    open(mp, 'w', encoding='utf-8', newline='\n').write('\n'.join(lines) + '\n')
    print('manifest.json 已更新。每次修改 private/ 的題庫後，請重新執行本程式。')


if __name__ == '__main__':
    check() if '--check' in sys.argv else encrypt()
