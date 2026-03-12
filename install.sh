#!/bin/bash
# Generate Meeting Notes - 安裝腳本
#
# 使用方式（macOS / Linux）：
#   bash install.sh
#
# 唯一的前置條件：macOS 或 Linux（bash 是內建的）

set -e  # 任何指令失敗就停止

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║      Generate Meeting Notes - 安裝中...          ║"
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

# ── 步驟 2：執行完整設定精靈 ───────────────────────────────────────────────────

echo ""
echo "  ▶ 啟動設定精靈..."
echo ""

cd "$SKILL_DIR"
uv run scripts/setup.py
