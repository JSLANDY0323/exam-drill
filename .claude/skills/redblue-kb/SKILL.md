---
name: redblue-kb
description: 拆解、校對 TOEIC 紅藍本（Hackers 新制多益聽力／閱讀題庫大全）PDF 成 Markdown 知識庫，或查詢紅藍本題目、解答、聽力音檔對照時使用。
---

# 紅藍本知識庫

工作流程、檔案結構、校對稿格式都寫在 `private/TOEIC/TOEIC紅藍本/kb/README.md`（Codex、Gemini 共用同一份），先完整讀它再動手：

1. 讀 `private/TOEIC/TOEIC紅藍本/kb/README.md`。
2. 看 `private/TOEIC/TOEIC紅藍本/kb/progress.md` 挑一章（或使用者指定的章節 id），一次只做一章。
3. 用 `py tools/redblue_kb.py render <書> <頁> --printed` 看原圖，對照 `raw/` 原稿寫 `L/` 或 `R/` 校對稿。
4. 跑 `py tools/redblue_kb.py check` 與 `status`，在 CHANGELOG.md 記一筆。

書是市售著作，內容不可上傳、不可放進 `data/`，回覆時不要大段貼出原文。
