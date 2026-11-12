"""各 10 回聽力（國際學村《最新！新制多益 TOEIC 聽力題庫解析》TEST 01–10）→ private/toeic10_listening.json。

用法：
    py tools/build_toeic10_listening.py            # 全部 10 回
    py tools/build_toeic10_listening.py 3 4        # 只轉指定回次（輸出檔仍只含這幾回，正式產生請不加參數）
    py tools/build_toeic10_listening.py --redo-img # 重新裁切照片與圖表

來源：private/toeic_md/listening/testNN/TESTNN.md（status 為 done／reviewed）
媒體：private/toeic_md/listening/media/（自動產生，不可上傳）
    TESTNN_Q1.jpg …   Part 1 照片、Part 3／4 圖表（從題本 PDF 依題號位置裁切）
    TESTNN.mp3        音檔轉成單聲道 24 kHz 56 kbps（同紅藍本 audio_64k；需要 ffmpeg）
時戳：private/toeic_md/listening/audio_ts.json（py tools/listening_ts.py --book toeic10 產生）
裁切修正：private/toeic_md/listening/crop_fix.json（選用）{"TEST01_Q62.jpg": [頁碼, x0, y0, x1, y1]}，座標是 PDF 點

格式沿用紅藍本聽力模擬考（mock:"listening"）：Part 1–2 每題、Part 3–4 每個題組有逐題播放片段 t。
標籤用 t_p1–t_p4（同紅藍本聽力）；聽力 TEST 01 原書有「考點」，另存成 kp。
網頁上的媒體鍵是 img/t10/… 與 audio/t10/…，由 tools/encrypt_ai.py 加密到 data/media/。

產生後：
    1. 本程式自動用 update_manifest.check_exam 檢查每一題
    2. 請使用者執行 py tools/encrypt_ai.py（需要密碼）
    3. 再跑 py tools/update_manifest.py
"""
import json, pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
SRC = ROOT / "private" / "toeic_md" / "listening"
MEDIA = SRC / "media"
TS_JSON = SRC / "audio_ts.json"
FIX_JSON = SRC / "crop_fix.json"
BOOK = ROOT / "參考書" / "TOEIC" / "聽力閱讀各 10 回" / "聽力"
PDF_Q = BOOK / "最新！新制多益 TOEIC 聽力題庫解析（題本）.pdf"
AUDIO = BOOK / "聽力模擬國際學村"
OUT_JSON = ROOT / "private" / "toeic10_listening.json"
ANS = {"A": 0, "B": 1, "C": 2, "D": 3}
ABOUT = "TOEIC 聽力模擬考（國際學村《最新！新制多益 TOEIC 聽力題庫解析》TEST 01–10）"
P1_Q = "Picture {n}. Select the statement that best describes what is happening in the picture."
ZOOM = 2.6                          # PDF 點 → 像素；照片約 720 px 寬，與紅藍本圖片相近

_LABELS = (r"來源|難易度|口音[^：\n]*|圖片[^：\n]*|原文[^：\n]*|題目|答案|翻譯[^：\n]*|解析[^：\n]*|換句話說[^：\n]*|詞彙[^：\n]*|"
           r"考點|編者註[^：\n]*|原書[^：\n]*|題組說明|題組詞彙[^：\n]*|圖表[^：\n]*|說話者|補充來源核對|地圖[^：\n]*|圖例[^：\n]*|"
           r"中譯[^：\n]*|說明翻譯|例題圖片|目標分數|音檔")
STOP = rf"(?:{_LABELS})"


def clean(t):
    t = re.sub(r"</?u>", "", t)
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", t)
    t = t.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&amp;", "&").replace("&nbsp;", " ")
    t = re.sub(r"<br\s*/?>", "\n", t)
    t = re.sub(r"\\([\\_<>\[\]()#+.!|~`*-])", r"\1", t)
    lines = [l.rstrip() for l in t.split("\n")]
    return "\n".join(l for l in lines if l.strip()).strip()


def label_block(body, label_re):
    """`label：同行文字` 加上到下一個已知標籤之前的所有行；回傳 (同行文字, 後續文字) 或 None。"""
    m = re.search(rf"^(?:{label_re})：[ \t]*(.*)$", body, re.M)
    if not m:
        return None
    rest = body[m.end():]
    n = re.search(rf"^(?:{STOP})：|^!\[", rest, re.M)
    return m.group(1), (rest[: n.start()] if n else rest).strip("\n")


def block_text(body, label_re):
    b = label_block(body, label_re)
    return clean(b[0] + "\n" + b[1]) if b else ""


def quote(body, label_re):
    """引用區塊（> 開頭）→ 每位說話者一行。"""
    b = label_block(body, label_re)
    if not b:
        return ""
    ls = [re.sub(r"^>\s?", "", l) for l in (b[0] + "\n" + b[1]).splitlines()]
    return clean("\n".join(ls))


def notes(body):
    return [clean(m.group(1)) for m in re.finditer(r"^(?:編者註|原書疑點)[^：\n]*：(.*)$", body, re.M)]


def first_page(body):
    m = re.search(r"\(assets/question-(\d+)\.png\)", body)
    return int(m.group(1)) if m else None


def parse_q(n, body, part, kps):
    pre = body.split("\n答案：", 1)[0]
    opts = [clean(m.group(2)) for m in re.finditer(r"^\(([A-D])\)\s*(.*?)\s*$", pre, re.M)]
    a = re.search(r"^答案：\s*\(?([A-D])\)?\s*$", body, re.M)
    if not a:
        sys.exit(f"Q{n}：答案不是單一個 A–D")
    if part == 1:
        q = P1_Q.format(n=n)
    elif part == 2:
        q = clean(label_block(body, "原文[^：\n]*")[0])
    else:
        q = clean(label_block(body, "題目")[0])
    ex = label_block(body, "解析[^：\n]*")
    e_lines, w_lines = [], []
    for l in clean((ex[0] + "\n" + ex[1]) if ex else "").splitlines():
        (w_lines if re.match(r"^\([A-D]\)\s*\[[OX]\]", l) else e_lines).append(l)
    e = "\n".join(e_lines)
    para = block_text(body, "換句話說[^：\n]*")
    if para:
        e += "\n\n換句話說：" + para
    nt = notes(body)
    if nt:
        e += "\n\n編者註：" + "\n編者註：".join(nt)
    item = {"n": n, "part": part, "q": q, "o": opts, "a": ANS[a.group(1)], "g": f"t_p{part}",
            "trans": block_text(body, "翻譯[^：\n]*"), "e": e.strip() or "請見下方各選項解析。"}
    if w_lines:
        item["w"] = "\n".join(w_lines)
    kp = block_text(body, "考點").rstrip("。")
    if kp:
        item["kp"] = kp
        kps.append(kp)
    voc = block_text(body, "詞彙[^：\n]*")
    if voc and not voc.startswith("原書此題未另列"):
        item["voc"] = voc.replace("\n", "；")
    acc = block_text(body, "口音[^：\n]*").rstrip("。")
    if acc:
        item["accent"] = acc
    if part == 1:
        d = block_text(body, "圖片[^：\n]*")
        if d:
            item["imgDesc"] = d
    return item


def parse_set(body):
    refer = block_text(body, "題組說明").replace("-", "–")
    s = {"refer": refer, "script": quote(body, "原文[^：\n]*"), "trans": quote(body, "翻譯[^：\n]*")}
    acc = block_text(body, "口音[^：\n]*").rstrip("。")
    if acc:
        s["accent"] = acc
    voc = block_text(body, "題組詞彙[^：\n]*")
    if voc:
        s["voc"] = voc.replace("\n", "；")
    return s


def build(nn, kps, crops):
    path = SRC / f"test{nn:02d}" / f"TEST{nn:02d}.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    st = re.search(r"^status:\s*(\S+)", text, re.M)
    if not st or st.group(1) not in ("done", "reviewed"):
        print(f"略過 TEST{nn:02d}：status 不是 done／reviewed")
        return None
    tag = f"TEST{nn:02d}"
    parts = re.split(r"^(#{2,4} .*)$", text, flags=re.M)
    qs, sets, cur = [], [], None
    for h, body in zip(parts[1::2], parts[2::2]):
        mq = re.match(r"### Q(\d+)\s*$", h)
        if h.startswith("#### 題組"):
            s = parse_set(body)
            s["_n0"] = int(re.search(r"Q(\d+)", h).group(1))
            s["_notes"] = notes(body)
            if "![" in body:
                s["img"] = f"t10/{tag}_Q{s['_n0']}.jpg"
                crops.append((nn, "g", s["_n0"], first_page(body[body.index("!["):])))
            sets.append(s)
            cur = len(sets) - 1
            continue
        if not mq:
            continue
        n = int(mq.group(1))
        part = 1 if n <= 6 else 2 if n <= 31 else 3 if n <= 70 else 4
        q = parse_q(n, body, part, kps)
        if part == 1:
            q["img"] = f"t10/{tag}_Q{n}.jpg"
            pg = first_page(body[body.index("![") :]) if "![" in body else first_page(body)
            crops.append((nn, "p", n, pg))
        if part >= 3:
            q["s"] = cur
        qs.append(q)
    # 題組層級的編者註放進題組第一題的詳解（原文與翻譯要逐行對照，不能夾註記）
    for i, S in enumerate(sets):
        nt = S.pop("_notes")
        first = next(q for q in qs if q.get("s") == i)
        if first["n"] != S.pop("_n0"):
            sys.exit(f"{tag}：題組 {i} 的第一題對不上")
        if nt:
            first["e"] += "\n\n編者註（題組）：" + "\n編者註（題組）：".join(nt)
    if [q["n"] for q in qs] != list(range(1, 101)):
        sys.exit(f"{tag}：題號不是 1–100 連續（共 {len(qs)} 題）")
    return {"id": f"t10l_{nn:02d}", "title": f"聽力 TEST {nn:02d}（國際學村）", "kind": "toeic", "listen": 1, "part": 0,
            "mock": "listening", "audio": f"t10/{tag}.mp3", "sets": sets, "qs": qs}


def validate(exams):
    import update_manifest as um
    tags = json.loads((ROOT / "data" / "tags.json").read_text(encoding="utf-8")).get("tags", {})
    err, note = [], []
    for ex in exams:
        um.check_exam(ex, f"private/{OUT_JSON.name}", tags, err, note)
        for q in ex["qs"]:
            want = 3 if q["part"] == 2 else 4
            if len(q["o"]) != want:
                err.append(f"{ex['id']} Q{q['n']}：選項 {len(q['o'])} 個（應為 {want}）")
            if not q["trans"] or not q["q"]:
                err.append(f"{ex['id']} Q{q['n']}：缺題目或翻譯")
        for s in ex["sets"]:
            if not s["script"] or not s["trans"] or not s["refer"]:
                err.append(f"{ex['id']} {s.get('refer')}：題組缺原文、翻譯或說明")
            elif len(s["script"].splitlines()) != len(s["trans"].splitlines()):
                note.append(f"{ex['id']} {s['refer'][:20]}：原文 {len(s['script'].splitlines())} 行、翻譯 {len(s['trans'].splitlines())} 行（不逐句對照）")
    return err, note


# ---------- 媒體 ----------

def _ink(img, thr=225):
    import numpy as np
    return np.asarray(img.convert("L")) < thr


def crop_photo(doc, page, order, count):
    """照片頁一頁一或兩張；依題號先後取由上而下第 order 張。"""
    from PIL import Image
    import numpy as np
    pg = doc[page - 1]
    pix = pg.get_pixmap(matrix=__import__("fitz").Matrix(ZOOM, ZOOM))
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    W, H = img.size
    # 照片上緣和左側題號「1.」的上緣對齊（題號不在 PDF 文字層，用像素找）；天空等偏白的部分偵測不到，所以不靠照片本身找上緣
    lab = _ink(img, 200)[:, int(W * .12): int(W * .26)].mean(axis=1) > 0
    labels, s = [], None
    for y, v in enumerate(list(lab) + [False]):
        if v and s is None:
            s = y
        elif not v and s is not None:
            if 10 <= y - s <= 40 and y < H * .9:
                labels.append(s)
            s = None
    if len(labels) != count:
        raise RuntimeError(f"PDF {page}：找到 {len(labels)} 個題號（預期 {count}）")
    ink = _ink(img, 250)              # 頁面底色是純白；照片偏亮的部分也要算進去
    xa, xb = int(W * .22), int(W * .925)   # 避開左側題號／掃描陰影與右側 LISTENING 書籤
    top = labels[order] - 3
    limit = labels[order + 1] - 10 if order + 1 < count else int(H * .9)
    ys = np.nonzero(ink[top:limit, xa:xb].mean(axis=1) > .02)[0]
    bottom = top + int(ys[-1]) + 1
    xs = np.nonzero(ink[top:bottom, xa:xb].mean(axis=0) > .3)[0] + xa
    return img.crop((int(xs[0]), top, int(xs[-1]) + 1, bottom))


def crop_graphic(doc, page, n0):
    """圖表在題組第一題「N.」的正上方、同一欄；往上到前一題的選項（或頁首）為止。"""
    import fitz
    from PIL import Image
    import numpy as np
    pg = doc[page - 1]
    W = pg.rect.width
    words = pg.get_text("words")
    hits = [w for w in words if re.fullmatch(rf"{n0}\.?", w[4]) and (w[0] < W * .2 or W * .5 < w[0] < W * .62)]
    if not hits:
        raise RuntimeError(f"PDF {page}：找不到題號 {n0}.")
    hx0, hy0 = hits[0][0], hits[0][1]
    cx0, cx1 = (0, W * .5) if hx0 < W * .5 else (W * .5, W * .925)
    above = [w for w in words if cx0 <= w[0] < cx1 and w[3] < hy0 - 2 and
             (re.fullmatch(r"\(?[A-D]\)", w[4]) or re.fullmatch(r"\d{2,3}\.", w[4])) and w[0] < cx0 + W * .16]
    top = max([w[3] for w in above], default=0) + 2
    clip = fitz.Rect(cx0, top, cx1, hy0 - 2)
    pix = pg.get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), clip=clip)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    ink = _ink(img, 200)
    rows = ink.mean(axis=1)
    # 去掉題組之間的分隔線（細橫線）與零星雜點：以 8px 以上的空白切塊，只留高度 > 12px 的塊
    blocks, s, gap = [], None, 0
    for y, v in enumerate(list(rows > .004) + [False] * 9):
        if v:
            if s is None:
                s = y
            gap = 0
        elif s is not None:
            gap += 1
            if gap >= 8:
                if y - gap - s > 12:
                    blocks.append((s, y - gap + 1))
                s, gap = None, 0
    if not blocks:
        raise RuntimeError(f"PDF {page}：題號 {n0} 上方沒有圖表")
    y0, y1 = blocks[0][0], blocks[-1][1]
    xs = np.nonzero(ink[y0:y1].mean(axis=0) > .002)[0]
    pad = 6
    return img.crop((max(0, int(xs[0]) - pad), max(0, y0 - pad), min(img.width, int(xs[-1]) + pad), min(img.height, y1 + pad)))


def make_images(crops, redo):
    import fitz
    MEDIA.mkdir(parents=True, exist_ok=True)
    fixes = json.loads(FIX_JSON.read_text(encoding="utf-8")) if FIX_JSON.exists() else {}
    todo = [c for c in crops if redo or not (MEDIA / f"TEST{c[0]:02d}_Q{c[2]}.jpg").exists()]
    if not todo:
        return []
    doc = fitz.open(str(PDF_Q))
    fails = []
    for nn, kind, n, page in todo:
        name = f"TEST{nn:02d}_Q{n}.jpg"
        try:
            if name in fixes:
                from PIL import Image
                p, *box = fixes[name]
                pix = doc[p - 1].get_pixmap(matrix=fitz.Matrix(ZOOM, ZOOM), clip=fitz.Rect(*box))
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            elif kind == "p":
                same = sorted(c[2] for c in crops if c[0] == nn and c[1] == "p" and c[3] == page)
                img = crop_photo(doc, page, same.index(n), len(same))
            else:
                img = crop_graphic(doc, page, n)
            img.save(MEDIA / name, quality=82, optimize=True)
        except Exception as e:
            fails.append(f"{name}（PDF {page}）：{e}")
    return fails


def make_audio(nums):
    MEDIA.mkdir(parents=True, exist_ok=True)
    for nn in nums:
        out = MEDIA / f"TEST{nn:02d}.mp3"
        if out.exists():
            continue
        src = AUDIO / f"TEST{nn:02d}.mp3"
        print(f"轉檔 {src.name} → {out.relative_to(ROOT)}", flush=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-ac", "1", "-ar", "24000", "-b:a", "56k", str(out)], check=True)


def add_clips(exams):
    from build_listening_quiz import clip_ranges
    if not TS_JSON.exists():
        print("找不到 audio_ts.json，沒有加入逐題片段（先執行 py tools/listening_ts.py --book toeic10）")
        return
    ts = json.loads(TS_JSON.read_text(encoding="utf-8"))
    for ex in exams:
        key = ex["audio"].split("/")[-1]
        if key not in ts:
            print(f"注意：{ex['id']} 沒有時戳")
            continue
        rng = clip_ranges(ts[key])
        for q in ex["qs"]:
            if q["part"] <= 2:
                q["t"] = rng[("q", q["n"])]
        for s in ex["sets"]:
            n0 = next(q["n"] for q in ex["qs"] if q.get("s") == ex["sets"].index(s))
            s["t"] = rng[("s", n0)]


def write(exams):
    lines = ["{", f' "about":{json.dumps(ABOUT, ensure_ascii=False)},', ' "exams":[']
    out = []
    for ex in exams:
        head = {k: v for k, v in ex.items() if k not in ("sets", "qs")}
        s = "  " + json.dumps(head, ensure_ascii=False, separators=(",", ":"))[:-1]
        s += ',"sets":[\n' + ",\n".join("   " + json.dumps(x, ensure_ascii=False, separators=(",", ":")) for x in ex["sets"]) + "\n  ]"
        s += ',"qs":[\n' + ",\n".join("   " + json.dumps(q, ensure_ascii=False, separators=(",", ":")) for q in ex["qs"]) + "\n  ]}"
        out.append(s)
    lines.append(",\n".join(out))
    lines += [" ]", "}"]
    OUT_JSON.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    nums = [int(x) for x in sys.argv[1:] if x.isdigit()] or list(range(1, 11))
    kps, crops = [], []
    exams = [x for x in (build(n, kps, crops) for n in nums) if x]
    fails = make_images(crops, "--redo-img" in sys.argv)
    make_audio([int(ex["id"][-2:]) for ex in exams])
    add_clips(exams)
    missing = [f"{c[0]:02d}_Q{c[2]}" for c in crops if not (MEDIA / f"TEST{c[0]:02d}_Q{c[2]}.jpg").exists()]
    err, note = validate(exams)
    write(exams)
    for ex in exams:
        print(f"{ex['id']}：{len(ex['qs'])} 題、{len(ex['sets'])} 個題組、圖表 {sum(1 for s in ex['sets'] if s.get('img'))} 張")
    for f in fails:
        print("裁切失敗：", f)
    if missing:
        print("缺圖：", "、".join(missing))
    for n in note:
        print("提醒：", n)
    if err:
        print("\n檢查失敗：")
        for e in err[:30]:
            print("  ✗", e)
        sys.exit(1)
    print(f"\n已寫入 {OUT_JSON.relative_to(ROOT)}（update_manifest 逐題檢查通過）")


if __name__ == "__main__":
    main()
