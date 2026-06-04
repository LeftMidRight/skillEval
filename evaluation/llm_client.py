"""LLM 调用客户端。

用于 Module 2 阅读顺序（视觉判断）和 Module 3 reasoning（文本问答）。
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any


class LLMClient:
    """封装大模型 API 调用。"""

    def __init__(
        self,
        api_key: str,
        model: str = "ep-20260526173832-2vrr2",
        base_url: str = "https://ark-cn-beijing.bytedance.net/api/v3/responses",
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self._last_call_time = 0.0
        self._min_interval = 0.5  # 限速：两次调用最小间隔（秒）

    def _rate_limit(self) -> None:
        """限速等待。"""
        elapsed = time.time() - self._last_call_time
        if elapsed < self._min_interval:
            time.sleep(self._min_interval - elapsed)
        self._last_call_time = time.time()

    def chat(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.0,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """发送对话请求。

        Args:
            messages: [{"role": "user", "content": [...]}]
            temperature: 温度参数。
            max_retries: 最大重试次数。

        Returns:
            API 响应的 JSON dict。
        """
        import urllib.request
        import urllib.error

        payload = json.dumps({
            "model": self.model,
            "input": messages,
            "temperature": temperature,
        }, ensure_ascii=False).encode("utf-8")

        for attempt in range(max_retries):
            self._rate_limit()
            req = urllib.request.Request(
                self.base_url,
                data=payload,
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}",
                },
            )

            try:
                with urllib.request.urlopen(req, timeout=120) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8", errors="replace")
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    print(f"  LLM HTTP {e.code}, retry in {wait}s...")
                    time.sleep(wait)
                else:
                    raise RuntimeError(f"LLM API error {e.code}: {body[:300]}")
            except Exception as e:
                if attempt < max_retries - 1:
                    print(f"  LLM error: {e}, retry...")
                    time.sleep(2)
                else:
                    raise

    def chat_with_image(
        self,
        image_path: str | Path,
        text_prompt: str,
    ) -> dict[str, Any]:
        """发送含图片的对话请求。

        Args:
            image_path: 图片文件路径（PNG/JPEG）。
            text_prompt: 文本提示。

        Returns:
            API 响应。
        """
        image_path = Path(image_path)
        if not image_path.exists():
            raise FileNotFoundError(f"Image not found: {image_path}")

        # 读取并 base64 编码
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        ext = image_path.suffix.lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"

        messages = [{
            "role": "user",
            "content": [
                {
                    "type": "input_image",
                    "image_url": f"data:{mime};base64,{image_data}",
                },
                {
                    "type": "input_text",
                    "text": text_prompt,
                },
            ],
        }]

        return self.chat(messages)

    def chat_text(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        """发送纯文本对话请求。

        Args:
            system_prompt: 系统提示。
            user_prompt: 用户提示。

        Returns:
            API 响应。
        """
        messages = [{
            "role": "user",
            "content": [
                {"type": "input_text", "text": f"{system_prompt}\n\n{user_prompt}"},
            ],
        }]

        return self.chat(messages)

    def extract_json(self, response: dict[str, Any]) -> dict[str, Any]:
        """从 API 响应中提取 JSON 内容。"""
        try:
            # 尝试从 output 中提取
            output = response.get("output", [])
            for item in output:
                if isinstance(item, dict):
                    content_list = item.get("content", [])
                    for c in content_list:
                        if isinstance(c, dict) and c.get("type") == "output_text":
                            text = c.get("text", "")
                            # 尝试提取 JSON
                            return self._parse_json(text)
        except Exception:
            pass
        return {"error": "failed to parse response", "raw": str(response)[:500]}

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        """从文本中提取 JSON。"""
        # 直接尝试解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试提取 ```json ... ``` 块
        import re
        match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        # 尝试提取最外层 {...}
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        return {"error": "no json found", "text": text[:500]}
