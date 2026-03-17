#!/bin/bash
# audio-to-meeting-notes - 安裝腳本
#
# 使用方式（macOS / Linux）：
#   bash install.sh
#
# 唯一的前置條件：macOS 或 Linux（bash 是內建的）

set -e  # 任何指令失敗就停止

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_INSTALL_DIR="$HOME/.claude/skills/generate-meeting-notes"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║    generate-meeting-notes - 安裝中...            ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ── 步驟 1：安裝 uv ────────────────────────────────────────────────────────────

if command -v uv &> /dev/null; then
    echo "  ✅ uv 已安裝（$(uv --version)）"
else
    echo "  ⬇️  正在安裝 uv（Python 套件管理器）..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # 讓當前 shell 能找到 uv
    export PATH="$HOME/.local/bin:$PATH"
    source "$HOME/.local/bin/env" 2>/dev/null || true

    if ! command -v uv &> /dev/null; then
        echo "  ❌ uv 安裝後仍找不到，請重新開啟終端後再執行 bash install.sh"
        exit 1
    fi
    echo "  ✅ uv 安裝成功"
fi

# ── 步驟 2：安裝 Claude skill ──────────────────────────────────────────────────

echo ""
echo "  ▶ 安裝 skill 到 ~/.claude/skills/generate-meeting-notes/ ..."
echo "  ⚠️  注意：安裝完成後請勿移動此目錄（$REPO_DIR）"
echo "       若移動後 skill 失效，請重新執行 bash install.sh"

mkdir -p "$SKILL_INSTALL_DIR"
cp -r "$REPO_DIR/skill/." "$SKILL_INSTALL_DIR/"

# 將 SKILL.md 中的 {SKILL_BASE_DIR} 替換為 repo 的實際路徑
sed -i.bak "s|{SKILL_BASE_DIR}|$REPO_DIR|g" "$SKILL_INSTALL_DIR/SKILL.md"
rm -f "$SKILL_INSTALL_DIR/SKILL.md.bak"

echo "  ✅ skill 已安裝至 $SKILL_INSTALL_DIR"

# ── 步驟 3：執行完整設定精靈 ───────────────────────────────────────────────────

echo ""
echo "  ▶ 啟動設定精靈..."
echo ""

cd "$REPO_DIR"
uv run skill/scripts/setup.py
