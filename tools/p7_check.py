"""TOEIC Part 7（data/toeic_part7.json）的命題規格檢查。規格與理由見 readme.md「TOEIC Part 7」一節。

用法（在專案資料夾執行）：
  py tools/p7_check.py              檢查全部 Part 7 題組
  py tools/p7_check.py p7_t5        只檢查指定題組（可列多個）

錯誤（結束碼 1）：結構不符真考、題號或「Questions x-y refer to」不連續、句子插入題的 [1]–[4]
  或言外之意題引用的時間與原句在文章中找不到、詳解最後提到的選項與 a 不符、缺欄位。
提醒：正解位置分布、「正解是最長選項」比例過高、跨篇題太少等。
完整模擬測驗（id 為 p7_t*）必須是 54 題：單篇 10 組（2/2/2/2/3/3/3/4/4/4 題）、雙篇 2 組、三篇 3 組，各 5 題。
"""
import json, os, re, sys, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "toeic_part7.json")
L = "ABCD"
FULL_SETS = [2, 2, 2, 2, 3, 3, 3, 4, 4, 4, 5, 5, 5, 5, 5]
FULL_DOCS = [1] * 10 + [2, 2, 3, 3, 3]
NEEDED = ("n", "p", "g", "q", "o", "a", "h", "trans", "e", "w")


def docs_of(P):
    return P.get("docs") or [P]


def paragraphs(text):
    """依空行分段；和真考一樣，不把稱謂（Dear Ms. Lee,／Hello,）算成一段。"""
    return [x for x in re.split(r"\n\s*\n", text) if x.strip() and not re.fullmatch(r"(Dear|Hello|Hi|Greetings|To whom)\b[^\n]{0,50}[,:]", x.strip())]


def check_exam(ex, err, warn):
    eid, qs, P = ex["id"], ex["qs"], ex.get("passages", [])
    full = eid.startswith("p7_t")
    sets = collections.OrderedDict()
    for i, q in enumerate(qs):
        sets.setdefault(q.get("p"), []).append(i)
    if list(sets) != sorted(sets):
        err.append(f"{eid}：題目的 p 沒有依文章順序排列")
    if full:
        if len(qs) != 54:
            err.append(f"{eid}：完整測驗應為 54 題，目前 {len(qs)} 題")
        if [len(v) for v in sets.values()] != FULL_SETS:
            err.append(f"{eid}：各組題數應為 {FULL_SETS}，目前 {[len(v) for v in sets.values()]}")
        if [len(docs_of(p)) for p in P] != FULL_DOCS:
            err.append(f"{eid}：各組篇數應為單篇×10、雙篇×2、三篇×3，目前 {[len(docs_of(p)) for p in P]}")
        if [q.get("n") for q in qs] != list(range(147, 201)):
            err.append(f"{eid}：題號應為 147–200 連續")
    for pi, idx in sets.items():
        if not isinstance(pi, int) or not 0 <= pi < len(P):
            continue
        p, ns = P[pi], [qs[i].get("n") for i in idx]
        m = re.match(r"Questions (\d+)[-–](\d+) refer to the following ", p.get("en", ""))
        if not m or (int(m.group(1)), int(m.group(2))) != (ns[0], ns[-1]):
            err.append(f"{eid} 第 {pi} 篇：en 應為「Questions {ns[0]}-{ns[-1]} refer to the following …」，目前是 {p.get('en')!r}")
        if not p.get("trans"):
            err.append(f"{eid} 第 {pi} 篇：缺少全文翻譯 trans")
        if "docs" in p:
            for d in p["docs"]:
                if not d.get("kind", "").startswith("第") or not d.get("text"):
                    err.append(f"{eid} 第 {pi} 篇：docs 的 kind 要以「第一篇：」等開頭且要有 text")
            cross = sum(qs[i].get("g") == "t_p7cross" for i in idx)
            need = 1 if len(p["docs"]) == 2 else 2
            if cross < need:
                warn.append(f"{eid} 第 {pi} 篇（{len(p['docs'])} 篇組）：跨篇題只有 {cross} 題，真考通常至少 {need} 題")
    for i, q in enumerate(qs):
        tag = f"{eid} 第 {q.get('n', i)} 題"
        miss = [k for k in NEEDED if k not in q or q[k] in ("", None)]
        if miss:
            err.append(f"{tag}：缺少欄位 {miss}"); continue
        if len(q["o"]) != 4:
            err.append(f"{tag}：要有四個選項")
        letters = re.findall(r"\(([A-D])\)", q["e"])
        if not letters or L.index(letters[-1]) != q["a"]:
            err.append(f"{tag}：詳解最後提到的選項應為正解 ({L[q['a']]})（新題請以「故選 ({L[q['a']]})。」結尾）")
        p = P[q["p"]] if 0 <= q["p"] < len(P) else {}
        full_text = "\n".join(d.get("head", "") + "\n" + d.get("text", "") for d in docs_of(p))
        if q["g"] == "t_p7sent":
            if q["o"] != ["[1]", "[2]", "[3]", "[4]"]:
                err.append(f"{tag}：句子插入題的選項要是 [1]–[4]")
            if any(full_text.count(f"[{k}]") != 1 for k in "1234"):
                err.append(f"{tag}：文章中 [1]–[4] 必須各出現一次")
            if not re.search(r"\n\"[^\"]+\"$", q["q"]):
                err.append(f"{tag}：題幹最後一行要放插入句（用雙引號）")
        mi = re.match(r"At (\d{1,2}:\d{2} [AP]\.M\.), what does .+ writes?, \"(.+)\"\?$", q["q"])
        if mi:
            if mi.group(1) not in full_text or mi.group(2) not in full_text:
                err.append(f"{tag}：言外之意題引用的時間 {mi.group(1)} 或原句「{mi.group(2)}」在文章中找不到")
        elif "mean when" in q["q"]:
            err.append(f"{tag}：言外之意題請用真考句型 At h:mm A.M., what does Mr. X (most likely) mean when he writes, \"…\"?")
        mv = re.search(r"the word \"([^\"]+)\" in paragraph (\d+)", q["q"])
        if mv:
            word, k = mv.group(1), int(mv.group(2))
            texts = [d.get("text", "") for d in docs_of(p)]
            if not any(len(paragraphs(t)) >= k and re.search(rf"\b{re.escape(word)}\b", paragraphs(t)[k - 1]) for t in texts):
                err.append(f"{tag}：第 {k} 段找不到「{word}」")
    # 統計：正解位置、正解是否常是最長選項（應試技巧可利用的偏誤）
    pos = collections.Counter(q["a"] for q in qs)
    ranked = [q for q in qs if len({len(o) for o in q["o"]}) > 1]  # [1]–[4] 這類等長選項不列入
    rank = collections.Counter(sorted((len(o) for o in q["o"]), reverse=True).index(len(q["o"][q["a"]])) for q in ranked)
    n = len(ranked)
    if full and (max(pos.values()) - min(pos.get(k, 0) for k in range(4)) > 3):
        warn.append(f"{eid}：正解位置不平均 " + "／".join(f"{L[k]} {pos.get(k, 0)}" for k in range(4)))
    if n >= 10 and rank[0] / n > 0.35:
        warn.append(f"{eid}：正解是（並列）最長選項的比例 {rank[0] / n:.0%}，應在 35% 以下（理想約 25%）")
    tags = collections.Counter(q["g"] for q in qs)
    return f"{eid}：{len(qs)} 題｜正解 " + "／".join(f"{L[k]}{pos.get(k, 0)}" for k in range(4)) + \
        "｜正解長度名次（1＝最長）" + "／".join(f"{k + 1}:{rank.get(k, 0)}" for k in range(4)) + \
        "｜" + "、".join(f"{k[4:]}{v}" for k, v in sorted(tags.items()))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    d = json.load(open(DATA, encoding="utf-8"))
    want = set(sys.argv[1:])
    err, warn = [], []
    for ex in d["exams"]:
        if not want or ex["id"] in want:
            print(check_exam(ex, err, warn))
    for title, items in (("提醒", warn), ("錯誤", err)):
        if items:
            print(f"\n【{title}】{len(items)} 項")
            for x in items:
                print("  " + x)
    if err:
        sys.exit(1)
    print("\n沒有錯誤。")


if __name__ == "__main__":
    main()
