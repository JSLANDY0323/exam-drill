"""各 10 回聽力音檔語音辨識（faster-whisper）。

用法：py tools/toeic10_asr.py 1 2      # 轉 TEST01、TEST02
輸入：參考書/TOEIC/聽力閱讀各 10 回/聽力/聽力模擬國際學村/TESTNN.mp3（市售書音檔，不可上傳）
輸出：private/toeic_md/listening/testNN/asr.json（逐段 start/end/text）與 asr.txt（[mm:ss] 文字）
用途：找每題開始秒數、與 TESTNN.md 原文逐句比對。結果只放 private/。
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "參考書" / "TOEIC" / "聽力閱讀各 10 回" / "聽力" / "聽力模擬國際學村"
OUT = ROOT / "private" / "toeic_md" / "listening"


def decode(path):
    # faster-whisper 內建 decode_audio 與目前 PyAV 版本不合，自己解碼成 16 kHz 單聲道（同 listening_ts.py）
    import av, numpy as np
    with av.open(str(path)) as c:
        rs = av.AudioResampler(format="s16", layout="mono", rate=16000)
        buf = [o.to_ndarray().reshape(-1) for fr in c.decode(audio=0) for o in rs.resample(fr)]
    return np.concatenate(buf).astype(np.float32) / 32768.0


def main(nums):
    from faster_whisper import WhisperModel
    model = WhisperModel("small", device="cpu", compute_type="int8")
    for n in nums:
        nn = f"{int(n):02d}"
        mp3 = SRC / f"TEST{nn}.mp3"
        out = OUT / f"test{nn}"
        out.mkdir(parents=True, exist_ok=True)
        segs, _ = model.transcribe(decode(mp3), language="en", vad_filter=True,
                                   word_timestamps=False, beam_size=5)
        rows = []
        for s in segs:
            rows.append({"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()})
            print(f"TEST{nn} {s.start:7.1f} {s.text.strip()[:60]}", flush=True)
        (out / "asr.json").write_text(json.dumps({"src": f"參考書/TOEIC/聽力閱讀各 10 回/聽力/聽力模擬國際學村/TEST{nn}.mp3", "model": "small", "segments": rows}, ensure_ascii=False, indent=1), encoding="utf-8")
        (out / "asr.txt").write_text("\n".join(f"[{int(r['start'])//60:02d}:{int(r['start'])%60:02d}] {r['text']}" for r in rows) + "\n", encoding="utf-8")
        print(f"TEST{nn} done: {len(rows)} segments", flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or ["1", "2"])
