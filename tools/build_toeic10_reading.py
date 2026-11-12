"""從 private/toeic_md/reading/testNN/TESTNN.md（各 10 回閱讀轉檔）產生 private/toeic10_reading.json。

用法：
    py tools/build_toeic10_reading.py            # 全部 10 回
    py tools/build_toeic10_reading.py 1 2        # 只做指定回次（輸出檔仍會包含這幾回）

只收 frontmatter status 為 done／reviewed 的回次。產生後：
    1. 本程式自動用 update_manifest.check_exam 檢查每一題（欄位、答案索引、標籤）
    2. 請使用者執行 py tools/encrypt_ai.py（需要密碼；SOURCES 已含 toeic10_reading.json，會自動在 manifest 加一行）
    3. 再跑 py tools/update_manifest.py
明文只放 private/，不可上傳。

資料對應（沿用 build_reading_mock.py 的格式，網頁的「閱讀整份模擬考」直接可用）：
  每回一份試卷（mock:"reading"），Part 5 題目沒有 p；Part 6／7 題目以 p 指向 passages。
  Part 6 的空格 -------〈Q131〉 轉成 {{131}}；題目欄 q 留空（空格在文章裡）。
  多篇文章：P.docs＝[{kind,text}…]，翻譯用 --- 分隔。<u>、&emsp;、<br> 轉成純文字，**粗體**、*斜體*、| 表格 | 保留（網頁會渲染）。
  標籤 g：這套書沒有「考點：」欄，改由解析開頭的題型（〔…〕或第一句，例如「推論 細節資訊」）對應 data/tags.json 的標籤，
  同時存成 kp。
  原書看不清楚、被標【待核】的詞彙條目整條不收（會印出清單）。
"""
import json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
SRC = ROOT / "private" / "toeic_md" / "reading"
OUT_JSON = ROOT / "private" / "toeic10_reading.json"
ANS = {"A": 0, "B": 1, "C": 2, "D": 3}
ABOUT = "TOEIC 閱讀模擬考（國際學村《最新！新制多益 TOEIC 閱讀題庫解析》TEST 01–10）"
_LABELS = r"來源|難易度|題目|空格位置|答案|翻譯[^：\n]*|解析[^：\n]*|詞彙|變換表達方式|題組說明中譯[^：\n]*|題組說明|文章原文|文章中譯[^：\n]*|題組詞彙"
STOP = rf"(?:{_LABELS}|編者註[^：\n]*)"
STOP_ART = rf"(?:{_LABELS})"          # 文章原文／中譯：編者註常夾在兩篇文章之間，不能當結尾


def tag_for(part, kp):
    """題型（解析開頭）→ data/tags.json 的標籤；依序比對，先中先贏。"""
    rules = {
        5: [("主動態", "t_p5voice"), ("相關連接詞", "t_p5corr"), ("對等連接句型", "t_p5corr"), ("名詞子句", "t_p5ncl"),
            ("連接詞", "t_p5conj"), ("不定代名詞", "t_p5indef"), ("代名詞", "t_p5pron"), ("介系詞", "t_p5prep"),
            ("比較級", "t_p5comp"), ("最高級", "t_p5comp"), ("數量", "t_p5qty"), ("慣用", "t_p5chunk"), ("搭配", "t_p5chunk"),
            ("副詞選擇", "t_p5adv"), ("詞彙", "t_p5vocab"), ("類似意義", "t_p5vocab"), ("未來式", "t_p5tense"), ("完成式", "t_p5tense"),
            ("過去式", "t_p5tense"), ("動詞位置", "t_p5fin"), ("助動詞", "t_p5fin")],
        6: [("選出適當的句子", "t_p6sent"), ("連接副詞", "t_p6conn"), ("詞彙", "t_p6word"), ("位置", "t_p6word")],
        7: [("多篇", "t_p7cross"), ("選擇句子位置", "t_p7sent"), ("Not/True", "t_p7not"), ("尋找主題", "t_p7main"), ("主旨", "t_p7main"),
            ("推論", "t_p7infer"), ("同義詞", "t_p7vocab"), ("掌握意圖", "t_p7vocab")],
    }
    for key, tag in rules[part]:
        if key in kp:
            return tag
    return {5: "t_p5pos", 6: "t_p6gram", 7: "t_p7detail"}[part]


def clean(t):
    t = re.sub(r"</?u>", "", t)
    t = t.replace("&emsp;", "　").replace("&ensp;", " ").replace("&nbsp;", " ")
    t = re.sub(r"<br\s*/?>", "\n", t)
    t = t.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&amp;", "&")
    t = t.replace("\\*", "＊")                                    # 文字裡的星號（註記用）；避免被網頁當成斜體符號
    t = re.sub(r"\\([\\_<>\[\]()#+.!|~`-])", r"\1", t)           # 其他 markdown 跳脫字元 \< \> 還原
    return "\n".join(l.rstrip() for l in t.split("\n")).strip()


def quote_text(lines):
    """文章區塊有兩種寫法：每行加「> 」的引用區塊（多數回次），或直接寫（閱讀 TEST 01–04 部分題組）；兩者都收。"""
    out = []
    for l in lines:
        if re.match(r"^編者註[^：\n]*：", l):
            continue                                              # 夾在文章中的編者註另外收（見 parse_group）
        if l.startswith(">"):
            out.append(l[2:] if l.startswith("> ") else l[1:])
        else:
            out.append(l)
    return clean("\n".join(out))


def label_block(body, label_re, stop=STOP):
    """取 `label：`（可接同行文字）到下一個已知標籤之前的所有行。"""
    m = re.search(rf"^({label_re})：[ \t]*(.*)$", body, re.M)
    if not m:
        return None
    rest = body[m.end():]
    n = re.search(rf"^{stop}：", rest, re.M)
    tail = rest[: n.start()] if n else rest
    return m.group(2), tail.strip("\n")


def split_docs(tail):
    """「文章 N（kind）」分段；沒有就是單篇。回傳 [(kind, [引用行])]。"""
    parts = re.split(r"^文章 \d+（([^）\n]*)）\s*$", tail, flags=re.M)
    if len(parts) == 1:
        return [("", [l for l in tail.splitlines()])]
    return [(parts[i], parts[i + 1].splitlines()) for i in range(1, len(parts), 2)]


def parse_group(chunk, part, dropped):
    P = {}
    s = label_block(chunk, "題組說明")
    P["en"] = s[0].strip() if s else ""
    kind = re.search(r"refer to the following (.+?)\.?$", P["en"])
    P["kind"] = kind.group(1) if kind else ""
    art = label_block(chunk, "文章原文", STOP_ART)
    if not art:
        sys.exit("題組缺 文章原文：" + P["en"])
    docs = split_docs(art[1] + "\n" + art[0] if art[0] else art[1])
    texts = [quote_text(ls) for _, ls in docs]
    if part == 6:
        texts = [re.sub(r"-{3,}〈Q(\d+)〉", r"{{\1}}", t) for t in texts]
    if len(texts) > 1:
        P["docs"] = [{"kind": k, "text": t} for (k, _), t in zip(docs, texts)]
        P["text"] = "\n\n".join(texts)
    else:
        P["text"] = texts[0]
    tr = label_block(chunk, "文章中譯[^：\n]*", STOP_ART)
    if tr:
        td = [re.sub(r"〈Q(\d+)〉", r"（\1）", quote_text(ls)) for _, ls in split_docs(tr[1])]
        P["trans"] = "\n\n---\n\n".join(td)
    notes = [m.group(0).split("：", 1)[1].strip() for m in re.finditer(r"^編者註[^：\n]*：.*$", chunk, re.M)]
    if notes:
        P["trans"] = P.get("trans", "") + "\n\n編者註：" + "\n編者註：".join(notes)
    v = label_block(chunk, "題組詞彙")
    if v:
        lines = [v[0]] + [l for l in v[1].splitlines()]
        vt = "；".join(x.strip().rstrip("。；") for x in lines if x.strip())    # 多篇文章的詞彙分行寫（文章 1：…／文章 2：…）
        P["voc"] = drop_pending(vt, dropped, P["en"])
    return P


def drop_pending(voc, dropped, where):
    keep = []
    if voc.startswith("原書此題未另列詞彙"):
        return ""
    for item in re.split(r"；", voc):
        if "【待核】" in item:
            dropped.append(f"{where}：{item.strip()}")
        elif item.strip():
            keep.append(item.strip())
    return "；".join(keep)


def parse_q(n, body, part, dropped):
    q = {"n": n}
    opts = []
    pre = body.split("\n答案：", 1)[0]
    for line in pre.splitlines():
        m = re.match(r"^\(([A-D])\) (.*?)\s*$", line)
        if m:
            opts.append(m.group(2))
    a = re.search(r"^答案：\s*([A-D])\s*$", body, re.M)
    if not a:
        sys.exit(f"Q{n}：答案不是單一個 A–D")
    qt = label_block(body, "題目")
    qtext = clean(qt[0]) if qt else ""
    if part == 6:
        qtext = ""
    tr = label_block(body, "翻譯[^：\n]*")
    ex = label_block(body, "解析[^：\n]*")
    para = label_block(body, "變換表達方式")
    voc = label_block(body, "詞彙")
    ed = [m.group(0).split("：", 1)[1].strip() for m in re.finditer(r"^編者註[^：\n]*：.*$", body, re.M)]
    e = clean(ex[1] if ex else "")
    kp = ""
    if e:
        b = re.match(r"〔([^〕]+)〕", e)
        kp = b.group(1) if b else re.split(r"[。：]", e)[0][:40]
    if para and para[1].strip():
        e += "\n\n變換表達方式：\n" + clean(para[1])
    if ed:
        e += "\n\n編者註：" + "\n編者註：".join(ed)
    item = {"n": n, "part": part}
    return item, {"q": qtext, "o": opts, "a": ANS[a.group(1)], "kp": kp,
                  "trans": clean(("\n".join(x for x in (tr[0], tr[1]) if x.strip())) if tr else ""), "e": e,
                  "voc": drop_pending(clean(voc[0] if voc and voc[0].strip() else (voc[1] if voc else "")), dropped, f"Q{n}")}


def build(nn, dropped):
    path = SRC / f"test{nn:02d}" / f"TEST{nn:02d}.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    fm = re.match(r"---\n(.*?)\n---\n", text, re.S)
    st = re.search(r"^status:\s*(\S+)", fm.group(1), re.M).group(1) if fm else ""
    if st not in ("done", "reviewed"):
        print(f"略過 TEST{nn:02d}：status 是 {st!r}")
        return None
    passages, qs, cur = [], [], None
    parts = re.split(r"^(#### 題組｜.*|### Q\d+)\s*$", text, flags=re.M)
    # parts: [前言, 標題1, 內容1, 標題2, 內容2, …]
    for h, body in zip(parts[1::2], parts[2::2]):
        if h.startswith("####"):
            n0 = int(re.search(r"Q(\d+)", h).group(1))
            part = 6 if n0 <= 146 else 7
            passages.append(parse_group(body, part, dropped))
            cur = len(passages) - 1
            continue
        n = int(h.split("Q")[1])
        part = 5 if n <= 130 else 6 if n <= 146 else 7
        item, q = parse_q(n, body, part, dropped)
        if len(q["o"]) != 4:
            sys.exit(f"TEST{nn:02d} Q{n}：選項不是 4 個")
        if part != 5:
            item["p"] = cur
        item.update({"g": tag_for(part, q["kp"]), "q": q["q"], "o": q["o"], "a": q["a"]})
        for k in ("kp", "trans", "e", "voc"):
            if q.get(k):
                item[k] = q[k]
        qs.append(item)
    nums = [q["n"] for q in qs]
    if nums != list(range(101, 201)):
        sys.exit(f"TEST{nn:02d}：題號不是 101–200 連續（共 {len(nums)} 題）")
    return {"id": f"t10r_{nn:02d}", "title": f"閱讀 TEST {nn:02d}（國際學村）", "kind": "toeic", "part": 0, "mock": "reading",
            "sub": "Part 5–7 共 100 題．限時 75 分鐘．整份寫完交卷後檢討", "passages": passages, "qs": qs}


def write(exams):
    lines = ["{", f' "about":{json.dumps(ABOUT, ensure_ascii=False)},', ' "exams":[']
    ex_txt = []
    for ex in exams:
        head = {k: v for k, v in ex.items() if k not in ("passages", "qs")}
        s = "  " + json.dumps(head, ensure_ascii=False, separators=(",", ":"))[:-1]
        s += ',"passages":[\n' + ",\n".join("   " + json.dumps(p, ensure_ascii=False, separators=(",", ":")) for p in ex["passages"]) + "\n  ]"
        s += ',"qs":[\n' + ",\n".join("   " + json.dumps(q, ensure_ascii=False, separators=(",", ":")) for q in ex["qs"]) + "\n  ]}"
        ex_txt.append(s)
    lines.append(",\n".join(ex_txt))
    lines += [" ]", "}"]
    OUT_JSON.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def validate(exams):
    """沿用 update_manifest 的逐題檢查（欄位、答案索引、標籤）。"""
    import update_manifest as um
    tags = json.loads((ROOT / "data" / "tags.json").read_text(encoding="utf-8")).get("tags", {})
    err, note = [], []
    for ex in exams:
        um.check_exam(ex, f"private/{OUT_JSON.name}", tags, err, note)
    return err, note


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    nums = [int(x) for x in sys.argv[1:] if x.isdigit()] or list(range(1, 11))
    dropped = []
    exams = [x for x in (build(n, dropped) for n in nums) if x]
    write(exams)
    err, note = validate(exams)
    import collections
    tc = collections.Counter(q["g"] for ex in exams for q in ex["qs"])
    for ex in exams:
        print(f"{ex['id']}：{len(ex['qs'])} 題、{len(ex['passages'])} 篇文章")
    print("標籤分布：", "、".join(f"{k} {v}" for k, v in sorted(tc.items(), key=lambda x: -x[1])))
    if dropped:
        print(f"\n因【待核】整條略過的詞彙 {len(dropped)} 條：")
        for d in dropped:
            print("  -", d[:100])
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
