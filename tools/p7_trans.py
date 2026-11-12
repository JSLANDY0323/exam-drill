"""TOEIC Part 7 逐句對照翻譯（data/toeic_part7.json 的 seg／hseg 欄位）。

檢討時右側面板可切換成「全文翻譯」，滑鼠移到左側英文句子，右側對應的中文會標示出來（反之亦然）。
資料放在每篇文章（單篇是 passage 本身，雙篇／三篇是 docs 裡的每一篇）：
  "seg":  [["英文句子", "中文翻譯"], ...]   對應 text
  "hseg": [["英文", "中文"], ...]           對應 head（選用）
英文依序把 text 切開，句子之間只能是空白或換行；網頁照英文的換行排中文段落。
對不上原文時網頁會退回不分句的顯示，所以改了 text 之後要重新跑 check。

用法（在專案資料夾執行）：
  py tools/p7_trans.py split p7_t1 草稿.json     自動斷句，產生待填中文的草稿（zh 留空）
  py tools/p7_trans.py apply 草稿.json [--dry]   檢查草稿並寫回題庫（中文不可留空）
  py tools/p7_trans.py check [p7_t1 ...]         檢查題庫裡已有的逐句翻譯
寫回後照常執行 py tools/update_manifest.py。
"""
import json, os, re, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "toeic_part7.json")
ABBR = {"Mr", "Ms", "Mrs", "Dr", "St", "Inc", "Co", "Ltd", "vs", "etc", "No", "Jr", "Sr", "U.S", "e.g", "i.e",
        "Jan", "Feb", "Mar", "Apr", "Jun", "Jul", "Aug", "Sep", "Sept", "Oct", "Nov", "Dec", "Ave", "Rd", "Blvd", "Dept", "approx"}


def docs_of(P):
    return P.get("docs") or [P]


def split_line(line):
    """一行再依句號／問號／驚嘆號斷句；[1]–[4] 插入位置獨立成一段。"""
    out, start = [], 0
    for m in re.finditer(r"[.!?][\"”')]?(?=\s+[\"“(\[A-Z0-9•])|\s(?=\[\d\])|\[\d\](?=\s)", line):
        end = m.end()
        prev = re.search(r"([A-Za-z.]+)\.$", line[start:m.start() + 1])
        if m.group().startswith(".") and prev and (prev.group(1) in ABBR or re.fullmatch(r"[A-Z]", prev.group(1))):
            continue  # 縮寫與名字縮寫（M. Osei）不斷句
        if prev and prev.group(1) in ("A.M", "P.M") and not re.match(r"\s+[\"“A-Z]", line[end:]):  # 「1:05 A.M. (June 15)」不斷
            continue
        if re.fullmatch(r"\s*\d+\.", line[start:end]):  # 「1. 項目」的編號不單獨成段
            continue
        seg = line[start:end].strip()
        if seg:
            out.append(seg)
        start = end
    if line[start:].strip():
        out.append(line[start:].strip())
    return out


def split_text(text):
    return [s for line in text.split("\n") for s in split_line(line)]


def match(text, seg):
    """英文段落必須依序出現、中間只有空白；回傳錯誤訊息（None 表示通過）。"""
    pos = 0
    for k, pair in enumerate(seg):
        if not (isinstance(pair, list) and len(pair) == 2 and all(isinstance(x, str) for x in pair)):
            return f"第 {k + 1} 段格式要是 [英文, 中文]"
        en, zh = pair
        if not en.strip() or not zh.strip():
            return f"第 {k + 1} 段英文或中文是空的：{en[:40]!r}"
        i = text.find(en, pos)
        if i < 0 or text[pos:i].strip():
            return f"第 {k + 1} 段在原文對不上（或前面漏了文字）：{en[:50]!r}"
        pos = i + len(en)
    if text[pos:].strip():
        return f"最後還有原文沒有翻到：{text[pos:pos + 50]!r}"
    return None


def check_exam(ex, err):
    n = 0
    for pi, P in enumerate(ex.get("passages", [])):
        for di, d in enumerate(docs_of(P)):
            for key, src in (("seg", "text"), ("hseg", "head")):
                if key in d:
                    n += 1
                    msg = match(d.get(src, ""), d[key])
                    if msg:
                        err.append(f"{ex['id']} 第 {pi} 組第 {di + 1} 篇 {key}：{msg}")
    return n


def cmd_split(eid, out):
    d = json.load(open(DATA, encoding="utf-8"))
    ex = next(x for x in d["exams"] if x["id"] == eid)
    draft = {"exam": eid, "passages": []}
    for pi, P in enumerate(ex["passages"]):
        docs = []
        for doc in docs_of(P):
            item = {"text": [[s, ""] for s in split_text(doc.get("text", ""))]}
            if doc.get("head"):
                item["head"] = [[s, ""] for s in split_text(doc["head"])]
            docs.append(item)
        draft["passages"].append({"p": pi, "docs": docs})
    with open(out, "w", encoding="utf-8") as f:
        f.write("{\"exam\":" + json.dumps(eid) + ",\"passages\":[\n")
        f.write(",\n".join(json.dumps(p, ensure_ascii=False) for p in draft["passages"]) + "\n]}\n")
    print(f"已產生 {out}：{sum(len(x['text']) + len(x.get('head', [])) for p in draft['passages'] for x in p['docs'])} 段待翻譯")


def cmd_apply(path, dry):
    draft = json.load(open(path, encoding="utf-8-sig"))
    d = json.load(open(DATA, encoding="utf-8"))
    ex = next(x for x in d["exams"] if x["id"] == draft["exam"])
    err = []
    for item in draft["passages"]:
        P = ex["passages"][item["p"]]
        docs = docs_of(P)
        if len(item["docs"]) != len(docs):
            err.append(f"第 {item['p']} 組：篇數 {len(item['docs'])} 與題庫 {len(docs)} 不符"); continue
        for di, (doc, it) in enumerate(zip(docs, item["docs"])):
            for key, src, dk in (("seg", "text", "text"), ("hseg", "head", "head")):
                if dk in it:
                    msg = match(doc.get(src, ""), it[dk])
                    if msg:
                        err.append(f"第 {item['p']} 組第 {di + 1} 篇 {key}：{msg}")
                    else:
                        doc[key] = it[dk]
    if err:
        print("草稿有問題，未寫入：\n  " + "\n  ".join(err)); sys.exit(1)
    if dry:
        print("檢查通過（--dry，未寫入）"); return
    write(d)
    print(f"已寫入 {draft['exam']} 的逐句翻譯；接著請執行 py tools/update_manifest.py")


def write(d):
    """只重寫文章那幾行（一篇一行），其餘排版原封不動。"""
    lines = open(DATA, encoding="utf-8").read().split("\n")
    ei, pi, inside = -1, 0, False
    for k, line in enumerate(lines):
        s = line.strip()
        if s.startswith("{\"id\":"):
            ei, pi, inside = ei + 1, 0, False
        if s.endswith("\"passages\":["):
            inside = True; continue
        if inside and s.startswith("]"):
            inside = False; continue
        if inside and s.startswith("{"):
            comma = "," if s.endswith(",") else ""
            new = json.dumps(d["exams"][ei]["passages"][pi], ensure_ascii=False, separators=(",", ":"))
            lines[k] = line[:len(line) - len(line.lstrip())] + new + comma
            pi += 1
    open(DATA, "w", encoding="utf-8", newline="\n").write("\n".join(lines))
    json.load(open(DATA, encoding="utf-8"))  # 寫完再讀一次，確定仍是合法 JSON


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    a = sys.argv[1:]
    if a[:1] == ["split"] and len(a) == 3:
        cmd_split(a[1], a[2])
    elif a[:1] == ["apply"] and len(a) >= 2:
        cmd_apply(a[1], "--dry" in a)
    elif a[:1] == ["check"]:
        d = json.load(open(DATA, encoding="utf-8"))
        err, n = [], 0
        for ex in d["exams"]:
            if len(a) == 1 or ex["id"] in a[1:]:
                k = check_exam(ex, err)
                if k:
                    print(f"{ex['id']}：{k} 處逐句翻譯（text 與 head 分開計）")
                    n += k
        if err:
            print("\n【錯誤】\n  " + "\n  ".join(err)); sys.exit(1)
        print(f"\n沒有錯誤（共 {n} 處）。")
    else:
        print(__doc__); sys.exit(2)


if __name__ == "__main__":
    main()
