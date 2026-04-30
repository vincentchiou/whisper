# 專案工作說明

## 專案身份

這個資料夾是 **Whisper 字幕神器 V2**。

不是抽獎系統。

## 第二版目標

讓使用者可以：

- 上傳音訊或影片
- 或直接貼上 YouTube 影片網址
- 用 Whisper 進行轉錄
- 下載：
  - SRT
  - 純文字轉錄稿
  - `SEO.txt`

## 目前狀態

- `app.py` 已支援第二版功能
- `index.html` 已支援雙輸入與三種輸出
- `requirements.txt` 已加入 `yt-dlp`
- `README.md`、`memory.md`、`SKILL.md` 已同步
- 第二版 smoke test 已通過
- 第二版 YouTube 端到端測試已通過

## 接手順序

1. 先讀 `memory.md`
2. 再看 `README.md`
3. 若是修功能：
   - 前端看 `index.html`
   - 後端看 `app.py`
4. 若是測完整流程，先跑 `start.bat`

## 常見檢查點

### YouTube 網址失敗

- 看 `yt-dlp` 是否安裝
- 看網路是否正常
- 看 ffmpeg 是否可用

### SRT / TXT / SEO.txt 有問題

- 看 `build_job_outputs`
- 看 `segments_to_transcript_text`
- 看 `build_seo_text`

### GPU 沒開起來

- 看 `/device-info`
- 看 `/cuda-diagnose`
- 先確認能不能正常轉錄，再判斷是否一定要修 GPU

