"""檢查各 10 回 TOEIC 轉檔（private/toeic_md/{listening,reading}/testNN/TESTNN.md）的格式與內容。

用法：
    py tools/check_toeic10.py                 # 檢查全部已解開的回次
    py tools/check_toeic10.py listening 3 4   # 只檢查聽力第 3、4 回
    py tools/check_toeic10.py reading         # 只檢查閱讀
    py tools/check_toeic10.py -v              # 另外列出每一條警告

結束碼：0＝沒有錯誤（可以有警告）；1＝有錯誤。只讀不寫。

錯誤（要修）：frontmatter 缺 status／status 不是 done、reviewed；題號不是 Q1–Q100（聽力）／Q101–Q200（閱讀）連續不重複；
  缺 來源／答案／翻譯／解析；答案不在 A–D；選項數不對（聽力 Part 2 為 3 個，其餘 4 個）；答案與該回簡答表不一致；
  圖片連結指向不存在的檔案；還有「待核」（原書看不清楚、尚未確認的地方）。
警告（參考，不影響結束碼）：缺 難易度（聽力第 1–3 回沒有）、缺 考點（只有聽力第 1 回有；網站的標籤分類要靠它）、
  找不到簡答表（聽力第 1 回；答案沒有交叉比對）、聽力 Part 3／4 題組數不是 23、閱讀題組數不是 19、有編者註。
"""
import re, sys, glob, os, collections
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent / "private" / "toeic_md"
RANGE = {"listening": (1, 100), "reading": (101, 200)}
GROUPS = {"listening": 23, "reading": 19}
LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)\)")
OPT = re.compile(r"^\(([A-D])\) ", re.M)


def key_of(d, kind):
    """讀簡答表：回傳 {題號: 字母}，找不到回傳 None。"""
    for p in sorted(d.rglob("answer_key*")):
        t = p.read_text(encoding="utf-8", errors="ignore")
        pairs = re.findall(r"^(\d{1,3})\s+([A-D])\s*$", t, re.M)
        if len(pairs) >= 90: return {int(a): b for a, b in pairs}
        s = re.sub(r"\s+", "", t)
        if re.fullmatch(r"[A-D]{100}", s):
            lo = RANGE[kind][0]
            return {lo + i: c for i, c in enumerate(s)}
    return None


def check(kind, nn, verbose):
    d = ROOT / kind / f"test{nn:02d}"
    md = d / f"TEST{nn:02d}.md"
    err, warn = [], collections.defaultdict(list)
    if not md.exists(): return None, [f"找不到 {md.relative_to(ROOT)}"], {}
    t = md.read_text(encoding="utf-8")
    fm = re.match(r"---\n(.*?)\n---", t, re.S)
    status = (re.search(r"^status:\s*(\S+)", fm.group(1), re.M) or [None, None])[1] if fm else None
    if status not in ("done", "reviewed"): err.append(f"frontmatter status 是 {status!r}（要 done 或 reviewed）")
    blocks = re.split(r"^### ", t, flags=re.M)[1:]
    nums = []
    parts = {}
    for b in blocks:
        head, body = b.split("\n", 1)
        m = re.fullmatch(r"Q(\d+)", head.strip())
        if not m: err.append(f"看不懂的小標題：### {head.strip()}"); continue
        q = int(m.group(1)); nums.append(q)
        for lab in ("來源", "答案", "翻譯", "解析"):
            if not re.search(rf"^{lab}[^：\n]*：", body, re.M): err.append(f"Q{q}：缺 {lab}")
        a = re.search(r"^答案：\s*([A-D])\s*$", body, re.M)
        if not a: err.append(f"Q{q}：答案不是單一個 A–D")
        parts[q] = a.group(1) if a else None
        # 選項：取「題目／原文」到「答案」之間
        pre = body.split("答案：", 1)[0]
        letters = OPT.findall(pre)
        want = 3 if kind == "listening" and 7 <= q <= 31 else 4
        if letters and len(letters) != want: err.append(f"Q{q}：選項 {len(letters)} 個（應為 {want}）")
        if not letters: err.append(f"Q{q}：找不到選項")
        if "待核" in body: err.append(f"Q{q}：含「待核」")
        for lab in ("難易度", "考點"):
            if not re.search(rf"^{lab}：", body, re.M): warn[f"缺 {lab}"].append(q)
        if "編者註" in body: warn["有編者註"].append(q)
        for link in LINK.findall(body):
            if link.startswith("http"): continue
            if not (d / link).exists(): err.append(f"Q{q}：圖片／連結不存在 {link}")
    lo, hi = RANGE[kind]
    if sorted(nums) != list(range(lo, hi + 1)) or nums != sorted(nums):
        miss = sorted(set(range(lo, hi + 1)) - set(nums)); dup = [n for n, c in collections.Counter(nums).items() if c > 1]
        err.append(f"題號不是 Q{lo}–Q{hi} 連續遞增（缺 {miss[:10]}、重複 {dup[:10]}）")
    key = key_of(d, kind)
    if key is None: warn["找不到簡答表（answer_key*），答案沒有交叉比對"].append("-")
    else:
        bad = [f"Q{q}（稿 {parts.get(q)}／表 {key.get(q)}）" for q in range(lo, hi + 1) if parts.get(q) != key.get(q)]
        if bad: err.append(f"答案與簡答表不一致 {len(bad)} 題：" + "、".join(bad[:8]))
    g = len(re.findall(r"^題組說明：", t, re.M))
    if g != GROUPS[kind]: warn[f"題組數 {g}（預期 {GROUPS[kind]}）"].append("-")
    return status, err, warn


def main():
    a = sys.argv[1:]
    verbose = "-v" in a
    a = [x for x in a if x != "-v"]
    kinds = [x for x in a if x in RANGE] or list(RANGE)
    nums = [int(x) for x in a if x.isdigit()] or list(range(1, 11))
    total_err = 0
    print(f"{'回次':<14}{'status':<10}{'錯誤':>5}  警告摘要")
    for kind in kinds:
        for nn in nums:
            if not (ROOT / kind / f"test{nn:02d}").exists():
                print(f"{kind} {nn:02d}".ljust(14) + "（尚未解開／未轉檔）"); continue
            status, err, warn = check(kind, nn, verbose)
            total_err += len(err)
            ws = "；".join(f"{k} {len(v)}" for k, v in warn.items())
            print(f"{kind} {nn:02d}".ljust(14) + f"{str(status):<10}{len(err):>5}  {ws}")
            for e in err[: (None if verbose else 6)]: print("    ✗", e)
            if len(err) > 6 and not verbose: print(f"    …還有 {len(err) - 6} 條（加 -v 看全部）")
            if verbose:
                for k, v in warn.items(): print("    △", k, v[:15])
    print(f"\n合計錯誤 {total_err} 條")
    sys.exit(1 if total_err else 0)


if __name__ == "__main__":
    main()
