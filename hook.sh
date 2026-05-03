#!/bin/bash
# Wake hook - 用户发消息时自动触发记忆回想
# Claude Code UserPromptSubmit hook 通过 stdin 传入 JSON

WAKE_DIR="$(dirname "$(realpath "$0")")"

# 从 stdin 读取 JSON，提取用户 prompt
INPUT=$(cat)
QUERY=$(echo "$INPUT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('prompt',''))" 2>/dev/null)

if [ -z "$QUERY" ]; then
    exit 0
fi

# 调用记忆层
MEMORY=$(cd "$WAKE_DIR" && .venv/bin/python3 daemon.py "$QUERY" 2>/dev/null)

if [ -n "$MEMORY" ] && [ "$MEMORY" != "无相关记忆。" ]; then
    echo "[记忆] $MEMORY"
fi
