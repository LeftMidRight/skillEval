from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
CONFIG_PATH = PROJECT_ROOT / "skill" / "script" / "config.yaml"
PARSER_PATH = PROJECT_ROOT / "skill" / "script" / "las_pdf_parse.py"
TEMP_CONFIG_PATH = SCRIPT_DIR / ".las_test_config.yaml"
OUTPUT_DIR = PROJECT_ROOT / "output" / "las_pdf_parse_sample"
OUTPUT_PATH = OUTPUT_DIR / "las_test_response.json"
PDF_SAMPLE_URL = (
    "https://las-ai-cn-shanghai-online.tos-cn-shanghai.volces.com/"
    "operator_cards_serving/public/online/las_pdf_parse_doubao/v1/pdf-sample.pdf"
)


def main() -> int:
    write_test_config()
    try:
        completed = subprocess.run(
            [sys.executable, str(PARSER_PATH), "--config", str(TEMP_CONFIG_PATH)],
            cwd=PROJECT_ROOT,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=180,
        )
        if completed.returncode != 0:
            print(completed.stdout)
            print(completed.stderr, file=sys.stderr)
            return completed.returncode

        response = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        assert_success_response(response)
        task_id = response["task_id"]
        billable_pages = response["poll_response"]["data"].get("billable_pages")
        print(f"LAS PDF parse test passed. task_id={task_id}, billable_pages={billable_pages}")
        print(f"Response written to {OUTPUT_PATH}")
        return 0
    finally:
        if TEMP_CONFIG_PATH.exists():
            TEMP_CONFIG_PATH.unlink()


def write_test_config() -> None:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"Missing base config: {CONFIG_PATH}")

    lines = CONFIG_PATH.read_text(encoding="utf-8").splitlines()
    output: list[str] = []
    section = ""
    for line in lines:
        stripped = line.strip()
        if stripped.endswith(":") and not line.startswith(" "):
            section = stripped[:-1]
            output.append(line)
            continue

        if section == "request":
            if stripped.startswith("url:"):
                output.append(f'  url: "{PDF_SAMPLE_URL}"')
                continue
            if stripped.startswith("task_id:"):
                output.append('  task_id: ""')
                continue
            if stripped.startswith("wait:"):
                output.append("  wait: true")
                continue

        if section == "output" and stripped.startswith("path:"):
            output.append(f'  path: "{OUTPUT_PATH.as_posix()}"')
            continue

        output.append(line)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_CONFIG_PATH.write_text("\n".join(output) + "\n", encoding="utf-8")


def assert_success_response(response: dict) -> None:
    submit_metadata = response["submit_response"]["metadata"]
    poll_metadata = response["poll_response"]["metadata"]
    data = response["poll_response"]["data"]

    if str(submit_metadata.get("business_code")) != "0":
        raise AssertionError(f"submit business_code is not 0: {submit_metadata}")
    if str(poll_metadata.get("business_code")) != "0":
        raise AssertionError(f"poll business_code is not 0: {poll_metadata}")
    if poll_metadata.get("task_status") != "COMPLETED":
        raise AssertionError(f"task is not completed: {poll_metadata}")
    if not data.get("markdown"):
        raise AssertionError("poll response does not contain markdown")


if __name__ == "__main__":
    raise SystemExit(main())
