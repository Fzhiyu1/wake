"""echo - 最小示例插件:把每次请求的 messages 数量打印到 lens 日志,不修改 body。

启用方式:
    export LENS_PLUGINS=examples.echo
    python lens.py

适合用作"看看插件 SDK 长什么样"的 hello-world。
"""

import logging

log = logging.getLogger("lens.echo")


class Plugin:
    async def on_messages_request(self, body: dict) -> dict:
        messages = body.get("messages", [])
        model = body.get("model", "?")
        log.info(f"echo: {len(messages)} messages, model={model}")
        return body
