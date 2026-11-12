"""紅藍本聽力音檔的逐題時戳：用語音辨識找出每題「Number N」、每個題組「Questions X through Y」在音檔中的秒數。

輸入：private/toeic_listening.json（由 build_listening_quiz.py 產生，決定每個音檔該有哪些題號）
輸出：private/TOEIC/TOEIC紅藍本/kb/audio_ts.json（自動產生，不要手改）
人工修正：private/TOEIC/TOEIC紅藍本/kb/audio_ts_fix.json（選用，格式同 audio_ts.json 的 q／s，會覆蓋偵測結果）
辨識逐字稿快取：private/TOEIC/TOEIC紅藍本/kb/_work/ts/（重跑時不必重新辨識）

用法：
  py tools/listening_ts.py                 # 辨識尚未快取的音檔，再重算全部時戳並列出問題
  py tools/listening_ts.py --only 關鍵字    # 只處理路徑含關鍵字的音檔
  py tools/listening_ts.py --redo 關鍵字    # 刪掉符合音檔的快取並重新辨識
  py tools/listening_ts.py --check         # 不辨識，只用現有快取重算並列出問題

audio_ts.json 每個音檔一行：
  dur：音檔長度（秒）
  q：Part 1／2 每題（以及 Part 3／4 念題目時）的開始秒數，鍵是題號
  s：Part 3／4 每個題組（Questions X through Y）的開始秒數，鍵是題組第一題的題號
  est：沒偵測到、用前後題推估的題號（q 的鍵或 "s32" 這種題組鍵）
結束時間＝下一個標記的開始時間，最後一個到 dur。
需要 faster-whisper（small 模型）與 PyAV。

各 10 回（國際學村）聽力：加 --book toeic10，音檔改用 參考書/TOEIC/聽力閱讀各 10 回/聽力/聽力模擬國際學村/TESTNN.mp3，
每回固定 Part 1 1–6、Part 2 7–31（q），Part 3／4 題組 32–98（s），不需要題庫 JSON：
  py tools/listening_ts.py --book toeic10 [--only TEST03]
  輸出 private/toeic_md/listening/audio_ts.json；修正 audio_ts_fix.json；快取 private/toeic_md/_work/ts/
"""
import argparse, hashlib, json, pathlib, re, statistics, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
PRIVATE_ROOT = ROOT / "private" / "TOEIC" / "TOEIC紅藍本"
AUDIO_DIR = PRIVATE_ROOT / "聽力"
QUIZ_JSON = ROOT / "private" / "toeic_listening.json"
OUT_JSON = PRIVATE_ROOT / "kb" / "audio_ts.json"
FIX_JSON = PRIVATE_ROOT / "kb" / "audio_ts_fix.json"
CACHE_DIR = PRIVATE_ROOT / "kb" / "_work" / "ts"

ONES = {"zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
        "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
        "seventeen": 17, "eighteen": 18, "nineteen": 19}
TENS = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
# 辨識常把「Number two」聽成「Number to」，只在關鍵字後第一個數字接受這些同音字
HOMOPHONES = {"to": 2, "too": 2, "won": 1, "for": 4, "fore": 4, "ate": 8}
LINKS = {"through", "thru", "to", "and"}


def use_toeic10():
    """切換成各 10 回聽力（國際學村）：每回一個完整音檔。"""
    global AUDIO_DIR, OUT_JSON, FIX_JSON, CACHE_DIR, ABOUT, expected_marks
    AUDIO_DIR = ROOT / "參考書" / "TOEIC" / "聽力閱讀各 10 回" / "聽力" / "聽力模擬國際學村"
    md = ROOT / "private" / "toeic_md"
    OUT_JSON = md / "listening" / "audio_ts.json"
    FIX_JSON = md / "listening" / "audio_ts_fix.json"
    CACHE_DIR = md / "_work" / "ts"
    ABOUT = "各 10 回聽力音檔逐題時戳（秒）。由 tools/listening_ts.py --book toeic10 產生，不要手改；修正請寫在 audio_ts_fix.json"
    marks = {"q": list(range(1, 32)), "s": list(range(32, 99, 3))}
    expected_marks = lambda: {f"TEST{n:02d}.mp3": marks for n in range(1, 11)
                              if (AUDIO_DIR / f"TEST{n:02d}.mp3").exists()}


ABOUT = "紅藍本聽力音檔逐題時戳（秒）。由 tools/listening_ts.py 產生，不要手改；修正請寫在 audio_ts_fix.json"


def expected_marks():
    """回傳 {音檔相對路徑: {"q": [題號…], "s": [題組首題號…]}}。"""
    d = json.loads(QUIZ_JSON.read_text(encoding="utf-8"))
    exp = {}

    def add(path, qs):
        if not path:
            return
        e = exp.setdefault(path, {"q": set(), "s": set()})
        for q in qs:
            if q["part"] in (1, 2):
                e["q"].add(q["n"])
            elif "s" in q and q["n"] == min(x["n"] for x in qs if x.get("s") == q["s"]):
                e["s"].add(q["n"])

    for ex in d["exams"]:
        add(ex.get("audio"), ex["qs"])
        add(ex.get("audioAlt"), ex["qs"])
        for p, pa in (ex.get("partAudios") or {}).items():
            pqs = [q for q in ex["qs"] if q["part"] == int(p)]
            add(pa.get("audio"), pqs)
            add(pa.get("audioAlt"), pqs)
    return {k: {"q": sorted(v["q"]), "s": sorted(v["s"])} for k, v in exp.items()}


def cache_path(rel):
    return CACHE_DIR / (hashlib.md5(rel.encode("utf-8")).hexdigest()[:12] + ".json")


def decode(path):
    # faster-whisper 內建的 decode_audio 與目前安裝的 PyAV 版本不合，自己解碼成 16 kHz 單聲道
    import av, numpy as np
    with av.open(str(path)) as c:
        rs = av.AudioResampler(format="s16", layout="mono", rate=16000)
        buf = [o.to_ndarray().reshape(-1) for fr in c.decode(audio=0) for o in rs.resample(fr)]
    return np.concatenate(buf).astype(np.float32) / 32768.0


_model = None


def transcribe(rel):
    global _model
    if _model is None:
        from faster_whisper import WhisperModel
        _model = WhisperModel("small", device="cpu", compute_type="int8")
    audio = decode(AUDIO_DIR / rel)
    # beam_size=1 或關掉 condition_on_previous_text 會讓「Number N」更常被漏掉，維持預設值
    segs, info = _model.transcribe(audio, language="en", word_timestamps=True)
    words = [[w.word, round(w.start, 2), round(w.end, 2)] for s in segs for w in (s.words or [])]
    data = {"audio": rel, "dur": round(info.duration, 2), "words": words}
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path(rel).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


def tokens(words):
    """把辨識結果拆成 (小寫 token, 開始秒數, 是否句首)；"32-34" 拆成 32、-、34，"thirty-two" 拆成 thirty、two。"""
    out = []
    prev = "."
    for w, st, en in words:
        # 段落第一個字的開始時間常被拉到前面的空白裡（「number」變成 5 秒長），改用結束時間往前推
        st = max(st, en - 0.9)
        bos = bool(re.search(r"[.?!]\s*$", prev))
        w2 = w.lower().replace("–", "-").replace("—", "-")
        for k, part in enumerate(re.findall(r"[a-z]+|\d+|-", w2)):
            out.append((part, st, bos and k == 0))
        prev = w
    return out


def parse_num(toks, i, first=True):
    """從 toks[i] 起讀一個 1–100 的數字，回傳 (值, 下一個位置) 或 (None, i)。"""
    if i >= len(toks):
        return None, i
    t = toks[i][0]
    if t.isdigit():
        return int(t), i + 1
    if t == "hundred" or (t == "one" and i + 1 < len(toks) and toks[i + 1][0] == "hundred"):
        return 100, i + (1 if t == "hundred" else 2)
    if t in TENS:
        v = TENS[t]
        j = i + 2 if i + 1 < len(toks) and toks[i + 1][0] == "-" else i + 1  # twenty-one 會被拆成 twenty、-、one
        if j < len(toks) and toks[j][0] in ONES and 0 < ONES[toks[j][0]] < 10:
            return v + ONES[toks[j][0]], j + 1
        return v, i + 1
    if t in ONES:
        return ONES[t], i + 1
    if first and t in HOMOPHONES:
        return HOMOPHONES[t], i + 1
    return None, i


def find_candidates(words):
    """回傳 (類型, 題號, 秒數, 強弱) 清單；類型 q＝Number N，s＝Questions X through Y。
    強＝有 Number／Questions 關鍵字；弱＝辨識漏掉關鍵字、只剩句首的「11.」或「16-18. Refer to」。"""
    toks = tokens(words)
    cands = []
    for i, (t, st, bos) in enumerate(toks):
        if t in ("number", "question", "questions"):
            n, j = parse_num(toks, i + 1)
            if n is None:
                continue
            if t.startswith("question") and j < len(toks) and (toks[j][0] in LINKS or toks[j][0] == "-"):
                m, _ = parse_num(toks, j + 1, first=False)
                if m is not None:  # 後一個數字常聽錯（16 through 15），不檢查
                    cands.append(("s", n, st, 1))
                    continue
            if t != "questions":
                cands.append(("q", n, st, 1))
        elif t.isdigit() and (bos or (i > 0 and toks[i - 1][0] not in ("number", "question", "questions")
                                      and i + 1 < len(toks) and toks[i + 1][0] == "-")):
            n = int(t)
            if i + 2 < len(toks) and toks[i + 1][0] in ("-", "through", "to"):
                m, j = parse_num(toks, i + 2, first=False)
                if m is not None and 0 < m - n <= 3 and j < len(toks) and toks[j][0] == "refer":
                    cands.append(("s", n, st, 0))
                    continue
            if bos:
                cands.append(("q", n, st, 0))
    return cands


def pick(cands, kind, wanted):
    """依時間順序替每個期望題號挑一個偵測結果，維持遞增；回傳 {題號: 秒數}。
    先只用強標記，缺的再到前後兩題之間找弱標記。"""
    got = {}
    strong = sorted((st, n) for k, n, st, s in cands if k == kind and n in wanted and s)
    weak = sorted((st, n) for k, n, st, s in cands if k == kind and n in wanted and not s)
    last = -1.0
    for n in sorted(wanted):
        hits = [st for st, m in strong if m == n and st > last]
        if hits:
            got[n] = hits[0]
            last = hits[0]
    # 若某題的時間比後面已確定的題目晚（被誤認），丟掉讓它進入推估
    keys = sorted(got)
    for a, b in zip(keys, keys[1:]):
        if got[a] >= got[b]:
            got.pop(a)
    for n in sorted(wanted):
        if n in got:
            continue
        lo = max((got[k] for k in got if k < n), default=-1.0)
        hi = min((got[k] for k in got if k > n), default=float("inf"))
        hits = [st for st, m in weak if m == n and lo < st < hi]
        if hits:
            got[n] = hits[0]
    return got


def gap_starts(words, lo, hi, k):
    """在 (lo, hi) 之間找 k 個最長的無聲空檔（相鄰兩字的間隔），回傳空檔後第一個字的開始秒數。"""
    gaps = [(words[i + 1][1] - words[i][2], words[i + 1][1]) for i in range(len(words) - 1)
            if lo + 3 < words[i + 1][1] < hi - 3]
    gaps = [g for g in gaps if g[0] >= 1.5]
    if len(gaps) < k:
        return None
    return sorted(st for _, st in sorted(gaps, reverse=True)[:k])


def estimate(marks, wanted, dur, words):
    """沒偵測到的題號：前後都有已知題號時，取兩者之間最長的幾個無聲空檔；找不到就線性內插。
    回傳 (完整 {題號: 秒數}, 推估的題號)。"""
    est = []
    full = dict(marks)
    known = sorted(marks)
    if not known:
        return full, sorted(wanted)
    missing = [n for n in sorted(wanted) if n not in marks]
    # 連續缺漏的題號一起處理
    runs = []
    for n in missing:
        if runs and runs[-1][-1] + 1 == n:
            runs[-1].append(n)
        else:
            runs.append([n])
    for run in runs:
        lo = max((k for k in known if k < run[0]), default=None)
        hi = min((k for k in known if k > run[-1]), default=None)
        if lo is not None and hi is not None and hi - lo == len(run) + 1:
            sts = gap_starts(words, marks[lo], marks[hi], len(run))
            if sts:
                full.update(zip(run, sts))
    for n in missing:
        est.append(n)
        if n in full:
            continue
        lo = max((k for k in known if k < n), default=None)
        hi = min((k for k in known if k > n), default=None)
        if lo is not None and hi is not None:
            full[n] = marks[lo] + (marks[hi] - marks[lo]) * (n - lo) / (hi - lo)
        elif lo is not None:
            gap = statistics.median([marks[b] - marks[a] for a, b in zip(known, known[1:])]) if len(known) > 1 else 20
            full[n] = min(marks[lo] + gap * (n - lo), dur - 1)
        else:
            gap = statistics.median([marks[b] - marks[a] for a, b in zip(known, known[1:])]) if len(known) > 1 else 20
            full[n] = max(marks[hi] - gap * (hi - n), 0)
    return full, est


def odd_gaps(marks, dur):
    """間隔明顯偏離中位數（< 45% 或 > 220%）的題號。"""
    keys = sorted(marks)
    if len(keys) < 3:
        return []
    ends = [marks[b] for b in keys[1:]] + [dur]
    gaps = [e - marks[k] for k, e in zip(keys, ends)]
    med = statistics.median(gaps[:-1])
    return [k for k, g in zip(keys[:-1], gaps[:-1]) if g < med * 0.45 or g > med * 2.2]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--redo")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--book", choices=["redblue", "toeic10"], default="redblue")
    args = ap.parse_args()
    if args.book == "toeic10":
        use_toeic10()

    exp = expected_marks()
    fixes = json.loads(FIX_JSON.read_text(encoding="utf-8")) if FIX_JSON.exists() else {}
    fixes.pop("about", None)
    todo = [r for r in exp if not args.only or args.only in r]

    if not args.check:
        for rel in todo:
            if args.redo and args.redo in rel and cache_path(rel).exists():
                cache_path(rel).unlink()
        need = [r for r in todo if not cache_path(r).exists()]
        for k, rel in enumerate(need, 1):
            t0 = time.time()
            data = transcribe(rel)
            print(f"[{k}/{len(need)}] {rel}（{data['dur']:.0f} 秒，辨識 {time.time() - t0:.0f} 秒）", flush=True)

    out = json.loads(OUT_JSON.read_text(encoding="utf-8")) if OUT_JSON.exists() else {}
    out.pop("about", None)
    problems = []
    by_gap = []  # 沒聽到「Questions X through Y」，改用上一題後的空檔判定的題組
    for rel in todo:
        cp = cache_path(rel)
        if not cp.exists():
            problems.append(f"{rel}：還沒辨識")
            continue
        data = json.loads(cp.read_text(encoding="utf-8"))
        cands = find_candidates(data["words"])
        dur = data["dur"]
        fx = fixes.get(rel, {})
        entry = {"dur": dur}
        est_all = []
        # Part 3／4：念題目的 Number N 也記下來（之後可單獨重播題目），不要求、不推估
        reads = pick(cands, "q", {n for s in exp[rel]["s"] for n in range(s, s + 3)})
        for kind in ("q", "s"):
            wanted = exp[rel][kind]
            if not wanted:
                if kind == "q" and reads:
                    entry["q"] = {str(n): round(v, 1) for n, v in sorted(reads.items())}
                continue
            got = pick(cands, kind, set(wanted))
            if kind == "s":
                # 辨識常把「Questions 7 through 9 refer to…」縮成「7.」：改用上一題念完後的第一個長空檔
                for n in wanted:
                    if n not in got and n - 1 in reads:
                        nxt = [w[1] for i, w in enumerate(data["words"][1:], 1)
                               if w[1] > reads[n - 1] and w[1] - data["words"][i - 1][2] >= 4]
                        if nxt and all(nxt[0] < v for k, v in got.items() if k > n):
                            got[n] = nxt[0]
                            by_gap.append(f"{rel}：題組 {n}")
            for n, v in fx.get(kind, {}).items():
                got[int(n)] = float(v)
            full, est = estimate(got, wanted, dur, data["words"])
            est_all += [str(n) if kind == "q" else f"s{n}" for n in est]
            label = "題" if kind == "q" else "題組"
            if est:
                problems.append(f"{rel}：{label} {', '.join(map(str, est))} 沒偵測到，已用前後推估")
            odd = [n for n in odd_gaps(full, dur) if n not in est]
            if odd:
                problems.append(f"{rel}：{label} {', '.join(map(str, odd))} 的長度不尋常，請抽聽確認")
            if kind == "q":
                full.update(reads)
            entry[kind] = {str(n): round(v, 1) for n, v in sorted(full.items())}
        if est_all:
            entry["est"] = est_all
        out[rel] = entry

    lines = ["{", f' "about":{json.dumps(ABOUT, ensure_ascii=False)},']
    body = [f" {json.dumps(k, ensure_ascii=False)}:{json.dumps(out[k], ensure_ascii=False, separators=(',', ':'))}"
            for k in sorted(out)]
    lines.append(",\n".join(body))
    lines.append("}")
    OUT_JSON.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    n_files = len(todo)
    print(f"已寫入 {OUT_JSON.relative_to(ROOT)}：{n_files} 個音檔")
    if by_gap:
        print(f"以上一題後的空檔判定開頭的題組 {len(by_gap)} 個（通常可信）：")
        for p in by_gap:
            print("  " + p)
    if problems:
        print(f"需要確認 {len(problems)} 項：")
        for p in problems:
            print("  " + p)
    else:
        print("全部題號都偵測到，沒有可疑間隔。")


if __name__ == "__main__":
    main()
