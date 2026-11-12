"""TOEIC 紅藍本（Hackers 新制多益聽力／閱讀題庫大全）知識庫工具。

PDF 在 參考書/TOEIC/紅藍本/；知識庫與音檔在 private/TOEIC/TOEIC紅藍本/（兩者皆忽略，不可上傳）。
工作流程與 md 格式見 private/TOEIC/TOEIC紅藍本/kb/README.md。

用法：
  py tools/redblue_kb.py scan                 # 逐頁掃描 → kb/pages.json（書頁碼、音檔、解答本頁）
  py tools/redblue_kb.py build                # 依 kb/sections.json 產生 raw/*.md、index.md、audio.md、progress.md
  py tools/redblue_kb.py render LB 61 [62 …]  # 把 PDF 頁轉成圖片（kb/_img/），校對時看圖用
  py tools/redblue_kb.py render LB 61-64 --printed   # 以「書上印的頁碼」指定
  py tools/redblue_kb.py page LB 61           # 印出單頁整理後的 OCR 文字
  py tools/redblue_kb.py status               # 校對進度
  py tools/redblue_kb.py check                # 檢查 sections.json 與校對檔格式

書代號：LB 聽力題本、LA 聽力解答本、RB 閱讀題本、RA 閱讀解答本。
頁碼一律分清楚：pdf＝PDF 檔第幾頁（從 1 起），書頁＝書上印的頁碼。
"""
import collections, difflib, json, os, re, sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_ROOT = os.path.join(ROOT, "參考書", "TOEIC", "紅藍本")
PRIVATE_ROOT = os.path.join(ROOT, "private", "TOEIC", "TOEIC紅藍本")
KB = os.path.join(PRIVATE_ROOT, "kb")
AUDIO = os.path.join(PRIVATE_ROOT, "聽力")
BOOKS = {
    "LB": ("全新！新制多益TOEIC 聽力題庫大全-ocr.pdf", "聽力題本"),
    "LA": ("全新！新制多益TOEIC 聽力題庫大全解答本-ocr.pdf", "聽力解答本"),
    "RB": ("全新！新制多益TOEIC 閱讀題庫大全-ocr.pdf", "閱讀題本"),
    "RA": ("全新！新制多益TOEIC 閱讀題庫大全解答本-ocr.pdf", "閱讀解答本"),
}
PAGES = os.path.join(KB, "pages.json")
SECTIONS = os.path.join(KB, "sections.json")
CHUNK = 12  # raw 檔每份最多幾頁


def fitz():
    import warnings
    warnings.filterwarnings("ignore")
    import fitz as f
    return f


_docs = {}
def doc(book):
    if book not in _docs:
        _docs[book] = fitz().open(os.path.join(PDF_ROOT, BOOKS[book][0]))
    return _docs[book]


def jload(p, default=None):
    if not os.path.exists(p): return default
    with open(p, encoding="utf-8") as f: return json.load(f)


def jsave(p, obj, compact=False):
    with open(p, "w", encoding="utf-8", newline="\n") as f:
        if compact:
            f.write("{\n" + ",\n".join(f"{json.dumps(k, ensure_ascii=False)}:{json.dumps(v, ensure_ascii=False)}" for k, v in obj.items()) + "\n}\n")
        else:
            json.dump(obj, f, ensure_ascii=False, indent=1); f.write("\n")


def wsave(p, text):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as f: f.write(text)


# ---------- OCR 文字整理 ----------
_words = None
def words(strict=True):
    """英文字表，用來黏回 OCR 拆開的英文字。strict：網站單字提示詞典＋虛詞；否則再加四本書的語料字表。"""
    global _words
    if _words is None:
        g = jload(os.path.join(ROOT, "data", "glossary", "toeic.json"), {})
        d = {w for w in set(g.get("w", {})) | set(g.get("f", {})) if len(w) >= 3 or w in FUNC_SET} | FUNC_SET
        c = set()
        if os.path.exists(CORPUS):
            with open(CORPUS, encoding="utf-8") as f: c = set(f.read().split())
        _words = (d, d | c)
    return _words[0 if strict else 1]


CORPUS = os.path.join(KB, "_words.txt")  # scan 時從四本書收集、完整出現 ≥3 次的英文字


FUNC = """a i an the is am are was were be been being it its in on at to of for from with without within into onto by as or and but nor
so if than then that this these those there their they them he him his she her we our us you your me my mine who whom whose which what
when where why how all any some each every both either neither not no yes do does did done have has had will would shall should can could
may might must about above after again against along among around before behind below beneath beside between beyond during except inside
near off out outside over since through throughout toward towards under until up upon while also just only very too here now ever never
one two three four five six seven eight nine ten other another such same own more most many much few less least go me""".lower()
FUNC_SET = set(FUNC.split())


def is_word(j, strict=True):
    """字表裡有，或去掉 -s/-es/-ed/-ing/-ly/-er 後（含雙子音、y→i、補 e）在字表裡。"""
    W = words(strict)
    j = j.lower()
    if j in W: return True
    for suf in ("ing", "ed", "es", "s", "ly", "er", "est"):
        if j.endswith(suf) and len(j) >= len(suf) + 3:
            st = j[: -len(suf)]
            if {st, st + "e", st[:-1] if len(st) > 2 and st[-1] == st[-2] else "", st[:-1] + "y" if st.endswith("i") else ""} & W: return True
    return False


CJK = r"㐀-鿿豈-﫿　-〿＀-￯"
TOK = re.compile(r"[A-Za-z]+(?:[ \t]+[A-Za-z]+)+")


def glue_words(s):
    """把 'Direc ti ons'、'chatti ng'、'wit h' 這類被拆開的字黏回去：連續 2–5 段相接後是字，且不是每段本來就都是字。"""
    part_ok = lambda p: p.lower() in FUNC_SET if len(p) <= 2 else is_word(p)
    def fix(m):
        parts = m.group(0).split()
        out, i = [], 0
        while i < len(parts):
            done = False
            # 先找詞典裡的字（最長優先），找不到才用語料字表（至少 6 個字母，避免黏成 Itis 之類）
            for strict in (True, False):
                for n in range(min(5, len(parts) - i), 1, -1):
                    seg = parts[i:i + n]
                    j = "".join(seg)
                    if len(j) >= (3 if strict else 6) and is_word(j, strict) and not all(part_ok(p) for p in seg) \
                            and not any(p[0].isupper() for p in seg[1:]):
                        out.append(j); i += n; done = True; break
                if done: break
            if not done: out.append(parts[i]); i += 1
        return " ".join(out)
    return TOK.sub(fix, s)


def clean_line(s):
    s = s.replace("　", " ").strip()
    s = re.sub(r"\((8)\)", "(B)", s)
    s = re.sub(r"\(0\)", "(D)", s)
    s = re.sub(r"\b[\dOo]*\d[\dOo]*\b", lambda m: m.group(0).replace("O", "0").replace("o", "0"), s)
    s = re.sub(r"[ \t]+", " ", s)
    return glue_words(s)


def join_lines(lines):
    out = ""
    for ln in lines:
        ln = clean_line(ln)
        if not ln: continue
        if not out: out = ln; continue
        a, b = out[-1], ln[0]
        cj = re.match(f"[{CJK}]", a) or re.match(f"[{CJK}]", b)
        out += ("" if cj else " ") + ln
    return out


def page_blocks(pg):
    """取文字區塊並依版面排序：整欄寬的區塊當分隔，中間的左欄先、右欄後。"""
    W = pg.rect.width
    mid = W / 2
    bl = []
    for b in pg.get_text("dict")["blocks"]:
        if b.get("type") != 0: continue
        lines = ["".join(s["text"] for s in l["spans"]).strip() for l in b["lines"]]
        lines = [l for l in lines if l]
        if not lines: continue
        x0, y0, x1, y1 = b["bbox"]
        H = pg.rect.height
        if (x0 > W * .9 or x1 < W * .1) and H * .08 < y0 and y1 < H * .9 and len("".join(lines)) <= 12: continue  # 頁緣的 Part 1–4 分頁標籤
        col = "L" if x1 <= mid + W * .04 else "R" if x0 >= mid - W * .04 else "F"
        bl.append([x0, y0, x1, y1, col, lines])
    bl.sort(key=lambda b: (b[1], b[0]))
    out, band = [], []
    def flush():
        band.sort(key=lambda b: (b[4] != "L", b[1], b[0]))
        out.extend(band); band.clear()
    for b in bl:
        if b[4] == "F": flush(); out.append(b)
        else: band.append(b)
    flush()
    return out, pg.rect.height


def _num(t):
    t = t.replace("O", "0").replace("o", "0").replace(" ", "")
    return int(t) if t.isdigit() else None


# 頁碼的樣子：「59」「I 199」（閱讀本：章名 I 頁碼）「150 l 全新…」（閱讀本左頁）
PNUM = [re.compile(r"^[|lI]\s*([\dOo]{1,3})$"), re.compile(r"^([\dOo]{1,3})\s*[|lI]\s"), re.compile(r"^([\dOo]{1,3})$")]


def printed_no(blocks, H):
    """頁底（或頁首）的頁碼 → (頁碼, 區塊序, 行序)。"""
    for pat in PNUM:
        for bi, b in enumerate(blocks):
            if not (b[1] > H * .88 or b[3] < H * .07): continue
            for li, l in enumerate(b[5]):
                m = pat.match(l.strip())
                if m and _num(m.group(1)): return _num(m.group(1)), bi, li
    return None, None, None


def page_text(book, p):
    """回傳 (文字, 書頁碼)；p 是 pdf 頁（1 起）。頁碼那一行不放進文字。"""
    blocks, H = page_blocks(doc(book)[p - 1])
    no, bi, li = printed_no(blocks, H)
    paras = []
    for k, b in enumerate(blocks):
        lines = [l for j, l in enumerate(b[5]) if not (k == bi and j == li)]
        if k == bi and li is not None:
            lines = [re.sub(r"^\d{1,3}\s*[|lI]\s+", "", l) for l in lines]
        t = join_lines(lines)
        if t: paras.append(t)
    return "\n\n".join(paras), no


# ---------- 音檔 ----------
def audio_files():
    out = []
    for r, ds, fs in os.walk(AUDIO):
        ds.sort()
        for f in sorted(fs):
            if f.lower().endswith(".mp3"):
                out.append(os.path.relpath(os.path.join(r, f), AUDIO).replace("\\", "/"))
    return out


def audio_order(f):
    """音檔在書中出現的順序：資料夾 → basic → Course 0 → Course 1… → Part Test。"""
    stem = os.path.splitext(os.path.basename(f))[0]
    m = re.match(r"P\d_(basics?|Course (\d)|Part Test)_?(\d*)", stem)
    if not m: return (os.path.dirname(f), 0, stem)
    rank = 0 if m.group(1).startswith("basic") else 9 if m.group(1) == "Part Test" else 1 + int(m.group(2))
    return (os.path.dirname(f), rank, int(m.group(3) or 0), stem)


def base_audio(files):
    return sorted((f for f in files if "Br. & Au Accent/" not in f), key=audio_order)


def parse_audio(raw, part, stems):
    """OCR 出來的音檔名（常有亂碼、多空格）→ 實際檔名主幹；part＝目前所在 Part（如 '2'）。"""
    s = re.sub(r"\s+", "", raw)
    s = s.replace("一", "_").replace("卫", "_1").replace("辶", "1_").replace(".", "_")
    s = re.sub(r"(?<=[\d_])[Oo]|[Oo](?=[\d_])", "0", s)
    m = re.search(r"P(\d)[_.]", s)
    p = m.group(1) if m else part
    cand = None
    if m2 := re.search(r"(\d{1,2})_?voc", s): cand = f"{int(m2.group(1)):02d}_voc"
    elif m2 := re.search(r"agnostic(_Part\d)?", s): cand = "Diagnostic" + (m2.group(1) or "")
    elif m2 := re.search(r"ActualTest(\d)(_Part\d)?", s): cand = f"Actual Test {m2.group(1)}" + (m2.group(2) or "")
    elif m2 := re.search(r"Pronunciation_?(\d{1,2})", s, re.I): cand = f"Pronunciation_{int(m2.group(1)):02d}"
    elif p and re.search(r"Course0_?Type", s, re.I): cand = f"P{p}_Course 0_Type Analysis"
    elif p and (m2 := re.search(r"Course(\d)_(\d{1,2})", s)): cand = f"P{p}_Course {m2.group(1)}_{int(m2.group(2)):02d}"
    elif p and (m2 := re.search(r"basics?_?(\d{1,2})", s)): cand = f"P{p}_{'basic' if p == '1' else 'basics'}_{int(m2.group(1)):02d}"
    elif p and re.search(r"PartTest", s): cand = f"P{p}_Part Test"
    return stems.get(cand) if cand else None


MP3 = re.compile(r"([A-Za-z0-9_ .&\-㐀-鿿]{3,40}?)\s*\.\s*m\s*p\s*3", re.I)
ANS = re.compile(r"(?:解答本|正確答案)\s*[Pp]\s*[.．。,]?\s*([\dOo]{1,3})")


# ---------- scan ----------
def build_corpus():
    """四本書 OCR 裡完整出現 ≥3 次的英文字（小寫、≥2 字母），補網站詞典沒收的字。"""
    global _words
    cnt = collections.Counter()
    for book in BOOKS:
        for pg in doc(book):
            cnt.update(w.lower() for w in re.findall(r"(?<![A-Za-z])[A-Za-z]{2,}(?![A-Za-z])", pg.get_text()))
    keep = sorted(w for w, c in cnt.items() if c >= 3)
    os.makedirs(KB, exist_ok=True)
    wsave(CORPUS, "\n".join(keep) + "\n")
    _words = None
    print("英文字表", len(keep), "字")


def cmd_scan(args):
    build_corpus()
    files = audio_files()
    pages = {}
    for book in BOOKS:
        d = doc(book)
        rows = []
        for i in range(d.page_count):
            txt, no = page_text(book, i + 1)
            row = {"no": no, "n": len(txt)}
            if book in ("LB", "RB"):
                aud = [m.group(1).strip() for m in MP3.finditer(txt)]
                if aud: row["ocr_mp3"] = aud
                ans = [_num(a) for a in ANS.findall(txt)]
                if ans: row["ans"] = ans
            row["head"] = next((l for l in txt.split("\n") if len(l.strip()) > 3), "")[:30]
            rows.append(row)
        # 書頁碼：附近 ±6 頁的 offset 多數決，補沒抓到的、修正離群值
        offs = collections.Counter(i + 1 - r["no"] for i, r in enumerate(rows) if r["no"])
        ok = {o for o, c in offs.items() if c >= 5}  # 只信出現夠多次的 offset，章節標籤等誤判的數字不算
        runs = [(i, i + 1 - r["no"]) for i, r in enumerate(rows) if r["no"] is not None and i + 1 - r["no"] in ok]
        for i, r in enumerate(rows):
            near = [o for j, o in runs if abs(j - i) <= 6]
            o = collections.Counter(near).most_common(1)[0][0] if near else offs.most_common(1)[0][0]
            r["ocr_no"] = r["no"]
            r["no"] = i + 1 - o if i + 1 - o > 0 else None
        # 重複掃描的頁（同一書頁出現兩次）→ 標 dup，內容以第一次為準
        seen = {}
        for i, r in enumerate(rows):
            if r["no"] is None: continue
            if r["no"] in seen: r["dup"] = seen[r["no"]]
            else: seen[r["no"]] = i + 1
        nos = sorted(seen)
        gaps = [n for n in range(nos[0], nos[-1] + 1) if n not in seen] if nos else []
        pages[book] = rows
        print(f"{book} {d.page_count} 頁；書頁 {nos[0] if nos else '?'}–{nos[-1] if nos else '?'}；offset {offs.most_common(3)}；"
              f"重複 {sum(1 for r in rows if 'dup' in r)} 頁；缺頁 {gaps[:20]}")
    # 音檔（只有聽力題本的音檔在資料夾裡）：先逐一解析，再用「書中順序」補解析不出的
    base = base_audio(files)
    stems = {os.path.splitext(os.path.basename(f))[0]: f for f in base}
    pos = {f: k for k, f in enumerate(base)}
    refs, part = [], None
    for i, r in enumerate(pages["LB"]):
        if "dup" in r: continue
        for raw in r.get("ocr_mp3", []):
            m = re.search(r"P\s*(\d)\s*[_.]", raw)
            if m: part = m.group(1)
            f = parse_audio(raw, part, stems)
            if f and (m := re.match(r".*/P(\d)_", f)): part = m.group(1)
            refs.append([i, raw, f])
    fixed = 0
    for k, ref in enumerate(refs):
        prev = next((pos[x[2]] for x in reversed(refs[:k]) if x[2]), -1)
        nxt = next((pos[x[2]] for x in refs[k + 1:] if x[2]), len(base))
        if ref[2] and prev < pos[ref[2]] < nxt: continue
        if nxt - prev == 2: ref[2] = base[prev + 1]; fixed += 1
        elif ref[2] and pos[ref[2]] <= prev: pass  # 同一音檔在後面頁再出現（如 Part Test 跨頁），保留
        else: ref[2] = ref[2] if ref[2] and prev < pos[ref[2]] else None
    unresolved = []
    for i, raw, f in refs:
        if f: pages["LB"][i].setdefault("mp3", []).append(f)
        else: unresolved.append((i + 1, raw))
    missing = [f for f in base if not any(f in r.get("mp3", []) for r in pages["LB"])]
    with open(PAGES, "w", encoding="utf-8", newline="\n") as f:
        f.write("{\n" + ",\n".join(json.dumps(b, ensure_ascii=False) + ":[\n" + ",\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n]"
                                   for b, rows in pages.items()) + "\n}\n")
    print(f"音檔：參照 {len(refs)} 處，依順序補正 {fixed}，對不到 {len(unresolved)}；題本沒標到的音檔 {len(missing)} 個")
    for u in unresolved: print("   對不到", u)
    for f in missing: print("   沒標到", f)


# ---------- sections / build ----------
QBOOK = ("LB", "RB")              # 題本：依 sections.json 分章
ABOOK = {"LB": "LA", "RB": "RA"}  # 解答本：不分章，每 CHUNK 頁一份 raw


def load_sections():
    s = jload(SECTIONS)
    if not s: sys.exit("找不到 kb/sections.json")
    return s


def pdf_of(pages, book, printed):
    for i, r in enumerate(pages[book]):
        if r["no"] == printed and "dup" not in r: return i + 1
    return None


def resolve(sections, pages):
    """把 sections.json 的書頁起點換成 pdf 頁範圍（a–b）；每本書內依序相接。"""
    out = []
    for book in QBOOK:
        secs = [s for s in sections["sections"] if s["book"] == book]
        for k, s in enumerate(secs):
            a = s.get("pdf") or pdf_of(pages, book, s["start"])
            if a is None: sys.exit(f"{s['id']}：找不到書頁 {s['start']}")
            nx = secs[k + 1] if k + 1 < len(secs) else None
            b = (nx.get("pdf") or pdf_of(pages, book, nx["start"])) - 1 if nx else len(pages[book])
            out.append(dict(s, a=a, b=b))
    return out


def printed_range(pages, book, a, b):
    nos = [pages[book][p - 1]["no"] for p in range(a, b + 1) if pages[book][p - 1]["no"] and "dup" not in pages[book][p - 1]]
    return (min(nos), max(nos)) if nos else (None, None)


def answer_chunks(pages, book):
    """解答本 raw 檔切法：[(檔名, pdf 起, pdf 迄, 書頁起, 書頁迄)]。"""
    n = len(pages[book])
    out = []
    for a in range(1, n + 1, CHUNK):
        b = min(n, a + CHUNK - 1)
        lo, hi = printed_range(pages, book, a, b)
        out.append((f"raw/{book}/{book}_{lo or 0:03d}-{hi or 0:03d}.md", a, b, lo, hi))
    return out


def chunks_for(pages, book, lo, hi):
    return [c for c in answer_chunks(pages, book) if c[3] is not None and c[3] <= hi and c[4] >= lo]


def sec_audio(sec, pages, extra=None):
    got = []
    for p in range(sec["a"], sec["b"] + 1):
        for f in pages[sec["book"]][p - 1].get("mp3", []):
            if f not in got: got.append(f)
    for f in sec.get("audio", []) + (extra or {}).get(sec["id"], []):
        if f not in got: got.append(f)
    return got


def auto_audio(secs, pages, files):
    """題本頁首與 sections.json 都沒標到的音檔 → 放進書中順序前一個音檔所在的章節。"""
    base = base_audio(files)
    where = {}
    for s in secs:
        for f in sec_audio(s, pages): where.setdefault(f, s["id"])
    extra = collections.defaultdict(list)
    for k, f in enumerate(base):
        if f in where: continue
        prev = next((base[j] for j in range(k - 1, -1, -1) if base[j] in where and os.path.dirname(base[j]) == os.path.dirname(f)), None)
        if prev: extra[where[prev]].append(f); where[f] = where[prev]
    return extra


def accent_versions(f, files):
    """09. Part Practice_Br. & Au Accent 裡同一段內容的英澳口音版本。"""
    stem = os.path.splitext(os.path.basename(f))[0]
    return [x for x in files if "Br. & Au Accent/" in x and os.path.basename(x).startswith(stem + "_Br")]


def raw_name(sec, k=None):
    return f"raw/{sec['book']}/{sec['id']}" + (f"_{k}" if k else "") + ".md"


def raw_parts(sec, pages):
    rng = [p for p in range(sec["a"], sec["b"] + 1)]
    return [rng[i:i + CHUNK] for i in range(0, len(rng), CHUNK)] or [[]]


def proof_path(sec):
    return f"{sec['book'][0]}/{sec['id']}.md"


def proof_state(sec):
    p = os.path.join(KB, proof_path(sec))
    if not os.path.exists(p): return "未校對"
    with open(p, encoding="utf-8") as f: head = f.read(800)
    m = re.search(r"^status:\s*(\S+)", head, re.M)
    return {"done": "已校對", "partial": "校對中"}.get(m.group(1) if m else "", "校對中")


def page_md(book, p, pages):
    r = pages[book][p - 1]
    mp = r.get("mp3", [])
    head = [f"<!-- page {book} pdf={p} 書頁={r['no']}" + (f" mp3={'|'.join(mp)}" if mp else "") + " -->", f"## 書頁 {r['no']}（pdf {p}）", ""]
    if "dup" in r: return head + [f"（重複掃描，內容同 pdf {r['dup']}，略過）", ""]
    txt, _ = page_text(book, p)
    return head + [txt.strip() or "（本頁沒有可辨識的文字，多半是全圖頁，請看圖）", ""]


def ans_note(s, pages):
    if not s.get("ans"): return ""
    ab = ABOOK[s["book"]]
    lo, hi = s["ans"]
    cs = chunks_for(pages, ab, lo, hi)
    return f"{BOOKS[ab][1]}書頁 {lo}–{hi}" + ("（推估）" if s.get("ans_guess") else "") + "：" + "、".join(f"`{c[0]}`" for c in cs)


def cmd_build(args):
    pages = jload(PAGES) or sys.exit("先跑 scan")
    secs = resolve(load_sections(), pages)
    files = audio_files()
    extra = auto_audio(secs, pages, files)
    only = set(args)
    for s in secs:
        if only and s["id"] not in only: continue
        parts = raw_parts(s, pages)
        aud = sec_audio(s, pages, extra)
        for k, ps in enumerate(parts, 1):
            L = [f"# {s['title']}（OCR 原稿{f' {k}/{len(parts)}' if len(parts) > 1 else ''}）", "",
                 f"> 自動擷取的 OCR 文字，**未校對**：中文有形近錯字、英文可能斷字、雙欄順序可能錯、圖片內容沒有文字。看原圖：`py tools/redblue_kb.py render {s['book']} {ps[0]}-{ps[-1]}`",
                 f"> 書：{BOOKS[s['book']][1]}｜id：`{s['id']}`｜類型：{s['kind']}｜校對稿：`{proof_path(s)}`（{proof_state(s)}）"]
            if aud: L.append("> 音檔：" + "、".join(f"`{a}`" for a in aud))
            if s.get("ans"): L.append("> 解答：" + ans_note(s, pages))
            L.append("")
            for p in ps: L += page_md(s["book"], p, pages)
            wsave(os.path.join(KB, raw_name(s, k if len(parts) > 1 else None)), "\n".join(L))
    if not only:
        for qb, ab in ABOOK.items():
            owners = [s for s in secs if s["book"] == qb and s.get("ans")]
            for name, a, b, lo, hi in answer_chunks(pages, ab):
                who = [s for s in owners if s["ans"][0] <= (hi or 0) and s["ans"][1] >= (lo or 0)]
                L = [f"# {BOOKS[ab][1]} 書頁 {lo}–{hi}（OCR 原稿）", "",
                     f"> 自動擷取的 OCR 文字，**未校對**（雙欄頁的左右欄順序已盡量排好）。看原圖：`py tools/redblue_kb.py render {ab} {a}-{b}`",
                     "> 這幾頁是下列題本章節的解答：" + ("、".join(f"`{s['id']}` {s['title']}" for s in who) or "（前頁或未對應）"), ""]
                for p in range(a, b + 1): L += page_md(ab, p, pages)
                wsave(os.path.join(KB, name), "\n".join(L))
    write_index(secs, pages, files, extra)
    print("完成：", len(secs), "個章節")


def write_index(secs, pages, files, extra):
    L = ["# 紅藍本知識庫目錄", "",
         "> 由 `py tools/redblue_kb.py build` 產生，不要手改；要改章節切分請改 `sections.json`。", "",
         "書頁＝書上印的頁碼；pdf＝PDF 檔頁數。raw＝OCR 原稿（未校對）；校對稿＝對照原圖校正、題目與解答合併後的版本（`L/`、`R/`）。", ""]
    for book in QBOOK:
        L += [f"## {BOOKS[book][1]}（{book}）", "", "| id | 章節 | 類型 | 書頁 | pdf | 音檔 | 解答本書頁 | raw | 校對稿 |", "|---|---|---|---|---|---|---|---|---|"]
        for s in [x for x in secs if x["book"] == book]:
            parts = raw_parts(s, pages)
            raws = " ".join(f"[{k}]({raw_name(s, k if len(parts) > 1 else None)})" for k in range(1, len(parts) + 1))
            aud = sec_audio(s, pages, extra)
            lo, hi = printed_range(pages, book, s["a"], s["b"])
            ans = (f"{s['ans'][0]}–{s['ans'][1]}" + ("?" if s.get("ans_guess") else "")) if s.get("ans") else ""
            pf = f"[{proof_state(s)}]({proof_path(s)})" if proof_state(s) != "未校對" else "未校對"
            L.append(f"| `{s['id']}` | {s['title']} | {s['kind']} | {lo}–{hi} | {s['a']}–{s['b']} | {len(aud) or ''} | {ans} | {raws} | {pf} |")
        ab = ABOOK[book]
        L += ["", f"### {BOOKS[ab][1]}（{ab}）raw", "", " ".join(f"[{c[3]}–{c[4]}]({c[0]})" for c in answer_chunks(pages, ab)), ""]
    L += ["類型：intro 前言／lesson 教學＋練習／test 整回測驗／vocab 單字。解答本書頁後面有「?」的是頁底沒印參照、由前後章推估的範圍。", ""]
    wsave(os.path.join(KB, "index.md"), "\n".join(L))
    # 音檔對照
    used = collections.defaultdict(list)
    for s in secs:
        for f in sec_audio(s, pages, extra):
            pp = [p for p in range(s["a"], s["b"] + 1) if f in pages[s["book"]][p - 1].get("mp3", [])]
            used[f].append((s, pp))
    A = ["# 聽力音檔對照表", "",
         "> 由 `py tools/redblue_kb.py build` 產生，不要手改。音檔路徑相對於 `private/TOEIC/TOEIC紅藍本/聽力/`。",
         "> 書頁＝頁首印著這個檔名的題本頁；「—」表示頁首沒印（Hackers Test、Part Test、分 Part 檔），由 sections.json 指定或依書中順序歸到前一個音檔的章節。", "",
         "| 音檔 | 題本章節 | 書頁 | 解答本書頁 | 英澳口音版（09. Part Practice） |", "|---|---|---|---|---|"]
    for f in base_audio(files):
        acc = "、".join(f"`{os.path.basename(x)}`" for x in accent_versions(f, files))
        rows = used.get(f)
        if not rows: A.append(f"| `{f}` | （未對應） |  |  | {acc} |"); continue
        for s, pp in rows:
            pg = ",".join(str(pages[s["book"]][p - 1]["no"]) for p in pp) or "—"
            ans = f"{s['ans'][0]}–{s['ans'][1]}" if s.get("ans") else ""
            A.append(f"| `{f}` | `{s['id']}` {s['title']} | {pg} | {ans} | {acc} |")
    A += ["", "## 說明", "",
          "- 整卷音檔（`Diagnostic.mp3`、`Actual Test 1.mp3`、`Actual Test 2.mp3`）＝同資料夾 Part1–4 分檔接起來。",
          "- `10. Vocabulary/NN_voc.mp3` 對應題本書末「聽力必考單字」DAY NN；`08. Am. & Br. Accent/` 對應「美式發音與英式發音」。",
          "- 閱讀題本不建音檔連結。`互動式聽力答題訓練光碟.exe` 是書附光碟程式，不要執行。", ""]
    wsave(os.path.join(KB, "audio.md"), "\n".join(A))
    st = collections.Counter(proof_state(s) for s in secs)
    P = ["# 校對進度", "", "> 由 `py tools/redblue_kb.py build`／`status` 產生，不要手改；狀態取自各校對稿開頭的 `status:`。", "",
         f"共 {len(secs)} 章：" + "、".join(f"{k} {v}" for k, v in st.items()), "",
         "| id | 書 | 章節 | 類型 | pdf 頁數 | 狀態 |", "|---|---|---|---|---|---|"]
    for s in secs:
        P.append(f"| `{s['id']}` | {s['book']} | {s['title']} | {s['kind']} | {s['b'] - s['a'] + 1} | {proof_state(s)} |")
    wsave(os.path.join(KB, "progress.md"), "\n".join(P) + "\n")


def parse_pages(book, args, printed):
    pages = jload(PAGES) if printed else None
    out = []
    for a in args:
        x, _, y = a.partition("-")
        for p in range(int(x), int(y or x) + 1):
            if printed:
                q = pdf_of(pages, book, p)
                if q is None: sys.exit(f"{book} 找不到書頁 {p}")
                out.append(q)
            else: out.append(p)
    return out


def cmd_render(args):
    printed = "--printed" in args
    args = [a for a in args if a != "--printed"]
    dpi = 110
    if "--dpi" in args:
        i = args.index("--dpi"); dpi = int(args[i + 1]); del args[i:i + 2]
    book, ps = args[0].upper(), parse_pages(args[0].upper(), args[1:], printed)
    os.makedirs(os.path.join(KB, "_img"), exist_ok=True)
    for p in ps:
        out = os.path.join(KB, "_img", f"{book}_p{p:03d}.png")
        doc(book)[p - 1].get_pixmap(dpi=dpi).save(out)
        print(out)


def cmd_page(args):
    printed = "--printed" in args
    args = [a for a in args if a != "--printed"]
    book = args[0].upper()
    for p in parse_pages(book, args[1:], printed):
        txt, no = page_text(book, p)
        print(f"===== {book} pdf {p}（書頁 {no}）\n{txt}\n")


def cmd_status(args):
    pages = jload(PAGES) or sys.exit("先跑 scan")
    secs = resolve(load_sections(), pages)
    files = audio_files()
    write_index(secs, pages, files, auto_audio(secs, pages, files))
    st = collections.Counter((s["book"], proof_state(s)) for s in secs)
    for book in QBOOK:
        print(book, BOOKS[book][1], {k[1]: v for k, v in st.items() if k[0] == book})


Q_HEAD = re.compile(r"^### ([A-Z]{1,4}\d{1,3})\s*$", re.M)  # 題目標題：### EX1、### HP3、### T12、### Q101
FIELDS = ("音檔", "圖片", "文章", "題目", "原文", "答案", "翻譯", "解析", "詞彙")


def check_proof(path, sec, files):
    """校對稿格式檢查，回傳問題清單。"""
    with open(path, encoding="utf-8") as f: t = f.read()
    bad = []
    m = re.match(r"---\n(.*?)\n---\n", t, re.S)
    if not m: return ["開頭沒有 --- front matter ---"]
    fm = m.group(1)
    for k in ("id", "status", "source"):
        if not re.search(rf"^{k}:", fm, re.M): bad.append(f"front matter 缺 {k}")
    if not re.search(rf"^id:\s*{re.escape(sec['id'])}\s*$", fm, re.M): bad.append("front matter id 和檔名不一致")
    if not re.search(r"^status:\s*(done|partial)\s*$", fm, re.M): bad.append("status 只能是 done 或 partial")
    for a in re.findall(r"`([^`]+\.mp3)`", t):
        if a not in files: bad.append(f"音檔不存在：{a}")
    if re.search(r"^\((8|0)\)", t, re.M): bad.append("殘留 OCR 選項錯字 (8)/(0)")
    qs = [(mm.group(1), mm.end()) for mm in Q_HEAD.finditer(t)]
    seen = set()
    for k, (qid, pos) in enumerate(qs):
        if qid in seen: bad.append(f"題號重複：{qid}")
        seen.add(qid)
        body = t[pos: qs[k + 1][1] if k + 1 < len(qs) else len(t)]
        body = re.split(r"^#{1,3} ", body, maxsplit=1, flags=re.M)[0]
        if not re.search(r"^答案：\s*\(?[A-D]\)?\s*$", body, re.M): bad.append(f"{qid} 缺「答案：A–D」")
        if not re.search(r"^\(A\) ", body, re.M) and "原文：" not in body: bad.append(f"{qid} 沒有選項 (A)…")
    return bad


def cmd_check(args):
    pages = jload(PAGES) or sys.exit("先跑 scan")
    secs = resolve(load_sections(), pages)
    files = set(audio_files())
    bad = 0
    ids = collections.Counter(s["id"] for s in secs)
    for k, v in ids.items():
        if v > 1: print("重複 id", k); bad += 1
    for s in secs:
        if s["b"] < s["a"]: print("頁範圍錯誤", s["id"], s["a"], s["b"]); bad += 1
        for f in s.get("audio", []):
            if f not in files: print("sections.json 音檔不存在", s["id"], f); bad += 1
        p = os.path.join(KB, proof_path(s))
        if os.path.exists(p):
            for x in check_proof(p, s, files): print(proof_path(s), x); bad += 1
    print("檢查完畢，問題", bad)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    cmds = {"scan": cmd_scan, "build": cmd_build, "render": cmd_render, "page": cmd_page, "status": cmd_status, "check": cmd_check}
    if len(sys.argv) < 2 or sys.argv[1] not in cmds: sys.exit(__doc__)
    cmds[sys.argv[1]](sys.argv[2:])
