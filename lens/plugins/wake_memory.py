"""wake_memory - lens 可选插件:每次请求调 wake daemon 注入相关记忆,顺便剥旧注入避免累积。

仅在显式设置 `LENS_PLUGINS=wake_memory` 时加载。
"""

import logging
import os
import re
import subprocess
from pathlib import Path

log = logging.getLogger("lens.wake_memory")

# 同 repo:wake 根目录就是 lens/plugins/ 的祖父目录
WAKE_DIR = Path(__file__).resolve().parents[2]
WAKE_PYTHON = WAKE_DIR / ".venv" / "bin" / "python3"
WAKE_DAEMON = WAKE_DIR / "daemon.py"
WAKE_TIMEOUT = int(os.environ.get("WAKE_TIMEOUT", "15"))

# 兼容旧版 Claude Code UserPromptSubmit hook 的注入(可能还残留在历史 messages 里)
HOOK_PATTERN = re.compile(
    r"<system-reminder>\s*UserPromptSubmit hook success: \[记忆\][\s\S]*?</system-reminder>"
)

# 自己上一轮在 system 里塞的 [当前相关记忆] 块
SYSTEM_INJECTION_PATTERN = re.compile(
    r"\n*\[当前相关记忆\][\s\S]*?\[/当前相关记忆\]\n*"
)


def strip_hook_injection(text: str) -> str:
    if not text:
        return text
    return HOOK_PATTERN.sub("", text).strip()


def strip_system_injection(text: str) -> str:
    if not text:
        return text
    return SYSTEM_INJECTION_PATTERN.sub("", text)


def call_wake(query: str) -> str:
    """调 wake daemon 拿当前 query 的相关记忆。"""
    if not WAKE_DAEMON.exists():
        log.warning(f"wake daemon not found at {WAKE_DAEMON}, skipping recall")
        return ""
    if not WAKE_PYTHON.exists():
        log.warning(f"wake python not found at {WAKE_PYTHON}, skipping recall")
        return ""

    try:
        result = subprocess.run(
            [str(WAKE_PYTHON), str(WAKE_DAEMON), query],
            capture_output=True,
            text=True,
            timeout=WAKE_TIMEOUT,
            cwd=str(WAKE_DIR),
        )
        # 把 daemon 的 stderr (含 finish_reason / token usage) 转发到自己的 log
        if result.stderr:
            for line in result.stderr.strip().splitlines():
                log.info(line)
        memory = result.stdout.strip()
        if memory and memory != "无相关记忆。":
            return memory
    except subprocess.TimeoutExpired:
        log.warning(f"wake daemon timed out after {WAKE_TIMEOUT}s")
    except Exception as e:
        log.error(f"wake call failed: {e}")
    return ""


def extract_user_query(messages: list) -> str:
    """抓最新一条用户消息文本(剥掉残留 hook 注入)。"""
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            cleaned = strip_hook_injection(content)
            if cleaned:
                return cleaned[:500]
        elif isinstance(content, list):
            for block in content:
                if block.get("type") == "text":
                    cleaned = strip_hook_injection(block.get("text", ""))
                    if cleaned:
                        return cleaned[:500]
    return ""


class Plugin:
    async def on_messages_request(self, body: dict) -> dict:
        messages = body.get("messages", [])
        if not messages:
            return body

        # Step 1: 剥掉 messages 里所有累加的旧 hook 注入
        # 注意:如果一条消息内容完全就是 hook 注入,剥完会变空,
        # Anthropic API 拒收空 text block,所以 strip 后为空就保留原样。
        stripped_count = 0
        for msg in messages:
            content = msg.get("content")
            if isinstance(content, str):
                new_content = strip_hook_injection(content)
                if new_content != content and new_content.strip():
                    msg["content"] = new_content
                    stripped_count += 1
            elif isinstance(content, list):
                for block in content:
                    if block.get("type") == "text":
                        text = block.get("text", "")
                        new_text = strip_hook_injection(text)
                        if new_text != text and new_text.strip():
                            block["text"] = new_text
                            stripped_count += 1

        # Step 2: 抓当前用户 query
        query = extract_user_query(messages)
        if not query:
            return body

        # Step 3: 调 wake 拿新鲜记忆
        memory = call_wake(query)
        if not memory:
            log.info(f"stripped {stripped_count} old hook injections, no new recall")
            return body

        # Step 4: 剥掉 system 里上一轮自己注入的旧记忆
        system = body.get("system")
        sys_stripped_chars = 0
        if isinstance(system, str):
            new_system = strip_system_injection(system)
            sys_stripped_chars = len(system) - len(new_system)
            system = new_system
            body["system"] = system
        elif isinstance(system, list):
            for block in system:
                if block.get("type") == "text":
                    text = block.get("text", "")
                    new_text = strip_system_injection(text)
                    if new_text != text:
                        sys_stripped_chars += len(text) - len(new_text)
                        block["text"] = new_text
            system[:] = [b for b in system if not (b.get("type") == "text" and not b.get("text", "").strip())]

        # Step 5: 注入新记忆到 system 块
        memory_block = f"\n\n[当前相关记忆]\n{memory}\n[/当前相关记忆]"

        if isinstance(system, str):
            body["system"] = system + memory_block
        elif isinstance(system, list):
            system.append({"type": "text", "text": memory_block})
        else:
            body["system"] = memory_block.strip()

        log.info(
            f"stripped {stripped_count} msg-hook + {sys_stripped_chars} sys-chars, "
            f"injected {len(memory)} chars new"
        )
        return body
