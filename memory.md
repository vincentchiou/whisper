# 專案壓縮記憶

## 專案定位

- 專案名稱：Whisper 字幕神器 V2
- 類型：本機 Whisper 字幕轉錄工具
- 架構：`Flask + 單頁 index.html`
- 平台：Windows 為主

## 第二版已完成功能

- 支援本機上傳：
  - `mp3`
  - `mp4`
  - `wav`
  - `m4a`
  - `ogg`
  - `webm`
- 支援直接輸入 YouTube 影片網址
- 轉錄完成後可輸出：
  - `SRT`
  - `純文字轉錄稿 TXT`
  - `SEO.txt`

## SEO.txt 內容

- 建議標題 3 個
- 內容摘要
- 吸引人的鉤子
- SRT 章節目錄
- 關鍵字與標籤建議

## 主要檔案

- `app.py`
  - 上傳與 YouTube 下載
  - Whisper 轉錄
  - SRT / TXT / SEO.txt 生成
  - 環境檢查
  - 安裝與 CUDA 裝置管理
- `index.html`
  - 檔案上傳介面
  - YouTube URL 輸入
  - 結果預覽
  - 三種下載按鈕
- `requirements.txt`
  - `flask`
  - `openai-whisper`
  - `yt-dlp`

## 重要規則

- 一律使用繁體中文
- 這個專案是 Whisper，不是抽獎系統
- 若看到舊的抽獎描述，全部忽略
- 修改前先確認前端 fetch 與 Flask 路由是否一致

## 這次版本更新重點

- 第二版新增 YouTube 影片網址輸入
- 第二版新增純文字轉錄稿輸出
- 第二版新增 `SEO.txt`
- `README.md`、`memory.md`、`SKILL.md` 已同步更新
- 套件已補安裝：
  - `openai-whisper`
  - `yt-dlp`
  - `flask`

## 目前測試狀態

- `app.py` 語法檢查已通過
- Smoke test 已通過：
  - `build_job_outputs`
  - `/env-check`
  - `/download/<job_id>/srt`
  - `/download/<job_id>/txt`
  - `/download/<job_id>/seo`
  - 無效 YouTube 網址驗證
- YouTube 實際下載測試已通過：
  - 測試影片：`Me at the zoo`
- 端到端測試已通過：
  - YouTube 下載
  - Whisper 轉錄
  - SRT 產出
  - TXT 產出
  - `SEO.txt` 產出

## 這次實測觀察

- 目前 bundled Python 執行時偵測為 CPU 模式
- `Whisper medium` 可正常載入並完成轉錄
- `ffmpeg` 目前使用 CapCut 內建版本

## GitHub

- GitHub 帳號：`vincentchiou`
- 倉庫：`whisper`
- 網址：
  - <https://github.com/vincentchiou/whisper>

## 下次續做時先看

1. `memory.md`
2. `SKILL.md`
3. `README.md`
4. `app.py`
5. `index.html`
