"""批量解析 25 份财报 PDF 通过 LAS。

读取 config.yaml 模板（获取 LAS 认证信息），
遍历 data/eval_dataset/_all_pdfs/ 下所有 PDF，
调用 LAS submit → poll → 保存 JSON + Markdown。

输出结构：
    output/las_results/{股票代码}/
        las_response.json
        report.md
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

# 确保项目根路径在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from skill.script.las_client import (
    LasApiError,
    extract_task_id,
    poll_task,
    submit_pdf,
    task_status,
)

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

TOS_BASE = "https://ark-auto-2108530377-cn-beijing-default.tos-cn-beijing.volces.com"
PDF_PREFIX = "FinAR_PDF/_all_pdfs"
OUTPUT_BASE = PROJECT_ROOT / "output" / "las_results"

# 所有 25 个股票代码
STOCK_CODES = [
    "600064", "600070", "600082", "600083", "600100",
    "600114", "600130", "600133", "600168", "600193",
    "600225", "600322", "600569", "600597", "600626",
    "600933", "603201", "603228", "603256", "603299",
    "603313", "603316", "603421", "603586", "603707",
]

TERMINAL_STATUSES = {"COMPLETED", "FAILED", "CANCELED", "CANCELLED"}


# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------

def load_las_config() -> dict[str, Any]:
    """从 skill/script/config.yaml 加载 LAS 配置段。"""
    config_path = PROJECT_ROOT / "skill" / "script" / "config.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"LAS config not found: {config_path}")

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
            continue
        key, value = line.strip().split(":", 1)
        current_section[key] = _parse_config_value(value.strip())
    return config


def _parse_config_value(value: str) -> Any:
    import os
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


# ---------------------------------------------------------------------------
# 单个 PDF 处理
# ---------------------------------------------------------------------------

def process_pdf(
    las_config: dict[str, Any],
    stock_code: str,
    poll_interval: float = 5.0,
    max_polls: int = 30,
) -> dict[str, Any]:
    """处理单个 PDF：提交 → 轮询 → 保存结果。

    Returns:
        结果 dict（与 las_pdf_parse.py 的 output 格式一致）
    """
    pdf_url = f"{TOS_BASE}/{PDF_PREFIX}/{stock_code}.pdf"
    print(f"  [{stock_code}] Submitting: {pdf_url}")

    # Submit
    submit_response = submit_pdf(las_config, pdf_url)
    task_id = extract_task_id(submit_response)
    print(f"  [{stock_code}] Task ID: {task_id}")

    result: dict[str, Any] = {
        "request": {
            "url": pdf_url,
            "operator_id": las_config["las"]["operator_id"],
            "operator_version": las_config["las"]["operator_version"],
        },
        "task_id": task_id,
        "submit_response": submit_response,
    }

    # Poll until done
    for attempt in range(max_polls):
        poll_response = poll_task(las_config, task_id)
        status = task_status(poll_response)

        if attempt == 0 or attempt % 5 == 0:
            print(f"  [{stock_code}] Poll {attempt+1}/{max_polls}: {status}")

        if status in TERMINAL_STATUSES:
            result["poll_response"] = poll_response
            print(f"  [{stock_code}] Final: {status}")

            # 日志错误信息
            metadata = poll_response.get("metadata", {})
            if status == "COMPLETED":
                data = poll_response.get("data", {})
                md_len = len(data.get("markdown", "")) if isinstance(data, dict) else 0
                billable = data.get("billable_pages", "?") if isinstance(data, dict) else "?"
                print(f"  [{stock_code}] Markdown: {md_len} chars, Billable pages: {billable}")
            else:
                biz_code = metadata.get("business_code", "?")
                err_msg = metadata.get("error_msg", "")
                print(f"  [{stock_code}] business_code={biz_code} error={err_msg[:200]}")
            break

        time.sleep(poll_interval)
    else:
        # 最后一次 poll
        result["poll_response"] = poll_task(las_config, task_id)
        print(f"  [{stock_code}] Timeout after {max_polls} polls")

    # 保存结果
    output_dir = OUTPUT_BASE / stock_code
    output_dir.mkdir(parents=True, exist_ok=True)

    # 保存完整 JSON
    json_path = output_dir / "las_response.json"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  [{stock_code}] JSON saved: {json_path}")

    # 提取并保存 Markdown
    markdown = _extract_markdown(result)
    md_path = output_dir / "report.md"
    if markdown:
        md_path.write_text(markdown, encoding="utf-8")
        print(f"  [{stock_code}] Markdown saved: {md_path} ({len(markdown)} chars)")
    else:
        print(f"  [{stock_code}] WARNING: No markdown in response")

    return result


def _extract_markdown(result: dict[str, Any]) -> str:
    poll = result.get("poll_response", {})
    if isinstance(poll, dict):
        data = poll.get("data", {})
        if isinstance(data, dict):
            md = data.get("markdown", "")
            if md:
                return md
    return ""


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Batch LAS PDF Parse — 25 Financial Reports")
    print("=" * 60)

    las_config = load_las_config()
    print(f"LAS endpoint: {las_config['las']['base_url']}")
    print(f"PDF source: {TOS_BASE}/{PDF_PREFIX}/")
    print(f"Output: {OUTPUT_BASE}")
    print()

    results: dict[str, dict[str, Any]] = {}
    success = 0
    failed = 0

    for i, code in enumerate(STOCK_CODES, 1):
        print(f"\n[{i}/25] Processing {code}...")
        try:
            result = process_pdf(las_config, code)
            results[code] = result

            status = task_status(result.get("poll_response", {}))
            if status == "COMPLETED":
                success += 1
            else:
                failed += 1
        except LasApiError as e:
            print(f"  [{code}] LAS API ERROR: {e}")
            results[code] = {"error": str(e)}
            failed += 1
        except Exception as e:
            print(f"  [{code}] UNEXPECTED ERROR: {e}")
            import traceback
            traceback.print_exc()
            results[code] = {"error": str(e)}
            failed += 1

    # 汇总
    print("\n" + "=" * 60)
    print("BATCH COMPLETE")
    print("=" * 60)
    print(f"Total: {len(STOCK_CODES)}")
    print(f"Success: {success}")
    print(f"Failed: {failed}")

    # 保存汇总
    summary_path = OUTPUT_BASE / "batch_summary.json"
    summary = {
        "total": len(STOCK_CODES),
        "success": success,
        "failed": failed,
        "results": {
            code: {
                "task_id": r.get("task_id", ""),
                "status": task_status(r.get("poll_response", {})),
            }
            if "error" not in r
            else {"error": r["error"]}
            for code, r in results.items()
        },
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Summary saved: {summary_path}")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
