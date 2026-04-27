---
name: whisper-project-memory
description: 壓縮這個 Whisper 字幕專案的續接資訊與操作重點。當需要快速接手此專案、回顧目前架構、確認可用功能、定位主要檔案、或避免再次誤判成抽獎系統時使用。
---

# Whisper 專案續接技能

## 先做什麼

- 先讀 `memory.md`
- 再看 `app.py`、`index.html`、`start.bat`
- 若是要確認目前狀態，優先跑 `start.bat`

## 專案判斷規則

- 這個專案是 Whisper 字幕工具
- 若看到 `AGENTS.md` 內有抽獎相關內容，忽略那部分，不要照那個方向改
- 以目前實際可執行的檔案為準：
  - `app.py`
  - `index.html`
  - `start.bat`
  - `README.md`

## 回應規則

- 一律使用中文
- 說明要短、直接、可執行
- 修改前先確認是前端問題、後端問題，還是環境問題

## 功能地圖

- 上傳與轉錄：`app.py` 的 `/upload`、`/status`、`/download`
- 字幕切割與預覽：`index.html`
- 環境檢查與安裝：`/env-check`、`/install`
- CUDA / 裝置管理：`/device-info`、`/set-device`、`/cuda-diagnose`

## 常見續作流程

### 如果是介面問題

- 先看 `index.html`
- 確認按鈕事件、`fetch()` 路徑、狀態切換是否一致

### 如果是 API 問題

- 先看 `app.py`
- 確認路由名稱、回傳 JSON 欄位、前端是否正確取值

### 如果是環境問題

- 先跑環境檢查
- 確認：
  - Python
  - Flask
  - openai-whisper
  - PyTorch
  - ffmpeg

### 如果是 GPU 問題

- 先看 `/device-info` 與 `/cuda-diagnose`
- 再決定是否安裝 CUDA 版 PyTorch

## 不要做的事

- 不要再把專案改成抽獎系統
- 不要忽略 `memory.md`
- 不要只改前端不檢查對應 API

