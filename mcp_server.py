#!/usr/bin/env python3
"""Wake MCP Server - 记忆层 MCP 工具"""

import json
import os
import sys
from daemon import recall

# 知识库归属人,影响 memory_recall 工具的描述。模型据此判断何时调用。
# 设环境变量 WAKE_OWNER (例如 "fangzhiyu") 让描述更具体,默认通用描述。
KB_OWNER = os.environ.get("WAKE_OWNER", "").strip()

if KB_OWNER:
    RECALL_DESC = (
        f"从 {KB_OWNER} 的个人知识库中回忆与当前话题相关的记忆。"
        "当对话涉及个人经历、过去讨论过的概念、人物关系、或项目历史时调用。"
    )
else:
    RECALL_DESC = (
        "从用户的个人知识库中回忆与当前话题相关的记忆。"
        "当对话涉及用户的过往经历、已讨论过的概念、相关人物、或正在进行的项目时调用。"
    )


def handle_request(request):
    method = request.get("method")

    if method == "initialize":
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "wake", "version": "0.1.0"}
        }

    elif method == "tools/list":
        return {
            "tools": [{
                "name": "memory_recall",
                "description": RECALL_DESC,
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "当前对话的主题或需要回忆的内容"
                        }
                    },
                    "required": ["query"]
                }
            }]
        }

    elif method == "tools/call":
        tool_name = request["params"]["name"]
        if tool_name == "memory_recall":
            query = request["params"]["arguments"]["query"]
            result = recall(query)
            return {
                "content": [{"type": "text", "text": result}]
            }

    elif method == "notifications/initialized":
        return None

    return {"error": {"code": -32601, "message": f"Unknown method: {method}"}}

def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        request = json.loads(line)
        request_id = request.get("id")

        response = handle_request(request)

        if response is not None:
            output = {"jsonrpc": "2.0", "id": request_id, "result": response}
            sys.stdout.write(json.dumps(output) + "\n")
            sys.stdout.flush()

if __name__ == "__main__":
    main()
