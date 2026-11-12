"""TOEIC Part 5 單字題（data/toeic_p5_words.json）的檢查與新增工具。

用法（在專案資料夾執行）：
  py tools/p5_words.py check                 檢查整個題庫，並印出涵蓋率
  py tools/p5_words.py add 草稿.json          把草稿題目接在各 Day 題組最後面，更新 manifest 版本
  py tools/p5_words.py add 草稿.json --dry    只檢查草稿，不寫入
  py tools/p5_words.py rewrite 草稿.json      改寫既有題目的「其他選項」說明（w），不動題目與選項
  py tools/p5_words.py version               手動修改題庫後，統一格式並更新 manifest 版本

草稿格式（JSON 陣列，一題一個物件；正解一律寫在 o 的第一個）：
  {"day":5,"p":"v","q":"…_______…","o":["正解","誤1","誤2","誤3"],
   "t":"中文翻譯","e":"【線索】…【正解】正解（中文）…",
   "w":[["(v.) 誤1的中文釋義。","常考搭配，以及放進本題錯在哪裡"],["…","…"],["…","…"]]}
  p：n 名詞／v 動詞／a 形容詞／d 副詞／p 片語
  可選 target：教材完整詞條。片語只挖一個字時必填，例如 target="in lieu of"、正解 lieu。
新增時正解會放到該題組目前最少的位置（A–D 平均），其餘選項隨機排列；不會動到既有題目。

rewrite 草稿格式：{"p5_w01":{"1":{"B":["(adj.) 充足的。","常用於 plentiful supply …"],"C":[…],"D":[…]}}}
  外層是題組 id，內層是第幾題（從 1 起算），再來是錯誤選項的字母。

其他選項說明（w）的格式：每個錯誤選項兩行，依 A–D 順序，行與行用換行分開。
  (A) afflict (v.) 折磨、使痛苦。
  → 常用於疾病或災難折磨人（be afflicted with …）；demand 是市場需求，不是會受苦的人。
  第一行：選項字、詞性（n./v./adj./adv./prep./conj./pron.，可多個）、中文釋義。
  第二行：常考搭配或固定用法，再直接點出錯在哪裡（詞性不符、搭配對象錯、易混淆字）。
  不可用「不搭配…」「不符合題意／句意」這類沒有資訊的套話。
"""
import json, os, re, sys, random, hashlib, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "toeic_p5_words.json")
MANIFEST = os.path.join(ROOT, "data", "manifest.json")
VOCAB = os.path.join(ROOT, "private", "TOEIC_Vocabulary_Day1-30.md")
L = "ABCD"
POS = {"n": "t_p5wn", "v": "t_p5wv", "a": "t_p5wa", "d": "t_p5wd", "p": "t_p5wp"}
TAG2POS = {v: k for k, v in POS.items()}
HINT = {
    "n": "四個選項都是名詞 → 看空格前後的動詞、形容詞與介系詞，判斷需要哪一個意思的名詞。",
    "v": "四個選項都是動詞 → 看受詞是什麼、主詞做什麼動作，以及後面接的介系詞。",
    "a": "四個選項都是形容詞 → 看它修飾的名詞或主詞，以及句中說明原因或結果的線索字。",
    "d": "四個選項都是副詞 → 看它修飾的動詞或形容詞，以及句子要表達的程度、時間或方式。",
    "p": "把選項放回空格，還原完整片語；核對固定搭配、前後結構及商務情境，選出唯一合適的字。",
}
BE = {"be", "is", "are", "was", "were", "been"}
POS_RE = r"\((?:n|v|adj|adv|prep|conj|pron)\.\)"
BANNED = ["不搭配", "題意", "句意", "字表"]                # 沒有資訊的套話
IRREG = {"came": "come", "fell": "fall", "took": "take", "made": "make", "gave": "give", "got": "get", "ran": "run"}


def load_vocab():
    days, cur = {}, None
    for line in open(VOCAB, encoding="utf-8"):
        m = re.match(r"## Day (\d+)$", line.strip())
        if m:
            cur = int(m.group(1)); days[cur] = set()
        elif cur and line.startswith("| ") and not line.startswith("| 單字"):
            days[cur].add(re.sub(r"（.*?）", "", line.split("|")[1]).strip().lower())
    return days


def in_list(ans, words):
    """答案（可能是變化形，例如 postponed、slipped my mind）是否為教材單字。"""
    a = " ".join(IRREG.get(x, x) for x in ans.lower().split())
    for w in words:
        if a == w: return True
        if " " not in w and " " not in a:
            if len(w) >= 4 and a.startswith(w[:max(4, len(w) - 2)]): return True
            if len(w) == 3 and a.startswith(w) and len(a) <= 6: return True
        else:
            aw = [x for x in a.split() if x not in BE] or a.split()
            ww = [x for x in w.split() if x not in BE] or w.split()
            if a in w or w in a or (aw[0][:4] == ww[0][:4] and aw[-1] == ww[-1]): return True
    return False


def norm(s): return re.sub(r"\W+", " ", (s or "").lower()).strip()


def other_questions():
    seen = set()
    for f in os.listdir(os.path.join(ROOT, "data")):
        if f.startswith("toeic") and f.endswith(".json") and f != "toeic_p5_words.json":
            for x in json.load(open(os.path.join(ROOT, "data", f), encoding="utf-8")).get("exams", []):
                seen |= {norm(q.get("q")) for q in x["qs"]}
    return seen


def check_item(tag, q, o, ans, e, w_text, days, day, target=None, pos=None):
    """回傳問題清單。o 為四個選項，ans 為正解文字。"""
    bad = []
    if q.count("_______") != 1: bad.append("空格不是剛好一個 _______")
    if len(o) != 4 or len({x.lower() for x in o}) != 4: bad.append(f"選項需四個且不重複：{o}")
    if not e.startswith("【線索】") or "【正解】" not in e: bad.append("詳解要用「【線索】…【正解】…」格式")
    if ans.lower() not in e.lower(): bad.append(f"詳解沒有提到正解 {ans}")
    if re.search(r"\([A-D]\)", e): bad.append("詳解不可寫選項字母（選項會打亂）")
    tested = target or ans
    if not in_list(tested, days.get(day, set())): bad.append(f"教材詞條 {tested} 不在 Day {day} 單字表")
    if target:
        # The target records the whole phrase, not just its tested component.
        t = norm(target)
        if " " in t:
            before, after = q.split("_______", 1) if q.count("_______") == 1 else (q, "")
            left, middle, right = norm(before).split(), norm(ans).split(), norm(after).split()
            tokens, target_tokens = left + middle + right, t.split()
            restored = any(tokens[i:i + len(target_tokens)] == target_tokens
                           and i <= len(left) and len(left) + len(middle) <= i + len(target_tokens)
                           for i in range(len(tokens) - len(target_tokens) + 1))
            if not restored:
                bad.append(f"填入正解後未還原完整教材片語 {target}")
        elif not in_list(ans, {target.lower()}):
            bad.append(f"正解 {ans} 與教材詞條 {target} 不符")
    if pos == "p":
        if len(ans.split()) != 1: bad.append("片語題需只挖一個字，不能把整段片語當正解")
        if any(len(option.split()) != 1 for option in o): bad.append("片語題的四個選項都必須是單一字詞")
        if not target: bad.append("單字挖空的片語題必須記錄完整 target")
    return [f"{tag}：{b}" for b in bad]


def w_text(o, a, pairs):
    """pairs：依 A–D 順序、略過正解的 [釋義行, 說明行]，組成 w 字串。"""
    wrong = [j for j in range(4) if j != a]
    return "\n".join(f"({L[j]}) {o[j]} {d}\n→ {r}" for j, (d, r) in zip(wrong, pairs))


def check_w(o, a, w):
    """檢查其他選項說明的格式，回傳問題清單。"""
    bad, lines = [], w.split("\n")
    wrong = [j for j in range(4) if j != a]
    if len(lines) != 6: return [f"其他選項說明要 6 行（每個錯誤選項 2 行），目前 {len(lines)} 行"]
    for k, j in enumerate(wrong):
        head, why = lines[2 * k], lines[2 * k + 1]
        if not re.match(re.escape(f"({L[j]}) {o[j]} ") + POS_RE + r" \S", head):
            bad.append(f"第 {2*k+1} 行要是「({L[j]}) {o[j]} (詞性.) 中文釋義」：{head}")
        if not why.startswith("→ ") or len(why) < 12: bad.append(f"第 {2*k+2} 行要以「→ 」開頭並寫出搭配與錯誤原因：{why}")
    bad += [f"不可使用套話「{b}」" for b in BANNED if b in w]
    return bad


def write_data(d):
    with open(DATA, "w", encoding="utf-8", newline="\n") as f:
        f.write('{"about":' + json.dumps(d["about"], ensure_ascii=False) + ',"exams":[\n')
        for j, x in enumerate(d["exams"]):
            head = json.dumps({k: v for k, v in x.items() if k != "qs"}, ensure_ascii=False)[:-1]
            f.write(" " + head + ',"qs":[\n' + ",\n".join("   " + json.dumps(q, ensure_ascii=False) for q in x["qs"]) + "\n ]}" + ("," if j < len(d["exams"]) - 1 else "") + "\n")
        f.write("]}\n")
    v = hashlib.md5(open(DATA, "rb").read()).hexdigest()[:8]
    m = open(MANIFEST, encoding="utf-8").read()
    m2 = re.sub(r'("path":"toeic_p5_words\.json".*?"v":")[0-9a-f]{8}"', lambda mm: mm.group(1) + v + '"', m, count=1)
    open(MANIFEST, "w", encoding="utf-8", newline="\n").write(m2)
    return v


def cmd_check():
    days, d, others = load_vocab(), json.load(open(DATA, encoding="utf-8")), other_questions()
    probs, seen, answers, dist = [], set(), set(), collections.Counter()
    for x in d["exams"]:
        day = int(x["id"][-2:])
        for i, q in enumerate(x["qs"]):
            tag = f"{x['id']} 第 {i+1} 題"
            if not isinstance(q.get("a"), int) or not 0 <= q["a"] < len(q.get("o", [])):
                probs.append(f"{tag}：正解索引無效"); continue
            ans = q["o"][q["a"]]; dist[q["a"]] += 1; answers.add((day, (q.get("target") or ans).lower()))
            probs += check_item(tag, q["q"], q["o"], ans, q["e"], q["w"], days, day, q.get("target"), TAG2POS.get(q["g"]))
            if q["g"] not in TAG2POS: probs.append(f"{tag}：標籤 {q['g']} 不是 t_p5w*")
            probs += [f"{tag}：{b}" for b in check_w(q["o"], q["a"], q["w"])]
            k = norm(q["q"])
            if k in seen or k in others: probs.append(f"{tag}：題目與既有題目重複")
            seen.add(k)
    total_words = sum(len(v) for v in days.values())
    print(f"題組 {len(d['exams'])}，題目 {sum(len(x['qs']) for x in d['exams'])}，答案位置 A–D：{[dist[i] for i in range(4)]}")
    print(f"教材單字（各 Day 合計）{total_words}，已當正解考過約 {len(answers)}")
    print("\n".join(probs) or "沒有問題")
    return not probs


def cmd_add(path, dry):
    days, d, others = load_vocab(), json.load(open(DATA, encoding="utf-8")), other_questions()
    exams = {int(x["id"][-2:]): x for x in d["exams"]}
    seen = others | {norm(q["q"]) for x in d["exams"] for q in x["qs"]}
    draft, probs = json.load(open(path, encoding="utf-8-sig")), []  # 容許 Windows 編輯器加的 BOM
    for n, it in enumerate(draft, 1):
        tag = f"草稿第 {n} 題"
        need = {"day", "p", "q", "o", "t", "e", "w"}
        if not need <= set(it) or set(it) - need - {"target"}: probs.append(f"{tag}：必要欄位是 {sorted(need)}，另可加 target"); continue
        if it["day"] not in exams: probs.append(f"{tag}：沒有 Day {it['day']}")
        if it["p"] not in POS: probs.append(f"{tag}：p 要是 n/v/a/d/p")
        if len(it["w"]) != 3 or any(not isinstance(p, list) or len(p) != 2 for p in it["w"]):
            probs.append(f"{tag}：w 要有三組 [釋義行, 說明行]"); continue
        if re.search(r"\([A-D]\)", json.dumps(it["w"], ensure_ascii=False)): probs.append(f"{tag}：理由不可寫選項字母")
        probs += [f"{tag}：{b}" for b in check_w(it["o"], 0, w_text(it["o"], 0, it["w"]))]
        probs += check_item(tag, it["q"], it["o"], it["o"][0], it["e"], "", days, it["day"], it.get("target"), it["p"])
        if norm(it["q"]) in seen: probs.append(f"{tag}：題目與既有題目重複")
        seen.add(norm(it["q"]))
    if probs:
        print("\n".join(probs)); return False
    rnd = random.Random()
    for it in draft:
        x = exams[it["day"]]
        cnt = collections.Counter(q["a"] for q in x["qs"])
        a = min(range(4), key=lambda k: (cnt[k], rnd.random()))
        rest = list(zip(it["o"][1:], it["w"])); rnd.shuffle(rest)
        order = rest[:a] + [(it["o"][0], None)] + rest[a:]
        o = [o for o, _ in order]
        x["qs"].append({"g": POS[it["p"]], "q": it["q"], "o": o, "a": a, "h": HINT[it["p"]],
                        "trans": it["t"], "e": it["e"], "w": w_text(o, a, [r for _, r in order if r is not None])})
        if it.get("target"): x["qs"][-1]["target"] = it["target"]
    if dry:
        print(f"草稿 {len(draft)} 題檢查通過（--dry，未寫入）"); return True
    v = write_data(d)
    print(f"已新增 {len(draft)} 題，manifest 版本 v = {v}")
    return True


def cmd_rewrite(path, dry):
    d = json.load(open(DATA, encoding="utf-8"))
    exams, probs, n = {x["id"]: x for x in d["exams"]}, [], 0
    for eid, items in json.load(open(path, encoding="utf-8-sig")).items():
        if eid not in exams: probs.append(f"沒有題組 {eid}"); continue
        for k, pairs in items.items():
            tag, qs = f"{eid} 第 {k} 題", exams[eid]["qs"]
            if not k.isdigit() or not 1 <= int(k) <= len(qs): probs.append(f"{tag}：題號不存在"); continue
            q = qs[int(k) - 1]
            wrong = [L[j] for j in range(4) if j != q["a"]]
            if sorted(pairs) != wrong: probs.append(f"{tag}：要寫錯誤選項 {wrong}，草稿是 {sorted(pairs)}"); continue
            w = w_text(q["o"], q["a"], [pairs[c] for c in wrong])
            b = check_w(q["o"], q["a"], w)
            if b: probs += [f"{tag}：{x}" for x in b]; continue
            q["w"], n = w, n + 1
    if probs:
        print("\n".join(probs)); return False
    if dry:
        print(f"{n} 題檢查通過（--dry，未寫入）"); return True
    print(f"已改寫 {n} 題，manifest 版本 v = {write_data(d)}")
    return True


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["rewrite"] and len(args) >= 2:
        sys.exit(0 if cmd_rewrite(args[1], "--dry" in args) else 1)
    if args[:1] == ["check"]:
        sys.exit(0 if cmd_check() else 1)
    if args[:1] == ["version"]:  # 手動改過 data/toeic_p5_words.json 後，重寫檔案並更新 manifest 版本
        print("manifest 版本 v =", write_data(json.load(open(DATA, encoding="utf-8")))); sys.exit(0)
    if args[:1] == ["add"] and len(args) >= 2:
        sys.exit(0 if cmd_add(args[1], "--dry" in args) else 1)
    print(__doc__); sys.exit(2)
