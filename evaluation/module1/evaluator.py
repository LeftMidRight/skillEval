"""Module 1 主协调器。

整合文本准确率、表格还原度、数值提取率三个子指标。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from module1.utils import get_xbrl_for_company, load_xbrl_dataset
from evaluation.scenes import get_scene_label

from .cross_page import evaluate_cross_page_continuity
from .number_accuracy import evaluate_number_accuracy
from .table_fidelity import compute_mineru_fidelity, compute_xbrl_item_recall
from .text_accuracy import evaluate_text_accuracy


def evaluate_company(
    company_code: str,
    las_markdown: str | None = None,
    las_results_dir: str | Path | None = None,
    xbrl_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """对单家公司执行 Module 1 全部评测。

    Args:
        company_code: 股票代码，如 "603421"。
        las_markdown: LAS 输出的 markdown（合并跨页后）。为 None 时自动从 las_results_dir 加载。
        las_results_dir: LAS 解析结果目录，含 `<code>/report.md`。
        xbrl_records: 预加载的 XBRL 数据集。为 None 时自动加载。

    Returns:
        {
            "company_code": str,
            "text_accuracy": {...},
            "table_fidelity": {"xbrl_item_recall": {...}, "mineru_fidelity": {...}},
            "number_accuracy": {...},
        }
    """
    # 加载数据
    if las_results_dir is None:
        las_results_dir = PROJECT_ROOT / "output" / "las_results"

    if las_markdown is None:
        md_path = Path(las_results_dir) / company_code / "report.md"
        if md_path.exists():
            las_markdown = md_path.read_text(encoding="utf-8")
        else:
            raise FileNotFoundError(f"LAS markdown not found: {md_path}")

    if xbrl_records is None:
        xbrl_dir = PROJECT_ROOT / "data" / "FinAR-Bench"
        xbrl_records = []
        for split in ["dev.txt", "test.txt"]:
            path = xbrl_dir / split
            if path.exists():
                xbrl_records.extend(load_xbrl_dataset(path))

    xbrl_record = get_xbrl_for_company(xbrl_records, company_code)
    if xbrl_record is None:
        raise ValueError(f"XBRL record not found for company {company_code}")

    # ---- 1.1 文本准确率 ----
    text_result = evaluate_text_accuracy(las_markdown, company_code)

    # ---- 1.2 表格还原度 ----
    xbrl_recall = compute_xbrl_item_recall(las_markdown, xbrl_record)
    mineru_fidelity = compute_mineru_fidelity(las_markdown, company_code)

    # ---- 1.3 数值提取率 ----
    number_result = evaluate_number_accuracy(las_markdown, xbrl_record, company_code)

    # ---- 1.4 跨页表格连续性 ----
    cross_page_result = evaluate_cross_page_continuity(las_markdown, company_code)

    scene = get_scene_label(company_code)

    return {
        "company_code": company_code,
        "scene": scene,
        "text_accuracy": text_result,
        "table_fidelity": {
            "xbrl_item_recall": xbrl_recall,
            "mineru_fidelity": mineru_fidelity,
        },
        "number_accuracy": number_result,
        "cross_page_continuity": cross_page_result,
    }


def evaluate_all(
    company_codes: list[str],
    las_results_dir: str | Path | None = None,
    output_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    """批量执行 Module 1 评测。

    Args:
        company_codes: 股票代码列表。
        las_results_dir: LAS 解析结果目录。
        output_path: 保存结果的 JSON 路径。

    Returns:
        评测结果列表。
    """
    # 预加载 XBRL
    xbrl_dir = PROJECT_ROOT / "data" / "FinAR-Bench"
    xbrl_records: list[dict[str, Any]] = []
    for split in ["dev.txt", "test.txt"]:
        path = xbrl_dir / split
        if path.exists():
            xbrl_records.extend(load_xbrl_dataset(path))
    print(f"Loaded {len(xbrl_records)} XBRL records")

    results: list[dict[str, Any]] = []
    for i, code in enumerate(company_codes):
        print(f"[{i+1}/{len(company_codes)}] {code}...", end=" ")
        try:
            result = evaluate_company(
                code,
                las_results_dir=las_results_dir,
                xbrl_records=xbrl_records,
            )
            results.append(result)
            print("OK")
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({"company_code": code, "error": str(e)})

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"\nSaved: {output_path}")

    return results
