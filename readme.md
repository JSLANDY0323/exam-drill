# 刷題網站維護筆記

> AI Agent 請先讀 [AGENTS.md](AGENTS.md)（工作規則與必跑指令）。本檔是程式架構與功能細節；歷次修改紀錄在 [CHANGELOG.md](CHANGELOG.md)。

## 概要

- 工作資料夾：`G:\我的雲端硬碟\Quiz_app`（Google 雲端硬碟）。D:\Codex\test 仍有 .git，但已無 data/。
- 部署：GitHub Pages（exam-drill），使用者自行 push。黑白簡約目錄式首頁。
- 首頁順序：統計學 → 巨量資料概論 → AI應用規劃師（初級／中級）→ TOEIC → 刷題統計。
- 本機預覽：`py -m http.server 8000`，或雙擊 `本機預覽.bat`。

## 檔案架構

```
AGENTS.md             # AI Agent 工作規則（唯一的 AI 入口檔）
CHANGELOG.md          # 歷次修改紀錄
index.html            # 版面＋CSS＋程式（約 119 KB、1,570 行），不含題目
favicon.svg           # 網站圖示（疊放題卡，透明底、隨淺色／深色模式換色）；favicon-32.png（透明底）、apple-touch-icon.png（白底）固定用淺色配色，三檔一起由 tools/make_icons.py 產生
data/manifest.json    # 載入清單（依 files 順序載入；v＝內容雜湊）
data/README.md        # 格式與修改規則（含 acc、target 欄位）
data/tags.json        # 所有 TAGS；前綴 t_＝TOEIC、s_＝統計、ai_／ai2_＝AI應用規劃師、其他＝巨量資料
data/stat_past.json      # s104–s113、s115（scope stat）
data/toeic_p5_mock.json / s1 / s2 / s3 / adv, toeic_p5_words.json, toeic_p6.json, toeic_part7.json
data/bigdata_past.json   # p104–p113、p115（kind past；114 年 PDF 中沒有）
data/bigdata_mock.json   # e1–e3（kind mock）
data/ai_*.enc.json       # AI應用規劃師題庫的加密檔（公開上傳的只有這些）
private/ai_jr.json       # 明文：ai_jr_p1c1 … ai_jr_p7c3（scope ai_jr，16 章 610 題）
private/ai_sr_common.json # 明文：ai_sr_c1–c9（中級科目一，track com，377 題；必考）
private/ai_sr_ml.json    # 明文：ai_sr_ml1–ml12（中級科目三 機器學習技術與應用，track ml，397 題）
private/ai_sr_bd.json    # 明文：ai_sr_bd1–bd13（中級科目二 大數據處理分析與應用，track bd，467 題）
tools/update_manifest.py # 改完 data 後執行：檢查全部題庫（含 private/ 明文）、比對 baseline、更新 v
tools/baseline.json      # 每題指紋（題幹雜湊:正解索引:正解文字雜湊），偵測插入／刪除／調換
tools/encrypt_ai.py      # 加密 private/ 的 AI 題庫 → data/*.enc.json 並更新 manifest（--check 驗證密碼）
tools/p5_words.py        # Part 5 單字題 Day 1–30：check／add／version（規則見下方「TOEIC Part 5 單字題」）
tools/p7_check.py        # Part 7 命題規格檢查：54 題結構、題號、插入題／言外之意題、正解長度偏誤（規則見下方「TOEIC Part 7」）
tools/p7_trans.py        # Part 7 逐句對照翻譯（seg／hseg）：自動斷句產生草稿、寫回題庫、檢查是否對得上原文
tools/make_icons.py      # 產生網站圖示 favicon.svg／favicon-32.png／apple-touch-icon.png（需要 Pillow；造型參數在檔案開頭）
tools/make_glossary.py   # 產生檢討用單字／片語提示詞典 data/glossary/toeic.json（來源 ECDICT＋glossary_extra.json，見下方「單字提示」）
tools/glossary_extra.json # 詞典的人工補充：繁體釋義覆寫、補片語、drop＝不要比對的片語
參考書/                # AI應用規劃師、國營、TOEIC 紅藍本與各 10 回 PDF（不可上傳）
private/TOEIC/TOEIC紅藍本/ # 紅藍本 kb、音檔（不可上傳）
private/TOEIC/AI轉檔_md/  # 各 10 回轉檔 zip（不可上傳）
private/toeic_md/        # 各 10 回既有轉檔成品，原位不搬
參考書/TOEIC/聽力閱讀各 10 回/聽力/聽力模擬國際學村/ # 各 10 回聽力音檔 TEST01–10.mp3（不可上傳，參考書/ 已忽略）
private/TOEIC_Vocabulary_Day1-30.md  # 單字題教材（著作權內容，已受 private/ 忽略規則保護）
.gitignore               # 排除 private/、參考書/、Gist.txt，並保留舊來源目錄的過渡保護
```

## 程式架構（index.html）

### 載入與資料分類

- 載入：manifest → 平行 fetch（`?v=`＋no-cache）→ `addData` → `buildIndex` → `DATA_READY`。題目鍵 `QM[題組id-索引]`。
- 題組欄位 `scope`：stat／ai_jr／ai_sr；無 scope 時 kind toeic→TOEIC，其餘→巨量資料。`exScope()`、`scopeName()`、`scopeTags()`。
- AI 中級分三個科目（官方編號；科目一必考，科目二、三擇一）：題組欄位 `track`（com＝科目一、bd＝科目二 大數據、ml＝科目三 機器學習）；虛擬 scope `ai_com`／`ai_ml`／`ai_bd`（`SR_TRACK`，inScope 只取該 track），首頁三個資料夾各自有錯題分析／抽考。科目一在兩本指南中題目與編排完全相同，只收一份。標籤前綴 `ai2_`（ai2_c／ai2_ml／ai2_bd）。
- 題目可選欄位 `acc`：官方多重正解／一律給分；`okAns(q,k)`、`keyTxt(q)`。
- 畫面路由：`render()` 依 `st.view` 選 `vHome`／`vToeic`／`vExam`／`vReading`（Part 6/7）／`vPset`／`vPrac`／`vReport`／`vStats`／`vNotes`／`vSync`／`vUnlock`。

### 對外 TOEIC／站長自用

- 單字提示（`glossHTML`）：TOEIC 題目檢討時（Part 5 題幹與選項、Part 6／7 文章、題目、選項），滑鼠移到英文字上顯示詞性與中文；字在詞典片語中（2–5 字、只隔空白，字可用原形比對，取最長）時整組標示並先列片語意思。手機用點的。題幹空格以正解代入比對（in _______ of → in lieu of）。詞典 `data/glossary/toeic.json` 在第一次進入檢討時才下載（約 760 KB，不在 manifest）。
  - 只想套用 `tools/glossary_extra.json` 的修改（沒有 ecdict.csv）：`py tools/make_glossary.py --patch`；`f` 欄是變化形→原形的覆寫（ECDICT 判錯時用，null＝取消對應）。
  - 產生：`py tools/make_glossary.py ecdict.csv路徑 [--report]`。ecdict.csv 從 https://github.com/skywind3000/ECDICT 下載（MIT，約 66 MB，不放進專案），另需 `pip install opencc-python-reimplemented`（簡轉台灣繁體）。只收題庫實際出現的字與片語；片語只收一般、商業、法律釋義，[計][電][化] 等專業釋義不收。單字每行一個詞性、最多 6 個義項。
  - 單字題 Day 1–30 的情境釋義會併進詞典並排在第一行（`question_senses`／`merge_senses`）：正解取詳解「【正解】字（意思）」，錯誤選項取 `w` 的「(詞性) 意思」，所以改了單字題的詳解也要重跑。題目當形容詞／名詞用的變化形（challenging、bound、earnings）列在 `k`，提示框先列本身的意思、存卡也存原字（`GL.ks`）；當動詞用的變化形（soared）照樣存原形。
  - 單字卡顯示的釋義以目前的詞典為準（`vMean`），詞典更新後舊卡片跟著更新；存卡時記下的 `m` 只在詞典查不到時使用。
  - 改了 TOEIC 題庫或 `tools/glossary_extra.json` 後要重跑。誤判的片語加進 `drop`，錯的釋義在 `w`／`p` 覆寫；`--report` 會列出題庫片語（`target`）沒對到的與查不到的字。
  - 網頁的比對規則（`glossHTML`）與工具（`runs`、`norm`、候選原形）必須一致，改一邊要一起改。
- 左側側邊欄（`renderSide`）：「TOEIC」與「站長自用」。寬螢幕（≥900px）固定在左側，可收合成圖示列（localStorage `quiz-side`）；窄螢幕為漢堡選單滑出。
- 單字卡／錯題分析／隨機抽考／筆記複習／刷題統計在頂列中間（`TOOLS`，依此順序；寬度 <760px 時改放在側邊選單），目錄內不列。對外固定 TOEIC；站長沿用 st.scope，錯題分析／抽考頁上方有科目切換（`scopeChips`）。
- 隨機抽考（view `pset`，`vPset`）：科目（站長才有其他考科）→ TOEIC 再選題型：聽力題／閱讀題（可勾 Part，聽力只收有片段時戳的題目）、聽力／閱讀整份模擬考（隨機開一份現有模擬考卷）→ 範圍（錯題／標註／錯題＋標註／有筆記／全部題目；「全部題目」只出章節練習、不含模擬考）→ 題數。上次的選擇記在 localStorage `quiz-pf`（`PF`）。`pfIds` 篩候選題，`newQuiz` 出題：聽力走 `newLRand`（題組整組出），閱讀只勾 Part 5 且範圍全部題目時可選「依真考題型比例／基礎」（`newDaily`）或完全隨機。設定存在 `st.pr.cfg`，「再抽一回」照同樣設定重抽。目錄內不再放抽考入口。
  - 抽題優先順序（`drawInfo`／`freshFirst`）：抽考作答不寫進 `st.ans`，所以改看刷題紀錄 `st.tlog`（試卷與抽考都會記）每題最近一次作答。錯題複習名額（Part 5 依比例 3 題、聽力 2 個單位）只給「試卷做錯、之後沒答對過、且 3 天內沒做過」的題；其餘先出試卷與抽考都沒做過的，3 天內做過的排最後（`RECENT_MS`）。只看 `st.ans` 的話，同一批錯題會每次都被抽到。
- 瀏覽紀錄（`navInit`／`navSync`／popstate）：換頁（畫面＋題組＋科目＋模式，換題不算）就 `history.pushState`，所以 Alt+←／Alt+→、手機返回鍵在站內前後切換。最底下有一筆哨兵 `{qz:1,sent:1}`；退到哨兵或比最新一頁退了超過 `NAV_MAX`（20）頁就 `confirm` 是否離開，離開用 `history.go` 一次跳出本站紀錄，不離開就 `history.forward()` 回原頁。最新頁序號存在 sessionStorage `quiz-navtop`，重新整理後沿用。
- 對外（預設）只看到 `vToeic`：Part 5／6／7，同步按鈕隱藏。`render()` 會把非 TOEIC 的畫面導回 TOEIC 首頁。
- 站長自用＝`isOwner()`（`st.mode==="owner"` 且 `AILock.ok`）：沿用 AI 題庫密碼（view `unlock`），解鎖後顯示完整目錄（`vHome`）＋同步。頂列右上角的「登入／登出」（`.authbtn`）：未解鎖時開密碼頁，已解鎖時登出（清除記住的金鑰並重新整理）；窄螢幕且有同步按鈕時只顯示圖示。
- 注意：統計學、巨量資料的 data/*.json 仍是公開明文，只是介面不顯示；只有 AI 題庫真的加密。

### AI 題庫加密

- AI 題庫取自市售指南（勁園／台科大，版權頁禁止轉載），所以公開網站只放加密檔；明文只在 private/，**不可上傳**。
- 修改 AI 題目：改 private/ 的 JSON → `py tools/update_manifest.py --check` → 使用者執行 `py tools/encrypt_ai.py`（輸入密碼兩次，至少 12 字元）→ `py tools/update_manifest.py`。每次加密會產生新的 salt，各裝置需重新輸入密碼。
- 網頁：manifest 中 `"enc":1` 的檔案放進 `AILock.locked`，首頁 AI 資料夾顯示「輸入密碼解鎖題庫」（view `unlock`）。Web Crypto 以 PBKDF2-SHA256（600,000 次）導出金鑰、AES-256-GCM 解密、DecompressionStream 解 gzip。勾選「記住這台裝置」會把導出的金鑰（不是密碼）存在 localStorage `quiz-ai-key`；「鎖定題庫」清除它。
- 鎖定時 AI 題目不在 QM 中，作答紀錄仍保留在 st.ans；render() 會把指向不存在題目的 exam／prac 畫面導回目錄。

### TOEIC 聽力：整段播放／逐題播放

- 題庫 `private/toeic_listening.json` 由 `tools/build_listening_quiz.py` 從紅藍本知識庫產生（加密後才上傳）。音檔與圖片也走站長金鑰加密（`data/media/`），在記憶體解密成 blob 播放。
- 各 10 回聽力 `private/toeic10_listening.json` 由 `tools/build_toeic10_listening.py` 產生（10 份 `mock:"listening"`，每回一個完整音檔，沒有 `partAudios`／英澳口音版）。媒體路徑以 `t10/` 開頭（`img/t10/TEST01_Q1.jpg`、`audio/t10/TEST01.mp3`），原檔在 `private/toeic_md/listening/media/`；網頁用 `lRaw()` 把路徑對應到未加密時的本機位置，`encrypt_ai.py` 用 `media_src()` 找原檔。時戳用 `py tools/listening_ts.py --book toeic10` 產生。
- 逐題片段：`tools/listening_ts.py` 用語音辨識找每題「Number N」、每個題組「Questions X through Y」的秒數 → `kb/audio_ts.json`；build 時寫成 Part 1／2 題目的 `t`、Part 3／4 題組（`sets[]`）的 `t`，英澳口音版是 `tA`，格式 `[開始, 結束]`（秒）。模擬考的片段以分 Part 音檔（`partAudios`）為準，章節練習以 `audio`／`audioAlt` 為準。
- 聽力畫面（`vListening`）有兩種模式，選擇記在 localStorage `quiz-lclip`：
  - 整段播放：一個 `<audio id="laudio">` 連續播完，勾選後按「交卷並檢討」一次批改；音檔播完（`ended`）會自動交卷（`lSubmit(ex,true)`，不詢問未作答題）。
  - 逐題播放（預設）：每題／每個題組有自己的播放鍵，用不在畫面裡的 `LClip.au` 播放片段、到結束秒數自動暫停；Part 1／2 選了就批改，題組三題都選了才一起批改。畫面上全是題組時（Part 3／4 練習、模擬考的 Part 3／4 分頁，`lPaged`）一個題組一頁，上方 `.setnav` 切換，目前頁記在 `lSetPage`（不存檔，預設第一個沒寫完的題組）。
- Part 3／4 題組檢討（兩種模式都一樣）：`.l-rev` 左欄是播放器（`lPlayerHTML`：播放鍵、片段內時間軸、倒退／快轉 3 秒、語速）＋圖表＋原文（`lScriptHTML` 逐句英中對照，可隱藏翻譯，記在 `quiz-lhidetr`），右欄題目與詳解；電腦版左欄 sticky、自己捲動，900px 以下改成上下排。有檢討中的題組時 `.wrap` 加 `lwide` 放寬到 1180px。
- 聽力隨機抽考（隨機抽考頁選「聽力題」，`newLRand`，`st.pr.src="lrand"`）：從篩好的候選題抽，題組只要有一題在範圍內就整組出；題卡由 `lCard` 畫（一般 `card()` 遇到聽力題會轉給它），作答走一般抽考流程、不覆蓋試卷紀錄。題組（`prGroup`）整組放同一頁（`lSetCard`，上一題／下一題用 `prStep` 跳過同組題目），作答先暫存在 `st.pr.dr`（可改），整組都選完才一起寫進 `st.pr.ans` 批改，檢討時和章節練習一樣用 `.l-rev` 左右分欄（`lSetCard` 設 `lWide` 讓版面變寬）；作答時間是題組頁的計時平均分給每題。題組的原文要等同一回抽考裡該組題目都寫完才顯示。

### TOEIC 閱讀模擬考（第一回、第二回）

- 題庫 `private/toeic_reading_mock.json` 由 `tools/build_reading_mock.py` 從紅藍本知識庫 `kb/R/R_AT1.md`、`R_AT2.md`（實戰模擬試題 1、2）產生，加密後才上傳（`data/toeic_reading_mock.enc.json`；還沒加密前是 `{"enc":1,"pending":"檔名"}` 佔位檔，本機解鎖後直接讀 private/ 明文，線上讀不到）。每份一個題組（`mock:"reading"`，`part:0`），Part 5 題目沒有 `p`，Part 6／7 以 `p` 指向 `passages`（多篇文章放 `docs`）；文章文字可含 `**粗體**`、`*斜體*`、`| 表格 |`，Part 6 空格是 `{{題號}}`。題目另有 `kp`（解答本的考點）、`voc`（詞彙）。
- 畫面 `vRMock`（`render()` 視為分欄閱讀畫面，保留左右欄捲動位置）：先顯示說明與「開始作答」，按下後 `st.rm[試卷id].t0` 開始倒數 75 分鐘（`RM_MS`，離開網頁也算時間，`setInterval` 每秒檢查，時間到自動交卷）。上方 `.setnav` 依 Part 分組切換：Part 5 一頁（`.reading.one` 單欄）、Part 6／7 一篇文章一頁。作答中的選擇存在 `st.p7d`，交卷（`rmSubmit`）才寫進 `st.ans` 並記 `st.rm[id].sub`；作答時間＝用掉的時間平均分給有作答的題目。交卷後（或 st.ans 已有這份的作答）是檢討模式：總分與各 Part 分數、逐題翻譯／考點／詳解／詞彙／筆記，右欄可切換全文翻譯；「重新作答」清掉這份的作答與 `st.rm`。`st.rm` 不同步。

### 檢討筆記與筆記複習

- 作答後的詳解下方有「我的筆記」（`noteBox`），單題、抽考、Part 6／7 題組檢討都有。存在 `st.notes`／`st.noteT`（鍵同作答 id），隨 Gist 同步與備份碼（mergeMap 合併）；清除作答紀錄不會刪筆記。
- Markdown＋LaTeX：第一次顯示筆記時才從 jsDelivr 載入 marked 12.0.2、KaTeX 0.16.11、DOMPurify 3.1.6（`MD.load`）；離線時顯示原文。`MD.RE` 先保護程式碼與 `\$`，`$` 後接數字不算公式。
- 隨機抽考多一個範圍「有筆記的題目」；錯題分析的錯題清單標「有筆記」；複製題目會附上筆記。
- 筆記複習（view `notes`，頂列第 4 個工具，徽章＝今天到期數）：`st.nrev[id]={lv,due}`＋`nrevT`（同步合併）。第一次寫筆記時排在明天（lv0）；`NREV_DAYS=[1,3,7,14]`，複習時答對 lv+1、答錯回 lv0，lv4＝已熟練（due:null，可「重新複習」排回今天）。due 是當地午夜。複習用 st.pr（src `nrev`，scope 站長 `all`／對外 `toeic`），作答前不顯示筆記；`nrevGrade` 在 pick 時評分。

### 單字卡

- 存卡片：單字提示框（`glShow`）下方有「存片語」「存單字」按鈕（提示框可點，滑鼠移出 280ms 後才關）。單字存原形（`glWordCard`：took → take、profits → profit）；例句取所在句子（`glSentence`，題幹空格用 `.qtext` 的 `data-fill` 填回正解）；出處是目前題目 id（`glSrc`）。
- 資料：`st.vocab[鍵]`，鍵為「w:字」或「p:片語」，值 `{k,t,m,ex,src,at,note,rv}`；`st.vocabT` 記修改／刪除時間，隨 Gist 同步與備份碼（mergeMap 合併，刪除也會同步）。所有寫入走 `vocabSet`。
- 頁面（view `vocab`，頂列第 1 個工具，徽章＝今日任務還沒翻的張數）：「今日任務」＝今天和昨天存的卡片（`vTask`，先列昨天的）；點卡片翻面看釋義與例句（例句中標出該字），今天翻過面（`rv`）就算完成（`vDone`）。「全部」依存入日期分組。卡片有出處連結、複製（字、釋義、例句、出處、筆記）、筆記（純文字，`vnote-in`）、刪除。翻面狀態只在本次瀏覽（`vFlip`）。

### 作答計時、刷題統計與進步曲線

- `QT={key,start,away}`；`timingKey()`：單題 "q|id"、抽考 "p|id|i"、Part 6/7 題組 "set|exId|p"；已作答、頁面隱藏或視窗失焦時為 null。`syncTimer()` 在 render() 結尾與 visibility/blur/focus 時呼叫，key 改變就從 0 重新計時。
- 送出時 `logTime(id,ms,ok,{src})`；Part 6/7 交卷時總時間 ÷ 題數（記 ms、set、sm）。紀錄存 `st.tlog`（保留 180 天），獨立於 st.ans：清除作答紀錄／錯題重做不會刪除，重做會再記一筆。同步 payload 含 tlog，`mergeTlog` 以 t|id 聯集。
- `vStats`：今天 KPI、目前速度（最近 10 題）、進步曲線（`vTrend`）、今天各科、最近 14 天表。
- 進步曲線：依科目分類（`tlogCat`：TOEIC Part 5/6/7、統計學、巨量資料概論、AI 初級／中級），只畫有作答的日子；兩張單軸小圖（正確率 0–100%、平均每題時間），SVG 依容器寬度產生（resize 時重繪），hover/tap 顯示 tooltip；「含重做／只算第一次作答」切換（`firstOnly` 以題目第一筆紀錄為準）。偏好存 st.chartCat、st.chartFirst。
- 全域 CSS `svg{width:18px;stroke:currentColor}` 是給 icon 用的，圖表需 `.chart` 覆寫並讓 text/hit 圓 stroke:none。

### 紀錄相容與同步

- 作答鍵為「題組id-索引」。新增題目一律接在題組最後面或新增題組，不可插入中間、刪題或改題組 ID（`tools/update_manifest.py` 會擋）。
- 遷移表（留在 index.html）：EXAM_MIGRATE、QUESTION_MIGRATE、P7_OLD_EXAMS、OPTION_REMAP；remapOpts 在 migrateData 之前。
- Gist 同步：quiz-sync-v1／quiz-progress.json（含 tlog）。`Gist.txt` 是同步資料的本機副本，已排除上傳。

## 題庫內容現況

| 科目 | 題數 | 備註 |
|---|---|---|
| TOEIC Part 5 文法與綜合 | 3523 | mock 80＋s1 645＋s2 645＋s3 280＋adv 1873 |
| TOEIC Part 5 單字 Day 1–30 | 1800 | 見下方專節 |
| TOEIC Part 6 Test 1–17 | 272 | |
| TOEIC Part 7 Test 1–8＋Double／Triple Practice | 457 | 規格見下方「TOEIC Part 7」一節 |
| 統計學考古題 | 271 | 答案與官方一致 |
| 巨量資料概論 考古題／模擬考 | 279／75 | 考古題已依官方 PDF 核對 |
| AI應用規劃師 初級 | 610 | 答案與書中答案表全部一致 |
| AI應用規劃師 中級（科目一／二／三） | 377／467／397 | 由指南 PDF 文字層解析 |

- 統計學：s109 Q1 直方圖文字已修正；補／修多則詳解。
- AI 初級答案頁（PDF）：25/44/62/82/105/126/143/161/177/195/214/235/256/272/288/304。
- AI 中級：9 題書中答案表與解析不符（c4 Q23、bd2 Q38、bd3 Q9、bd7 Q27、bd13 Q3/5/9/12/17），已依解析更正並在詳解註明；bd1 Q15（偏態）、ml2 Q7（線性變換）保留書中答案並加註意；bd1 Q33–37 書中無解析，已補充說明。
- 巨量資料：模擬考 e1–e3 已修正；未涵蓋考點可做模擬測驗 4、5。
- TOEIC Part 5：各題組 A／B／C／D 正解數盡量平均（215 題的題組為 54／54／54／53）；題目附四選一、提示 `h`、翻譯 `trans`、詳解 `e`、干擾選項說明 `w`。

## 大量出題流程

規格檔＋檢查程式 → 平行撰寫子代理 → 平行審題子代理 → 打亂答案位置合併（接在題組最後面）→ `py tools/update_manifest.py` → 瀏覽器實測。過去的出題規格與檢查程式放在 scratchpad 的 p5new/、p7new/。

## TOEIC Part 5：題型比例與依比例抽考

隨機抽考頁選「閱讀題」、只勾 Part 5、範圍「全部題目」時，出題方式可選「依真考題型比例」「基礎」或「完全隨機」，題數自訂（原本的「每日 15 題」入口已併進隨機抽考）。下文的「每日 15 題」指 15 題時的平均。

### 真考比例（2026-10-27 查證）

ETS 沒有公布 Part 5 各題型的題數，以下是日本備考網站與講座的估計：

- **詞性（品詞）**：一回 30 題中約 7–8 題（STUDYing、fumi-eigo），EnglishBlitz 估約 40%。
- **單字（語彙）**：約 15 題（STUDYing），EnglishBlitz 估約 30%，ALC 的分析是 53%。
- **文法**：其餘約 9–10 題。常考的是動詞形態（時態、語態、真動詞、主詞動詞一致）、連接詞與介系詞的區分、代名詞、關係詞，比較級、分詞、不定詞與動名詞較少。

來源：[STUDYing Part 5 攻略](https://studying.jp/toeic/about-more/part5-strategy.html)、[ENGLISH JOURNAL 語彙問題](https://ej.alc.co.jp/tag/TOEIC/toeic-auth-part5-20250615)、[EnglishBlitz 文法對策](https://englishblitz.com/resources/toeic-guide/part5-grammar)、[fumi-eigo Part 5 對策](https://fumi-eigo.com/toeic-part5/)。各來源差異不小，本站取中間值。

### 本站採用的比例（`index.html` 的 `P5_MIX`）

| 類別 | 每 30 題 | 每日 15 題平均 | 對應標籤 |
|---|---|---|---|
| 詞性 | 8 | 4 | t_p5pos、t_pos、t_p5noun |
| 單字 | 10 | 5 | t_p5vocab、t_p5chunk、t_vocab、單字 Day 1–30（t_p5wn／wv／wa／wd／wp）、t_p5adv |
| 介系詞 | 2 | 1 | t_p5prep |
| 動詞形態 | 4 | 2 | t_p5fin、t_p5voice、t_p5tense、t_p5agree |
| 連接詞 | 2 | 1 | t_p5conj、t_conn、t_p5cadv、t_p5corr |
| 代名詞 | 1.5 | 0.75 | t_p5pron、t_p5indef |
| 關係詞與子句 | 1 | 0.5 | t_p5rel、t_p5ncl |
| 其他文法 | 1.5 | 0.75 | t_p5qty、t_p5det、t_p5comp、t_p5deg、t_p5part、t_p5ger、t_p5caus、t_p5inv、t_p5subj、t_grammar |

**出題方式（`newDaily`）**

- 每類先給整數題數，剩下的名額依小數部分隨機分配，所以單回會有一點差異，但長期平均符合比例。瀏覽器模擬 2,000 回，結果與上表一致。
- 「基礎每日 15 題」只用第一～三階段的題組。沒有的題型（介系詞、關係詞、其他文法）按比例分給其他題型。
- 各類內合計最多 3 題錯題複習，其餘優先出沒做過的題目，3 天內做過的排最後（判斷方式見「隨機抽考」的 `drawInfo`）。題目頁副標題會顯示本回的題型分配。
- 每日 15 題**不限時**：寫一題、檢討一題，已移除原本的 6 分鐘倒數。每題的作答計時仍會記錄，供刷題統計使用。
- **新增 Part 5 標籤時，要把它加進 `P5_MIX` 的某一類**，否則不會出現在每日 15 題。可以在瀏覽器主控台用 `p5Ids(false).map(id=>QM[id].q.g)` 檢查有沒有漏掉的標籤。

## TOEIC Part 5 單字題（Day 1–30）：出題原則與分工方式

> 給接手的 AI Agent：改這批題目前，請先讀完本節。

### 檔案與工具

- 教材：`private/TOEIC_Vocabulary_Day1-30.md`（市售單字書整理，Day 1–30、每 Day 約 100 個字）。**著作權內容**，已由 private/ 的 .gitignore 規則排除，不可上傳。
- 題庫：`data/toeic_p5_words.json`。題組 `p5_w01`–`p5_w30`（stage 7），各 60 題，共 1800 題。首頁位置：TOEIC → Part 5 →「單字　Day 1–30」。
- 工具：`tools/p5_words.py`，在專案資料夾執行。
  - `check`：檢查整個題庫並印出涵蓋率。
  - `add 草稿.json [--dry]`：新增題目（格式見檔頭說明）。
  - `rewrite 草稿.json [--dry]`：改寫既有題目的 `w`（其他選項說明），不動題目、選項與正解。
  - `version`：手動修改題庫後，統一格式並更新 manifest 版本。
- 標籤依詞性分：`t_p5wn` 名詞、`t_p5wv` 動詞、`t_p5wa` 形容詞、`t_p5wd` 副詞、`t_p5wp` 片語，錯題分析會依此分組。

### 目前狀態

- 各 Day 分三批出題（20 → 40 → 60），每批新題的正解都取自該 Day 尚未當正解的詞條。各 Day 的 A／B／C／D 正解各 15 題，全庫各 450 題。
- **涵蓋情況：** 教材各 Day 詞條合計 2994（跨 Day 重複仍分別計算），依 Day 計算已考過約 1800 個正解考點，約 60%；尚未涵蓋全部教材。`check` 以 `target` 或正解文字計算考點，變化形對應屬近似統計，不能直接與跨 Day 去重後的教材總數比較。
- **出題依據：** 依照對多益 Part 5 的理解出題，**沒有逐題對照 ETS 官方題目**。

### 題型要像真考（出題原則）

1. **格式：** 一句商務情境句、一個空格（固定寫成 `_______`）、四個選項。
2. **選項：** 四個選項詞性相同，靠句中的線索字和語意判斷。
3. **正解：** 一定是該 Day 單字表裡的字。可以用變化形，例如 postponed、slipped my mind，`check` 會自動對應。
4. **錯誤選項要「看似可以」，不能一看就刪。** 使用以下兩種：
   - **意思相近，但搭配或語法不對（優先）。** 例如：
     - appreciative of 對 grateful for／thankful for／pleased with
     - soared 對 raised／lifted（及物）、arose（用於問題發生）
     - unplug 對 switch／shut（要加 off）
     - incur 對 occur／recur／concur
     - occupy 對 inhabit／dwell／reside
     - 其他可用的差異：及物或不及物、接 to V 或 V-ing、主詞要是人或物、可數或不可數。
   - **形近字。** 例如 prescription／description／subscription，complimentary／complementary。多益單字題也常這樣出。
   - **不要用意思差很遠、一看就能刪的字。** 例如問房間夠不夠大，不要用 spacious／marginal／therapeutic 這種組合。
5. **只能有一個答案（最重要）。** 把每個錯誤選項逐一放進句子讀一遍。只要有一個「也說得通」，就換掉。真正的同義詞不可當錯誤選項，例如 big 之於 large、shorten 之於 streamline。拿不準時，寧可改用形近字。
6. **片語題：** 挖空片語中的一個字，例如 in ___ of → lieu、comply ___ → with，四個選項都用單一字詞。草稿與題庫中的 `target` 必填完整教材搭配，例如 `"target":"in lieu of"`，正解只寫 `lieu`。`check` 會驗證填回空格後確實還原該搭配，且空格位於搭配內。
7. **解說欄位：**
   - `e` 用「【線索】句中哪個字或哪段話提示答案【正解】答案（中文）＋說明」。
   - `w` 逐一說明每個錯誤選項，每個選項兩行（網頁逐行顯示）：
     ```
     (A) afflict (v.) 折磨、使痛苦。
     → 常用被動 be afflicted with / by（疾病、災難）折磨人或地區；demand 是抽象的市場需求，不是受苦的對象。
     ```
     - 第一行：選項字、詞性（n./v./adj./adv./prep./conj./pron.，一字多詞性就都列出）、中文釋義。
     - 第二行：常考搭配或固定用法，再直接點出錯在哪裡：詞性或結構不符（後面接的介系詞、及物與否、主詞要是人）、搭配對象錯、易混淆的形近字。
     - **禁止沒有資訊的套話**：「不搭配…」「不符合題意／句意」「不是影響既有需求」這類只重複結論、沒說原因的寫法。`check` 會擋「不搭配」「題意」「句意」「字表」。
     - 全部 1800 題都已是此格式，`check` 會擋下舊的一行格式；要改既有題目的說明，用 `rewrite`。
   - `trans` 放整句中文翻譯。
   - 草稿的 `e` 和 `w` 都**不可寫 (A)(B) 等字母**，因為選項會被打亂。`add`／`rewrite` 會自動補上字母和選項字。
8. **比例：** 這批只出單字題。詞性題和文法題在其他題組已經有，這裡不需要。

### 修改規則（不可破壞作答紀錄）

- 作答紀錄以「題組 id－題目順序」記錄。**只能把新題加在題組最後面**，不可插入、刪除或調換題目順序。
- 修改既有題目時，**不要改正解的位置（a）和正解文字**，只換錯誤選項和說明。（2026-10-26 的片語改版是經授權的例外，見 CHANGELOG。）一般維護不得重新排列選項或改變考點。
- 新增題目：寫好草稿 → `py tools/p5_words.py add 草稿.json --dry` 確認無誤 → 拿掉 `--dry` 正式寫入 → `py tools/p5_words.py check` → `py tools/update_manifest.py`。
- 手動修改題庫：直接改 `data/toeic_p5_words.json` → `py tools/p5_words.py check` → `py tools/p5_words.py version` → `py tools/update_manifest.py`。

## TOEIC Part 7：命題研究與出題原則

> 給接手的 AI Agent：新增或修改 Part 7 前，請先讀完本節，寫完執行 `py tools/p7_check.py`。

### 官方規格（2026-10-27 查證）

- **題數與結構**：閱讀測驗共 100 題、75 分鐘；Part 7 共 54 題，其中單篇 29 題、多篇 25 題（IIBC 官方說明）。多篇是雙篇 2 組、三篇 3 組，每組 5 題。真考的單篇是 10 組，每組 2–4 題。
- **改制重點**：2016 年起（臺灣 2018 年）改制後加入三項，ETS 研究報告 RM-17-05 的說法是「當前使用中的溝通形式」與「連結多個來源的資訊」：
  1. 手機簡訊、即時訊息、多人線上聊天。
  2. 理解寫作者意圖的題目（言外之意）。
  3. 三篇閱讀，加上句子插入題。
- **官方題幹句型**（取自 ETS 官方樣題）：
  - `What is suggested about …?`
  - `What is indicated about …?`
  - `According to the …, why/what …?`
  - `What is NOT a stated …?`
  - `Who most likely is …?`
  - `What will … most likely do …?`
  - `At 12:15, what does Mr. X mean when he writes, "Sure thing"?`
  - `In which of the positions marked [1], [2], [3], and [4] does the following sentence best belong?`
- **文本類型**：官方指示語寫的是 magazine and newspaper articles, e-mails, and instant messages。樣題另有 advertisement、information、text message chain、advertisement＋e-mail、advertisement＋online shopping cart＋e-mail。常見類型還有 letter、memo、notice、web page、form、invoice、schedule、review、press release、job posting、coupon、menu、agenda 等。

來源：[IIBC TOEIC L&R 測驗形式](https://www.iibc-global.org/english/toeic/test/lr/about/format.html)、[ETS 官方樣題 PDF](https://www.mx.ets.org/content/dam/ets-org/pdfs/toeic/toeic-listening-reading-sample-test.pdf)、[ETS RM-17-05](https://www.es.ets.org/Media/Research/pdf/RM-17-05.pdf)、[Wikipedia: TOEIC](https://en.wikipedia.org/wiki/TOEIC)。

### 本題庫比對結果（Test 1–4、雙篇／三篇練習；Test 5–8 依本節原則新增）

**符合真考的部分**

- Test 1–4 各 54 題，結構與題號完全照真考：
  - 單篇 147–175：2/2/2/2/3/3/3/4/4/4 題。
  - 雙篇 176–185、三篇 186–200。
  - 每組都有 `Questions x-y refer to the following …`。
- 每回各有 2 題言外之意（At h:mm…mean when he writes）、2 題句子插入、2–3 題同義字，都和真考相同。
- 文本類型多元：簡訊、多人聊天、廣告、優惠券、發票、公告、網頁、徵才、備忘錄、信件、文章、新聞稿、時程表、表單、評論、估價單、收據、行程表等。
- 正確選項大多用同義改寫，不照抄原文：只有 3% 的正解和原文有連續 4 字相同，干擾選項是 4%。
- A／B／C／D 正解分布平均（每回 12–15）。
- 單篇長度中位數約 190 字（108–281），多篇每篇約 120 字，與真考相近。

**偏差（新題要避免）**

1. **正解常是最長的選項。** 原本約 50% 的題目正解是（並列）最長選項，最短選項當正解只有約 10%。「挑最長的」就能大幅提高猜對率；真考不會有這種偏誤。
   - Test 1–4 已修正：只加長 48 個干擾選項，正解、`a` 和題幹都沒動。修正後最長者占 22–26%。
   - 仍有的偏斜：正解常是「第二長」（44–56%），當「最短」的只有 6–12%。之後修題可優先把干擾選項改短。
   - 新題的正解長度名次要大致平均（每回最長者 ≤35%）。`p7_check.py` 會提醒。
   - 練習題組 p7_5 仍是 36%，還沒修。
2. **言外之意題沒有獨立標籤。** 這類題和同義字題共用 `t_p7vocab`（標籤說明有寫「特定句子的言外之意」）。新題沿用 `t_p7vocab`，避免錯題分析的分類突然改變。
3. **句子插入標記的寫法不同。** 真考印成 `-- [1] --`，本題庫寫成 `[1]`。前端與既有題目都用 `[1]`，維持現狀即可。
4. **少見的文本類型。** 菜單、議程、會議紀錄、問卷、產品說明、常見問題（FAQ）、線上購物車等真考會出現的類型，舊題沒有或很少。新題優先補這些。

### 出題原則

1. **結構**：完整模擬測驗（id `p7_t數字`）固定 54 題，照上面的組數、題號與篇數。練習題組可以只出雙篇或三篇。
2. **題型配比（每回約略）**：
   - 主旨／目的 4–5、細節 18–22、推論 6–8、NOT 題 3–5
   - 同義字 2–3、言外之意 2、句子插入 2
   - 跨篇整合：雙篇每組 1–2 題、三篇每組 2–3 題
3. **句型用官方說法**：見上方。言外之意題固定寫成 `At 2:11 P.M., what does Mr. X most likely mean when he writes, "…"?`，時間與原句必須和文章完全一致。
4. **句子插入**：文章中 `[1]`–`[4]` 各出現一次。題幹寫成 `In which of the positions marked [1], [2], [3], and [4] does the following sentence best belong?`，換行後用雙引號放插入句。選項固定是 `[1]`–`[4]`。插入句要有指示詞或轉折線索（Such、These、However）。
5. **同義字題**：`the word "X" in paragraph N`。段落依空行計算，稱謂（Dear…,）不算一段。被考的字要用到「不是最常見的那個意思」，例如 honor＝accept、draw＝attract。
6. **選項**：
   - 正解要同義改寫，不照抄原文。
   - 干擾選項要「文中有提到但答非所問」或「把人／時間／條件張冠李戴」，不能一眼就刪。
   - 四個選項長度相近，正解不要特別長或特別詳細。
7. **跨篇題**：必須同時用到兩篇以上的資訊才能作答。典型做法是一篇給規則、價目或時程，另一篇給個人情況或變動。
8. **欄位**：
   - 文章：`kind`（中文＋英文）、`head`、`text`、`trans`（全文翻譯）、`en`。多篇題組用 `docs`，頂層的 `text` 是各篇合併的純文字，供複製題目用。
   - 逐句對照翻譯（選用）：`seg`（對應 `text`）、`hseg`（對應 `head`），格式 `[["英文句子","中文"], …]`，單篇放在文章本身、多篇放在 `docs` 的每一篇。交卷檢討時右側面板可切換「題目檢討／全文翻譯」，滑鼠移到任一側的句子，兩側同一句一起標示。英文要依序切開原文，句子之間只能是空白或換行；一組裡有任何一篇對不上原文，該組就退回舊的 `trans` 折疊區塊。Test 1–8 與雙篇／三篇練習全部都有；新增的題組也要補上。用 `py tools/p7_trans.py split／apply／check` 產生草稿、寫回與檢查（`split` 是自動斷句，寫回前要逐段看過：表格列、名字縮寫、時間後面接大寫字的地方偶爾會切錯）。
   - 題目：`n`、`p`、`g`、`q`、`o`、`a`、`h`（提示）、`trans`（題目翻譯）、`e`（引用原文英文＋說明，以「故選 (X)。」結尾）、`w`（逐一說明錯誤選項）。
9. **人名、公司、地名**：一律虛構。不要使用真實企業或 ETS 題目原文。

### 修改規則

- 新增完整測驗時開新題組，放在 toeic_part7.json 中 `p7_t4` 之後、練習題組之前（首頁依檔案順序列出）。不要使用 `p7_1`–`p7_4`，這些舊 id 在遷移表 `P7_OLD_EXAMS` 中。
- 既有題組只能在最後面加題，不可調換文章或題目順序。
- 流程：寫題 → `py tools/p7_check.py p7_tN` → `py tools/update_manifest.py` → 瀏覽器實際作答一組單篇、一組三篇。
- 改了文章的 `text` 或 `head` 後，有逐句翻譯的題組要再跑 `py tools/p7_trans.py check`，對不上的句子要一起改。
