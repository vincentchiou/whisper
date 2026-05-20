---
name: whisper-project-memory
description: 壓縮這個 Whisper 字幕專案第二版的續接資訊與操作重點。當需要快速接手此專案、確認 YouTube 輸入、TXT/SEO/進階SEO 輸出、字幕術語校正、長影音分段轉錄、本地或雲端模型對接，或避免再次誤判成抽獎系統時使用。
---

# Whisper 專案 SKILL

## 固定前提

- 這是 Whisper 專案，不是抽獎系統
- 所有介面、文件、輸出都使用繁體中文
- 使用者姓名固定為 `邱文盛`
- 平台以 Windows 為主
- 主架構是 `Flask + 單頁 HTML/CSS/JS`

## 核心功能

- 本機音訊 / 影片上傳
- YouTube 影片網址輸入
- Whisper 字幕轉錄
- `fine / standard / coarse` 字幕切割
- `SRT / TXT / SEO.txt / 進階SEO.txt` 下載
- Python / Whisper / yt-dlp / ffmpeg / CUDA 環境檢查
- GPU / CUDA 狀態與切換

## 進階 SEO 規則

- `SEO.txt` 是規則式輸出，不需外部模型
- `進階SEO.txt` 才會呼叫本地或雲端模型
- 只在「轉錄開始前」已成功連線且選好模型時生成
- 支援：
  - `Ollama`
  - `LM Studio`
  - `Groq`
  - `Mistral`
  - `Google AI Studio`
  - `Google Gemini API`
  - `OpenAI`

### 進階 SEO 輸出格式

- 固定四段：
  - `一、建議標題 3 個`
  - `二、內容摘要`
  - `三、關鍵字與標籤`
  - `四、章節目錄`
- `內容摘要`
  - 先給約 300 字的摘要段落
  - 再列核心重點條列
  - 不可出現「第一點 / 第二點 / 第三點」
- `關鍵字與標籤`
  - 只能是一行 hashtags
  - 格式固定為 `#關鍵字,#關鍵字,...`
- `章節目錄`
  - 直接說該段重點
  - 每段約 1 到 2 句
  - 不可出現「這段在說明什麼」這類模板語
- 不可輸出：
  - `補充提醒`
  - `第五段`
  - `第六段`
  - 免責聲明
  - 多餘寒暄

### 長文本處理

- 若逐字稿過長，必須先分段再整合
- 不可直接把整份長逐字稿一次丟給模型
- 要先分段摘要，再整合成最終 `進階SEO.txt`
- 目標是降低 `LM Studio` / 本地模型 timeout

## 字幕與術語規則

- 優先校正 AI / 技術英文詞：
  - `OpenAI`
  - `ChatGPT`
  - `Whisper`
  - `YouTube`
  - `SEO`
  - `GPU`
  - `CUDA`
  - `NVIDIA`
  - `PyTorch`
  - `API`
  - `LLM`
- `SRT / TXT / SEO.txt / 進階SEO.txt` 一律繁體中文

## 長影音與 VAD

- 已啟用 `silero-vad`
- 長影音分段轉錄前先跑 VAD
- 沒有正常人聲的 chunk 直接略過
- 不可因最後空白段讓整體任務報錯
- 短影音也要在 Whisper 後再用 VAD 過濾異常片段
- 若 VAD 偵測失敗，要安全退回一般 Whisper 流程

## 下載檔名規則

- 所有下載檔名都用關鍵詞命名
- 總長不得超過 20 字
- 格式：
  - `關鍵詞字幕.srt`
  - `關鍵詞逐字稿.txt`
  - `關鍵詞SEO.txt`
  - `關鍵詞進階SEO.txt`

## 修改時優先檢查

- `app.py`
  - `/upload`
  - `/status/<job_id>`
  - `/download/<job_id>/<kind>`
  - `run_whisper`
  - `build_seo_text`
  - `generate_advanced_seo_text`
- `index.html`
  - AI 進階 SEO 連線區塊
  - 下載區塊
  - 狀態訊息
- `start.bat`
  - `.venv`
  - Python 偵測
  - 套件安裝

## 發布前檢查

- 掃描：
  - `*.md`
  - `*.txt`
  - `*.py`
  - `*.bat`
  - `*.html`
- 不可把以下內容推上 GitHub / Release：
  - API key
  - token
  - secret
  - password
  - client secret
  - Bearer token

## 接手順序

1. `memory.md`
2. `SKILL.md`
3. `README.md`
4. `app.py`
5. `index.html`
