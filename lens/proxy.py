#!/usr/bin/env python3
"""lens - Anthropic API 代理。光透过它折射变形。"""

import importlib
import json
import logging
import os
import sys
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, Response
import httpx
import uvicorn

UPSTREAM = os.environ.get("LENS_UPSTREAM", "https://api.anthropic.com")
PORT = int(os.environ.get("LENS_PORT", "8765"))
# 上游代理（可选）。中国大陆用户访问 api.anthropic.com 通常需要走代理。
UPSTREAM_PROXY = os.environ.get("LENS_UPSTREAM_PROXY") or None
# 启用的插件（逗号分隔），从 plugins/ 加载。默认 wake_memory（同 repo 自带）。
PLUGIN_NAMES = [p for p in os.environ.get("LENS_PLUGINS", "wake_memory").split(",") if p.strip()]

# 让 plugins.* 这种 import 能解析到 lens/plugins/
sys.path.insert(0, str(Path(__file__).resolve().parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("lens")

PLUGINS = []
for name in PLUGIN_NAMES:
    try:
        mod = importlib.import_module(f"plugins.{name}")
        PLUGINS.append(mod.Plugin())
        log.info(f"loaded plugin: {name}")
    except Exception as e:
        log.error(f"failed to load plugin {name}: {e}")

app = FastAPI()


async def apply_plugins(body_bytes: bytes, path: str) -> bytes:
    """对 messages 类请求应用插件链。"""
    if not body_bytes or "messages" not in path:
        return body_bytes

    try:
        body = json.loads(body_bytes)
    except Exception:
        return body_bytes

    for plugin in PLUGINS:
        try:
            body = await plugin.on_messages_request(body)
        except Exception as e:
            log.error(f"plugin {plugin.__class__.__module__} failed: {e}")

    return json.dumps(body, ensure_ascii=False).encode("utf-8")


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def proxy(request: Request, path: str):
    body = await request.body()
    headers = {k: v for k, v in request.headers.items() if k.lower() != "host"}

    # 应用插件
    new_body = await apply_plugins(body, path)
    if new_body != body:
        log.info(f"plugin modified body: {len(body)} -> {len(new_body)} bytes")
        body = new_body
        # 更新 content-length
        headers["content-length"] = str(len(body))

    target_url = f"{UPSTREAM}/{path}"
    log.info(f"{request.method} /{path} ({len(body)} bytes)")

    is_stream = body and (b'"stream":true' in body or b'"stream": true' in body)

    if is_stream:
        # 先建连接读到响应头，再用迭代器流式 yield body
        client = httpx.AsyncClient(timeout=600.0, proxy=UPSTREAM_PROXY)
        req = client.build_request(
            method=request.method,
            url=target_url,
            content=body,
            headers=headers,
            params=request.query_params,
        )
        response = await client.send(req, stream=True)

        async def body_iter():
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()
                await client.aclose()

        response_headers = {
            k: v for k, v in response.headers.items()
            if k.lower() not in ("transfer-encoding", "content-encoding", "content-length")
        }
        return StreamingResponse(
            body_iter(),
            status_code=response.status_code,
            headers=response_headers,
            media_type=response.headers.get("content-type", "text/event-stream"),
        )
    else:
        async with httpx.AsyncClient(timeout=600.0, proxy=UPSTREAM_PROXY) as client:
            response = await client.request(
                method=request.method,
                url=target_url,
                content=body,
                headers=headers,
                params=request.query_params,
            )
            response_headers = {
                k: v for k, v in response.headers.items()
                if k.lower() not in ("transfer-encoding", "content-encoding", "content-length")
            }
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=response_headers,
            )


if __name__ == "__main__":
    log.info(f"lens starting on http://localhost:{PORT}")
    log.info(f"upstream: {UPSTREAM}")
    log.info(f"upstream proxy: {UPSTREAM_PROXY}")
    log.info(f"plugins: {[p.__class__.__module__ for p in PLUGINS]}")
    log.info(f"to use: export ANTHROPIC_BASE_URL=http://localhost:{PORT}")
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")
