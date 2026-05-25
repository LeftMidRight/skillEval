from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from las_client import LasApiError, extract_task_id, poll_task, submit_pdf, task_status


TERMINAL_STATUSES = {"COMPLETED", "FAILED", "CANCELED", "CANCELLED"}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LAS PDF parse submit/poll from config.yaml.")
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.yaml")))
    args = parser.parse_args()

    config = load_config(args.config)
    request_config = config["request"]
    output_path = Path(config["output"]["path"])

    pdf_url = request_config.get("url", "")
    task_id = request_config.get("task_id", "")
    if bool(pdf_url) == bool(task_id):
        raise LasApiError("config request.url and request.task_id must contain exactly one value")

    if pdf_url:
        submit_response = submit_pdf(config, pdf_url)
        task_id = extract_task_id(submit_response)
        result: dict[str, Any] = {
            "request": {
                "url": pdf_url,
                "operator_id": config["las"]["operator_id"],
                "operator_version": config["las"]["operator_version"],
            },
            "task_id": task_id,
            "submit_response": submit_response,
        }
        if request_config.get("wait", False):
            result["poll_response"] = poll_until_done(config, task_id)
    else:
        result = {
            "task_id": task_id,
            "poll_response": poll_task(config, task_id),
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote LAS response to {output_path}")
    return 0


def poll_until_done(config: dict[str, Any], task_id: str) -> dict[str, Any]:
    max_polls = int(config["request"].get("max_polls", 20))
    poll_interval = float(config["request"].get("poll_interval", 5.0))
    latest: dict[str, Any] = {}

    for attempt in range(max_polls):
        latest = poll_task(config, task_id)
        if task_status(latest) in TERMINAL_STATUSES:
            return latest
        if attempt < max_polls - 1:
            time.sleep(poll_interval)
    return latest


def load_config(path: str) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        raise LasApiError(f"config file does not exist: {config_path}")

    config: dict[str, Any] = {}
    current_section: dict[str, Any] | None = None
    for raw_line in config_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        if not line.startswith(" "):
            section = line.rstrip(":")
            current_section = {}
            config[section] = current_section
            continue
        if current_section is None:
            raise LasApiError(f"invalid config line: {raw_line}")
        key, value = line.strip().split(":", 1)
        current_section[key] = parse_value(value.strip())

    return config


def parse_value(value: str) -> Any:
    value = value.strip('"').strip("'")
    if value.startswith("${") and value.endswith("}"):
        value = os.getenv(value[2:-1], "")
    if value.lower() == "true":
        return True
    if value.lower() == "false":
        return False
    if value.isdigit():
        return int(value)
    try:
        return float(value)
    except ValueError:
        return value


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except LasApiError as exc:
        print(f"LAS request failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
