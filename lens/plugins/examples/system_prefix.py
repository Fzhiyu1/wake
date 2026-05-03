"""system_prefix - 示例插件:往 system 块前面塞一段固定文本。

演示了"如何安全地修改 system 字段"——它可能是 str、list[block]、或 None,三种都要处理。

用法:
    export LENS_SYSTEM_PREFIX="始终用中文回答。"
    export LENS_PLUGINS=examples.system_prefix
    python lens.py
"""

import logging
import os

log = logging.getLogger("lens.system_prefix")

PREFIX = os.environ.get("LENS_SYSTEM_PREFIX", "")


class Plugin:
    async def on_messages_request(self, body: dict) -> dict:
        if not PREFIX:
            return body

        block = f"{PREFIX}\n\n"
        system = body.get("system")

        if system is None:
            body["system"] = PREFIX
        elif isinstance(system, str):
            body["system"] = block + system
        elif isinstance(system, list):
            system.insert(0, {"type": "text", "text": block})

        log.info(f"system_prefix: prepended {len(PREFIX)} chars")
        return body
