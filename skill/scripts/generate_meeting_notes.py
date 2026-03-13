#!/usr/bin/env python3
"""
generate_meeting_notes.py - 自動化會議記錄產生流程

流程：
  1. 用 ffmpeg 將音訊拆成 10 分鐘片段 → ~/Downloads/
  2. 上傳所有片段到 NotebookLM 指定 Notebook
  3. 等待 AI 處理完成
  4. 用自定義 prompt 產生結構化會議記錄（ReportFormat.CUSTOM）
  5. 下載報告內容
  6. 建立 Google Doc 並寫入內容
  7. 在 Shared Drive 建立日期子資料夾
  8. 將 Google Doc 移入子資料夾

用法：
    python3 generate_meeting_notes.py <audio_file_path>

範例：
    python3 generate_meeting_notes.py ~/Desktop/data_meeting_20260309.m4a
"""

import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "generate-meeting-notes"
CONFIG_PATH = CONFIG_DIR / "config.json"
SKILL_DIR = Path(__file__).parent.parent
DEFAULT_PROMPT_PATH = SKILL_DIR / "references" / "default-prompt.md"


# ─── 設定 ───────────────────────────────────────────────────────────────────

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        print("❌ 尚未設定。請先執行：")
        print(f"   python3 {Path(__file__).parent}/setup.py")
        sys.exit(1)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def load_prompt(config: dict, meeting: dict) -> str:
    prompt_path = Path(config.get("prompt_path", "")).expanduser()
    if prompt_path.exists():
        base = prompt_path.read_text(encoding="utf-8")
    elif DEFAULT_PROMPT_PATH.exists():
        base = DEFAULT_PROMPT_PATH.read_text(encoding="utf-8")
    else:
        base = "請根據提供的會議音訊，撰寫一份完整的繁體中文會議記錄，包含關鍵要點、討論過程、行動項目。"

    custom = meeting.get("custom_prompt", "").strip()
    if custom:
        return base.rstrip() + "\n\n---\n\n" + custom
    return base


# ─── 音訊處理 ─────────────────────────────────────────────────────────────────

def extract_date(filename: str) -> str:
    """從檔名提取 YYYYMMDD，例如 data_meeting_20260309.m4a → 20260309"""
    match = re.search(r"(\d{8})", filename)
    if not match:
        raise ValueError(
            f"無法從檔名提取日期（需含 YYYYMMDD）：{filename}\n"
            f"範例：data_meeting_20260309.m4a"
        )
    return match.group(1)


def split_audio(audio_path: Path) -> list[Path]:
    """用 ffmpeg 將音訊拆成 10 分鐘片段，輸出到 ~/Downloads/"""
    output_dir = Path.home() / "Downloads"
    basename = audio_path.stem
    ext = audio_path.suffix
    output_pattern = str(output_dir / f"{basename}_output_%03d{ext}")

    print(f"\n🎵 拆分音訊為 10 分鐘片段...")
    result = subprocess.run(
        [
            "ffmpeg", "-i", str(audio_path),
            "-f", "segment",
            "-segment_time", "600",
            "-c", "copy",
            output_pattern,
            "-y",  # 覆蓋已存在的檔案
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"❌ ffmpeg 錯誤：\n{result.stderr[-2000:]}")
        sys.exit(1)

    segments = sorted(output_dir.glob(f"{basename}_output_*{ext}"))
    if not segments:
        print("❌ 沒有產生任何片段，請確認音訊檔格式正確")
        sys.exit(1)

    print(f"✅ 建立 {len(segments)} 個片段 → ~/Downloads/")
    return segments


# ─── NotebookLM ────────────────────────────────────────────────────────────────

async def upload_and_generate(
    notebook_name: str,
    segments: list[Path],
    prompt: str,
) -> str:
    """上傳音訊片段、等待處理、產生報告，回傳報告文字內容"""
    import tempfile
    from notebooklm import NotebookLMClient
    from notebooklm.types import ReportFormat

    async with await NotebookLMClient.from_storage() as client:

        # 找到指定 Notebook
        notebooks = await client.notebooks.list()
        notebook = next(
            (nb for nb in notebooks if nb.title == notebook_name), None
        )
        if not notebook:
            available = [nb.title for nb in notebooks]
            raise ValueError(
                f"找不到 Notebook：'{notebook_name}'\n"
                f"可用的 Notebook：{available}"
            )
        print(f"\n📚 使用 Notebook：{notebook.title} ({notebook.id})")

        # 上傳音訊片段
        print(f"\n⬆️  上傳 {len(segments)} 個音訊片段...")
        source_ids = []
        for seg in segments:
            print(f"   上傳 {seg.name}...")
            source = await client.sources.add_file(notebook.id, str(seg))
            source_ids.append(source.id)
        print(f"✅ 上傳完成")

        # 等待所有 sources 處理完成
        print(f"\n⏳ 等待 NotebookLM 分析音訊（可能需要數分鐘）...")
        for i, source_id in enumerate(source_ids, 1):
            while True:
                source = await client.sources.get(notebook.id, source_id)
                if source is None:
                    await asyncio.sleep(5)
                    continue
                if source.is_ready:
                    print(f"   [{i}/{len(source_ids)}] {source.title or source_id} ✓")
                    break
                elif source.is_error:
                    raise RuntimeError(
                        f"音訊處理失敗：{source.title or source_id}"
                    )
                await asyncio.sleep(5)
        print("✅ 所有音訊分析完成")

        # 產生報告
        print(f"\n📝 產生會議記錄報告...")
        gen_status = await client.artifacts.generate_report(
            notebook_id=notebook.id,
            report_format=ReportFormat.CUSTOM,
            source_ids=source_ids,
            language="zh-TW",
            custom_prompt=prompt,
        )

        # 等待報告完成（最多 10 分鐘）
        final_status = await client.artifacts.wait_for_completion(
            notebook.id, gen_status.task_id, timeout=600
        )
        if final_status.is_failed:
            raise RuntimeError(f"報告產生失敗：{final_status.error}")
        print("✅ 報告產生完成")

        # 下載報告內容（markdown 格式）
        fd, tmp_file = tempfile.mkstemp(suffix=".md")
        import os; os.close(fd)
        tmp_path = Path(tmp_file)
        await client.artifacts.download_report(
            notebook_id=notebook.id,
            output_path=str(tmp_path),
            artifact_id=gen_status.task_id,
        )
        content = tmp_path.read_text(encoding="utf-8")
        tmp_path.unlink(missing_ok=True)
        return content


# ─── Google 認證 ───────────────────────────────────────────────────────────────

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
]


def get_google_credentials():
    """
    依序嘗試三種認證來源：
    1. credentials.json（SA 或 OAuth Client）
    2. gcloud user credentials（gcloud auth login --enable-gdrive-access）
    3. ADC（gcloud auth application-default login）
    """
    creds_path = CONFIG_DIR / "credentials.json"

    # ── 來源 1：credentials.json ──
    if creds_path.exists():
        with open(creds_path, encoding="utf-8") as f:
            creds_data = json.load(f)

        if creds_data.get("type") == "service_account":
            from google.oauth2 import service_account
            return service_account.Credentials.from_service_account_file(
                str(creds_path), scopes=GOOGLE_SCOPES
            )

        if "installed" in creds_data or "web" in creds_data:
            # OAuth Client → InstalledAppFlow，token 存本機
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow

            token_path = CONFIG_DIR / "google_token.json"
            creds = None
            if token_path.exists():
                creds = Credentials.from_authorized_user_file(
                    str(token_path), GOOGLE_SCOPES
                )
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(
                        str(creds_path), GOOGLE_SCOPES
                    )
                    creds = flow.run_local_server(port=0)
                token_path.write_text(creds.to_json())
            return creds

    # ── 來源 2 & 3：google.auth.default()
    # 會依序嘗試：gcloud user credentials → ADC → metadata server
    try:
        import google.auth
        creds, _ = google.auth.default(scopes=GOOGLE_SCOPES)
        return creds
    except Exception as e:
        raise RuntimeError(
            "找不到有效的 Google 認證，請執行以下其中一個指令：\n"
            "  gcloud auth login --enable-gdrive-access\n"
            "  gcloud auth application-default login\n"
            f"原始錯誤：{e}"
        ) from e


# ─── Google Drive ──────────────────────────────────────────────────────────────

def _parse_inline_bold(text: str) -> tuple[str, list[tuple[int, int]]]:
    """解析 **bold** 標記，回傳 (純文字, [(start, end), ...])"""
    plain = ""
    bold_ranges = []
    last_end = 0
    for m in re.finditer(r"\*\*(.+?)\*\*", text):
        plain += text[last_end:m.start()]
        bs = len(plain)
        plain += m.group(1)
        bold_ranges.append((bs, len(plain)))
        last_end = m.end()
    plain += text[last_end:]
    return plain, bold_ranges


def _parse_blocks(content: str) -> list[tuple[str, list[str]]]:
    """將 Markdown 拆成 ('text', lines) 和 ('table', lines) 交替的 block 列表"""
    blocks: list[tuple[str, list[str]]] = []
    text_lines: list[str] = []
    table_lines: list[str] = []

    for line in content.rstrip("\n").split("\n"):
        if re.match(r"^\|", line):
            if text_lines:
                blocks.append(("text", text_lines))
                text_lines = []
            table_lines.append(line)
        else:
            if table_lines:
                blocks.append(("table", table_lines))
                table_lines = []
            text_lines.append(line)

    if table_lines:
        blocks.append(("table", table_lines))
    if text_lines:
        blocks.append(("text", text_lines))
    return blocks


def _parse_table_rows(table_lines: list[str]) -> list[list[str]]:
    """解析 Markdown 表格，跳過分隔列，回傳 rows（每 row 是 cells 列表）"""
    rows = []
    for line in table_lines:
        if re.match(r"^\|\s*[-:]+[-:\s|]*\s*\|", line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if any(cells):
            rows.append(cells)
    return rows


def _classify_line(line: str) -> tuple[str, int, str, list]:
    """解析單行 Markdown，回傳 (kind, level, plain_text, bold_ranges)"""
    m = re.match(r"^(#{1,6})\s+(.*)", line)
    if m:
        plain, bolds = _parse_inline_bold(m.group(2))
        return "heading", len(m.group(1)), plain, bolds

    m = re.match(r"^(\s*)[\*\-]\s+(.*)", line)
    if m:
        plain, bolds = _parse_inline_bold(m.group(2))
        return "bullet", len(m.group(1)), plain, bolds

    if re.match(r"^[-\*_]{3,}\s*$", line):
        return "normal", 0, "", []

    plain, bolds = _parse_inline_bold(line)
    return "normal", 0, plain, bolds


def _markdown_to_gdocs(
    content: str,
) -> tuple[str, list[dict], list[tuple[int, list]]]:
    """將 Markdown 轉為 Google Docs API 請求。
    回傳：
      plain_text  — 不含表格的純文字，insertText 插入 index=1
      fmt_requests — 段落樣式與文字樣式 requests
      tables      — [(doc_insert_index, rows), ...] 按出現順序排列
                    呼叫方需以**反向順序**逐一 insertTable + 填入 cell
    """
    HEADING_STYLES = {
        1: "HEADING_1", 2: "HEADING_2", 3: "HEADING_3",
        4: "HEADING_4", 5: "HEADING_5", 6: "HEADING_6",
    }
    blocks = _parse_blocks(content)
    plain_parts: list[str] = []
    fmt_requests: list[dict] = []
    tables: list[tuple[int, list]] = []
    char_pos = 0  # plain_parts 已累積的字元數

    for block_type, block_lines in blocks:
        if block_type == "table":
            rows = _parse_table_rows(block_lines)
            if rows:
                tables.append((1 + char_pos, rows))
            continue

        for line in block_lines:
            kind, level, plain, bolds = _classify_line(line)
            line_start = 1 + char_pos
            line_end = line_start + len(plain)
            para_range = {"startIndex": line_start, "endIndex": line_end + 1}

            if kind == "heading":
                fmt_requests.append({
                    "updateParagraphStyle": {
                        "range": para_range,
                        "paragraphStyle": {"namedStyleType": HEADING_STYLES[level]},
                        "fields": "namedStyleType",
                    }
                })
                # H1 一律加粗
                if level == 1:
                    fmt_requests.append({
                        "updateTextStyle": {
                            "range": para_range,
                            "textStyle": {"bold": True},
                            "fields": "bold",
                        }
                    })
            elif kind == "bullet":
                fmt_requests.append({
                    "createParagraphBullets": {
                        "range": para_range,
                        "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                    }
                })

            for bs, be in bolds:
                if bs < be:
                    fmt_requests.append({
                        "updateTextStyle": {
                            "range": {
                                "startIndex": line_start + bs,
                                "endIndex": line_start + be,
                            },
                            "textStyle": {"bold": True},
                            "fields": "bold",
                        }
                    })

            plain_parts.append(plain + "\n")
            char_pos += len(plain) + 1

    full_text = "".join(plain_parts)
    return full_text, fmt_requests, tables


def create_gdoc_in_shared_drive(
    date: str,
    content: str,
    meeting: dict,
) -> str:
    """建立 Google Doc，在 Shared Drive 建立日期子資料夾，將文件移入"""
    from googleapiclient.discovery import build

    creds = get_google_credentials()
    docs = build("docs", "v1", credentials=creds)
    drive = build("drive", "v3", credentials=creds)

    series_name = meeting["series_name"]
    series_folder_id = meeting["folder_id"]
    doc_title = f"會議記錄_{series_name}_{date}"

    # 在 Shared Drive 建立日期子資料夾
    print(f"\n📁 建立子資料夾：{date}...")
    subfolder = drive.files().create(
        body={
            "name": date,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [series_folder_id],
        },
        supportsAllDrives=True,
        fields="id",
    ).execute()
    subfolder_id = subfolder["id"]

    # 建立 Google Doc
    print(f"📄 建立 Google Doc：{doc_title}...")
    doc = docs.documents().create(body={"title": doc_title}).execute()
    doc_id = doc["documentId"]

    # 寫入內容（Markdown 轉 Google Docs 格式）
    plain_text, fmt_requests, tables = _markdown_to_gdocs(content)

    # Phase 1：插入所有文字 + 格式
    docs.documents().batchUpdate(
        documentId=doc_id,
        body={
            "requests": [
                {"insertText": {"location": {"index": 1}, "text": plain_text}},
                *fmt_requests,
            ]
        },
    ).execute()

    # Phase 2：插入表格（反向順序，避免前面的 index 被後面的插入影響）
    for table_doc_idx, rows in reversed(tables):
        num_cols = max(len(row) for row in rows)
        num_rows = len(rows)

        # 插入表格結構
        docs.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": [{
                "insertTable": {
                    "rows": num_rows,
                    "columns": num_cols,
                    "location": {"index": table_doc_idx},
                }
            }]},
        ).execute()

        # 讀取文件，取得各 cell 的實際 paragraph startIndex
        doc_body = docs.documents().get(documentId=doc_id).execute()
        cell_indices: dict[tuple[int, int], int] = {}
        for elem in doc_body.get("body", {}).get("content", []):
            if "table" not in elem:
                continue
            if abs(elem.get("startIndex", 0) - table_doc_idx) <= 5:
                for r, trow in enumerate(elem["table"]["tableRows"]):
                    for c, tcell in enumerate(trow["tableCells"]):
                        content = tcell.get("content", [])
                        if content:
                            cell_indices[(r, c)] = content[0]["startIndex"]
                break

        # 填入 cell 內容（以 index 反向順序插入，避免前面的插入影響後面的 index）
        cell_data: list[tuple[int, str]] = []
        for r, row in enumerate(rows):
            for c, cell_text in enumerate(row[:num_cols]):
                plain_cell, _ = _parse_inline_bold(cell_text)
                if plain_cell and (r, c) in cell_indices:
                    cell_data.append((cell_indices[(r, c)], plain_cell))

        cell_data.sort(key=lambda x: x[0], reverse=True)
        cell_requests = [
            {"insertText": {"location": {"index": idx}, "text": text}}
            for idx, text in cell_data
        ]
        if cell_requests:
            docs.documents().batchUpdate(
                documentId=doc_id,
                body={"requests": cell_requests},
            ).execute()

    # 移動到 Shared Drive 子資料夾
    print(f"🚀 移動至 Shared Drive...")
    file_info = drive.files().get(
        fileId=doc_id,
        fields="parents",
        supportsAllDrives=True,
    ).execute()
    prev_parents = ",".join(file_info.get("parents", []))

    drive.files().update(
        fileId=doc_id,
        addParents=subfolder_id,
        removeParents=prev_parents,
        supportsAllDrives=True,
        fields="id",
    ).execute()

    return f"https://docs.google.com/document/d/{doc_id}/edit"


# ─── 後處理 ────────────────────────────────────────────────────────────────────

def preprocess_content(content: str) -> str:
    """清理 NotebookLM 可能回傳的 HTML 標籤。
    - <u>text</u> 獨行 → **text**（事件標題）
    - 其他 HTML 標籤直接移除
    """
    # 獨行的 <u>...</u> → **...**（事件標題格式）
    content = re.sub(r"^<u>(.*?)</u>\s*$", r"**\1**", content, flags=re.MULTILINE)
    # 其餘 HTML 標籤一律去除
    content = re.sub(r"<[^>]+>", "", content)
    return content


def inject_attendees(content: str, attendees: list[str]) -> str:
    """在報告內容中插入與會者列表（位於日期行之後）。"""
    if not attendees:
        return content
    # 若已有與會者行則跳過（避免重複，相容「與會者」與「與會人員」兩種寫法）
    if re.search(r"與會者|與會人員", content):
        return content
    attendees_line = f"- 與會者：{', '.join(attendees)}"
    lines = content.split("\n")
    for i, line in enumerate(lines):
        if re.match(r"^- 日期：", line):
            lines.insert(i + 1, attendees_line)
            return "\n".join(lines)
    # fallback：插入在標題行之後
    for i, line in enumerate(lines):
        if re.match(r"^#\s", line):
            lines.insert(i + 1, attendees_line)
            return "\n".join(lines)
    return attendees_line + "\n" + content


# ─── 清理 ──────────────────────────────────────────────────────────────────────

def cleanup_segments(segments: list[Path], auto_delete: bool = False):
    if auto_delete:
        for seg in segments:
            seg.unlink(missing_ok=True)
        print(f"✅ 已刪除 {len(segments)} 個片段")
        return
    try:
        confirm = input("\n是否刪除 ~/Downloads/ 中的音訊片段？(y/N): ").strip().lower()
    except EOFError:
        confirm = "n"
    if confirm == "y":
        for seg in segments:
            seg.unlink(missing_ok=True)
        print(f"✅ 已刪除 {len(segments)} 個片段")


# ─── 主程式 ────────────────────────────────────────────────────────────────────

async def main(audio_file: str, meeting_key: str, delete_segments: bool = False):
    config = load_config()
    meetings = config.get("meetings", {})

    if meeting_key not in meetings:
        available = ", ".join(meetings.keys())
        print(f"❌ 找不到會議類型：'{meeting_key}'")
        print(f"   可用的會議類型：{available}")
        sys.exit(1)

    meeting = meetings[meeting_key]

    if not meeting.get("folder_id"):
        print(f"❌ 會議類型 '{meeting_key}' 尚未設定 folder_id，請更新 config.json")
        sys.exit(1)

    audio_path = Path(audio_file).expanduser().resolve()
    if not audio_path.exists():
        print(f"❌ 找不到音訊檔：{audio_path}")
        sys.exit(1)

    date = extract_date(audio_path.name)
    print(f"\n📅 會議日期：{date}")
    print(f"🎙️  音訊檔：{audio_path.name}")
    print(f"📋 會議類型：{meeting_key}（{meeting['series_name']}）")

    # 1. 拆分音訊
    segments = split_audio(audio_path)

    # 2. 載入 prompt（含 custom_prompt 合併）
    prompt = load_prompt(config, meeting)

    # 3. 上傳 + 等待 + 產生報告
    content = await upload_and_generate(
        meeting["notebook_name"], segments, prompt
    )

    # 4. 後處理：清理 HTML 標籤 + 注入與會者
    content = preprocess_content(content)
    content = inject_attendees(content, meeting.get("attendees", []))

    # 5. 建立 Google Doc 並移至 Shared Drive
    doc_url = create_gdoc_in_shared_drive(date, content, meeting)

    drive_path = f"{meeting.get('folder_name', meeting['series_name'])}/{date}"

    print(f"\n{'=' * 50}")
    print(f"🎉 完成！")
    print(f"📎 Google Doc：{doc_url}")
    print(f"📂 Drive 路徑：{drive_path}")
    print(f"{'=' * 50}")
    print(f"RESULT_URL: {doc_url}")
    print(f"RESULT_DRIVE_PATH: {drive_path}")
    print(f"RESULT_SERIES_NAME: {meeting['series_name']}")
    print(f"RESULT_DATE: {date}")
    print("\n💡 接下來請人工微調：專案名稱、人名等細節")

    # 6. 發送 Slack 通知
    slack_channel = meeting.get("slack_channel", "").strip()
    if slack_channel:
        print(f"\n📣 發送 Slack 通知到 {slack_channel}...")
        try:
            from send_slack_notification import send_notification
            send_notification(slack_channel, doc_url, drive_path, meeting["series_name"], date)
        except Exception as e:
            print(f"⚠️  Slack 通知失敗（不影響結果）：{e}")
    else:
        print("\n⚠️  未設定 slack_channel，跳過 Slack 通知")
        print("   如需通知，請在 config.json 對應的會議類型中加入 slack_channel")

    cleanup_segments(segments, auto_delete=delete_segments)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="自動化產生會議記錄",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="範例：\n  python3 generate_meeting_notes.py ~/Desktop/data_meeting_20260309.m4a --meeting data內會",
    )
    parser.add_argument("audio_file", help="音訊檔路徑（檔名需含 YYYYMMDD）")
    parser.add_argument("--meeting", "-m", required=True, help="會議類型（對應 config.json 中的 meetings key）")
    parser.add_argument("--delete-segments", action="store_true", help="完成後自動刪除 ~/Downloads/ 中的音訊片段，不詢問確認")
    args = parser.parse_args()

    asyncio.run(main(args.audio_file, args.meeting, delete_segments=args.delete_segments))
