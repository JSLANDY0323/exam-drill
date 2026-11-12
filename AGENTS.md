# AGENTS.md — 給 AI Agent 的工作規則

> 本專案唯一的 AI 入口檔，Codex、Claude Code、Gemini 都依這份規則工作。
> Codex 預設自動讀；Gemini CLI 由 `.gemini/settings.json`（`context.fileName`）指定讀這份；Claude Code 不會自動讀，要在對話開頭請它先讀。
> 不要另外建立 CLAUDE.md、GEMINI.md 等其他規則檔；規則有變動時只改這裡。

## 專案是什麼

刷題網站（純前端、無建置流程），部署在 GitHub Pages（repo：exam-drill，使用者自己 push）。
科目：TOEIC Part 5／6／7（對外公開）、統計學、巨量資料概論、AI應用規劃師初級／中級（站長自用）。

- 工作資料夾在 Google 雲端硬碟，使用者會輪流用 Gemini、Codex、Claude Code 改檔。**動手前一律重新讀取要改的檔案**，不要沿用之前對話的記憶。
- 本機預覽：`py -m http.server 8000` → http://localhost:8000（不能直接雙擊 index.html）。

## 檔案地圖

| 路徑 | 內容 | 詳細說明 |
|---|---|---|
| `index.html` | 版面＋CSS＋全部程式（約 1,570 行），不含題目 | readme.md「程式架構」 |
| `data/manifest.json` | 載入清單，`v`＝內容雜湊 | 由工具自動更新，不要手改 `v` |
| `data/*.json` | 題庫，一題一行 | data/README.md（欄位格式） |
| `data/*.enc.json` | AI 題庫加密檔 | 明文在 `private/` |
| `private/` | AI 題庫明文（受著作權保護） | **不可上傳**，已在 .gitignore |
| `tools/update_manifest.py` | 檢查全部題庫＋更新 manifest | 見下方「改完題庫」 |
| `tools/baseline.json` | 每題的指紋，用來偵測既有題目被改動 | 不要手改 |
| `tools/p5_words.py` | Part 5 單字題 Day 1–30 專用工具 | readme.md「TOEIC Part 5 單字題」 |
| `tools/p7_check.py` | Part 7 命題規格檢查（改 toeic_part7.json 後必跑） | readme.md「TOEIC Part 7」 |
| `tools/p7_trans.py` | Part 7 逐句對照翻譯（seg／hseg）的草稿、寫回與檢查 | readme.md「TOEIC Part 7」欄位說明 |
| `tools/make_icons.py` | 產生網站圖示（favicon.svg、favicon-32.png、apple-touch-icon.png） | 不要手改這三個圖檔，改工具開頭的參數再執行 |
| `tools/make_glossary.py` | 產生檢討用單字／片語提示詞典 data/glossary/toeic.json（不要手改該檔） | readme.md「程式架構」單字提示；改完 TOEIC 題庫後重跑 |
| `tools/glossary_extra.json` | 詞典的人工補充（繁體釋義、補片語、drop 誤判片語） | 同上 |
| `tools/encrypt_ai.py` | 加密 private/ → data/*.enc.json | 需要使用者輸入密碼 |
| `private/TOEIC/TOEIC紅藍本/` | 紅藍本（Hackers 聽力／閱讀題庫大全）聽力音檔、`kb/` Markdown 知識庫與 `kb/img/` 題目照片／圖表（市售書，**不可上傳**，已在 .gitignore） | `private/TOEIC/TOEIC紅藍本/kb/README.md`（拆解、校對流程與格式） |
| `tools/redblue_kb.py` | 紅藍本知識庫工具：掃描 PDF、產生 OCR 原稿與目錄／音檔對照、轉圖、檢查校對稿 | 同上；Claude Code 可用 `/redblue-kb` |
| `tools/build_listening_quiz.py` | 從 `private/TOEIC/TOEIC紅藍本/kb/L/*.md` 產生 `private/toeic_listening.json`（72 個題組、1,244 題） | 改完 `kb/L/` 後執行，再跑 `update_manifest.py` 與 `encrypt_ai.py` |
| `tools/build_reading_mock.py` | 從 `private/TOEIC/TOEIC紅藍本/kb/R/R_AT*.md`（只收 status: done）產生 `private/toeic_reading_mock.json`（閱讀模擬考第一回、第二回，各 100 題） | 改完 `kb/R/R_AT*.md` 後執行，再跑 `update_manifest.py`，請使用者執行 `encrypt_ai.py` |
| `tools/listening_ts.py` | 用語音辨識（faster-whisper）找出聽力音檔每題／每個題組的開始秒數 → `private/TOEIC/TOEIC紅藍本/kb/audio_ts.json`（不要手改；修正寫在 `kb/audio_ts_fix.json`）。加 `--book toeic10` 改處理各 10 回音檔 → `private/toeic_md/listening/audio_ts.json`（修正寫在同資料夾 `audio_ts_fix.json`） | 工具開頭說明；紅藍本需先有 `private/toeic_listening.json`；需要 faster-whisper（`py -3.13 -m pip install faster-whisper`） |
| `readme.md` | 程式架構、功能細節、出題原則 | |
| `CHANGELOG.md` | 歷次修改紀錄 | 需要查歷史時才讀 |
| `參考書/AI應用規劃師/`、`參考書/國營/`、`參考書/TOEIC/` | 參考 PDF；紅藍本在 `參考書/TOEIC/紅藍本/`，各 10 回在 `參考書/TOEIC/聽力閱讀各 10 回/`；整棵不可上傳 | |
| `private/toeic_md/`、`private/TOEIC/AI轉檔_md/` | 各 10 回既有轉檔成品（不搬）與轉檔 zip；不可混入紅藍本 | |
| `參考書/TOEIC/聽力閱讀各 10 回/聽力/聽力模擬國際學村/` | 各 10 回聽力書（國際學村《最新！新制多益 TOEIC 聽力題庫解析》）的音檔 `TEST01.mp3`–`TEST10.mp3`，一回一檔、收錄 Part 1–4（原書標示 `TEST 01.mp3`…）；市售書，**不可上傳**（`參考書/` 已在 .gitignore）。只用於 `private/toeic_md/listening/testNN/` 的聽辨校對，不可與紅藍本音檔混用 | `private/toeic_md/PLAN.md` |
| `tools/check_toeic10.py` | 各 10 回轉檔格式檢查（20 回：題號、選項、答案、簡答表、圖片連結、待核）：`py tools/check_toeic10.py [listening\|reading] [回次]`，只讀；各 AI 轉完一回要跑，結束碼 0 才算完成 | `private/toeic_md/PLAN.md` |
| `tools/build_toeic10_reading.py` | 從 `private/toeic_md/reading/testNN/TESTNN.md`（status 為 done／reviewed）產生 `private/toeic10_reading.json`（閱讀 TEST 01–10，各 100 題，格式同閱讀模擬考 `mock:"reading"`）；標籤由解析開頭的題型對應。改完轉檔後執行，再跑 `update_manifest.py`，請使用者執行 `encrypt_ai.py` | `private/toeic_md/PLAN.md` |
| `tools/build_toeic10_listening.py` | 從 `private/toeic_md/listening/testNN/TESTNN.md` 產生 `private/toeic10_listening.json`（聽力 TEST 01–10，各 100 題，格式同聽力模擬考 `mock:"listening"`，標籤 t_p1–t_p4）；同時從題本 PDF 裁 Part 1 照片與圖表、把音檔轉成 56 kbps，放在 `private/toeic_md/listening/media/`（不可上傳），並讀 `audio_ts.json` 加逐題片段。網頁媒體鍵是 `img/t10/…`、`audio/t10/…`。執行後請使用者執行 `encrypt_ai.py`，再跑 `update_manifest.py` | 工具開頭說明 |
| `tools/toeic10_asr.py` | 各 10 回聽力音檔語音辨識：`py tools/toeic10_asr.py 1 2` → `private/toeic_md/listening/testNN/asr.json`／`asr.txt`（逐段秒數＋英文），供找題目秒數與比對原文 | 工具開頭說明 |

## 絕對不能違反的規則

1. **作答紀錄以「題組id-題目順序」為鍵**（例如 `p5_pos-12`）。因此：
   - 新題一律接在題組 `qs` 的**最後面**，或開新題組。
   - 不可插入、刪除、調換題目順序，不可刪除或改名題組 `id`。
   - 修改既有題目時，不改正解位置 `a`，也不調換選項順序（網頁不打亂選項，紀錄存的是選項索引）。
   - 真的必須搬動時，要在 index.html 的遷移表（`EXAM_MIGRATE`、`QUESTION_MIGRATE`、`OPTION_REMAP`）加對應，並先問使用者。
2. **著作權**：AI 題庫明文只放 `private/`，網站只放加密檔。不要把 private/ 的內容複製到 data/、readme 或其他會上傳的地方。紅藍本知識庫（`private/TOEIC/TOEIC紅藍本/kb/`）同理，之後做成 quiz 也要走 private/＋加密。
3. **對外／站長模式**：對外只顯示 TOEIC；統計學、巨量資料的 JSON 雖然是公開明文，介面只有站長解鎖後才顯示。不要讓非 TOEIC 內容出現在對外畫面。
4. 不要自己 push、不要執行 `encrypt_ai.py`（需要使用者的密碼）；改完 private/ 的 AI 題庫後，請使用者自己執行。

## 改完題庫一定要做

```
py tools/update_manifest.py
```

- 結束碼 0：檢查通過，已更新 manifest 的 `v` 與 tools/baseline.json。
- 結束碼 1（錯誤）：JSON 格式、欄位、標籤、題組 id 重複、題組被刪或題數變少。修正後重跑。
- 結束碼 2（需要確認）：既有題目的題幹／正解位置／正解文字和 baseline 不同。
  - 出現「疑似插入、刪除或調換順序」→ 你把題目插到中間了，改成接在最後面。
  - 確定是刻意的修正（錯字、更正答案）→ 向使用者說明改了哪幾題，再執行 `py tools/update_manifest.py --accept`。
- 只想檢查不寫入：`--check`。
- 單字題（toeic_p5_words.json）先用 `p5_words.py add／check`，最後一樣跑 update_manifest.py。
- 新增資料檔：在 manifest.json 的 `files` 加一行 `{"path":"新檔.json","title":"…"}` 再跑工具。新標籤要先加進 `data/tags.json`。

## 改完程式（index.html）

- 用 `py -m http.server 8000` 開起來實際操作，至少確認：首頁載入沒有錯誤、改到的畫面能用、手機寬度（375px）不跑版、深色模式正常。
- 全域 CSS `svg{width:18px}` 是給 icon 用的；圖表要用 `.chart` 覆寫。
- 筆記的 Markdown／KaTeX 函式庫是從 jsDelivr 延遲載入，離線時要能顯示原文。

## 交接

- 完成一批修改後，在 `CHANGELOG.md` 最上面加一筆（日期、改了什麼、題數變化）。
- 只有規則或架構改變時才改 AGENTS.md／readme.md；不要把歷史紀錄寫進這兩份。

## 尚未決定的事

- `private/TOEIC_Vocabulary_Day1-30.md` 是市售單字書整理（著作權內容），已在 private/，受 .gitignore 保護，不可上傳。
