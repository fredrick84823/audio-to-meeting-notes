#!/usr/bin/env python3
"""
setup.py - Generate Meeting Notes 一鍵設定

只需要系統內建的 Python 3（macOS 預設有），其他工具全部自動安裝。

執行方式：
    python3 scripts/setup.py
"""

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

# ─── 路徑設定 ──────────────────────────────────────────────────────────────────

SKILL_DIR = Path(__file__).parent.parent
CONFIG_DIR = Path.home() / ".config" / "generate-meeting-notes"
CONFIG_PATH = CONFIG_DIR / "config.json"
NOTEBOOKLM_STORAGE = Path.home() / ".notebooklm" / "storage_state.json"
GOOGLE_ADC = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
GOOGLE_SCOPES = ",".join([
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/cloud-platform",
])

IS_MAC = platform.system() == "Darwin"
IS_WIN = platform.system() == "Windows"

# ─── 輸出工具 ──────────────────────────────────────────────────────────────────

def header(title: str):
    print(f"\n{'─' * 52}")
    print(f"  {title}")
    print(f"{'─' * 52}")

def ok(msg: str):    print(f"  ✅ {msg}")
def warn(msg: str):  print(f"  ⚠️  {msg}")
def err(msg: str):   print(f"  ❌ {msg}")
def tip(msg: str):   print(f"  💡 {msg}")
def info(msg: str):  print(f"     {msg}")

def step(n: int, total: int, title: str):
    print(f"\n[{n}/{total}] {title}")

def run(cmd, **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kwargs)

def run_in_skill(cmd: list, **kwargs) -> subprocess.CompletedProcess:
    """在 skill 目錄下用 uv run 執行"""
    return run(["uv", "run"] + cmd, cwd=SKILL_DIR, **kwargs)

def abort(msg: str):
    err(msg)
    print("\n設定中斷。解決問題後重新執行 setup.py。")
    sys.exit(1)

# ─── Step 1：uv ────────────────────────────────────────────────────────────────

def check_install_uv():
    if shutil.which("uv"):
        result = run(["uv", "--version"], capture_output=True, text=True)
        ok(f"uv 已安裝（{result.stdout.strip()}）")
        return

    warn("uv 未安裝，正在安裝...")
    if IS_MAC:
        if shutil.which("brew"):
            result = run(["brew", "install", "uv"])
            if result.returncode == 0:
                ok("uv 安裝成功（透過 Homebrew）")
                return
        # fallback：官方 install script
        result = run("curl -LsSf https://astral.sh/uv/install.sh | sh", shell=True)
        if result.returncode == 0:
            uv_path = Path.home() / ".local" / "bin"
            os.environ["PATH"] = f"{uv_path}:{os.environ['PATH']}"
            ok("uv 安裝成功")
            return
    elif IS_WIN:
        result = run(
            'powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"',
            shell=True
        )
        if result.returncode == 0:
            ok("uv 安裝成功")
            return

    abort(
        "無法自動安裝 uv\n"
        "  請手動安裝：https://docs.astral.sh/uv/getting-started/installation/"
    )

# ─── Step 2：ffmpeg ────────────────────────────────────────────────────────────

def check_install_ffmpeg():
    if shutil.which("ffmpeg"):
        result = run(["ffmpeg", "-version"], capture_output=True, text=True)
        version = result.stdout.split("\n")[0] if result.stdout else "unknown"
        ok(f"ffmpeg 已安裝")
        return

    warn("ffmpeg 未安裝，正在安裝...")
    if IS_MAC and shutil.which("brew"):
        result = run(["brew", "install", "ffmpeg"])
        if result.returncode == 0:
            ok("ffmpeg 安裝成功（透過 Homebrew）")
            return
        abort("Homebrew 安裝 ffmpeg 失敗，請手動執行：brew install ffmpeg")

    # 無法自動安裝時引導使用者
    err("無法自動安裝 ffmpeg")
    if IS_MAC:
        tip("請安裝 Homebrew 後執行：brew install ffmpeg")
        tip("Homebrew 安裝：https://brew.sh")
    elif IS_WIN:
        tip("請下載 ffmpeg：https://ffmpeg.org/download.html#build-windows")
        tip("解壓後將 ffmpeg.exe 加入系統 PATH")
    else:
        tip("請用套件管理器安裝：sudo apt install ffmpeg")

    input("\n安裝完成後按 Enter 繼續...")
    if not shutil.which("ffmpeg"):
        abort("仍找不到 ffmpeg，請確認安裝完成並重試")
    ok("ffmpeg 已就緒")

# ─── Step 3：gcloud CLI ────────────────────────────────────────────────────────

def check_install_gcloud():
    if shutil.which("gcloud"):
        result = run(["gcloud", "--version"], capture_output=True, text=True)
        version_line = result.stdout.split("\n")[0] if result.stdout else ""
        ok(f"gcloud 已安裝（{version_line}）")
        return

    warn("gcloud CLI 未安裝（需要用來存取 Google Drive）")
    if IS_MAC and shutil.which("brew"):
        tip("正在透過 Homebrew 安裝（約 300MB，需要幾分鐘）...")
        result = run(["brew", "install", "--cask", "google-cloud-sdk"])
        if result.returncode == 0:
            # brew cask 安裝後需要重新載入 PATH
            sdk_path = Path("/usr/local/Caskroom/google-cloud-sdk/latest/google-cloud-sdk/bin")
            if sdk_path.exists():
                os.environ["PATH"] = f"{sdk_path}:{os.environ['PATH']}"
            if shutil.which("gcloud"):
                ok("gcloud 安裝成功")
                return

    err("請手動安裝 gcloud CLI：")
    if IS_MAC:
        info("方式一（推薦）：brew install --cask google-cloud-sdk")
        info("方式二：https://cloud.google.com/sdk/docs/install")
    else:
        info("下載安裝：https://cloud.google.com/sdk/docs/install")

    input("\n安裝完成後按 Enter 繼續...")
    if not shutil.which("gcloud"):
        abort("仍找不到 gcloud，請確認安裝完成並重試")
    ok("gcloud 已就緒")

# ─── Step 4：Python 套件 ────────────────────────────────────────────────────────

def setup_python_deps():
    info("安裝 Python 套件（首次約需 1 分鐘）...")
    result = run(["uv", "sync"], cwd=SKILL_DIR, capture_output=True, text=True)
    if result.returncode != 0:
        abort(f"套件安裝失敗：\n{result.stderr[-500:]}")
    ok("Python 套件安裝完成")

    info("安裝 Playwright Chromium（約 170MB）...")
    result = run(
        ["uv", "run", "playwright", "install", "chromium"],
        cwd=SKILL_DIR,
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        abort(f"Playwright 安裝失敗：\n{result.stderr[-300:]}")
    ok("Playwright Chromium 安裝完成")

# ─── Step 5：NotebookLM 登入 ───────────────────────────────────────────────────

def check_notebooklm_auth() -> bool:
    if not NOTEBOOKLM_STORAGE.exists():
        return False
    # 快速驗證 session 是否有效
    result = run_in_skill(
        ["python", "-c",
         "import asyncio; from notebooklm import NotebookLMClient; "
         "asyncio.run(NotebookLMClient.from_storage().__aenter__()); print('OK')"],
        capture_output=True, text=True, timeout=15
    )
    return "OK" in result.stdout

def setup_notebooklm_auth():
    if check_notebooklm_auth():
        ok("NotebookLM 已登入")
        return

    warn("需要登入 NotebookLM")
    info("即將開啟瀏覽器，請用你的 Google 帳號登入")
    input("  按 Enter 開始...")
    result = run(["uv", "run", "notebooklm", "login"], cwd=SKILL_DIR)
    if result.returncode != 0:
        abort("NotebookLM 登入失敗，請稍後重試")
    ok("NotebookLM 登入成功")

# ─── Step 6：Google Drive 認證 ─────────────────────────────────────────────────

def check_google_auth() -> bool:
    """實際呼叫 Drive API 確認認證有效且有 Drive scope"""
    result = run_in_skill(
        ["python", "-c",
         "import google.auth; "
         "from googleapiclient.discovery import build; "
         "creds, _ = google.auth.default(scopes=['https://www.googleapis.com/auth/drive']); "
         "svc = build('drive', 'v3', credentials=creds); "
         "svc.files().list(pageSize=1, supportsAllDrives=True).execute(); "
         "print('OK')"],
        capture_output=True, text=True, timeout=30
    )
    return "OK" in result.stdout


def setup_google_auth():
    if check_google_auth():
        ok("Google Drive 認證有效")
        return

    warn("需要 Google Drive 認證")
    info("即將開啟瀏覽器，請用你的公司 Google 帳號登入")
    info("（使用 gcloud 官方 OAuth，不會出現『app blocked』錯誤）")
    input("  按 Enter 開始...")

    result = run([
        "gcloud", "auth", "login",
        "--enable-gdrive-access",
        "--update-adc",  # 同時更新 ADC，讓 google.auth.default() 能找到
    ])
    if result.returncode != 0:
        abort("Google 認證失敗，請稍後重試")

    if not check_google_auth():
        abort(
            "認證完成，但 Drive API 測試失敗\n"
            "  請確認你的帳號有 Google Drive 存取權限"
        )
    ok("Google Drive 認證完成")

# ─── Step 7：使用者設定 ────────────────────────────────────────────────────────

def ask(prompt_text: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    value = input(f"  {prompt_text}{hint}: ").strip()
    return value if value else default


def setup_config():
    existing_meetings = {}
    existing_slack_token = ""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, encoding="utf-8") as f:
            existing = json.load(f)
        existing_meetings = existing.get("meetings", {})
        existing_slack_token = existing.get("slack_bot_token", "")
        info("找到現有設定（現有會議類型將保留，可新增或略過）")

    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    # Slack Bot Token（全域設定）
    print()
    print("  【設定 Slack Bot Token】")
    print("  至 api.slack.com → 你的 App → OAuth & Permissions → Bot User OAuth Token")
    print("  格式：xoxb-xxxxxxxxxx-xxxxxxxxxx-xxxxxxxxxxxxxxxx")
    slack_bot_token = ask(
        "Slack Bot Token（空白跳過 Slack 通知功能）",
        existing_slack_token,
    )

    # 預設 prompt
    user_prompt = CONFIG_DIR / "prompt.md"
    if not user_prompt.exists():
        shutil.copy(SKILL_DIR / "references" / "default-prompt.md", user_prompt)
        info(f"已複製預設 prompt → {user_prompt}（可自行編輯）")

    meetings = dict(existing_meetings)

    print()
    print("  【設定會議類型】")
    print("  每個會議類型對應一個 Notebook 與一個 Shared Drive 資料夾。")
    print("  可設定多個（例如：data內會、pm會議）。輸入空白結束。")
    print()

    while True:
        print(f"  目前已有會議類型：{list(meetings.keys()) or '（無）'}")
        key = input("  新增/更新會議類型（例：data內會），空白則完成：").strip()
        if not key:
            break

        existing_m = meetings.get(key, {})
        print(f"  ── 設定「{key}」──")

        notebook = ask(
            "NotebookLM Notebook 名稱（例：DataTeam 會議記錄）",
            existing_m.get("notebook_name", ""),
        )
        tip(f"請確認已在 notebooklm.google.com 手動建立名為「{notebook}」的 Notebook")
        tip("若 Notebook 不存在，執行腳本時會報錯：找不到 Notebook")
        print("  請從瀏覽器開啟 Shared Drive 資料夾，複製網址中的 Folder ID")
        print("  https://drive.google.com/drive/folders/【這段就是 Folder ID】")
        folder_id = ask(
            "Shared Drive Folder ID",
            existing_m.get("folder_id", ""),
        )
        folder_name = ask(
            "資料夾顯示名稱（用於 Slack 通知，例：週一週四_Data_內會）",
            existing_m.get("folder_name", key),
        )
        series_name = ask(
            "會議系列簡稱（用於文件命名，例：Data內會）",
            existing_m.get("series_name", key),
        )
        print("  請在 Slack 中右鍵點擊 channel → View channel details → 複製 Channel ID")
        slack_channel = ask(
            "Slack Channel ID（例：C0XXXXXXXXX，空白跳過）",
            existing_m.get("slack_channel", ""),
        )

        meetings[key] = {
            "notebook_name": notebook,
            "folder_id": folder_id,
            "folder_name": folder_name,
            "series_name": series_name,
            "slack_channel": slack_channel,
            "attendees": existing_m.get("attendees", []),
            "custom_prompt": existing_m.get("custom_prompt", ""),
        }
        ok(f"「{key}」已設定")
        print()

    if not meetings:
        warn("未設定任何會議類型，稍後請手動編輯 config.json")

    config = {
        "slack_bot_token": slack_bot_token,
        "meetings": meetings,
        "prompt_path": str(user_prompt),
    }
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    ok(f"設定已儲存 → {CONFIG_PATH}")
    tip("與會者（attendees）與補充說明（custom_prompt）請直接編輯 config.json")

# ─── 最終驗證 ──────────────────────────────────────────────────────────────────

def final_verify():
    result = run_in_skill(
        ["python", "-c",
         "from notebooklm import NotebookLMClient; "
         "from googleapiclient.discovery import build; "
         "import json, pathlib; "
         "cfg = json.loads(pathlib.Path('~/.config/generate-meeting-notes/config.json').expanduser().read_text()); "
         "keys = list(cfg.get('meetings', {}).keys()); "
         "print('OK:', ', '.join(keys) if keys else '（無會議類型）')"],
        capture_output=True, text=True, timeout=15
    )
    if "OK:" in result.stdout:
        meetings_info = result.stdout.split("OK:")[-1].strip()
        ok(f"驗證通過（會議類型：{meetings_info}）")
    else:
        warn("驗證出現問題，但可能不影響使用")
        if result.stderr:
            info(result.stderr[:200])

# ─── 主程式 ────────────────────────────────────────────────────────────────────

def main():
    TOTAL = 7

    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║      Generate Meeting Notes - 一鍵設定           ║")
    print("╚══════════════════════════════════════════════════╝")

    step(1, TOTAL, "檢查 uv（Python 套件管理器）")
    check_install_uv()  # 透過 install.sh 通常已存在；直接執行 setup.py 時的保險

    step(2, TOTAL, "檢查 ffmpeg（音訊處理）")
    check_install_ffmpeg()

    step(3, TOTAL, "檢查 gcloud（Google 雲端工具）")
    check_install_gcloud()

    step(4, TOTAL, "安裝 Python 套件")
    setup_python_deps()

    step(5, TOTAL, "登入 NotebookLM")
    setup_notebooklm_auth()

    step(6, TOTAL, "設定 Google Drive 認證")
    setup_google_auth()

    step(7, TOTAL, "填寫個人設定")
    setup_config()

    header("驗證")
    final_verify()

    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║  🎉 設定完成！                                    ║")
    print("╠══════════════════════════════════════════════════╣")
    print("║  執行範例：                                       ║")
    print(f"║  1. cd {str(SKILL_DIR)[:38]:<38} ║")
    print("║  2. uv run scripts/generate_meeting_notes.py \\   ║")
    print("║        ~/Desktop/meeting_YYYYMMDD.m4a \\          ║")
    print("║        --meeting data內會                        ║")
    print("╚══════════════════════════════════════════════════╝")
    print()


if __name__ == "__main__":
    main()
