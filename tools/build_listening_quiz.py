"""從 private/TOEIC/TOEIC紅藍本/kb/L/*.md 產生 private/toeic_listening.json（多益聽力 Part 1–4 章節測驗與兩回模擬考）。

用法：
    py tools/build_listening_quiz.py
"""
import json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
KB_L = ROOT / "private" / "TOEIC" / "TOEIC紅藍本" / "kb" / "L"
IMG_DIR = ROOT / "private" / "TOEIC" / "TOEIC紅藍本" / "kb" / "img"
AUDIO_DIR = ROOT / "private" / "TOEIC" / "TOEIC紅藍本" / "聽力"
OUT_JSON = ROOT / "private" / "toeic_listening.json"
TS_JSON = ROOT / "private" / "TOEIC" / "TOEIC紅藍本" / "kb" / "audio_ts.json"  # tools/listening_ts.py 產生
CLIP_PAD = 0.3  # 片段往前多播 0.3 秒、在下一題開始前 0.2 秒停，避免切掉「Number N」或聽到下一題
CLIP_TAIL = 0.2

ANS_MAP = {"A": 0, "B": 1, "C": 2, "D": 3}

def clean_title(sec_id, raw_title):
    # e.g. "Part 1｜Course 1-1 人物動作照片（單人）" -> "Course 1-1　人物動作照片（單人）｜Hackers Practice"
    t = re.sub(r"^Part\s*\d\s*[｜|]\s*", "", raw_title).strip()
    t = re.sub(r"^Course\s+\d+\s+[^　\s]+\s*　\s*", "", t)
    if sec_id.endswith("_T"):
        m = re.match(r"L\d_C(\d)_T", sec_id)
        return f"Course {m.group(1)}　Hackers Test"
    if sec_id.endswith("_PT"):
        m = re.match(r"L(\d)_PT", sec_id)
        return f"Part {m.group(1)}　Part Test"
    if sec_id == "L_AT1":
        return "第一回（Actual Test 1）"
    if sec_id == "L_AT2":
        return "第二回（Actual Test 2）"
    m = re.match(r"L(\d)_C(\d)_(\d+)", sec_id)
    if m:
        c_num, u_num = m.group(2), m.group(3)
        # Extract topic name
        topic = re.sub(r"^Course\s*\d+-\d+\s*", "", t)
        topic = re.sub(r"^\d+\.\s*", "", topic).strip()
        return f"Course {c_num}-{u_num}　{topic}"
    return t


def find_br_au_audio(rel_mp3):
    if not rel_mp3:
        return None
    p = pathlib.Path(rel_mp3)
    cand = f"09. Part Practice_Br. & Au Accent/{p.parent.as_posix()}/{p.stem}_Br. & Au Accent.mp3"
    if (AUDIO_DIR / cand).exists():
        return cand
    return None


def parse_question_block(sec_id, qid, body, part, set_idx=None, set_obj=None):
    # Extract question number
    qnum = int(re.search(r"\d+", qid).group(0))
    # Accent from 音檔 line if present
    m_aud = re.search(r"^音檔：[^\n]*?（([^）]+)）", body, re.M)
    accent = ""
    if m_aud:
        acc_parts = [x.strip() for x in m_aud.group(1).split("，") if "發音" in x or "對話" in x]
        accent = "，".join(acc_parts)

    # Image description (Part 1 or Part 3/4)
    m_img = re.search(r"^圖片：([^\n]+)", body, re.M)
    img_desc = m_img.group(1).strip() if m_img else ""

    # Question stem & options
    # In Part 1: 原文：\n(A) ...\n(B) ...\n(C) ...\n(D) ...
    # In Part 2: 原文：Question?\n(A) ...\n(B) ...\n(C) ...
    # In Part 3/4: 題目：Question?\n(A) ...\n(B) ...\n(C) ...\n(D) ...
    q_stem = ""
    if part == 1:
        q_stem = f"Picture {qnum}. Select the statement that best describes what is happening in the picture."
    elif part == 2:
        m_q = re.search(r"^原文：\s*([^\n]+)", body, re.M)
        if m_q and not m_q.group(1).strip().startswith("(A)"):
            q_stem = m_q.group(1).strip()
        else:
            m_q2 = re.search(r"^原文：\s*\n+([^\n(][^\n]*)", body, re.M)
            q_stem = m_q2.group(1).strip() if m_q2 else f"Question {qnum}"
    else:
        m_q = re.search(r"^題目：\s*([^\n]+)", body, re.M)
        q_stem = m_q.group(1).strip() if m_q else f"Question {qnum}"

    # Extract English options (before 答案：)
    pre_ans = re.split(r"^答案：", body, maxsplit=1, flags=re.M)[0]
    opts_en = re.findall(r"^\([A-D]\)\s*([^\n]+)", pre_ans, re.M)
    opts_en = [o.strip() for o in opts_en]

    m_ans = re.search(r"^答案：\s*\(?([A-D])\)?\s*$", body, re.M)
    if not m_ans:
        raise ValueError(f"{sec_id} {qid}: missing answer")
    ans_idx = ANS_MAP[m_ans.group(1)]

    after_ans = re.split(r"^答案：\s*\(?[A-D]\)?\s*$", body, maxsplit=1, flags=re.M)[1]

    # Extract 翻譯 block (up to 解析： or 詞彙： or 校對註： or end)
    m_tr = re.search(r"^翻譯：\s*(.*?)(?=^(?:解析|詞彙|校對註)：|\Z)", after_ans, re.M | re.S)
    trans = m_tr.group(1).strip() if m_tr else ""

    # Extract 解析 block (up to 詞彙： or 校對註： or end)
    m_exp = re.search(r"^解析：\s*(.*?)(?=^(?:詞彙|校對註)：|\Z)", after_ans, re.M | re.S)
    raw_exp = m_exp.group(1).strip() if m_exp else ""

    # Separate option breakdown lines `- (A) ...` if present
    exp_lines = []
    w_lines = []
    for line in raw_exp.splitlines():
        ls = line.strip()
        if re.match(r"^-\s*\([A-D]\)", ls):
            w_lines.append(re.sub(r"^-\s*", "", ls))
        else:
            exp_lines.append(ls)
    exp_text = "\n".join(x for x in exp_lines if x).strip()
    w_text = "\n".join(w_lines).strip()
    if not exp_text and w_text:
        exp_text = "請見下方各選項解析。"

    # Extract 詞彙 block
    m_voc = re.search(r"^詞彙：\s*([^\n]+)", after_ans, re.M)
    voc = m_voc.group(1).strip() if m_voc else ""

    q_obj = {
        "n": qnum,
        "part": part,
        "q": q_stem,
        "o": opts_en,
        "a": ans_idx,
        "g": f"t_p{part}",
        "trans": trans,
        "e": exp_text,
    }
    if w_text:
        q_obj["w"] = w_text
    if voc:
        q_obj["voc"] = voc
    if accent:
        q_obj["accent"] = accent
    if part == 1:
        img_name = f"{sec_id}_{qid}.jpg"
        if not (IMG_DIR / img_name).exists():
            raise FileNotFoundError(f"Missing Part 1 image: {img_name}")
        q_obj["img"] = img_name
        if img_desc:
            # Strip PDF page ref from start of img_desc if any
            clean_desc = re.sub(r"^題本書頁\s*\d+（pdf\s*\d+）[上下]圖(?:；[^。]+)?。\s*", "", img_desc)
            q_obj["imgDesc"] = clean_desc
    if set_idx is not None:
        q_obj["s"] = set_idx
    return q_obj


def parse_set_header(sec_id, set_text, first_qid, last_qid):
    # Extract refer line (Questions X-Y refer to ...)
    m_ref = re.search(r"^(Questions\s+\d+[–-]\d+\s+refer\s+to\s+[^\n]+)", set_text, re.M)
    qnum0 = re.search(r"\d+", first_qid).group(0)
    qnum1 = re.search(r"\d+", last_qid).group(0)
    refer = m_ref.group(1).strip() if m_ref else f"Questions {qnum0}–{qnum1}"

    # Extract accent from heading or 音檔 line
    m_acc = re.search(r"（[^）]*?((?:美式|英式|澳洲式)[^）]*)）", set_text)
    accent = m_acc.group(1).strip() if m_acc else ""

    # Extract 原文 blockquote or lines
    m_scr = re.search(r"^原文[^\n：:]*[：:]\s*\n((?:>.*(?:\n|$))+)", set_text, re.M)  # 允許「原文（照書…）：」
    if m_scr:
        script = "\n".join(re.sub(r"^>\s?", "", l) for l in m_scr.group(1).strip().splitlines())
    else:
        script = ""

    # Extract 對話翻譯 / 獨白翻譯 / 翻譯 blockquote
    m_tr = re.search(r"^(?:對話|獨白)?翻譯[^\n：:]*[：:]\s*\n((?:>.*(?:\n|$))+)", set_text, re.M)
    if m_tr:
        trans = "\n".join(re.sub(r"^>\s?", "", l) for l in m_tr.group(1).strip().splitlines())
    else:
        trans = ""

    # Extract 詞彙
    m_voc = re.search(r"^詞彙：\s*([^\n]+)", set_text, re.M)
    voc = m_voc.group(1).strip() if m_voc else ""

    # Check if there is a cropped graphic image for this set
    img_name = f"{sec_id}_{first_qid}.jpg"
    has_img = (IMG_DIR / img_name).exists()

    s_obj = {
        "refer": refer,
        "script": script,
        "trans": trans,
    }
    if accent:
        s_obj["accent"] = accent
    if voc:
        s_obj["voc"] = voc
    if has_img:
        s_obj["img"] = img_name
    return s_obj


def parse_file(md_path):
    sec_id = md_path.stem
    t = md_path.read_text(encoding="utf-8")
    m_title = re.search(r"^title:\s*(.+)$", t, re.M)
    raw_title = m_title.group(1).strip() if m_title else sec_id
    title = clean_title(sec_id, raw_title)

    # Split by ### QID (HP, HT, PT, Q)
    matches = list(re.finditer(r"(?m)^###\s+((?:HP|HT|PT|Q)\d+)\b", t))
    if not matches:
        return None

    is_mock = sec_id in ("L_AT1", "L_AT2")
    part_num = 0 if is_mock else int(sec_id[1])

    # Find primary audio
    if is_mock:
        at_n = "1" if sec_id == "L_AT1" else "2"
        folder = f"0{'6' if at_n == '1' else '7'}. Actual Test {at_n}"
        main_audio = f"{folder}/Actual Test {at_n}.mp3"
        part_audios = {}
        for p in (1, 2, 3, 4):
            pa = f"{folder}/Actual Test {at_n}_Part{p}.mp3"
            part_audios[str(p)] = {
                "audio": pa,
                "audioAlt": find_br_au_audio(pa),
            }
    else:
        # Look for audio in the test section
        m_test_sec = re.search(r"(?m)^##\s+.*?(Hackers Practice|Hackers Test|Part Test)", t)
        search_area = t[m_test_sec.start():] if m_test_sec else t
        auds = re.findall(r"`([^`]+\.mp3)`", search_area)
        base_auds = [a for a in auds if not a.startswith("09.")]
        main_audio = base_auds[0]
        part_audios = None

    alt_audio = find_br_au_audio(main_audio)

    qs = []
    sets = []

    # First collect all question slices
    q_slices = []
    for idx, m in enumerate(matches):
        qid = m.group(1)
        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(t)
        # Wait: if the next set header (## 題組 or ### 對話/獨白) starts before matches[idx+1], cut before that header!
        slice_raw = t[start:end]
        m_next_hdr = re.search(r"(?m)^(?:##\s+|###\s+(?!(?:HP|HT|PT|Q)\d+\b))", slice_raw)
        q_body = slice_raw[:m_next_hdr.start()] if m_next_hdr else slice_raw
        prev_end = matches[idx - 1].end() if idx > 0 else 0
        between = t[prev_end:m.start()]
        q_slices.append((qid, q_body, between))

    # Process questions
    i = 0
    while i < len(q_slices):
        qid, q_body, between = q_slices[i]
        qnum = int(re.search(r"\d+", qid).group(0))
        if is_mock:
            q_part = 1 if qnum <= 6 else 2 if qnum <= 31 else 3 if qnum <= 70 else 4
        else:
            q_part = part_num

        if q_part in (1, 2):
            q_obj = parse_question_block(sec_id, qid, q_body, q_part)
            qs.append(q_obj)
            i += 1
        else:
            # Part 3 or Part 4: group of 3 questions
            grp = q_slices[i:i + 3]
            first_qid, _, set_between = grp[0]
            last_qid = grp[-1][0]
            # Extract the set header from set_between (after the last question of previous group)
            # 取最靠近題目的標題：第一個題組的 set_between 是檔案開頭到第一題，前面可能還有 Example 題組的原文
            hdrs = list(re.finditer(r"(?m)^(?:##\s+題組|###\s+(?:對話|獨白|題組))", set_between))
            set_hdr_text = set_between[hdrs[-1].start():] if hdrs else set_between
            set_obj = parse_set_header(sec_id, set_hdr_text, first_qid, last_qid)
            set_idx = len(sets)
            sets.append(set_obj)
            for g_qid, g_body, _ in grp:
                q_obj = parse_question_block(sec_id, g_qid, g_body, q_part, set_idx=set_idx, set_obj=set_obj)
                qs.append(q_obj)
            i += 3

    ex = {
        "id": f"rb_{sec_id}",
        "title": title,
        "kind": "toeic",
        "listen": 1,
        "part": part_num,
        "audio": main_audio,
    }
    if alt_audio:
        ex["audioAlt"] = alt_audio
    if part_audios:
        ex["partAudios"] = part_audios
    if is_mock:
        ex["mock"] = "listening"
    if sets:
        ex["sets"] = sets
    ex["qs"] = qs
    return ex


def clip_ranges(entry):
    """audio_ts.json 的一個音檔 → {("q"|"s", 題號): [開始, 結束]}；結束＝下一個題目／題組標記的開始。
    Part 3／4 念題目的 Number N 不當成分界（題組要播到三題念完）。"""
    marks = [(v, "q", int(k)) for k, v in entry.get("q", {}).items()] + \
            [(v, "s", int(k)) for k, v in entry.get("s", {}).items()]
    set_qs = {n for k in entry.get("s", {}) for n in range(int(k), int(k) + 3)}
    bounds = sorted((v, kind, n) for v, kind, n in marks if not (kind == "q" and n in set_qs))
    out = {}
    for i, (v, kind, n) in enumerate(bounds):
        end = bounds[i + 1][0] - CLIP_TAIL if i + 1 < len(bounds) else entry["dur"]
        out[(kind, n)] = [round(max(0, v - CLIP_PAD), 1), round(end, 1)]
    return out


def add_clips(ex, ts):
    """逐題播放用的片段：Part 1／2 每題 t（標準音檔）／tA（英澳口音版），Part 3／4 每個題組 t／tA。
    模擬考以分 Part 音檔（partAudios）為準，章節練習以 audio／audioAlt 為準。回傳缺少時戳的項目數。"""
    missing = 0
    for key, alt in (("t", False), ("tA", True)):
        def src(part):
            if ex.get("partAudios"):
                pa = ex["partAudios"][str(part)]
                return pa.get("audioAlt") if alt else pa.get("audio")
            return ex.get("audioAlt") if alt else ex.get("audio")
        for q in ex["qs"]:
            rel = src(q["part"])
            if not rel:
                continue
            rng = clip_ranges(ts[rel]) if rel in ts else {}
            if q["part"] in (1, 2):
                r = rng.get(("q", q["n"]))
                if r:
                    q[key] = r
                else:
                    missing += 1
            elif "s" in q:
                s = ex["sets"][q["s"]]
                first = min(x["n"] for x in ex["qs"] if x.get("s") == q["s"])
                if q["n"] != first:
                    continue
                r = rng.get(("s", first))
                if r:
                    s[key] = r
                else:
                    missing += 1
    return missing


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    # Order files logically: Part 1..4 (C1_1..C1_n, C1_T, C2_1..C2_n, C2_T, C3_..., PT), then L_AT1, L_AT2
    def sort_key(p):
        s = p.stem
        if s in ("L3_00", "L3_B1"):
            return (0, 0, 0, 0)
        if s.startswith("L_AT"):
            return (9, int(s[-1]), 0, 0)
        part = int(s[1])
        if s.endswith("_PT"):
            return (part, 9, 99, 0)
        m = re.match(r"L\d_C(\d)_(T|\d+)", s)
        c = int(m.group(1))
        u = 99 if m.group(2) == "T" else int(m.group(2))
        return (part, c, u, 0)

    md_files = sorted(KB_L.glob("*.md"), key=sort_key)
    exams = []
    for p in md_files:
        if p.name in ("L3_00.md", "L3_B1.md"):
            continue
        ex = parse_file(p)
        if ex:
            exams.append(ex)

    # Validate every question & set
    total_q = 0
    for ex in exams:
        for q in ex["qs"]:
            total_q += 1
            expected_opts = 3 if q["part"] == 2 else 4
            if len(q["o"]) != expected_opts:
                raise ValueError(f"{ex['id']} Q{q['n']}: expected {expected_opts} options, got {len(q['o'])}: {q['o']}")
            if not q["trans"] or not q["e"]:
                raise ValueError(f"{ex['id']} Q{q['n']}: empty trans or e")
        for si, s in enumerate(ex.get("sets", [])):
            if not s["script"] or not s["trans"]:
                raise ValueError(f"{ex['id']} set {si} ({s['refer']}): empty script or trans")

    ts = json.loads(TS_JSON.read_text(encoding="utf-8")) if TS_JSON.exists() else {}
    missing = sum(add_clips(ex, ts) for ex in exams)
    if not ts:
        print("找不到 kb/audio_ts.json，沒有加入逐題片段（先執行 py tools/listening_ts.py）")
    elif missing:
        print(f"注意：{missing} 個題目／題組沒有時戳（新音檔請先執行 py tools/listening_ts.py）")

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "{",
        ' "about":"TOEIC 聽力題庫（Hackers 新制多益聽力題庫大全｜Part 1–4 章節練習與實戰模擬測驗 1–2）",',
        ' "exams":[',
    ]
    exam_Blocks = []
    for ex in exams:
        head = {k: v for k, v in ex.items() if k != "qs"}
        head_str = json.dumps(head, ensure_ascii=False, separators=(",", ":"))[:-1]
        q_lines = ",\n".join("   " + json.dumps(q, ensure_ascii=False, separators=(",", ":")) for q in ex["qs"])
        exam_Blocks.append(f"  {head_str},\"qs\":[\n{q_lines}\n  ]}}")
    lines.append(",\n".join(exam_Blocks))
    lines += [" ]", "}"]
    OUT_JSON.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"已產生 {OUT_JSON.relative_to(ROOT)}：{len(exams)} 份試卷、共 {total_q} 題")


if __name__ == "__main__":
    main()
