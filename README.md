# audio-to-meeting-notes

> Claude Code skill：將會議錄音透過 NotebookLM 自動轉換為 Google Doc 格式的結構化會議記錄。

## 功能

1. 用 `ffmpeg` 將音訊拆成 10 分鐘片段
2. 上傳至 [NotebookLM](https://notebooklm.google.com)，等待 AI 分析
3. 用自定義 prompt 產生結構化會議記錄（繁體中文）
4. 建立 Google Doc，移至 Shared Drive 指定資料夾
5. 透過 Slack 發送通知

## 前置條件

- macOS 或 Linux
- Google 帳號（有 Shared Drive 存取權限）
- [NotebookLM](https://notebooklm.google.com) 帳號，且已手動建立對應的 Notebook

## 安裝

```bash
git clone https://github.com/fredrick84823/audio-to-meeting-notes.git
cd audio-to-meeting-notes
bash install.sh
```

`install.sh` 會自動：
1. 安裝 `uv`（Python 套件管理器）
2. 複製 skill 到 `~/.claude/skills/audio-to-meeting-notes/`（Claude Code 自動載入）
3. 啟動互動式設定精靈（`setup.py`），引導完成：
- NotebookLM 登入
- Google Drive 認證
- 會議類型設定（Notebook 名稱、Shared Drive Folder ID 等）

設定完成後，config 儲存於 `~/.config/generate-meeting-notes/config.json`。

## 使用方式

```bash
uv run skill/scripts/generate_meeting_notes.py <音訊檔> --meeting <會議類型>
```

**範例：**

```bash
uv run skill/scripts/generate_meeting_notes.py ~/Desktop/data_meeting_20260309.m4a --meeting data內會
```

音訊檔名需包含 `YYYYMMDD` 日期（例：`meeting_20260309.m4a`）。

## 設定結構

`~/.config/generate-meeting-notes/config.json`：

```json
{
  "meetings": {
    "data內會": {
      "notebook_name": "DataTeam 會議記錄",
      "folder_id": "1abc...（Shared Drive Folder ID）",
      "folder_name": "週一週四_Data_內會",
      "series_name": "Data內會",
      "slack_channel": "C03RDL9RZL4",
      "attendees": ["Alice", "Bob", "Carol"],
      "custom_prompt": "報告順序：Alice → Bob → Carol"
    }
  },
  "prompt_path": "~/.config/generate-meeting-notes/prompt.md"
}
```

| 欄位 | 說明 |
|------|------|
| `notebook_name` | NotebookLM Notebook 名稱（須事先手動建立） |
| `folder_id` | Shared Drive 資料夾 ID（從 URL 取得） |
| `folder_name` | Slack 通知顯示的雲端路徑名稱 |
| `series_name` | 文件命名用的會議系列簡稱 |
| `slack_channel` | Slack channel ID（留空則由 agent 詢問） |
| `attendees` | 與會者清單，自動注入 Google Doc |
| `custom_prompt` | 附加給 NotebookLM 的補充說明（例如報告順序） |

## 流程

```
音訊檔
  ↓ ffmpeg — 拆成 10 分鐘片段
~/Downloads/{basename}_output_001.m4a ...
  ↓ NotebookLM — 上傳 + AI 分析
  ↓ CUSTOM prompt（prompt.md + custom_prompt）
會議記錄文字
  ↓ HTML 標籤清理 + 注入與會者
  ↓ Google Docs API — Markdown 轉格式化文件
Google Doc：會議記錄_{series_name}_{YYYYMMDD}
  ↓ Google Drive API
{Shared Drive}/{series_folder}/{YYYYMMDD}/
```

## 腳本說明

| 腳本 | 說明 |
|------|------|
| `skill/scripts/generate_meeting_notes.py` | 主流程腳本 |
| `skill/scripts/replace_speakers.py` | 批次替換 Google Doc 中的 `[Speaker N]` 佔位符 |
| `skill/scripts/setup.py` | 互動式設定精靈 |

### replace_speakers.py

當 NotebookLM 無法辨識發言者時，Google Doc 會留下 `[Speaker 1]`、`[Speaker 2]` 等佔位符，可用此腳本批次替換：

```bash
uv run skill/scripts/replace_speakers.py \
  --doc-id https://docs.google.com/document/d/DOC_ID/edit \
  --mapping "Speaker 1=Alice" "Speaker 2=Bob"
```

## 自定義 Prompt

預設 prompt 安裝時複製至 `~/.config/generate-meeting-notes/prompt.md`，可直接編輯。
原始範本見 [`skill/references/default-prompt.md`](skill/references/default-prompt.md)。

## 依賴套件

NotebookLM 自動化透過 [notebooklm-py](https://github.com/teng-lin/notebooklm-py?tab=readme-ov-file#complete-notebooklm-coverage) 實現，支援完整的 NotebookLM API 操作。

## 疑難排解

| 問題 | 解法 |
|------|------|
| NotebookLM 認證失敗 | `uv run notebooklm login` |
| Google Drive 權限不足 | `gcloud auth login --enable-gdrive-access` |
| 找不到 Notebook | 確認已在 notebooklm.google.com 手動建立，名稱完全一致 |
| 找不到會議類型 | 確認 `--meeting` 的值與 config.json 中的 key 一致 |
