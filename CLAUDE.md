# 專案工作說明

## 專案身份

這個資料夾是 **Whisper 字幕神器**。

## 專案目標

建立一個在 Windows 本機執行的 Whisper 字幕工具，讓使用者可以：

- 上傳音訊或影片
- 等待 Whisper 轉錄
- 預覽字幕結果
- 下載 `.srt`
- 檢查環境與安裝缺少套件
- 查看並切換 CPU / GPU 執行模式

## 目前狀態

- `app.py` 已整理為可用的 Flask 後端
- `index.html` 已整理為單頁操作介面
- `README.md` 已改為 Whisper 說明
- `memory.md` 已建立，用來壓縮專案記憶
- `SKILL.md` 已建立，用來快速續接

## 接手順序

1. 先讀 `memory.md`
2. 再看 `README.md`
3. 若是修功能：
   - 前端看 `index.html`
   - 後端看 `app.py`
4. 若是驗證整體流程，先跑 `start.bat`

## 實作偏好

- 一律使用繁體中文
- 修改要以實際執行流程為準
- 優先保留目前 Whisper 架構，不要大改方向
- 若只是修 bug，先做最小修改

## 常見檢查點

### 上傳失敗

- 檢查 `index.html` 的 `fetch("/upload")`
- 檢查 `app.py` 的副檔名限制與儲存路徑

### 一直轉圈沒有結果

- 檢查 `/status/<job_id>` 的輪詢
- 檢查 Whisper 模型是否成功載入
- 檢查 ffmpeg 是否可用

### 下載失敗

- 檢查 `/download/<job_id>`
- 檢查工作狀態是否真的到 `done`

### GPU 無法使用

- 檢查 `/device-info`
- 檢查 `/cuda-diagnose`
- 必要時使用 CUDA 安裝流程

