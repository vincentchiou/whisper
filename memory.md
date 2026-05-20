# Whisper 專案壓縮記憶

## 專案定位

- 專案名稱：Whisper 字幕神器 V2
- 主題：本機字幕轉錄工具，不是抽獎系統
- 技術：`Flask + 單頁 HTML/CSS/JS`
- 平台：Windows 為主
- 語言：所有介面、文件、輸出都使用繁體中文

## 目前功能

- 支援本機音訊 / 影片上傳
- 支援 YouTube 影片網址輸入
- Whisper 字幕轉錄
- 字幕切割模式：`fine`、`standard`、`coarse`
- 下載：
  - `SRT`
  - `TXT`
  - `SEO.txt`
  - `進階SEO.txt`
- 環境檢查：
  - Python
  - Flask
  - openai-whisper
  - yt-dlp
  - requests
  - silero-vad
  - PyTorch
  - ffmpeg
- GPU / CUDA 偵測與切換

## 進階 SEO 現況

- `SEO.txt` 是規則式輸出，不需要外部模型
- `進階SEO.txt` 才會呼叫本地或雲端模型
- 支援服務：
  - `Ollama`
  - `LM Studio`
  - `Groq`
  - `Mistral`
  - `Google AI Studio`
  - `Google Gemini API`
  - `OpenAI`
- 只有在「開始這次轉錄之前」已連線成功並選好模型，才會生成 `進階SEO.txt`
- API Key 只保留在瀏覽器工作階段，不寫入專案檔案

## 進階 SEO 固定規則

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
  - 只輸出一行 hashtags
  - 格式固定為 `#關鍵字,#關鍵字,...`
- `章節目錄`
  - 直接說明該段重點
  - 每段約 1 到 2 句
  - 不可出現「這段在說明什麼」這類模板語
- 不可輸出：
  - `補充提醒`
  - `第五段`
  - `第六段`
  - 免責聲明
  - 多餘寒暄

## 長文本與超時修正

- 進階 SEO 已改成長文本自動分段處理
- 流程：
  1. 先把長逐字稿切段
  2. 分段整理摘要 / 重點 / 關鍵字 / 章節
  3. 再整合成最後的 `進階SEO.txt`
- 目的：
  - 降低 `LM Studio` / 本地模型 read timeout
  - 避免長文一次丟進模型失敗
- 已補上品質檢查與必要時重試

## Silero VAD

- 專案已接入 `silero-vad`
- 短影音：
  - Whisper 完成後再用 VAD 語音區間過濾異常字幕片段
- 長影音：
  - 分段轉錄前先檢查是否有正常人聲
  - 無語音 chunk 直接略過
  - 不會因尾段空白就讓整體任務失敗
- 若 VAD 偵測失敗，安全退回一般 Whisper 流程

## 檔名規則

- 所有下載檔案都改用關鍵詞短檔名
- 限制在 20 字以內
- 格式：
  - `關鍵詞字幕.srt`
  - `關鍵詞逐字稿.txt`
  - `關鍵詞SEO.txt`
  - `關鍵詞進階SEO.txt`

## 固定偏好

- 使用者姓名固定校正為 `邱文盛`
- AI / 技術英文詞彙要優先校正：
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
- 所有對外輸出一律繁體中文

## 發布與安全規則

- 發布 GitHub / Release 前，必須掃描：
  - `*.md`
  - `*.txt`
  - `*.py`
  - `*.bat`
  - `*.html`
- 不可包含：
  - API key
  - token
  - secret
  - password
  - client secret
  - Bearer token
- 一般說明文字裡提到 `token` 不算機密，但仍要人工判斷

## 主要檔案

- `app.py`
- `index.html`
- `start.bat`
- `requirements.txt`
- `README.md`
- `memory.md`
- `SKILL.md`

## 接手順序

1. `memory.md`
2. `SKILL.md`
3. `README.md`
4. `app.py`
5. `index.html`

## GitHub

- Repo：<https://github.com/vincentchiou/whisper>
