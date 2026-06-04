"""批量 PDF 解析处理器。

读取 PDF URL 列表，逐份调用 LAS 解析，输出批量汇总。
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from error_handler import (
    ErrorCode,
    OperationResult,
    check_poll_response,
    check_submit_response,
    validate_input,
)
from las_client import LasApiError, extract_task_id, poll_until_done, submit_pdf, task_status


BATCH_SUMMARY_SCHEMA = {
    "total": 0,
    "completed": 0,
    "failed": 0,
    "skipped": 0,
    "results": [],
}


def process_batch(
    config: dict[str, Any],
    url_list: list[str],
    output_dir: Path,
    wait: bool = True,
) -> dict[str, Any]:
    """逐份处理 PDF URL 列表。

    Args:
        config: LAS 配置字典（与 las_pdf_parse.py 共用 config.yaml 格式）。
        url_list: PDF URL 列表。
        output_dir: 输出目录基础路径（每份 PDF 生成子目录）。
        wait: 是否等待每份 PDF 解析完成。

    Returns:
        批量汇总 dict。
    """
    summary = dict(BATCH_SUMMARY_SCHEMA)
    summary["total"] = len(url_list)
    summary["results"] = []

    merge_tables = config.get("post_process", {}).get("merge_cross_page_tables", False)

    for idx, pdf_url in enumerate(url_list):
        print(f"\n[{idx + 1}/{len(url_list)}] {pdf_url[:100]}...")
        item_result = {
            "index": idx,
            "url": pdf_url,
            "success": False,
            "task_id": "",
            "errors": [],
            "output_dir": "",
        }

        # 输入校验
        validation = validate_input(pdf_url)
        if not validation.success:
            item_result["errors"] = validation.errors
            summary["failed"] += 1
            summary["results"].append(item_result)
            print(f"  SKIP: {validation.errors[0]['message']}")
            continue

        # 生成输出路径
        code = _derive_code(pdf_url, idx)
        task_dir = output_dir / code
        task_dir.mkdir(parents=True, exist_ok=True)
        item_result["output_dir"] = str(task_dir)

        try:
            # 提交
            submit_response = submit_pdf(config, pdf_url)
            submit_check = check_submit_response(submit_response)
            if not submit_check.success:
                item_result["errors"] = submit_check.errors
                summary["failed"] += 1
                summary["results"].append(item_result)
                print(f"  FAIL: {submit_check.errors[0]['message']}")
                continue

            task_id = extract_task_id(submit_response)
            item_result["task_id"] = task_id

            # 保存原始响应
            response = {
                "request": {"url": pdf_url, "operator_id": config["las"]["operator_id"],
                            "operator_version": config["las"]["operator_version"]},
                "task_id": task_id,
                "submit_response": submit_response,
            }

            # 轮询
            if wait:
                poll_response = poll_until_done(config, task_id)
                response["poll_response"] = poll_response
                poll_check = check_poll_response(poll_response)
                if not poll_check.success:
                    item_result["errors"] = poll_check.errors
                    summary["failed"] += 1
                    summary["results"].append(item_result)
                    (task_dir / "las_response.json").write_text(
                        json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")
                    print(f"  FAIL: {poll_check.errors[0]['message']}")
                    continue

            (task_dir / "las_response.json").write_text(
                json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8")

            # 后处理输出
            markdown = _extract_markdown(response)
            if markdown:
                if merge_tables:
                    from table_merger import merge_cross_page_tables
                    markdown = merge_cross_page_tables(markdown)
                    print("  Merged cross-page tables")

                (task_dir / "report.md").write_text(markdown, encoding="utf-8")

                # 结构化 JSON
                from structured_output import build_structured_output
                page_count = len(response.get("poll_response", {}).get("data", {}).get("detail", []))
                structured = build_structured_output(markdown, metadata={
                    "pdf_url": pdf_url, "task_id": task_id,
                    "total_pages": page_count or None,
                })
                (task_dir / "report_structured.json").write_text(structured, encoding="utf-8")

                # 数值提取
                from number_extractor import extract_numbers_from_markdown
                numbers = extract_numbers_from_markdown(markdown)
                (task_dir / "report_numbers.json").write_text(
                    json.dumps(numbers, ensure_ascii=False, indent=2), encoding="utf-8")

            item_result["success"] = True
            summary["completed"] += 1
            print(f"  OK (task_id={task_id})")

        except LasApiError as exc:
            item_result["errors"].append({
                "code": ErrorCode.API_SUBMIT_FAILED,
                "message": "API 请求失败",
                "detail": str(exc),
            })
            summary["failed"] += 1
            print(f"  ERROR: {exc}")

        except Exception as exc:
            item_result["errors"].append({
                "code": 999,
                "message": "未知错误",
                "detail": str(exc),
            })
            summary["failed"] += 1
            print(f"  ERROR: {exc}")

        summary["results"].append(item_result)

    # 保存汇总
    summary_path = output_dir / "batch_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nBatch complete: {summary['completed']}/{summary['total']} completed, "
          f"{summary['failed']} failed")
    print(f"Summary: {summary_path}")

    return summary


def _derive_code(url: str, index: int) -> str:
    """从 URL 推导股票代码或任务名。"""
    import re
    # 尝试匹配 6 位数字代码
    match = re.search(r"(\d{6})", url)
    if match:
        return match.group(1)
    # 回退：使用文件名
    filename = url.split("/")[-1].split("?")[0]
    name = filename.rsplit(".", 1)[0]
    if name:
        return name
    return f"task_{index:03d}"


def _extract_markdown(response: dict[str, Any]) -> str:
    poll = response.get("poll_response", {})
    if isinstance(poll, dict):
        data = poll.get("data", {})
        if isinstance(data, dict):
            md = data.get("markdown", "")
            if isinstance(md, str):
                return md
    return ""


# ---------------------------------------------------------------------------
# CLI 入口
# ---------------------------------------------------------------------------

def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Batch LAS PDF parse from URL list.")
    parser.add_argument("url_list", help="Path to file with one PDF URL per line")
    parser.add_argument("--config", default=str(Path(__file__).with_name("config.yaml")))
    parser.add_argument("--output-dir", default="output/batch")
    parser.add_argument("--no-wait", action="store_true", help="Submit only, don't wait for completion")
    args = parser.parse_args()

    # 加载配置
    from las_pdf_parse import load_config
    config = load_config(args.config)

    # 读取 URL 列表
    url_path = Path(args.url_list)
    if not url_path.exists():
        print(f"URL list file not found: {url_path}", file=sys.stderr)
        return 1

    urls = [l.strip() for l in url_path.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.strip().startswith("#")]

    if not urls:
        print("No URLs found in list file", file=sys.stderr)
        return 1

    print(f"Processing {len(urls)} PDFs...")
    output_dir = Path(args.output_dir)
    process_batch(config, urls, output_dir, wait=not args.no_wait)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
