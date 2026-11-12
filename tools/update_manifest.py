"""檢查 data/ 的題庫，並更新 data/manifest.json 的版本雜湊 v。改完任何題庫 JSON 後都要執行。

用法（在專案資料夾執行）：
  py tools/update_manifest.py            檢查全部題庫；沒有問題就更新 manifest 與 tools/baseline.json
  py tools/update_manifest.py --check    只檢查，不寫入任何檔案
  py tools/update_manifest.py --accept   確認「既有題目被修改」的警告都是刻意的，照樣寫入

檢查項目：
  錯誤（不寫入，結束碼 1）
    JSON 格式、題組 id 重複、題目欄位（q／o／a／acc／g／p）、標籤 g 不在 tags.json、
    manifest 列的檔案不存在、題組被刪除或題數變少（作答紀錄以「題組id-題目順序」記錄）
  需要確認（不寫入，結束碼 2；確認是刻意修改後加 --accept）
    既有題目的題幹、正解位置 a 或正解文字和 tools/baseline.json 不同。
    多半代表題目被插入、刪除或調換順序，會讓舊的作答紀錄對到錯的題目。
  提醒（不影響寫入）
    同一題組題幹重複、private/ 的明文比加密檔新（要重新執行 encrypt_ai.py）等

tools/baseline.json 記錄每一題的題幹、正解位置與正解文字的短雜湊（不含題目內容），
用來比對既有題目有沒有被改動。新題接在題組最後面時會自動加入，不需要 --accept。
"""
import hashlib, json, os, re, sys, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
PRIVATE = os.path.join(ROOT, "private")
MANIFEST = os.path.join(DATA, "manifest.json")
BASELINE = os.path.join(ROOT, "tools", "baseline.json")
L = "ABCD"


def h(s, n=6):
    return hashlib.md5(re.sub(r"\s+", " ", str(s)).strip().encode("utf-8")).hexdigest()[:n]


def fingerprint(q):
    """題幹雜湊:正解位置:正解文字雜湊。Part 6／7 的題幹含文章索引 p，聽力 Part 3／4 含題組索引 s。"""
    o, a = q.get("o") or [], q.get("a")
    ans = o[a] if isinstance(a, int) and 0 <= a < len(o) else ""
    return f"{h(str(q.get('p', q.get('s', ''))) + '|' + q.get('q', ''))}:{a}:{h(ans, 4)}"


def load_json(path):
    with open(path, "rb") as f:
        raw = f.read()
    return raw, json.loads(raw.decode("utf-8-sig"))


def check_exam(ex, where, tags, err, note):
    if not isinstance(ex.get("id"), str) or not ex["id"]:
        err.append(f"{where}：題組缺少 id"); return
    if not isinstance(ex.get("qs"), list):
        err.append(f"{where} {ex['id']}：缺少 qs 陣列"); return
    passages = ex.get("passages")
    stems = collections.defaultdict(list)
    for i, q in enumerate(ex["qs"]):
        tag = f"{ex['id']}-{i}"
        if not isinstance(q, dict):
            err.append(f"{tag}：題目不是物件"); continue
        if not isinstance(q.get("q"), str) or (passages is None and not q["q"].strip()):
            err.append(f"{tag}：q（題幹）是空的")  # Part 6 的空格題沒有題幹，q 可以是空字串
        o = q.get("o")
        if not isinstance(o, list) or len(o) < 2 or not all(isinstance(x, str) and x.strip() for x in o):
            err.append(f"{tag}：o（選項）至少要兩個非空字串"); o = []
        elif len(o) > len(L):
            err.append(f"{tag}：選項超過 {len(L)} 個，網頁只顯示 A–D")
        elif len({x.strip().lower() for x in o}) != len(o):
            note.append(f"{tag}：選項文字重複 {o}")
        a = q.get("a")
        if not isinstance(a, int) or isinstance(a, bool) or not 0 <= a < len(o or [0]):
            err.append(f"{tag}：a（正解索引）必須是 0–{max(len(o), 1) - 1} 的整數，目前是 {a!r}")
        if "acc" in q:
            acc = q["acc"]
            if not isinstance(acc, list) or not acc or not all(isinstance(x, int) and 0 <= x < len(o) for x in acc):
                err.append(f"{tag}：acc 必須是選項索引的陣列，目前是 {acc!r}")
            elif a not in acc:
                err.append(f"{tag}：acc {acc} 沒有包含 a={a}")
        g = q.get("g")
        if not g:
            err.append(f"{tag}：缺少標籤 g")
        elif g not in tags:
            err.append(f"{tag}：標籤 {g} 不在 data/tags.json")
        if passages is not None and q.get("part") != 5:  # 閱讀模擬考的 Part 5 沒有文章
            p = q.get("p")
            if not isinstance(p, int) or not 0 <= p < len(passages):
                err.append(f"{tag}：p（文章索引）必須是 0–{len(passages) - 1}，目前是 {p!r}")
        elif ex.get("kind") == "toeic" and not ex.get("listen") and isinstance(q.get("q"), str):  # 考古題、指南與聽力題組原本就有相同標準問句，只查自編的 Part 5
            stems[re.sub(r"\W+", " ", q["q"].lower()).strip()].append(i)
    for idx in stems.values():
        if len(idx) > 1:
            note.append(f"{ex['id']}：題幹重複（第 {', '.join(str(i + 1) for i in idx)} 題）")


def compare(ex_id, fps, base, err, warn):
    old = base.get(ex_id)
    if old is None:
        return
    if len(fps) < len(old):
        err.append(f"{ex_id}：題數由 {len(old)} 變成 {len(fps)}。不可刪題，只能把新題加在最後面")
    changed = []
    for i, (new, was) in enumerate(zip(fps, old)):
        if new == was:
            continue
        ns, na, nt = new.split(":"); ws, wa, wt = was.split(":")
        why = []
        if ns != ws:
            moved = [j for j in (i - 1, i + 1) if 0 <= j < len(old) and old[j].split(":")[0] == ns]
            why.append("題幹不同" + ("，和原本第 %d 題相同（疑似插入、刪除或調換順序）" % (moved[0] + 1) if moved else ""))
        if na != wa:
            why.append(f"正解位置 {L[int(wa)] if wa.isdigit() and int(wa) < 4 else wa} → {L[int(na)] if na.isdigit() and int(na) < 4 else na}")
        elif nt != wt:
            why.append("正解文字不同")
        changed.append(f"{ex_id}-{i}（第 {i + 1} 題）：" + "、".join(why))
    if len(changed) > 10:
        warn.append(f"{ex_id}：{len(changed)} 題和 baseline 不同，前幾題：")
        warn.extend("  " + c for c in changed[:5])
    else:
        warn.extend(changed)


def main():
    for stream in (sys.stdout, sys.stderr):  # Windows 主控台預設 cp950，中文會變亂碼
        stream.reconfigure(encoding="utf-8")
    write = "--check" not in sys.argv
    accept = "--accept" in sys.argv
    err, warn, note = [], [], []

    m_raw, m = load_json(MANIFEST)
    base = json.load(open(BASELINE, encoding="utf-8"))["exams"] if os.path.exists(BASELINE) else {}
    listed = {f["path"] for f in m["files"]}
    for name in sorted(os.listdir(DATA)):
        if name.endswith(".json") and name != "manifest.json" and name not in listed:
            note.append(f"data/{name} 沒有列在 manifest.json，網頁不會載入")

    tags = {}
    tag_path = os.path.join(DATA, "tags.json")
    if os.path.exists(tag_path):
        tags.update(load_json(tag_path)[1].get("tags", {}))

    owner = {}            # 題組 id → 所在檔案，用來找重複
    fps_all = {}          # 題組 id → 每題指紋
    counts = collections.Counter()
    for f in m["files"]:
        path = os.path.join(DATA, f["path"])
        if not os.path.exists(path):
            err.append(f"manifest 列了 data/{f['path']}，但檔案不存在"); continue
        try:
            raw, d = load_json(path)
        except ValueError as e:
            err.append(f"data/{f['path']}：JSON 格式錯誤 {e}"); continue
        f["v"] = hashlib.md5(raw).hexdigest()[:8]
        where = f"data/{f['path']}"
        if d.get("enc"):
            # 加密檔：改用 private/ 的明文檢查內容
            plain = os.path.join(PRIVATE, f["path"].replace(".enc.json", ".json"))
            if not os.path.exists(plain):
                note.append(f"{where}：找不到 private/ 明文，只更新版本、不檢查內容")
                for x in f.get("exams", []):
                    if x in owner: err.append(f"題組 id {x} 重複：{owner[x]}、{where}")
                    owner[x] = where
                continue
            if os.path.getmtime(plain) > os.path.getmtime(path) + 1:
                note.append(f"private/{os.path.basename(plain)} 比 {where} 新：記得執行 py tools/encrypt_ai.py 重新加密")
            try:
                d = load_json(plain)[1]
            except ValueError as e:
                err.append(f"private/{os.path.basename(plain)}：JSON 格式錯誤 {e}"); continue
            ids = [x.get("id") for x in d.get("exams", [])]
            if ids != f.get("exams"):
                note.append(f"{where}：manifest 的題組清單和 private/ 不同，請執行 py tools/encrypt_ai.py")
            where = f"private/{os.path.basename(plain)}"
        else:
            f["exams"] = [x.get("id") for x in d.get("exams", [])]
        tags.update(d.get("tags", {}) if f["path"] != "tags.json" else {})
        for ex in d.get("exams", []):
            check_exam(ex, where, tags, err, note)
            eid = ex.get("id")
            if not eid or not isinstance(ex.get("qs"), list):
                continue
            if eid in owner:
                err.append(f"題組 id {eid} 重複：{owner[eid]}、{where}（後載入的會蓋掉前面的）")
            owner[eid] = where
            fps_all[eid] = [fingerprint(q) if isinstance(q, dict) else "" for q in ex["qs"]]
            counts[where] += len(ex["qs"])

    for eid in base:
        if eid not in owner:
            err.append(f"題組 {eid} 不見了。不可刪除或改名題組 id（會遺失作答紀錄）")
    for eid, fps in fps_all.items():
        compare(eid, fps, base, err, warn)

    for title, items in (("提醒", note), ("需要確認", warn), ("錯誤", err)):
        if items:
            print(f"\n【{title}】{len(items)} 項")
            for x in items[:200]:
                print("  " + x)
            if len(items) > 200:
                print(f"  ……另有 {len(items) - 200} 項")
    print("\n題數：" + "、".join(f"{k} {v}" for k, v in counts.items()) + f"；合計 {sum(counts.values())} 題")

    if err:
        sys.exit("\n有錯誤，沒有寫入任何檔案。修正後再執行一次。")
    if warn and not accept:
        print("\n既有題目和 baseline 不同，沒有寫入。")
        print("如果是刻意修改（例如修正錯字、更正答案），確認後執行：py tools/update_manifest.py --accept")
        print("如果是不小心插入或調換了題目，請把新題移到題組最後面。")
        sys.exit(2)
    if not write:
        print("\n檢查通過（--check：沒有寫入）。"); return

    lines = ["{", f' "about":{json.dumps(m["about"], ensure_ascii=False)},', ' "files":[']
    lines.append(",\n".join("  " + json.dumps(f, ensure_ascii=False, separators=(",", ":")) for f in m["files"]))
    lines += [" ]", "}"]
    out = "\n".join(lines) + "\n"
    if out.encode("utf-8") != m_raw:
        open(MANIFEST, "w", encoding="utf-8", newline="\n").write(out)
        print("\n已更新 data/manifest.json")
    else:
        print("\nmanifest.json 沒有變動")

    merged = dict(base)
    merged.update(fps_all)
    b = ['{', ' "about":"update_manifest.py 用來比對既有題目是否被改動的指紋（題幹雜湊:正解索引:正解文字雜湊）。不要手動修改。",', ' "exams":{']
    b.append(",\n".join(f"  {json.dumps(k)}:{json.dumps(v, separators=(',', ':'))}" for k, v in merged.items()))
    b += [" }", "}"]
    open(BASELINE, "w", encoding="utf-8", newline="\n").write("\n".join(b) + "\n")
    print("已更新 tools/baseline.json")


if __name__ == "__main__":
    main()
