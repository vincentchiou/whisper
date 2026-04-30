# Whisper 字幕神器 V2

這是一個在本機執行的 Whisper 字幕轉錄工具，支援：

- 本機上傳音訊 / 影片
- 直接貼上 YouTube 影片網址
- 輸出 SRT 字幕
- 輸出純文字轉錄稿 TXT
- 輸出 YouTube SEO 建議內容 `SEO.txt`

整體架構是 `Flask + 單頁 HTML/CSS/JS`，適合在 Windows 上直接啟動使用。

## 第二版重點

- 新增 YouTube 網址輸入
- 新增純文字轉錄稿輸出
- 新增 `SEO.txt` 輸出，內容包含：
  - 建議標題 3 個
  - 內容摘要與吸引人的鉤子
  - SRT 章節目錄
  - 關鍵字與標籤建議

## 目前功能

- 上傳格式：`mp3`、`mp4`、`wav`、`m4a`、`ogg`、`webm`
- Whisper `medium` 模型轉錄
- 三種字幕切割模式：`fine`、`standard`、`coarse`
- 下載：
  - `.srt`
  - `.txt`
  - `SEO.txt`
- 環境檢查：
  - Python
  - Flask
  - openai-whisper
  - yt-dlp
  - PyTorch
  - ffmpeg
- CPU / GPU / CUDA 狀態查看與切換

## 啟動方式

直接執行：

```bat
start.bat
```

啟動後會開啟：

- [http://localhost:5000](http://localhost:5000)

## 安裝需求

- Windows 10 / 11
- Python 與 pip
- `ffmpeg`
- `yt-dlp`
- 建議記憶體至少 8 GB
- 若有 NVIDIA GPU，可搭配 CUDA 版 PyTorch 加速

## 手動安裝套件

```bat
python -m pip install -r requirements.txt
```

## ffmpeg 提醒

如果系統 PATH 還沒有 `ffmpeg`，可以：

1. 使用 CapCut / 剪映內建的 ffmpeg
2. 或自行安裝到 `C:\ffmpeg\bin`
3. 並把路徑加到系統 PATH

## YouTube SEO 說明

`SEO.txt` 是依目前 YouTube 官方公開建議整理的輔助輸出，方向包含：

- 標題與描述比 tags 更重要
- 描述前幾行要先說清楚影片主題
- 章節需從 `00:00` 開始，且至少 3 段
- tags 主要作為補強，不是唯一重點

這份內容是依轉錄稿自動整理的建議草稿，建議上片前再人工微調一次。

## 目錄

- `app.py`：Flask 後端與 Whisper 工作流程
- `index.html`：前端操作頁
- `start.bat`：Windows 啟動腳本
- `requirements.txt`：基本套件需求
- `memory.md`：這個專案的壓縮記憶
- `SKILL.md`：下次續接時的快速接手技能摘要
- `SOP-Whisper專案流程.md`：成功操作流程
- `uploads/`：暫存上傳檔案
