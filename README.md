# Whisper 字幕神器

這是一個在本機執行的 Whisper 字幕轉錄工具，提供可愛、直覺、手機也方便操作的前端介面，並用 Flask 提供上傳、轉錄、下載與環境檢查功能。

## 目前功能

- 上傳音訊或影片檔：`mp3`、`mp4`、`wav`、`m4a`、`ogg`、`webm`
- Whisper `medium` 模型轉錄
- 三種字幕切割模式：細緻、標準、寬鬆
- 下載 UTF-8 BOM 的 `.srt`
- 檢查 Python / Flask / openai-whisper / PyTorch / ffmpeg
- 協助安裝缺少的 pip 套件
- 查看 CPU / GPU / CUDA 狀態，切換裝置與卸載模型

## 啟動方式

直接執行：

```bat
start.bat
```

程式會優先找系統 Python；若找不到，會嘗試使用內建 Python。啟動後會自動開啟：

- [http://localhost:5000](http://localhost:5000)

## 安裝需求

- Windows 10 / 11
- Python 3.11 或 3.12 與 pip
- `ffmpeg`
- 建議記憶體至少 8 GB
- 若有 NVIDIA GPU，可搭配 CUDA 版 PyTorch 加速

> Windows 版 PyTorch 官方 wheel 主要支援 Python 3.9～3.12。若另一台電腦使用 Python 3.13 / 3.14，可能會出現找不到 `torchaudio` 或 CUDA 版 PyTorch 安裝檔的錯誤；建議改裝 Python 3.11 或 3.12。

> RTX 50 系列顯卡（例如 RTX 5060 Ti / `sm_120`）需要 CUDA 12.8 版 PyTorch wheel。若看到 `sm_120 is not compatible`，請在「裝置 / CUDA」面板安裝推薦的 `cu128` 版本，或重新執行新版 `start.bat`。

## 手動安裝套件

```bat
python -m pip install -r requirements.txt
```

## ffmpeg 提醒

如果系統 PATH 還沒有 `ffmpeg`，可以：

1. 使用 CapCut / 剪映內建的 ffmpeg
2. 或自行安裝到 `C:\ffmpeg\bin`
3. 並把路徑加到系統 PATH

## 目錄

- `app.py`：Flask 後端與 Whisper 工作流程
- `index.html`：前端操作頁
- `start.bat`：Windows 啟動腳本
- `requirements.txt`：基本套件需求
- `uploads/`：暫存上傳檔案
- `memory.md`：這個專案的壓縮記憶
- `SKILL.md`：下次續接時的快速接手技能摘要

## 接手提醒

- 這個專案是 Whisper 字幕工具
- 後續對話請一律使用中文
- 若要快速接手，先看 `memory.md`
