from __future__ import annotations

import json
from typing import Any
from urllib import error, request


class LasApiError(RuntimeError):
    pass


def submit_pdf(config: dict[str, Any], pdf_url: str) -> dict[str, Any]:
    las = config["las"]
    payload = {
        "operator_id": las["operator_id"],
        "operator_version": las["operator_version"],
        "data": {"url": pdf_url},
    }
    return post_json(f"{las['base_url'].rstrip('/')}/submit", las["api_key"], payload, int(las.get("timeout", 60)))


def poll_task(config: dict[str, Any], task_id: str) -> dict[str, Any]:
    las = config["las"]
    payload = {
        "operator_id": las["operator_id"],
        "operator_version": las["operator_version"],
        "task_id": task_id,
    }
    return post_json(f"{las['base_url'].rstrip('/')}/poll", las["api_key"], payload, int(las.get("timeout", 60)))


def post_json(url: str, api_key: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )

    try:
        with request.urlopen(req, timeout=timeout) as response:
            status_code = response.status
            response_body = load_json(response.read(), status_code)
    except error.HTTPError as exc:
        status_code = exc.code
        response_body = load_json(exc.read(), status_code)
    except error.URLError as exc:
        raise LasApiError(f"request failed: {exc.reason}") from exc

    if status_code >= 400:
        raise LasApiError(f"HTTP {status_code}: {response_body}")

    metadata = response_body.get("metadata", {})
    business_code = metadata.get("business_code")
    if business_code not in (None, "", "0", 0):
        raise LasApiError(f"business error {business_code}: {metadata.get('error_msg', response_body)}")

    return response_body


def extract_task_id(response: dict[str, Any]) -> str:
    metadata = response.get("metadata", {})
    task_id = metadata.get("task_id") or response.get("task_id")
    if not task_id:
        raise LasApiError("submit response does not contain task_id")
    return task_id


def task_status(response: dict[str, Any]) -> str:
    metadata = response.get("metadata", {})
    return str(metadata.get("task_status", "")).upper()


def load_json(raw: bytes, status_code: int) -> dict[str, Any]:
    text = raw.decode("utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise LasApiError(f"HTTP {status_code} returned non-JSON response: {text[:300]}") from exc
