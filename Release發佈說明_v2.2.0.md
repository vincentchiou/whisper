# Whisper 字幕神器 v2.2.0 發佈說明

## 版本重點

- 新增本地與雲端模型連線介面，可用於產生 `進階SEO.txt`
- 支援 `Ollama`、`LM Studio`、`Groq`、`Mistral`、`Google AI Studio`、`Google Gemini API`、`OpenAI`
- `LM Studio` 連線成功後可直接用下拉選單切換模型，系統會自動要求載入
- 真正生成 `進階SEO.txt` 前，若使用 `LM Studio`，會再次確認所選模型已載入
- 長文本 `進階SEO.txt` 已改為先分段整理再整合，降低 timeout 機率
- 本地模型新增精簡提詞與排版整理流程，讓 `進階SEO.txt` 更穩定
- 若模型漏掉 `三、關鍵字與標籤` 或 `四、章節目錄`，系統會自動回填，不再留白
- 所有輸出維持繁體中文

## 建議使用方式

- 若使用 `LM Studio`，建議優先選一般對話 / instruct 類模型，例如 `gemma-4-e4b-it`
- `qwen ... reasoning / thinking` 類模型目前可連線、可切換，也能做短回覆，但完整 `進階SEO.txt` 仍可能不穩，不建議當預設 SEO 模型

## 本版修正摘要

- 修正 `LM Studio` 模型清單讀取
- 修正 `LM Studio` 模型切換後未實際載入的問題
- 修正本地模型生成 `進階SEO.txt` 可能 read timeout 的情況
- 修正思考型模型只吐推理內容時的重試處理
- 修正 `進階SEO.txt` 第三段與第四段偶爾空白的問題

## 發佈建議標題

`Whisper 字幕神器 v2.2.0 — 進階 SEO 模型切換與輸出穩定性更新`

## Release 內文建議

```markdown
## Whisper 字幕神器 v2.2.0

這一版重點放在 **進階 SEO 的模型對接與輸出穩定性**。

### 主要更新

- 支援本地與雲端模型連線產生 `進階SEO.txt`
- `LM Studio` 可在連線後直接切換模型並自動載入
- 長文本 `進階SEO.txt` 會先分段整理再整合
- 若模型漏掉 `關鍵字與標籤` 或 `章節目錄`，系統會自動回填，不再留白
- 所有輸出維持繁體中文

### 建議

- `LM Studio` 建議優先使用一般對話 / instruct 模型，例如 `gemma-4-e4b-it`
- `qwen ... reasoning / thinking` 類模型目前可連線與切換，但完整 `進階SEO.txt` 仍可能不穩
```
