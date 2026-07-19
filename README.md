# Whisper 字幕神器 V2

Whisper 字幕神器 V2 是一個給 Windows 使用者的本機字幕工具，支援上傳音訊 / 影片，或直接貼上 YouTube 網址，快速輸出字幕、逐字稿與 SEO 內容。

## 主要功能

- 上傳本機音訊 / 影片
- 貼上 YouTube 影片網址
- Whisper 語音轉文字
- 字幕切割模式：`fine`、`standard`、`coarse`
- 下載 `SRT / TXT / SEO.txt / 進階SEO.txt`
- 支援本地與雲端模型生成進階 SEO
- 啟用 Silero VAD 過濾無語音或異常片段
- 顯示 Python、Whisper、yt-dlp、PyTorch、ffmpeg、CUDA 狀態

## 輸出檔案

每次下載的檔名都會改用影片或逐字稿的關鍵詞命名，並限制在 20 字以內，方便整理：

- `關鍵詞字幕.srt`
- `關鍵詞逐字稿.txt`
- `關鍵詞SEO.txt`
- `關鍵詞進階SEO.txt`

所有文字檔皆使用 `UTF-8 with BOM` 輸出，方便 Windows 直接開啟。

## 進階 SEO

基礎 `SEO.txt` 使用規則式整理，不需要外部模型。  
若要產生整理品質更高的 `進階SEO.txt`，請先在介面左側完成模型連線，並選好模型後再開始轉錄。

目前支援：

- 本地模型：`Ollama`、`LM Studio`
- 免費 / 低門檻雲端：`Groq`、`Mistral`、`Google AI Studio`
- 付費雲端：`Google Gemini API`、`OpenAI`

模型選擇規則：

- 連線成功後可直接用下拉選單選模型
- 若是 `LM Studio`，切換下拉選單後會自動要求 LM Studio 載入該模型
- 就算沒有手動重選，下次真正生成 `進階SEO.txt` 前也會再次確認 `LM Studio` 已載入該模型
- 若思考型模型第一輪只回推理內容，系統會自動再要求一次最終答案，降低空白回應機率
- `LM Studio` 建議優先選一般對話 / instruct 模型，例如 `gemma-4-e4b-it`
- `qwen ... reasoning / thinking` 這類思考型模型可連線與切換，但完整 `進階SEO.txt` 仍可能只吐推理內容，不建議當預設 SEO 模型
- 若模型漏掉「關鍵字與標籤」或「章節目錄」，系統會自動用程式分析結果補回，不讓第三、四段留白

注意事項：

- API Key 只保留在這次瀏覽器工作階段，不會寫進專案檔案
- 只有在「開始這次轉錄之前」已成功連線並選好模型，才會生成 `進階SEO.txt`

### 進階 SEO 固定格式

`進階SEO.txt` 固定輸出四段：

1. `一、建議標題 3 個`
2. `二、內容摘要`
3. `三、關鍵字與標籤`
4. `四、章節目錄`

格式規則：

- `內容摘要`
  - 先給約 300 字的摘要段落
  - 再用條列列出核心重點
  - 不可出現「第一點 / 第二點 / 第三點」
- `關鍵字與標籤`
  - 只輸出一行 hashtags
  - 格式固定為 `#關鍵字,#關鍵字,...`
- `章節目錄`
  - 直接說明該段重點
  - 每段約 1 到 2 句
  - 不可出現「這段在說明什麼」這類模板語
- 不可輸出 `補充提醒`、`第五段`、`第六段`、免責聲明或多餘寒暄

### 長文本處理

若逐字稿太長，進階 SEO 會自動：

1. 先把內容切成多段
2. 分段交給模型整理重點
3. 再把分段結果整合成最後的 `進階SEO.txt`

這樣可以降低本地模型或雲端模型因內容過長而超時的機率，特別是 `LM Studio` 或較小型本地模型。

## Silero VAD

專案已接入 `silero-vad`：

- 短影音：Whisper 完成後，會再過濾明顯不正常的字幕片段
- 長影音：分段轉錄前會先判斷該段是否有正常人聲
- 沒有可用人聲的 chunk 會略過，不會因最後一段空白就讓整體失敗

如果 VAD 偵測失敗，系統會自動退回一般 Whisper 流程，不會直接中斷整次任務。

## 驗證與環境診斷

2026-07-19 已完成一輪專案驗證與程式碼整理：

- `app.py` 已移除被後面同名函式覆蓋的 SEO 死碼，降低後續維護與除錯風險。
- 核心 Flask API smoke test 通過：`/`、`/env-check`、`/device-info`、`/cuda-diagnose`、`/llm/providers`。
- `/env-check` 已可區分「尚未安裝」與「套件已安裝但損壞 / DLL 載入失敗」。
- PyTorch DLL、`requests` bytecode、`yt-dlp` 依賴損壞時，會在環境檢查中顯示可讀錯誤，不會讓端點直接 500。

若環境檢查出現 `marshal data too short`、`PyTorch 載入失敗`、`cupti64_2025.1.1.dll` 或類似 DLL 錯誤，通常代表專案 `.venv` 已損壞。建議先關閉伺服器後重建 `.venv`，再重新執行 `start.bat`。

實際轉錄效能的關鍵檢查順序：

1. `.venv` 內的 `torch` 可正常匯入。
2. `/cuda-diagnose` 顯示 CUDA 可用。
3. RTX 50 系列 GPU 使用 CUDA 12.8 版 PyTorch wheel。
4. Whisper 模型實際跑在 GPU，而不是退回 CPU。
## 啟動方式

在專案資料夾直接執行：

```bat
start.bat
```

瀏覽器開啟：

- [http://localhost:5000](http://localhost:5000)

## 第一次安裝

專案會在資料夾內建立自己的 `.venv`，避免和其他 Python 環境互相干擾。

主要依賴：

```txt
flask
openai-whisper
yt-dlp
requests
silero-vad
```

## ffmpeg

程式會依序嘗試：

- 系統 `PATH`
- `C:\ffmpeg\bin`
- `C:\Program Files\ffmpeg\bin`
- CapCut / 剪映 內建 ffmpeg

## 主要檔案

- [app.py](</H:/我的雲端硬碟/Agent/project/專案-Whisper - GPT/app.py>)
- [index.html](</H:/我的雲端硬碟/Agent/project/專案-Whisper - GPT/index.html>)
- [start.bat](</H:/我的雲端硬碟/Agent/project/專案-Whisper - GPT/start.bat>)
- [requirements.txt](</H:/我的雲端硬碟/Agent/project/專案-Whisper - GPT/requirements.txt>)
- [memory.md](</H:/我的雲端硬碟/Agent/project/專案-Whisper - GPT/memory.md>)
- [SKILL.md](</H:/我的雲端硬碟/Agent/project/專案-Whisper - GPT/SKILL.md>)

## 發布前規則

- 所有對外輸出一律使用繁體中文
- 發布 GitHub / Release 前，必須掃描 `md / txt / py / bat / html` 檔案
- 不可把 API key、token、secret、password、個人憑證推上 GitHub

## GitHub

- Repo: [vincentchiou/whisper](https://github.com/vincentchiou/whisper)
