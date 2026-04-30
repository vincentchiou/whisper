---
name: whisper-project-memory
description: 壓縮這個 Whisper 字幕專案第二版的續接資訊與操作重點。當需要快速接手此專案、確認 V2 的 YouTube 輸入、TXT/SEO 輸出、定位主要檔案、或避免再次誤判成抽獎系統時使用。
---

# Whisper 專案續接技能

## 先做什麼

- 先讀 `memory.md`
- 再看 `README.md`
- 然後看：
  - `app.py`
  - `index.html`
  - `start.bat`

## 專案判斷規則

- 這個專案是 Whisper 字幕工具 V2
- 不是抽獎系統
- 第二版重點是：
  - YouTube 網址輸入
  - 純文字轉錄稿輸出
  - `SEO.txt` 輸出

## 回應規則

- 一律使用繁體中文
- 說明要直接、可執行
- 先分清楚是前端、後端、Whisper、yt-dlp、ffmpeg、還是 CUDA 問題

## 功能地圖

- 本機上傳 / YouTube 輸入：`/upload`
- 工作輪詢：`/status/<job_id>`
- 下載：
  - `/download/<job_id>/srt`
  - `/download/<job_id>/txt`
  - `/download/<job_id>/seo`
- 環境檢查：`/env-check`
- 安裝：`/install`
- CUDA：`/device-info`、`/set-device`、`/cuda-diagnose`

## 常見續作流程

### 如果是 YouTube 功能有問題

- 先看 `yt-dlp` 是否安裝
- 再看 `/upload` 的 `youtube_url` 流程
- 再確認網路與 ffmpeg 是否正常
- 可用 `Me at the zoo` 這類公開影片做快速下載測試

### 如果是 TXT / SEO.txt 有問題

- 先看 `app.py` 內：
  - `segments_to_transcript_text`
  - `build_seo_text`
  - `build_chapters`
  - `top_keywords`
- 第二版已驗證過：
  - SRT / TXT / SEO 三種輸出路由可下載
  - SEO 內容會包含章節、標題與標籤建議

### 如果是下載按鈕有問題

- 先看 `index.html`
- 再確認 `/download/<job_id>/<kind>` 對應是否一致

### 如果是環境問題

- 先跑環境檢查
- 確認：
  - Python
  - Flask
  - openai-whisper
  - yt-dlp
  - PyTorch
  - ffmpeg
- 若 bundled Python 顯示 CPU 模式，不代表功能壞掉；先看轉錄是否能完成

## 不要做的事

- 不要再把專案改成抽獎系統
- 不要忘了第二版有 YouTube 功能
- 不要只改前端不檢查 API
- 不要把 `SEO.txt` 當成最終人工文案，這是建議草稿
