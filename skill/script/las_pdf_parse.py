from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from las_client import LasApiError, extract_task_id, poll_task, poll_until_done, submit_pdf, task_status
from error_handler import (
    ErrorCode,
    OperationResult,
    check_poll_response,
    check_submit_response,
    validate_input,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LAS PDF parse submit/poll from config.yaml.")
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.yaml")))
    args = parser.parse_args()

    config = load_config(args.config)
    request_config = config["request"]
    output_path = Path(config["output"]["path"])
    op_result = OperationResult(success=True)

    pdf_url = request_config.get("url", "")
    task_id = request_config.get("task_id", "")
    if bool(pdf_url) == bool(task_id):
        raise LasApiError("config request.url and request.task_id must contain exactly one value")

    # ============================================================
    # 1. 输入校验
    # ============================================================
    if pdf_url:
        validation = validate_input(pdf_url)
        if not validation.success:
            op_result.errors = validation.errors
            op_result.success = False
            _save_error_result(op_result, output_path)
            _print_errors(op_result)
            return 1
        op_result.warnings = validation.warnings

    # ============================================================
    # 2. 提交 + 轮询
    # ============================================================
    try:
        if pdf_url:
            submit_response = submit_pdf(config, pdf_url)
            submit_check = check_submit_response(submit_response)
            if not submit_check.success:
                op_result.errors = submit_check.errors
                _save_error_result(op_result, output_path)
                _print_errors(op_result)
                return 1

            task_id = extract_task_id(submit_response)
            op_result.task_id = task_id
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
                poll_response = poll_until_done(config, task_id)
                result["poll_response"] = poll_response
                poll_check = check_poll_response(poll_response)
                if not poll_check.success:
                    op_result.errors = poll_check.errors
                op_result.warnings.extend(poll_check.warnings)
        else:
            poll_response = poll_task(config, task_id)
            result = {"task_id": task_id, "poll_response": poll_response}
            poll_check = check_poll_response(poll_response)
            if not poll_check.success:
                op_result.errors = poll_check.errors
            op_result.warnings.extend(poll_check.warnings)

    except LasApiError as exc:
        op_result.add_error(ErrorCode.API_SUBMIT_FAILED, str(exc))
        _save_error_result(op_result, output_path)
        _print_errors(op_result)
        return 1

    # ============================================================
    # 3. 保存原始响应
    # ============================================================
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result["_operation"] = op_result.to_dict()
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote LAS response to {output_path}")

    if op_result.warnings:
        for w in op_result.warnings:
            print(f"  [WARN] {w['message']}: {w['detail']}")

    # ============================================================
    # 4. 后处理输出
    # ============================================================
    markdown_path = config["output"].get("markdown_path")
    json_path = config["output"].get("json_path")
    numbers_path = config["output"].get("numbers_path")
    markdown = extract_markdown(result)

    if markdown_path and markdown:
        if config.get("post_process", {}).get("merge_cross_page_tables"):
            from table_merger import merge_cross_page_tables
            markdown = merge_cross_page_tables(markdown)
            print("Post-processed: merged cross-page tables, cleaned page noise")

        markdown_output_path = Path(markdown_path)
        markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_output_path.write_text(markdown, encoding="utf-8")
        print(f"Wrote LAS markdown to {markdown_output_path}")

        if json_path:
            from structured_output import build_structured_output
            page_count = len(result.get("poll_response", {}).get("data", {}).get("detail", []))
            structured_json = build_structured_output(markdown, metadata={
                "pdf_url": pdf_url or "",
                "task_id": task_id,
                "total_pages": page_count or None,
            })
            Path(json_path).parent.mkdir(parents=True, exist_ok=True)
            Path(json_path).write_text(structured_json, encoding="utf-8")
            print(f"Wrote structured JSON to {json_path}")

        if numbers_path:
            from number_extractor import extract_numbers_from_markdown
            numbers_data = extract_numbers_from_markdown(markdown)
            Path(numbers_path).parent.mkdir(parents=True, exist_ok=True)
            Path(numbers_path).write_text(
                json.dumps(numbers_data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Wrote extracted numbers to {numbers_path}")

        # 无表格警告
        table_count = markdown.count("<table>")
        if table_count == 0:
            op_result.add_warning(ErrorCode.NO_TABLES_FOUND, "解析结果中未检测到任何表格")

    elif markdown_path:
        op_result.add_error(ErrorCode.NO_MARKDOWN_OUTPUT, "LAS 响应中无 markdown 内容")
        _save_error_result(op_result, output_path)
        _print_errors(op_result)
        return 1

    if op_result.warnings:
        _save_warnings(op_result, output_path)

    return 0 if op_result.success else 1


def _save_error_result(op_result: OperationResult, output_path: Path) -> None:
    """保存错误结果到文件。"""
    error_path = output_path.with_name(output_path.stem + "_errors.json")
    error_path.parent.mkdir(parents=True, exist_ok=True)
    error_path.write_text(op_result.to_json(), encoding="utf-8")


def _save_warnings(op_result: OperationResult, output_path: Path) -> None:
    """保存警告到文件。"""
    warn_path = output_path.with_name(output_path.stem + "_warnings.json")
    warn_path.parent.mkdir(parents=True, exist_ok=True)
    warn_path.write_text(
        json.dumps({"warnings": op_result.warnings}, ensure_ascii=False, indent=2),
        encoding="utf-8")


def _print_errors(op_result: OperationResult) -> None:
    for err in op_result.errors:
        print(f"  [ERROR {err['code']}] {err['message']}: {err['detail']}", file=sys.stderr)


def extract_markdown(result: dict[str, Any]) -> str:
    poll_response = result.get("poll_response", {})
    if not isinstance(poll_response, dict):
        return ""
    data = poll_response.get("data", {})
    if not isinstance(data, dict):
        return ""
    markdown = data.get("markdown", "")
    return markdown if isinstance(markdown, str) else ""


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
    except Exception as exc:
        print(f"Unexpected error: {exc}", file=sys.stderr)
        raise SystemExit(2)
