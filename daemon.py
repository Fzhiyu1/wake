#!/usr/bin/env python3
"""Wake - 记忆层守护进程"""

import datetime
import json
import os
import sys
from pathlib import Path
from openai import OpenAI

WAKE_DIR = Path(__file__).parent
KB_SNAPSHOT = WAKE_DIR / "kb-snapshot.txt"
SYSTEM_PROMPT = WAKE_DIR / "system-prompt.md"

def load_env():
    env_path = WAKE_DIR / ".env"
    if env_path.exists():
        for line in env_path.read_text().strip().split("\n"):
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

def create_client():
    load_env()
    return OpenAI(
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url="https://api.deepseek.com"
    )

def load_context():
    kb = KB_SNAPSHOT.read_text(encoding="utf-8")
    prompt = SYSTEM_PROMPT.read_text(encoding="utf-8")
    return prompt + "\n\n---\n\n以下是完整知识库：\n\n" + kb

def recall(query: str) -> str:
    client = create_client()
    context = load_context()

    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": context},
            {"role": "user", "content": query}
        ],
        max_tokens=500,
        temperature=0.7  # 联想需要松散采样,不是检索
    )

    # 把 finish_reason / token 用量写到 stderr,不污染 stdout(供 lens 转发到 log)
    finish = response.choices[0].finish_reason
    usage = response.usage
    recall_text = response.choices[0].message.content.strip()

    sys.stderr.write(
        f"[wake] finish={finish} "
        f"prompt_tokens={usage.prompt_tokens} "
        f"completion_tokens={usage.completion_tokens}\n"
    )

    # 结构化日志:每次召回追加一条 JSONL,方便事后 grep / 统计
    log_path = WAKE_DIR / "data" / "recall.jsonl"
    log_path.parent.mkdir(exist_ok=True)
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": datetime.datetime.now().isoformat(),
            "query": query,
            "recall": recall_text,
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "finish": finish,
        }, ensure_ascii=False) + "\n")

    return recall_text

def main():
    if len(sys.argv) < 2:
        print("用法: python daemon.py <query>")
        print("示例: python daemon.py '我最近觉得自己越来越平庸了'")
        sys.exit(1)

    query = " ".join(sys.argv[1:])
    result = recall(query)
    print(result)

if __name__ == "__main__":
    main()
