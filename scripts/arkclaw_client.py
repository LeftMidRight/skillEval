"""ArkClaw/OpenClaw Gateway 客户端。

通过 OpenAI 兼容的 /v1/chat/completions 端点与 ArkClaw 上的 Skill 交互。

用法：
    # 1. 设置环境变量（或在代码中传入）
    set ARKCLAW_BASE_URL=https://<instance-id>.arkclaw-dashboard.cn-shanghai.volcapig.com
    set ARKCLAW_TOKEN=<your-gateway-token>

    # 2. 运行
    python scripts/arkclaw_client.py "请帮我解析这份财报"
    python scripts/arkclaw_client.py --list-models
    python scripts/arkclaw_client.py --skill financial-report-analyzer-skill "解析603421的年报"

文档参考：
    https://docs.openclaw.ai/gateway/openai-http-api
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any


ARKCLAW_BASE_URL = os.environ.get(
    "ARKCLAW_BASE_URL",
    "https://33g1v5uze124g6k70bpe0lkg5.arkclaw-dashboard.cn-shanghai.volcapig.com",
)
ARKCLAW_TOKEN = os.environ.get("ARKCLAW_TOKEN", "")
ARKCLAW_COOKIE = os.environ.get("ARKCLAW_COOKIE", "")


class ArkClawClient:
    """ArkClaw Gateway OpenAI 兼容客户端。

    通过 /v1/chat/completions 端点与部署在 ArkClaw 上的 Skill 对话。

    Args:
        base_url: ArkClaw 实例的 HTTPS 地址（不含路径）。
        token: Gateway Bearer token（从环境变量或 ArkClaw 控制面板获取）。
        cookie: Cookie 认证（某些 volcapig 部署使用 Cookie 而非 Bearer）。
        model: 目标 Skill/Agent，如 "openclaw/default" 或 "openclaw/<agentId>"。
    """

    def __init__(
        self,
        base_url: str = ARKCLAW_BASE_URL,
        token: str = ARKCLAW_TOKEN,
        cookie: str = "",
        model: str = "openclaw/default",
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.cookie = cookie or os.environ.get("ARKCLAW_COOKIE", "")
        self.model = model

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if self.cookie:
            h["Cookie"] = self.cookie
        return h

    def list_models(self) -> dict[str, Any]:
        """GET /v1/models — 列出可用的 Agent/Skill。"""
        url = f"{self.base_url}/v1/models"
        req = urllib.request.Request(url, method="GET", headers=self._headers())
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {e.code}: {body[:500]}")

    def chat(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        stream: bool = False,
        user: str | None = None,
        temperature: float | None = None,
        max_completion_tokens: int | None = None,
    ) -> dict[str, Any] | str:
        """POST /v1/chat/completions — 发送对话请求。

        Args:
            messages: OpenAI 格式的消息列表。
            model: 覆盖默认 model（如 "openclaw/financial-report-analyzer-skill"）。
            stream: 是否使用 SSE 流式响应。
            user: 会话标识，相同 user 值会共享同一 agent 会话。
            temperature: 采样温度。
            max_completion_tokens: 最大生成 token 数。

        Returns:
            非流式时返回完整响应 dict。
            流式时返回拼接的文本内容。
        """
        url = f"{self.base_url}/v1/chat/completions"
        payload: dict[str, Any] = {
            "model": model or self.model,
            "messages": messages,
            "stream": stream,
        }
        if user:
            payload["user"] = user
        if temperature is not None:
            payload["temperature"] = temperature
        if max_completion_tokens is not None:
            payload["max_completion_tokens"] = max_completion_tokens

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST", headers=self._headers())

        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                if stream:
                    return self._read_sse(resp)
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {e.code}: {body[:500]}")

    @staticmethod
    def _read_sse(resp) -> str:
        """读取 SSE 流并拼接内容。"""
        content_parts = []
        for line in resp:
            line = line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                if "content" in delta and delta["content"]:
                    content_parts.append(delta["content"])
            except json.JSONDecodeError:
                continue
        return "".join(content_parts)

    def chat_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs,
    ) -> str:
        """便捷方法：发送文本对话，返回助手回复内容。

        Args:
            prompt: 用户消息。
            system_prompt: 可选的系统提示。
            **kwargs: 传给 chat() 的额外参数。

        Returns:
            助手回复的文本内容。
        """
        messages: list[dict[str, Any]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        result = self.chat(messages, **kwargs)
        if isinstance(result, str):
            return result

        # 提取非流式响应的内容
        choices = result.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")
        return json.dumps(result, ensure_ascii=False, indent=2)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="ArkClaw/OpenClaw Gateway 客户端",
        epilog="环境变量: ARKCLAW_BASE_URL, ARKCLAW_TOKEN",
    )
    parser.add_argument("prompt", nargs="?", help="发送给 Skill 的消息")
    parser.add_argument("--list-models", action="store_true", help="列出可用模型/Skill")
    parser.add_argument("--skill", default=None, help="指定 Skill ID（如 financial-report-analyzer-skill）")
    parser.add_argument("--stream", action="store_true", help="使用流式响应")
    parser.add_argument("--system", default=None, help="系统提示")
    parser.add_argument("--session", default=None, help="会话 ID（相同 ID 共享上下文）")
    parser.add_argument("--base-url", default=None, help="覆盖 ArkClaw 实例 URL")
    parser.add_argument("--token", default=None, help="覆盖 Bearer token")
    parser.add_argument("--cookie", default=None, help="Cookie 认证头（某些 volcapig 部署使用 Cookie）")

    args = parser.parse_args()

    client = ArkClawClient(
        base_url=args.base_url or ARKCLAW_BASE_URL,
        token=args.token or ARKCLAW_TOKEN,
        cookie=args.cookie or ARKCLAW_COOKIE,
        model=f"openclaw/{args.skill}" if args.skill else "openclaw/default",
    )

    if args.list_models:
        print(f"查询可用模型: {client.base_url}/v1/models ...")
        try:
            models = client.list_models()
            print(json.dumps(models, ensure_ascii=False, indent=2))
        except RuntimeError as e:
            print(f"错误: {e}")
            if "401" in str(e):
                print("\n认证失败！请设置 ARKCLAW_TOKEN 环境变量或在 ArkClaw 控制面板中获取 Gateway Token。")
                print("  set ARKCLAW_TOKEN=<your-gateway-token>")
        return

    if not args.prompt:
        parser.print_help()
        return

    print(f"发送给 {client.model}: {args.prompt[:50]}...")
    try:
        result = client.chat_text(
            prompt=args.prompt,
            system_prompt=args.system,
            stream=args.stream,
            user=args.session,
        )
        print(result)
    except RuntimeError as e:
        print(f"错误: {e}")
        if "401" in str(e):
            print("\n认证失败！请设置 ARKCLAW_TOKEN 环境变量：")
            print("  set ARKCLAW_TOKEN=<your-gateway-token>")


if __name__ == "__main__":
    main()