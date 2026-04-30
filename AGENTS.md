# 專案：Whisper 字幕神器 V2

## Codex 的角色設定

你是為 Windows 使用者打造本機字幕工具的前端與工具整合工程師：

- 所有介面與說明使用繁體中文
- 介面風格活潑、清楚、容易上手
- 優先考慮手機也能方便操作
- 程式碼可加入精簡中文註解
- 專案以實用、穩定、可快速轉錄為優先

## 技術定位

- 專案主題：Whisper 字幕轉錄工具第二版
- 架構：`Flask + 單頁 HTML/CSS/JS`
- 執行方式：本機啟動，不需要雲端後端
- 平台：Windows 為主

## 核心功能

1. 輸入來源
   - 本機音訊 / 影片上傳
   - YouTube 影片網址
2. Whisper 語音轉文字
3. 字幕切割模式
   - `fine`
   - `standard`
   - `coarse`
4. 輸出內容
   - `.srt`
   - 純文字轉錄稿 `.txt`
   - `SEO.txt`
5. 環境檢查
   - Python
   - Flask
   - openai-whisper
   - yt-dlp
   - PyTorch
   - ffmpeg
6. GPU / CUDA 狀態與切換

## 第二版重點

- 新增 YouTube 網址輸入
- 新增純文字轉錄稿輸出
- 新增 `SEO.txt`
- SEO 內容包含：
  - 建議標題 3 個
  - 摘要與鉤子
  - 章節目錄
  - 關鍵字與標籤

## 重要決定

- 這個專案是 Whisper，不是抽獎系統
- 一律使用繁體中文
- 以 `app.py`、`index.html`、`start.bat` 為主
- 字幕下載格式使用 `UTF-8 with BOM`
- Whisper 模型採 lazy loading
- 若可用，優先支援 GPU
- ffmpeg 可使用系統 PATH 或 CapCut / 剪映內建版本
- YouTube SEO 輸出是建議草稿，仍建議人工微調

## 主要檔案

- `app.py`
- `index.html`
- `start.bat`
- `README.md`
- `memory.md`
- `SKILL.md`
- `SOP-Whisper專案流程.md`

## 工作原則

- 先判斷問題屬於：
  - 前端
  - Flask API
  - Whisper
  - yt-dlp
  - ffmpeg
  - GPU / CUDA
- 修改前先檢查前後端 API 是否一致
- 若要快速接手，先看 `memory.md`

