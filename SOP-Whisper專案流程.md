# Whisper 專案成功操作流程

## 用途

這份文件用來保存這次整理 Whisper 專案、修正說明文件、建立記憶、並部署到 GitHub 的成功流程。

下次若要開新 Session，只要把這份 SOP 丟給助理，就能更快接手。

---

## 一、建議使用方式

開新對話時，先明確說：

1. 這個專案是 **Whisper 字幕工具**
2. 一律使用 **繁體中文**
3. 先看專案內的：
   - `memory.md`
   - `SKILL.md`
   - `README.md`
   - `AGENTS.md`
   - `CLAUDE.md`
4. 以目前可執行的 `app.py`、`index.html`、`start.bat` 為主
5. 不要被舊的抽獎需求誤導

---

## 二、這次成功流程

### 1. 先釐清專案真正方向

- 原本 `AGENTS.md` 內有抽獎系統需求
- 但實際專案內容是 Whisper
- 正確做法是以目前真正可執行的檔案為準

### 2. 重建與整理核心檔案

- 重整 `app.py`
- 重建 `index.html`
- 更新 `README.md`
- 專案改回以 Whisper 為核心，不再混入抽獎內容

### 3. 補齊續接用文件

- 建立 `memory.md`
  - 壓縮專案背景
  - 記錄已完成工作
  - 記錄重要偏好
- 建立 `SKILL.md`
  - 讓下次接手時快速判斷方向
  - 明確寫出這是 Whisper，不是抽獎系統

### 4. 對齊說明文件

- 更新 `AGENTS.md`
- 更新 `CLAUDE.md`
- 補強 `README.md`

### 5. 部署到 GitHub

- 建立 `.gitignore`
- 初始化 git
- 建立第一次 commit
- 建立 GitHub 倉庫 `vincentchiou/whisper`
- 推送到 `main`

---

## 三、下次可直接複製的提示詞

```text
這個專案是 Whisper 字幕工具，不是抽獎系統。
請一律用繁體中文回覆。

先讀這些檔案再開始：
1. memory.md
2. SKILL.md
3. README.md
4. AGENTS.md
5. CLAUDE.md

接著確認：
- app.py
- index.html
- start.bat

請先根據目前專案狀態整理已完成 / 未完成事項，
不要被舊需求誤導。
如果要修改，請以最小變更為原則。
```

---

## 四、若要繼續開發 Whisper，建議標準流程

### A. 如果是修 bug

1. 先看 `memory.md`
2. 判斷問題屬於：
   - 前端
   - Flask API
   - Whisper 轉錄
   - ffmpeg
   - GPU / CUDA
3. 再進入對應檔案修改

### B. 如果是檢查專案是否正常

1. 執行 `start.bat`
2. 測試：
   - 上傳檔案
   - 轉錄進度
   - 預覽字幕
   - 下載 `.srt`
   - 環境檢查
   - GPU 切換

### C. 如果是要再部署到 GitHub

1. `git status`
2. `git add .`
3. `git commit -m "訊息"`
4. `git push`

---

## 五、這個專案的固定規則

- 一律使用繁體中文
- 這是 Whisper 專案
- 不要再改成抽獎系統
- 優先維持目前架構
- 修改前先確認前後端 API 是否一致
- 若對話變長，要回寫 `memory.md`

---

## 六、GitHub 資訊

- GitHub 使用者名稱：`vincentchiou`
- 倉庫名稱：`whisper`
- 倉庫網址：
  - <https://github.com/vincentchiou/whisper>

