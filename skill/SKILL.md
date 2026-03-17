---
name: generate-meeting-notes
description: >
  當使用者提到錄音檔（.m4a、.mp3、.wav 等）、想產生會議記錄、處理音訊、
  上傳至 NotebookLM、或說「幫我處理這次會議」、「generate meeting notes」、
  「音訊轉文字」、「整理會議內容」時，請主動使用此 skill。
  功能：自動將會議錄音拆分上傳至 NotebookLM → AI 分析 → 產生結構化繁體中文會議記錄
  → 建立 Google Doc → 移至公司 Shared Drive 指定資料夾 → 發送 Slack 通知。
  支援多種會議類型，每種類型對應獨立的 Notebook 與 Drive 資料夾。
allowed-tools: Bash, Read, Write
---

# Generate Meeting Notes

將會議錄音自動轉換為 Google Doc 格式的結構化會議記錄。

## 使用前提

1. 已安裝 `ffmpeg`（`brew install ffmpeg`）
2. 已執行 NotebookLM 認證（首次設定時會引導）
3. 已設定 Google Drive 認證（首次設定時會引導）
4. 已完成首次設定（見下方）

## 首次設定

```bash
cd {SKILL_BASE_DIR} && uv run skill/scripts/setup.py
```

設定後產生 `~/.config/generate-meeting-notes/config.json`，結構如下：

```json
{
  "meetings": {
    "data內會": {
      "notebook_name": "DataTeam 會議記錄",
      "folder_id": "1ItMYP0...",
      "folder_name": "週一週四_Data_內會",
      "series_name": "Data內會",
      "slack_channel": "C03XXXXXXX",
      "attendees": ["Alice", "Bob", "Carol", "PM-Name"],
      "custom_prompt": "本次會議報告順序固定如下：Alice → Bob → Carol，皆向 PM-Name（PM）報告。"
    }
  },
  "prompt_path": "~/.config/generate-meeting-notes/prompt.md"
}
```

**各欄位說明：**
- `attendees`：固定與會者清單，腳本自動填入 Google Doc 的「與會者」欄位
- `custom_prompt`：附加給 NotebookLM 的補充說明（例如報告順序、人名對照），有效提升講者辨識品質
- `folder_name`：Slack 通知中顯示的雲端路徑名稱

新增或修改會議類型：直接編輯 `~/.config/generate-meeting-notes/config.json`，在 `meetings` 下新增一個 key。

## 執行流程（Agent 必讀）

執行前必須依序向使用者確認以下資訊，**三個問題確認完畢才執行腳本**：

### Step 1：確認音訊檔路徑

如果使用者沒有提供音訊檔路徑，詢問：
> 請提供音訊檔路徑（例：`~/Desktop/data_meeting_20260311.m4a`）

### Step 2：確認會議類型

讀取 config 取得可用的會議類型：

```bash
cat ~/.config/generate-meeting-notes/config.json
```

列出 `meetings` 的所有 key，詢問使用者：
> 這是哪種會議？請選擇：
> 1. data內會
> 2. pm會議
> 3. data教授會議

### Step 3：確認 Slack channel

先讀取 config，若該會議類型有設定 `slack_channel`（非空字串），直接告知使用者：
> 完成後將自動發送通知到 config 設定的 channel（ID：`{slack_channel}`）。如需更改請告知。

若 `slack_channel` 為空，提醒使用者：
> 該會議類型尚未設定 Slack channel，完成後不會自動發送通知。如需設定，請重新執行 setup.py 並填入 Channel ID。

### Step 4：執行腳本

三個資訊都確認後執行（加上 `--delete-segments` 讓腳本完成後自動清理暫存片段，不需手動確認）：

```bash
cd {SKILL_BASE_DIR} && uv run skill/scripts/generate_meeting_notes.py <audio_file_path> --meeting <meeting_key> --delete-segments
```

範例：
```bash
cd {SKILL_BASE_DIR} && uv run skill/scripts/generate_meeting_notes.py ~/Desktop/data_professor_meeting_20260311.m4a --meeting data教授會議 --delete-segments
```

腳本結束時會輸出以下幾行，**務必從 stdout 解析並記住 `RESULT_URL`**，後續步驟會用到：

```
RESULT_URL: https://docs.google.com/document/d/<doc_id>/edit
RESULT_DRIVE_PATH: 週一週四_Data_內會/20260316
RESULT_SERIES_NAME: Data內會
RESULT_DATE: 20260316
```

### Step 4.5：解析匿名發言者（若有 [Speaker N] 佔位符）

腳本產出的 Google Doc 中，若 NotebookLM 無法辨識人聲，會留下 `[Speaker 1]`、`[Speaker 2]` 等佔位符。

**Agent 此時應：**

1. 讀取 config 中該會議類型的 `attendees` 與 `custom_prompt`：
   ```bash
   cat ~/.config/generate-meeting-notes/config.json
   ```
2. **請使用者開啟 `RESULT_URL` 的連結，並將 Google Doc 的前 30 行內容貼回對話**（Agent 無法直接開啟 URL）
3. 根據 `custom_prompt` 中的報告順序與 `attendees` 清單，以及使用者貼回的內容，推斷各 Speaker 對應誰
4. **向使用者確認對應關係**，例如：
   > 根據報告順序，我推測：
   > - [Speaker 1] → Fredrick
   > - [Speaker 2] → Frank
   > - [Speaker 3] → Mark
   >
   > 是否正確？有需要調整嗎？
5. 確認後，用腳本批次替換 Google Doc 中的佔位符：
   ```bash
   cd {SKILL_BASE_DIR} && uv run skill/scripts/replace_speakers.py \
     --doc-id <RESULT_URL 中的 doc id> \
     --mapping "Speaker 1=Fredrick" "Speaker 2=Frank" "Speaker 3=Mark"
   ```

> **若 Google Doc 中沒有任何 `[Speaker N]`**，跳過此步驟。

### Step 5：Slack 通知（腳本自動處理）

Slack 通知由 `generate_meeting_notes.py` 在結束時自動呼叫 `send_slack_notification.py` 發送，**不需要 Agent 介入**。

若腳本輸出出現 `⚠️  未設定 slack_channel` 或 `⚠️  Slack 通知失敗`，告知使用者原因：
- 未設定：重新執行 `setup.py` 填入 Slack Channel ID 即可
- 發送失敗：確認 Bot Token 正確，且 Bot 已加入目標 channel

## 自動化流程

```
音訊檔
  ↓ ffmpeg 拆成 10 分鐘片段
~/Downloads/{basename}_output_001.m4a ...
  ↓ notebooklm-py 上傳
NotebookLM（對應的 Notebook）
  ↓ 等待 AI 分析（依音訊長度需 2–10 分鐘）
  ↓ ReportFormat.CUSTOM + prompt.md + custom_prompt（含報告順序）
會議記錄文字內容（可能含「與會者A/B/C...」）
  ↓ 注入 attendees 列表為「與會者」欄位
  ↓ Google Docs API（Markdown 轉格式化文件）
Google Doc：會議記錄_{系列名稱}_{YYYYMMDD}
  ↓ Google Drive API
{Shared Drive}/{系列資料夾}/{YYYYMMDD}/
```

## 輸出結果

- **Google Doc 名稱**：`會議記錄_{series_name}_{YYYYMMDD}`
- **位置**：`{folder_id 對應資料夾}/{YYYYMMDD}/`
- **後續**：開啟連結，人工微調專案名稱、人名等細節

## 音訊檔命名支援

只要檔名含有連續 8 位數字（YYYYMMDD）即可自動提取日期：
- `data_meeting_20260309.m4a` → `20260309`
- `weekly_sync_20260312.mp3` → `20260312`

## 自定義 Prompt

預設 prompt 安裝後會複製到 `~/.config/generate-meeting-notes/prompt.md`，
可直接編輯來調整會議記錄的格式和重點。預設內容見 `references/default-prompt.md`。

## 疑難排解

- **ffmpeg 找不到**：執行 `brew install ffmpeg`（macOS），或 `sudo apt install ffmpeg`（Linux）
- **NotebookLM 認證失敗**：重新執行 `cd {SKILL_BASE_DIR} && uv run notebooklm login`
- **Google Drive 權限不足**：重新執行 `gcloud auth login --enable-gdrive-access`
- **找不到 Notebook**：確認 `config.json` 中 `notebook_name` 與 NotebookLM 完全一致
- **找不到會議類型**：確認 `--meeting` 的值與 `config.json` 中 `meetings` 的 key 完全一致
- **設定重置**：重新執行 `cd {SKILL_BASE_DIR} && uv run skill/scripts/setup.py`
