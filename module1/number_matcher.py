"""子指标 3：金融数值匹配率。

参照系：XBRL 表格中所有数值。
"""

from __future__ import annotations

from typing import Any

from module1.utils import extract_numbers, normalize_number, parse_xbrl_tables


def _extract_xbrl_numbers(xbrl_record: dict[str, Any]) -> set[str]:
    """从 XBRL 数据中提取所有标准化数值。

    包含三张表（利润表、资产负债表、现金流量表）中的所有单元格数值。
    """
    xbrl_tables = parse_xbrl_tables(xbrl_record["table"])
    numbers: set[str] = set()

    for table_name, rows in xbrl_tables.items():
        for row in rows:
            for col, val in row.items():
                val = val.strip()
                if not val:
                    continue
                # 尝试标准化
                norm = normalize_number(val)
                if norm != val or _looks_like_number(val):
                    numbers.add(norm)

    return numbers


def _looks_like_number(s: str) -> bool:
    """判断字符串是否为数值。"""
    s = s.replace(",", "").replace(" ", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        float(s)
        return True
    except ValueError:
        return False


def _extract_numbers_from_markdown(markdown: str) -> set[str]:
    """从 markdown 中提取所有标准化数值——仅限表格内。

    用 table 解析提取单元格值，避免文本数字（页码、年份等）污染。
    """
    from module1.utils import extract_all_tables, parse_html_tables

    normalized: set[str] = set()

    # 优先用 HTML 表格解析
    tables = extract_all_tables(markdown)
    for title, dict_list, tree in tables:
        if tree is not None:
            for row in tree.rows:
                for cell in row:
                    content = cell.content.strip()
                    if content and _looks_like_number(content.replace(",", "").replace(" ", "")):
                        norm = normalize_number(content)
                        normalized.add(norm)
        elif dict_list:
            for row in dict_list:
                for val in row.values():
                    val = val.strip()
                    if val and _looks_like_number(val.replace(",", "").replace(" ", "")):
                        norm = normalize_number(val)
                        normalized.add(norm)

    return normalized


def compute_number_f1(
    las_numbers: set[str],
    xbrl_numbers: set[str],
) -> dict:
    """计算数值匹配的 Precision / Recall / F1。

    Args:
        las_numbers: LAS 输出的标准化数值集合
        xbrl_numbers: XBRL 的标准化数值集合

    Returns:
        {precision, recall, f1, tp, fp, fn, matched_examples, missing_examples, extra_examples}
    """
    intersection = las_numbers & xbrl_numbers
    tp = len(intersection)
    fp = len(las_numbers - xbrl_numbers)
    fn = len(xbrl_numbers - las_numbers)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    # 采样示例（最多 10 个）
    missing = list(xbrl_numbers - las_numbers)[:10]
    extra = list(las_numbers - xbrl_numbers)[:10]
    matched = list(intersection)[:10]

    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "total_xbrl": len(xbrl_numbers),
        "total_las": len(las_numbers),
        "matched_examples": matched,
        "missing_examples": missing,
        "extra_examples": extra,
    }


def evaluate_number_accuracy(
    las_markdown: str,
    xbrl_record: dict[str, Any],
) -> dict:
    """评估 LAS 金融数值匹配率。

    Args:
        las_markdown: LAS 输出的完整 markdown
        xbrl_record: FinAR-Bench 的一条记录

    Returns:
        {precision, recall, f1, ...}
    """
    xbrl_numbers = _extract_xbrl_numbers(xbrl_record)
    las_numbers = _extract_numbers_from_markdown(las_markdown)
    return compute_number_f1(las_numbers, xbrl_numbers)
