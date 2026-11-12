"""產生檢討用的滑鼠提示詞典 data/glossary/toeic.json（只收 TOEIC 題庫實際出現的單字與片語）。
用法：py tools/make_glossary.py ECDICT的ecdict.csv路徑 [--report]
      py tools/make_glossary.py --patch     # 不需要 ecdict.csv：只把 glossary_extra.json 與整理規則套到現有的 toeic.json
  --patch 用在手上沒有 ecdict.csv、只想改 glossary_extra.json（w／p／f／drop）時；兩種模式的結果一致。
  整理規則（normalize）：去掉 \\r、無詞性的雜訊行（多半是 DOS／電腦指令釋義）、同詞性的行合併、vt./vi. → v.、a. → adj.。
  glossary_extra.json 的 f：變化形→原形的覆寫（原形 ECDICT 判錯時用；值為 null＝取消對應，字本身當原字）。
  需要 opencc-python-reimplemented（簡體轉台灣繁體）。
  ecdict.csv 來自 https://github.com/skywind3000/ECDICT（MIT 授權），約 66 MB，不放進專案。
  --report 另外列出：題庫片語（target）不在詞典裡的、詞典查不到的單字，方便補進 glossary_extra.json。

輸出格式：{"about":…, "f":{變化形:原形}, "w":{字:釋義}, "p":{片語:釋義}, "k":[以原字為主的變化形]}
  釋義每行一個詞性，例如 "v. 舉行；發生\nn. 地方"。
  單字題（toeic_p5_words.json）的情境釋義會併進來排在第一行：正解取詳解「【正解】字（意思）」，錯誤選項取其他選項說明的「(詞性) 意思」。
  k：當形容詞用的 -ing／-ed 形（challenging、salaried），提示與存卡以原字為主，不換成原形。
  片語用詞典原本的寫法（take place）；比對時句中每個字可用原字或原形（took → take），找最長的片語。
  網頁（index.html 的 glossHTML）用同一套規則比對，兩邊要一起改。
補充與覆寫：tools/glossary_extra.json（人工撰寫的繁體釋義），格式 {"w":{…}, "p":{…}, "drop":[不要的片語]}，優先於 ECDICT。
改完題庫或 glossary_extra.json 後重跑本工具。
"""
import csv, glob, itertools, json, os, re, sys, collections, unicodedata
from opencc import OpenCC

sys.stdout.reconfigure(encoding="utf-8")
csv.field_size_limit(10 ** 8)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "glossary", "toeic.json")
EXTRA = os.path.join(ROOT, "tools", "glossary_extra.json")
TOK = re.compile(r"[A-Za-zÀ-ÿ]+(?:['’-][A-Za-zÀ-ÿ]+)*")
BLANK = re.compile(r"_{3,}")
MAXN = 5                                              # 片語最多幾個字
POSLINE = re.compile(r"^(?:[a-z]+\.\s?)+")            # 行首詞性，例如 "vt. "、"adj. "
TAGLINE = re.compile(r"^\[([^\]]*)\]\s*")
KEEP_TAGS = {"經", "法", "商", "经"}                   # 片語只留一般釋義與商業、法律專業釋義
INFL = re.compile(r"(的過去式|的過去分詞|的現在分詞|的複數|的第三人稱單數|的比較級|的最高級|過去式|現在分詞)")
ARTICLE = {"a", "an", "the"}
ACCENTED = {"fiancé", "cafés", "cybercafé"}           # 這些保留重音、直接查 glossary_extra.json
WORDS = os.path.join(ROOT, "data", "toeic_p5_words.json")
TAGPOS = {"t_p5wn": "n.", "t_p5wv": "v.", "t_p5wa": "adj.", "t_p5wd": "adv."}
P_ALIAS = {"a": "adj", "vt": "v", "vi": "v"}
NOTE = re.compile(r"（[^（）]*(?:的過去|的現在分詞|的複數|的第三人稱|的比較級|的最高級)[^（）]*）")
cc = OpenCC("s2twp")


def texts():
    """題庫中會在檢討畫面顯示的英文：題幹（空格填入正解）、選項、文章（{{n}} 填入正解）、聽力原文。"""
    files = sorted(glob.glob(os.path.join(ROOT, "data", "toeic*.json"))) + sorted(glob.glob(os.path.join(ROOT, "private", "toeic*.json")))
    for f in files:
        if f.endswith(".enc.json"):
            continue
        for x in json.load(open(f, encoding="utf-8")).get("exams", []):
            qs = x.get("qs", [])
            byn = {q.get("n"): q for q in qs if q.get("n")}
            fill = lambda t: re.sub(r"\{\{(\d+)\}\}", lambda m: byn[int(m.group(1))]["o"][byn[int(m.group(1))]["a"]] if int(m.group(1)) in byn else " ", t)
            for P in x.get("passages", []) or []:
                for d in (P.get("docs") or [P]):
                    for k in ("head", "text"):
                        if d.get(k): yield fill(d[k])
            for S in x.get("sets", []) or []:
                if S.get("script"): yield S["script"]
            for q in qs:
                o = q.get("o", [])
                ans = o[q["a"]] if isinstance(q.get("a"), int) and q["a"] < len(o) else ""
                if q.get("q"): yield BLANK.sub(ans, q["q"])
                yield from (t for t in o if isinstance(t, str))


def norm(w):
    w = w.lower().replace("’", "'")
    if w not in ACCENTED: w = unicodedata.normalize("NFD", w).encode("ascii", "ignore").decode()  # résumé → resume
    return w[:-2] if w.endswith("'s") else w[:-1] if w.endswith("s'") else w


def runs(t):
    """依標點切成只以空白相連的字串列，片語不跨標點。"""
    for part in re.split(r"[^A-Za-zÀ-ÿ'’\-\s]+", t):
        ws = [norm(w) for w in TOK.findall(part)]
        if ws: yield ws


def paren(s, i):
    """s[i] 是「（」，回傳對應「）」的位置（允許巢狀）。"""
    depth = 0
    for j in range(i, len(s)):
        depth += {"（": 1, "）": -1}.get(s[j], 0)
        if depth == 0: return j
    return -1


def senses_of(t):
    t = NOTE.sub("", t).strip().rstrip("。；")
    out = []
    for s in re.split(r"[，、；;]", t):
        s = s.strip()
        if s and s not in out: out.append(s)
    return out


def question_senses():
    """單字題 Day 1–30 的情境釋義（題目裡實際考的意思）：
    正解取詳解「【正解】字（意思）」的括號，錯誤選項取其他選項說明「(A) 字 (詞性) 意思」。片語題不收（由片語詞典負責）。
    產生 (字, 詞性, [義項])。"""
    if not os.path.exists(WORDS): return
    for x in json.load(open(WORDS, encoding="utf-8"))["exams"]:
        for q in x["qs"]:
            pos, o = TAGPOS.get(q["g"]), q["o"]
            if not pos: continue
            ans, e = o[q["a"]], q.get("e", "")
            if "【正解】" in e:
                s = e.split("【正解】", 1)[1]; i = s.find("（"); j = paren(s, i) if i > 0 else -1
                if j > 0:
                    head, zh = s[:i].strip(), s[i + 1:j]
                    if head.lower() == ans.lower(): yield ans, pos, senses_of(zh)
                    elif ans.lower() in head.lower(): yield ans, pos, [f"{zh}（{head}）"]
            for line in (q.get("w") or "").split("\n"):
                m = re.match(r"\(([A-D])\) ", line)
                if not m: continue
                word = o["ABCD".index(m.group(1))]
                parts = re.split(r"\(([a-z]+)\.\)", line[m.end() + len(word):])
                for p, txt in zip(parts[1::2], parts[2::2]):
                    ss = senses_of(txt)
                    if ss and not any(b in txt for b in ("錯誤形式", "拼法錯誤", "罕用造字")): yield word, P_ALIAS.get(p, p) + ".", ss


def clean(tr, phrase=False):
    """ECDICT 中文釋義 → 台灣繁體；每行一個詞性，最多 4 行、每行最多 6 個義項。
    [計][電][化] 等專業標籤的行只在沒有一般釋義時才用（片語則直接不收）。"""
    lines = [cc.convert(l.strip()) for l in tr.replace("\\n", "\n").split("\n") if l.strip()]
    plain, tagged = [], []
    for l in lines:
        m = TAGLINE.match(l)
        if not m: plain.append(l)
        elif m.group(1) in KEEP_TAGS: tagged.append(l[m.end():])
        elif not phrase: tagged.append(l[m.end():])
    use = plain or tagged
    out = []
    for l in use[:4]:
        m = POSLINE.match(l); pos = m.group(0).strip() + " " if m else ""
        body = TAGLINE.sub("", l[m.end():] if m else l)
        senses = []
        for s in re.split(r"[；;,，]", body):
            s = s.strip()
            if s and s not in senses: senses.append(s)
        if senses: out.append(pos + "；".join(senses[:6]))
    return "\n".join(out)


def merge_senses(qs, old):
    """題目情境釋義排在最前面（同詞性合成一行），原本的詞典釋義接在後面並去掉重複的義項；最多 5 行。"""
    lines = [f"{p} {'；'.join(ss)}" for p, ss in qs.items()]
    seen = {s for ss in qs.values() for s in ss}
    for l in (old or "").split("\n"):
        m = POSLINE.match(l); pos = l[:m.end()] if m else ""
        rest = [s for s in (l[m.end():] if m else l).split("；") if s.strip() and s.strip() not in seen]
        if rest: lines.append(pos + "；".join(rest))
    return "\n".join(lines[:5])


POS_FIX = {"a": "adj", "vt": "v", "vi": "v", "vr": "v", "abbr": "abbr"}


def normalize(txt):
    """整理 ECDICT 釋義：去掉 \\r；有詞性的行存在時，丟掉沒詞性的行（多半是 DOS／電腦指令之類的雜訊）；
    vt./vi. 併成 v.、a. 改 adj.，同詞性的行合併成一行（去掉重複義項、最多 6 個）；最多 4 行。
    全部都沒有詞性的（縮寫、人名、手寫釋義）原樣保留。"""
    lines = [l.strip() for l in re.sub(r"\\r|\r", "", txt or "").split("\n") if l.strip()]
    has_pos = any(POSLINE.match(l) for l in lines)
    order, body = [], {}
    for l in lines:
        m = POSLINE.match(l)
        if m:
            toks = [POS_FIX.get(t, t) for t in m.group(0).replace(" ", "").split(".") if t]
            pos = "/".join(dict.fromkeys(toks)) + "."; rest = l[m.end():]
        elif has_pos: continue
        else: pos, rest = "", l
        if pos not in body: body[pos] = []; order.append(pos)
        for s in re.split(r"[；;]", rest):
            s = s.strip()
            if s and s not in body[pos]: body[pos].append(s)
    return "\n".join((p + " " if p else "") + "；".join(body[p][:6]) for p in order[:4] if body[p])


def patch():
    """不需要 ecdict.csv：把 glossary_extra.json（f／w／p／drop）與 normalize 套到現有的 toeic.json。"""
    d = json.load(open(OUT, encoding="utf-8"))
    extra = json.load(open(EXTRA, encoding="utf-8")) if os.path.exists(EXTRA) else {}
    W, F, P, K = d["w"], d["f"], d["p"], set(d.get("k", []))
    for k, v in extra.get("f", {}).items():
        if v: F[k] = v
        else: F.pop(k, None)
    for k in extra.get("drop", []): P.pop(k, None)
    xw, xp = extra.get("w", {}), extra.get("p", {})
    for k, v in xp.items():
        if k in P: P[k] = v
    new_p = [k for k in xp if k not in P and k not in set(extra.get("drop", []))]
    W.update(xw)
    W = {k: (v if k in xw else normalize(v)) for k, v in W.items()}
    W = {k: v for k, v in W.items() if v}
    bad = sorted(f for f, L in F.items() if L not in W)
    for f in bad: F.pop(f)
    d.update({"f": dict(sorted(F.items())), "w": dict(sorted(W.items())), "p": P, "k": sorted(K & set(W))})
    with open(OUT, "w", encoding="utf-8", newline="\n") as fo:
        json.dump(d, fo, ensure_ascii=False, separators=(",", ":"))
    print(f"patch 完成：單字 {len(W)}、變化形 {len(F)}、片語 {len(P)}；檔案 {os.path.getsize(OUT) // 1024} KB")
    if bad: print("原形查不到、已移除對應：", ", ".join(bad))
    if new_p: print("glossary_extra.json 的 p 有新片語（--patch 不會新增，需要 ecdict.csv 全部重產）：", ", ".join(new_p))


def main(path, report):
    corpus = list(texts())
    forms = collections.Counter(w for t in corpus for r in runs(t) for w in r)
    print(f"題庫英文字形 {len(forms)} 個")

    # 讀 ECDICT 兩次：先找變化形→原形與片語，再取題庫字形和它們原形的釋義
    lemma, phr = {}, {}
    for row in csv.DictReader(open(path, encoding="utf-8")):
        w, tr = row["word"], (row["translation"] or "").strip()
        lw = w.lower()
        if " " in w:
            ws = w.split()
            if tr and w == lw and 2 <= len(ws) <= MAXN and not (len(ws) == 2 and ws[0] in ARTICLE): phr.setdefault(lw, tr)
            continue
        for item in (row["exchange"] or "").split("/"):
            k, _, v = item.partition(":")
            if k and k in "pdi3s" and v and v.lower() in forms and v.lower() != lw: lemma.setdefault(v.lower(), lw)
    for k, v in json.load(open(EXTRA, encoding="utf-8")).get("f", {}).items() if os.path.exists(EXTRA) else []:
        if v: lemma[k] = v                                       # 人工指定原形（ECDICT 判錯時）
        else: lemma.pop(k, None)                                 # null＝不要對應到別的字
    need = set(forms) | set(lemma.values())
    ent = {}
    for row in csv.DictReader(open(path, encoding="utf-8")):
        w, tr = row["word"], (row["translation"] or "").strip()
        lw = w.lower()
        if tr and lw in need and (lw not in ent or w == lw): ent[lw] = tr
    extra = json.load(open(EXTRA, encoding="utf-8")) if os.path.exists(EXTRA) else {}
    xw, xp, drop = extra.get("w", {}), extra.get("p", {}), set(extra.get("drop", []))

    W, F = {}, {}
    for f in forms:
        L = lemma.get(f, f)
        if L != f: F[f] = L
        for k in {f, L}:
            if k in W: continue
            if k in xw: W[k] = xw[k]
            elif k in ent:
                c = clean(ent[k])
                if c and not (k == f and L != f and INFL.search(c) and len(c) < 40): W[k] = c
    cand = lambda w: [w, F[w]] if w in F else [w]

    # 單字題的情境釋義併進詞典：多義字至少要有題目考的那個意思，而且排在第一行。
    # 題目當形容詞、名詞、副詞用的變化形（challenging、salaried、bound、earnings）記在原字上，並列進 K（網頁提示與存卡都以原字為主）；
    # 當動詞用的變化形（soared）記在原形
    K, QS, nq = set(), collections.defaultdict(dict), 0
    core = lambda s: re.sub(r"（[^（）]*）$", "", s)
    for word, pos, ss in question_senses():
        w = norm(word)
        own = xw.get(w) or (cc.convert(ent[w]) if w in ent else "")
        if w in F and pos != "v." and own and not (pos == "n." and INFL.search(own)): K.add(w)  # 一般複數名詞（applicants）仍存原形
        key = w if w in K or w not in F else F[w]
        cur = QS[key].setdefault(pos, [])
        for s in ss:
            if core(s) in {core(x) for x in cur}: continue
            cur.append(s); nq += 1
    for key, qs in QS.items():
        if key in xw: continue                                  # 人工釋義優先
        W[key] = merge_senses(qs, W.get(key) or (clean(ent[key]) if key in ent else ""))
    W = {k: (v if k in xw else normalize(v)) for k, v in W.items()}
    W = {k: v for k, v in W.items() if v}
    print(f"單字題情境釋義 {nq} 個義項，併入 {len(QS)} 個字")

    # 題庫中真的出現的片語：每個字用原字或原形去比對詞典的片語
    pset = (set(phr) | set(xp)) - drop
    seen = collections.Counter()
    for t in corpus:
        for r in runs(t):
            cs = [cand(w) for w in r]
            for i in range(len(cs)):
                for n in range(2, min(MAXN, len(cs) - i) + 1):
                    for combo in itertools.product(*cs[i:i + n]):
                        k = " ".join(combo)
                        if k in pset: seen[k] += 1
    Pm = {}
    for k in sorted(seen):
        c = xp.get(k) or clean(phr[k], phrase=True)
        if c: Pm[k] = c

    data = {"about": "檢討畫面的滑鼠提示詞典，由 tools/make_glossary.py 產生，不要手改。釋義來源：ECDICT（https://github.com/skywind3000/ECDICT，MIT License，Copyright (c) 2017 Linwei）經 OpenCC 轉為台灣繁體，並以 tools/glossary_extra.json 補充。",
            "f": dict(sorted(F.items())), "w": dict(sorted(W.items())), "p": Pm, "k": sorted(K & set(W))}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as fo:
        json.dump(data, fo, ensure_ascii=False, separators=(",", ":"))
    miss = [w for w in forms if not any(c in W for c in cand(w))]
    print(f"單字釋義 {len(W)}、變化形 {len(F)}、片語 {len(Pm)}；查不到的字形 {len(miss)}；檔案 {os.path.getsize(OUT) // 1024} KB")

    if report:
        tg = set()
        for f in glob.glob(os.path.join(ROOT, "data", "toeic*.json")):
            for x in json.load(open(f, encoding="utf-8")).get("exams", []):
                tg |= {q["target"].lower() for q in x["qs"] if " " in (q.get("target") or "")}
        hit = lambda t: any(" ".join(c) in Pm for c in itertools.product(*[cand(norm(w)) for w in TOK.findall(t)]))
        lost = sorted(t for t in tg if not hit(t))
        print(f"\n題庫片語（target）{len(tg)} 個，詞典沒有的 {len(lost)} 個：")
        print("\n".join(lost))
        caps = {norm(w) for t in corpus for w in TOK.findall(t) if w[0].isupper()}
        print(f"\n查不到的單字（不含大寫開頭的專有名詞）：")
        print(", ".join(sorted(w for w in miss if w not in caps)))


if __name__ == "__main__":
    a = [x for x in sys.argv[1:] if not x.startswith("--")]
    if "--patch" in sys.argv: patch(); sys.exit(0)
    if not a: print(__doc__); sys.exit(2)
    main(a[0], "--report" in sys.argv)
