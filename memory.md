# 專案壓縮記憶

## 專案定位

- 專案名稱：Whisper 字幕神器 V2
- 類型：本機 Whisper 字幕轉錄工具
- 架構：`Flask + 單頁 index.html`
- 平台：Windows 為主

## 第二版功能

- 支援本機上傳：
  - `mp3`
  - `mp4`
  - `wav`
  - `m4a`
  - `ogg`
  - `webm`
- 支援 YouTube 影片網址輸入
- 轉錄完成後可輸出：
  - `SRT`
  - `純文字轉錄稿 TXT`
  - `SEO.txt`

## SEO.txt 規則

- 包含：
  - 建議標題 3 個
  - 內容摘要
  - 吸引人的鉤子
  - 章節目錄
  - 關鍵字與標籤建議
- 只保留一份章節目錄
- 不要再出現「章節導覽」
- 不要輸出「補充提醒」
- 章節目錄中的每段說明，要由該段的重要關鍵字組合成短句說明
- 章節說明不能只有單字，也不能太空泛

## 字幕與轉錄稿規則

- 使用者姓名固定校正為：`邱文盛`
- AI / 科技關鍵字優先校正：
  - OpenAI
  - ChatGPT
  - Whisper
  - YouTube
  - SEO
  - GPU
  - CUDA
  - NVIDIA
  - PyTorch
  - API
  - LLM
- SRT 裡面的英文關鍵術語要盡量貼近 AI 領域正確拼法

## 長影音規則

- 若影音很長，必須先分段轉錄，再整合時間軸與輸出
- 不能因為影音太長就省略內容
- 不能中斷後只輸出前半段

## 主要檔案

- `app.py`
  - 上傳與 YouTube 下載
  - Whisper 轉錄
  - SRT / TXT / SEO.txt 生成
  - 字幕文字清理
  - 長影音分段轉錄
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

## 已完成測試

- `app.py` 語法檢查通過
- smoke test 通過：
  - `build_job_outputs`
  - `/env-check`
  - `/download/<job_id>/srt`
  - `/download/<job_id>/txt`
  - `/download/<job_id>/seo`
  - 無效 YouTube 網址驗證
- YouTube 實際下載測試通過
- YouTube → Whisper → 三種輸出端到端測試通過
- 新規則驗證通過：
  - `邱文盛` 人名校正
  - AI 關鍵字校正
  - `SEO.txt` 去除重複章節區塊
  - `SEO.txt` 去除補充提醒
  - 長影音分段轉錄觸發

## 目前觀察

- 目前機器可用 CapCut 內建 `ffmpeg`
- 有時 bundled Python 會跑 CPU，有時可偵測到 GPU
- `Whisper medium` 可正常載入並完成轉錄

## GitHub

- GitHub 帳號：`vincentchiou`
- 倉庫：`whisper`
- 網址：
  - <https://github.com/vincentchiou/whisper>

## 接手順序

1. `memory.md`
2. `SKILL.md`
3. `README.md`
4. `app.py`
5. `index.html`
