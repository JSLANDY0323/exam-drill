# 題庫資料（data/）

網頁 `index.html` 只放版面與程式；開啟時讀取 `manifest.json`，再依 `files` 的順序載入各 JSON。

| 檔案 | 內容 |
|---|---|
| tags.json | 所有考點標籤（錯題分析依此順序顯示） |
| toeic_p5_mock.json | Part 5 綜合模擬、早期專項特訓 |
| toeic_p5_s1.json ／ s2 ／ s3 | Part 5 第一～三階段 |
| toeic_p5_adv.json | Part 5 進階考點 |
| toeic_p5_words.json | Part 5 單字題 Day 1–30（stage 7；依 TOEIC/TOEIC_Vocabulary_Day1-30.md 出題，每天 60 題，共 1800 題；片語只挖一個字）。新增或修改請用 `py tools/p5_words.py`，出題原則見專案根目錄 readme.md |
| toeic_p6.json | Part 6 |
| toeic_part7.json | Part 7 |
| stat_past.json | 統計學 考古題 |
| bigdata_past.json ／ bigdata_mock.json | 巨量資料概論 考古題／模擬考 |
| ai_jr.enc.json | AI應用規劃師 初級（章節模擬試題；加密） |
| ai_sr_common.enc.json | AI應用規劃師 中級 科目一 人工智慧技術應用與規劃（必考；加密） |
| ai_sr_bd.enc.json ／ ai_sr_ml.enc.json | AI應用規劃師 中級 科目二 大數據處理分析與應用／科目三 機器學習技術與應用（擇一報考；加密） |

AI應用規劃師題庫受著作權保護：明文放在專案的 `private/`（不上傳），改完後執行 `py tools/encrypt_ai.py` 產生這裡的 `*.enc.json`。

## 格式

```json
{"about":"說明","tags":{…可省略…},"exams":[
  {"id":"p5_pos","kind":"toeic","part":5,"stage":1,"title":"詞性題","sub":"…",
   "qs":[ {"g":"t_p5pos","q":"題目","o":["A","B","C","D"],"a":1,"h":"提示","trans":"翻譯","e":"詳解","w":"其他選項"} ]}
]}
```

- `kind`：`toeic`、`past`（考古題）、`mock`（巨量資料模擬考）。
- AI 中級題組另有 `track`：`com`（科目一）、`bd`（科目二）、`ml`（科目三）。
- `acc`（可省略）：官方公告多個答案都給分時列出所有正確選項索引，例如 `"acc":[0,2]`；一律給分用 `[0,1,2,3]`。`a` 仍要填其中一個。
- `target`（單字題選用、單字挖空的片語題必填）：對應教材的完整詞條。例如片語 in lieu of 只挖 lieu 時，記錄 `"target":"in lieu of"`，避免將單獨的 lieu 誤算成教材涵蓋。前端顯示與作答鍵不依賴此欄位。
- 一題一行，方便 git diff 與審閱。

## 修改規則（重要）

1. 作答紀錄以「題組 id－題目順序」記錄，所以**新增題目一律加在該題組 `qs` 的最後面**，不要插入中間、不要刪題、不要改題組 `id`。
2. 改完任何 JSON 後執行 `py tools/update_manifest.py`：檢查 JSON 格式、欄位、答案索引、標籤、題組 ID 重複，並更新版本雜湊 `v`（讓瀏覽器抓到新版）。
   - 它也會和 `tools/baseline.json` 比對既有題目；題幹、正解位置或正解文字變了會停下來（結束碼 2）。確認是刻意修改後加 `--accept`；只檢查不寫入用 `--check`。
3. 新增資料檔：在 `manifest.json` 的 `files` 加入 `{"path":"新檔.json","title":"說明"}`，再執行上面的程式。新標籤要先加進 `tags.json`。
4. 本機預覽不能直接雙擊 index.html，請在專案資料夾執行 `python -m http.server 8000`，再開 http://localhost:8000 。
