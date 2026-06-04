"""Module 1.3: 数值提取率。

- XBRL Recall: XBRL 中的关键数值在 LAS 表格中被找到的比例
- Mineru Jaccard: LAS 数值集合与 Mineru 数值集合的重叠度
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from module1.utils import (
    extract_numbers,
    load_reference_text,
    normalize_number,
    parse_xbrl_tables,
)

# 仅从 HTML 表格提取数值的简单正则
_TD_NUM_RE = re.compile(r"<td[^>]*>([^<]*)</td>", re.DOTALL)
_TH_NUM_RE = re.compile(r"<th[^>]*>([^<]*)</th>", re.DOTALL)


def _extract_numbers_from_html_tables(markdown: str) -> set[str]:
    """从 HTML <table> 的 <td> 中提取标准化数值集合。"""
    numbers: set[str] = set()
    for td_match in _TD_NUM_RE.finditer(markdown):
        text = td_match.group(1).strip()
        if not text:
            continue
        for num in extract_numbers(text):
            norm = normalize_number(num)
            if norm and norm != num:  # 成功标准化
                numbers.add(norm)
    return numbers


def _extract_numbers_from_xbrl(xbrl_record: dict[str, Any]) -> set[str]:
    """从 XBRL 记录的三张表中提取标准化数值集合。"""
    tables = parse_xbrl_tables(xbrl_record.get("table", ""))
    numbers: set[str] = set()
    for rows in tables.values():
        for row in rows:
            for key, val in row.items():
                if key == "项目" or not val.strip():
                    continue
                norm = normalize_number(val)
                if norm != val:
                    numbers.add(norm)
    return numbers


def _extract_numbers_from_mineru(mineru_text: str) -> set[str]:
    """从 Mineru 输出的 HTML 表格中提取标准化数值集合。"""
    return _extract_numbers_from_html_tables(mineru_text)


# ---------------------------------------------------------------------------
# 主接口
# ---------------------------------------------------------------------------


def evaluate_number_accuracy(
    las_markdown: str,
    xbrl_record: dict[str, Any],
    company_code: str = "",
    parser_output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """计算数值提取的双指标。

    Returns:
        {
            "xbrl_recall": float,
            "xbrl_found": int,
            "xbrl_total": int,
            "xbrl_missing_examples": [...],
            "mineru_jaccard": float,
            "mineru_overlap_count": int,
        }
    """
    las_numbers = _extract_numbers_from_html_tables(las_markdown)
    xbrl_numbers = _extract_numbers_from_xbrl(xbrl_record)

    # ---- XBRL Recall ----
    intersection = las_numbers & xbrl_numbers
    xbrl_total = len(xbrl_numbers)
    xbrl_found = len(intersection)
    xbrl_recall = xbrl_found / xbrl_total if xbrl_total > 0 else 1.0
    missing = list(xbrl_numbers - las_numbers)[:10]

    # ---- Mineru Jaccard ----
    if parser_output_dir is None:
        parser_output_dir = (
            PROJECT_ROOT / "data" / "FinAR-Bench" / "extracted"
            / "pdf_extractor_result" / "txt_output"
        )

    mineru_text = load_reference_text(
        Path(parser_output_dir) / "mineru", company_code or ""
    )
    mineru_jaccard = float("nan")
    mineru_overlap = 0
    if mineru_text:
        mineru_numbers = _extract_numbers_from_mineru(mineru_text)
        union = las_numbers | mineru_numbers
        mineru_overlap = len(las_numbers & mineru_numbers)
        mineru_jaccard = round(mineru_overlap / len(union), 3) if union else float("nan")

    return {
        "xbrl_recall": round(xbrl_recall, 3),
        "xbrl_found": xbrl_found,
        "xbrl_total": xbrl_total,
        "xbrl_missing_examples": missing,
        "mineru_jaccard": mineru_jaccard,
        "mineru_overlap_count": mineru_overlap,
    }
