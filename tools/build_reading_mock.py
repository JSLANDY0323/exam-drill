"""從 private/TOEIC/TOEIC紅藍本/kb/R/R_AT*.md 產生 private/toeic_reading_mock.json（多益閱讀模擬考第一回、第二回）。

用法：
    py tools/build_reading_mock.py

只收 front matter 為 status: done 的校對稿。產生後跑 py tools/update_manifest.py 檢查，
再請使用者執行 py tools/encrypt_ai.py 加密（明文只放 private/，不可上傳）。

每份試卷一個題組：Part 5 的題目沒有 p；Part 6／7 的題目以 p 指向 passages。
標籤 g 依校對稿每題的「考點：」自動對應；要指定時在該題加一行「標籤：t_xxx」。
"""
import json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
KB_R = ROOT / "private" / "TOEIC" / "TOEIC紅藍本" / "kb" / "R"
OUT_JSON = ROOT / "private" / "toeic_reading_mock.json"
TESTS = [("R_AT1", "rb_R_AT1", "第一回（實戰模擬試題 1）"), ("R_AT2", "rb_R_AT2", "第二回（實戰模擬試題 2）")]
ANS = {"A": 0, "B": 1, "C": 2, "D": 3}
FIELDS = ("題目", "答案", "考點", "翻譯", "解析", "Paraphrasing", "詞彙", "標籤")


def tag_for(part, kp):
    """考點文字 → data/tags.json 的標籤（依序比對，先中先贏）。"""
    rules = {
        5: [("時態", "t_p5tense"), ("假設", "t_p5inv"), ("相關連接詞", "t_p5corr"), ("關係", "t_p5rel"), ("疑問詞", "t_p5ncl"),
            ("代名詞", "t_p5pron"), ("連接", "t_p5conj"), ("介系詞", "t_p5prep"), ("詞彙", "t_p5vocab"), ("填入動詞", "t_p5fin")],
        6: [("句子", "t_p6sent"), ("連接", "t_p6conn"), ("時態", "t_p6gram"), ("詞彙", "t_p6word"), ("位置", "t_p6word")],
        7: [("綜合", "t_p7cross"), ("插入", "t_p7sent"), ("Not/True", "t_p7not"), ("主題", "t_p7main"), ("主旨", "t_p7main"),
            ("推論", "t_p7infer"), ("意圖", "t_p7vocab"), ("同義", "t_p7vocab"), ("5W1H", "t_p7detail")],
    }
    for key, tag in rules[part]:
        if key in kp:
            return tag
    return {5: "t_p5pos", 6: "t_p6gram", 7: "t_p7detail"}[part]


def quote_text(block):
    """把「> …」引用區塊還原成純文字（保留空行分段）。"""
    out = []
    for line in block.splitlines():
        if not line.startswith(">"):
            break
        out.append(line[2:] if line.startswith("> ") else line[1:])
    return "\n".join(out).strip().replace("\\*", "*")


def after(label, body):
    m = re.search(rf"^{label}：\n((?:>.*\n?)+)", body, re.M)
    return quote_text(m.group(1)) if m else ""


def parse_q(n, body):
    q = {"n": n}
    lines = body.strip("\n").splitlines()
    cur, buf, opts = None, {}, []
    for line in lines:
        mo = re.match(r"^\(([A-D])\) (.*)$", line)
        mf = re.match(rf"^({'|'.join(FIELDS)})：(.*)$", line)
        if mf:
            cur = mf.group(1); buf[cur] = [mf.group(2)] if mf.group(2) else []
        elif mo and cur in (None, "題目"):
            opts.append(mo.group(2).strip())
        elif cur:
            buf[cur].append(line)
    get = lambda k: "\n".join(buf.get(k, [])).strip()
    q["q"], q["o"] = get("題目"), opts
    if get("答案") not in ANS:
        sys.exit(f"Q{n}：答案不是 A–D")
    q["a"] = ANS[get("答案")]
    q["kp"] = get("考點")
    if get("翻譯"):
        q["trans"] = get("翻譯")
    e = get("解析")
    if get("Paraphrasing"):
        e += "\n\nParaphrasing：" + get("Paraphrasing")
    if e:
        q["e"] = e
    if get("詞彙"):
        q["voc"] = get("詞彙")
    q["tag"] = get("標籤")
    return q


def build(sec_id, ex_id, title):
    path = KB_R / f"{sec_id}.md"
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    fm = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not fm or not re.search(r"^status:\s*done\s*$", fm.group(1), re.M):
        print(f"略過 {sec_id}：校對稿還不是 status: done")
        return None
    passages, qs = [], []
    for g in re.split(r"^## ", text, flags=re.M)[1:]:
        head, _, body = g.partition("\n")
        if not head.startswith("題組："):
            continue
        part = 5 if "Part 5" in head else 6 if "Part 6" in head else 7
        p = None
        if part != 5:
            en = re.search(r"^(Questions \d+-\d+ refer to [^\n]+)$", body, re.M)
            art = after("文章", body)
            if part == 6:
                art = re.sub(r"---(\d+)---", r"{{\1}}", art)
            docs = [d.strip() for d in re.split(r"\n---\n", art)]
            P = {"en": en.group(1) if en else "", "kind": head[3:].split("（")[1].split("，")[0] if "（" in head else ""}
            if len(docs) > 1:
                P["docs"] = [{"text": d} for d in docs]
                P["text"] = "\n\n".join(docs)
            else:
                P["text"] = art
            tr = after("文章翻譯", body)
            if tr:
                P["trans"] = tr
            mv = re.search(r"^文章詞彙：(.*)$", body, re.M)
            if mv:
                P["voc"] = mv.group(1).strip()
            p = len(passages)
            passages.append(P)
        for qid, qb in re.findall(r"^### Q(\d+)\n(.*?)(?=^### |\Z)", body, re.S | re.M):
            q = parse_q(qid, qb)
            if len(q["o"]) != 4:
                sys.exit(f"{sec_id} Q{qid}：選項不是 4 個")
            item = {"n": int(qid), "part": part}
            if p is not None:
                item["p"] = p
            item.update({"g": q["tag"] or tag_for(part, q["kp"]), "q": q["q"], "o": q["o"], "a": q["a"]})
            for k in ("kp", "trans", "e", "voc"):
                if q.get(k):
                    item[k] = q[k]
            qs.append(item)
    nums = [q["n"] for q in qs]
    if nums != list(range(101, 201)):
        sys.exit(f"{sec_id}：題號不是 101–200 連續（共 {len(nums)} 題）")
    return {"id": ex_id, "title": title, "kind": "toeic", "part": 0, "mock": "reading",
            "sub": "Part 5–7 共 100 題．限時 75 分鐘．整份寫完交卷後檢討", "passages": passages, "qs": qs}


def main():
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    exams = [x for x in (build(*t) for t in TESTS) if x]
    out = {"about": "TOEIC 閱讀模擬考（Hackers 新制多益閱讀題庫大全｜實戰模擬試題 1–2）", "exams": exams}
    lines = ["{", f' "about":{json.dumps(out["about"], ensure_ascii=False)},', ' "exams":[']
    ex_txt = []
    for ex in exams:
        head = {k: v for k, v in ex.items() if k not in ("passages", "qs")}
        s = "  " + json.dumps(head, ensure_ascii=False, separators=(",", ":"))[:-1]
        s += ',"passages":[\n' + ",\n".join("   " + json.dumps(p, ensure_ascii=False, separators=(",", ":")) for p in ex["passages"]) + "\n  ]"
        s += ',"qs":[\n' + ",\n".join("   " + json.dumps(q, ensure_ascii=False, separators=(",", ":")) for q in ex["qs"]) + "\n  ]}"
        ex_txt.append(s)
    lines.append(",\n".join(ex_txt))
    lines += [" ]", "}"]
    OUT_JSON.parent.mkdir(exist_ok=True)
    OUT_JSON.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    for ex in exams:
        print(f"{ex['id']}：{len(ex['qs'])} 題、{len(ex['passages'])} 篇文章")
    print(f"已寫入 {OUT_JSON.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
