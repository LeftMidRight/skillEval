"""通过 WebSocket 直连 ArkClaw OpenClaw Gateway。

绕过 volcapig HTTP 认证，使用浏览器同款的 WebSocket 协议与 OpenClaw 对话。
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid

try:
    import websockets
except ImportError:
    print("需要安装 websockets 库: pip install websockets")
    sys.exit(1)

WSS_URL = os.environ.get(
    "ARKCLAW_WSS_URL",
    "wss://33g1v5uze124g6k70bpe0lkg5.arkclaw-dashboard.cn-shanghai.volcapig.com/claw-webui-ci-yeh1x7h24g5i3z2ryl5z",
)
ARKCLAW_TOKEN = os.environ.get("ARKCLAW_TOKEN", "")


async def send_message(prompt: str, system_prompt: str | None = None) -> str:
    """通过 WebSocket 发送消息并等待回复。

    OpenClaw WebUI 使用 Cloudflare Durable Objects 的 WebSocket 协议。
    客户端发送 JSON 消息，服务端返回流式响应。
    """
    print(f"连接到 {WSS_URL}...")

    async with websockets.connect(WSS_URL, max_size=10 * 1024 * 1024) as ws:
        print("已连接，发送消息...")

        # 构造请求消息
        # OpenClaw WebUI WebSocket 协议：支持 role: "user" 的消息
        message_id = str(uuid.uuid4())

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        request = {
            "type": "chat",
            "id": message_id,
            "messages": messages,
            "stream": True,
        }

        if ARKCLAW_TOKEN:
            request["token"] = ARKCLAW_TOKEN

        await ws.send(json.dumps(request, ensure_ascii=False))

        # 接收流式响应
        content_parts = []
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if msg.get("type") == "chunk":
                chunk = msg.get("content", "")
                print(chunk, end="", flush=True)
                content_parts.append(chunk)
            elif msg.get("type") == "done":
                break
            elif msg.get("type") == "error":
                error_msg = msg.get("message", "Unknown error")
                print(f"\n[ERROR] {error_msg}")
                break

        print()
        return "".join(content_parts)


async def list_models() -> list[dict]:
    """通过 WebSocket 获取可用模型列表。"""
    print(f"连接到 {WSS_URL}...")

    async with websockets.connect(WSS_URL, max_size=10 * 1024 * 1024) as ws:
        request = {"type": "list_models", "id": str(uuid.uuid4())}
        await ws.send(json.dumps(request, ensure_ascii=False))

        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if msg.get("type") == "models":
                return msg.get("models", [])
            elif msg.get("type") == "error":
                print(f"[ERROR] {msg.get('message', 'Unknown error')}")
                break

        return []


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="ArkClaw WebSocket 客户端（绕过 volcapig HTTP 认证）"
    )
    parser.add_argument("prompt", nargs="?", help="发送给 Skill 的消息")
    parser.add_argument("--list-models", action="store_true", help="列出可用模型")
    parser.add_argument("--system", default=None, help="系统提示")
    parser.add_argument("--wss-url", default=None, help="WebSocket URL")
    args = parser.parse_args()

    wss_url = args.wss_url or WSS_URL

    if args.list_models:
        models = asyncio.run(list_models())
        print(json.dumps(models, ensure_ascii=False, indent=2))
        return

    if not args.prompt:
        parser.print_help()
        return

    asyncio.run(send_message(args.prompt, system_prompt=args.system))


if __name__ == "__main__":
    main()
