"""密集数值提取器。

从合并后的 markdown 中提取所有表格数值，标准化格式，
输出结构化 JSON（含数值上下文、单位检测、格式异常标记）。
"""

from __future__ import annotations

import json
import re
from typing import Any

# ---------------------------------------------------------------------------
# 数值提取与标准化
# ---------------------------------------------------------------------------

# 金额型数值模式
_NUMBER_RE = re.compile(
    r"-?"  # 可选负号
    r"\(?"  # 可选左括号
    r"\d{1,3}(?:,\d{3})*"  # 整数部分（含千分位）
    r"(?:\.\d+)?"  # 可选小数
    r"\)?"  # 可选右括号
    r"%?"  # 可选百分号
)

# 单位声明模式
_UNIT_RE = re.compile(
    r"(?:单位|單位)\s*[:：]\s*(?:人民币)?\s*(元|千元|万元|亿元|百万元)",
)
_UNIT_FALLBACK_RE = re.compile(r"(元|千元|万元|亿元|百万元)")

# 纯数字（年份、序号、电话等非金额）
_YEAR_RE = re.compile(r"^20[012]\d$")
_PHONE_RE = re.compile(r"^[\d\-]{7,}$")
_SEQ_RE = re.compile(r"^\d{1,2}$")


def _is_financial_number(raw: str) -> bool:
    """判断是否为金融金额型数字，排除年份/序号/电话。"""
    stripped = raw.strip().replace(",", "").replace("(", "").replace(")", "").replace("%", "")
    if stripped.startswith("-"):
        stripped = stripped[1:]
    if not stripped:
        return False
    if _YEAR_RE.match(stripped):
        return False
    if _PHONE_RE.match(stripped):
        return False
    if _SEQ_RE.match(stripped) and raw.count(",") == 0:
        return False
    return True


def normalize_value(raw: str) -> dict[str, Any]:
    """标准化一个数值字符串。

    Returns:
        {
            "raw": 原始字符串,
            "value": 数值（float）,
            "is_negative": 是否负数,
            "is_percentage": 是否百分比,
            "has_thousands_separator": 是否有千分位逗号,
            "has_parentheses": 是否括号格式,
        }
    """
    result: dict[str, Any] = {
        "raw": raw.strip(),
        "is_negative": False,
        "is_percentage": "%" in raw,
        "has_parentheses": raw.strip().startswith("(") and ")" in raw,
    }

    s = raw.strip()
    # 括号负数: (1,234.56) → -1234.56
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1]
        result["is_negative"] = True
    elif s.startswith("-"):
        result["is_negative"] = True

    # 百分号剥离
    if s.endswith("%"):
        s = s[:-1]

    # 千分位逗号
    result["has_thousands_separator"] = "," in s
    s = s.replace(",", "")

    try:
        val = float(s)
        if result["is_negative"]:
            val = -abs(val)
        result["value"] = val
    except ValueError:
        result["value"] = None

    return result


# ---------------------------------------------------------------------------
# 表格数值提取
# ---------------------------------------------------------------------------

# 表格标题匹配（在 markdown 中查找表格前最近的标题）
_TITLE_BEFORE_TABLE = re.compile(r"(?:^|\n)(#{1,3})\s+(.+?)\n")


def _find_table_context(markdown: str, table_start: int) -> tuple[str, str]:
    """找到表格前最近的标题作为上下文。"""
    preceding = markdown[:table_start]
    matches = list(_TITLE_BEFORE_TABLE.finditer(preceding))
    if matches:
        last = matches[-1]
        return f"{'#' * len(last.group(1))} {last.group(2)}", ""
    return "", ""


def _extract_table_headers(html: str) -> list[str]:
    """从 HTML 表头提取列名。"""
    headers: list[str] = []
    thead_match = re.search(r"<thead>(.*?)</thead>", html, re.DOTALL)
    if thead_match:
        for th in re.finditer(r"<th[^>]*>(.*?)</th>", thead_match.group(1), re.DOTALL):
            headers.append(re.sub(r"<[^>]+>", "", th.group(1)).strip())
    return headers


def extract_numbers_from_markdown(markdown: str) -> dict[str, Any]:
    """从 markdown 的所有表格中提取标准化数值。

    Args:
        markdown: 合并跨页表格后的 markdown。

    Returns:
        {
            "numbers": [{table_index, row, col, raw, value, row_label, column_header, ...}],
            "unit_detection": {...},
            "format_issues": [...],
            "summary": {total_numbers, tables_with_numbers, ...}
        }
    """
    all_numbers: list[dict[str, Any]] = []
    format_issues: list[dict[str, Any]] = []
    detected_units: dict[str, int] = {}

    # 全局单位检测
    for m in _UNIT_RE.finditer(markdown):
        unit = m.group(1)
        detected_units[unit] = detected_units.get(unit, 0) + 1

    # 解析每张表格
    table_pattern = re.compile(r"<table>(.*?)</table>", re.DOTALL)
    tables = list(table_pattern.finditer(markdown))

    for ti, table_match in enumerate(tables):
        html = table_match.group(1)
        table_start = table_match.start()

        # 表格上下文
        title_ctx, _ = _find_table_context(markdown, table_start)

        # 表头列名
        headers = _extract_table_headers(f"<table>{html}</table>")

        # 解析 tbody 行
        tbody_match = re.search(r"<tbody>(.*?)</tbody>", html, re.DOTALL)
        if not tbody_match:
            thead_end = html.find("</thead>")
            if thead_end > 0:
                body_html = html[thead_end + len("</thead>"):]
            else:
                body_html = html
        else:
            body_html = tbody_match.group(1)

        rows = list(re.finditer(r"<tr>(.*?)</tr>", body_html, re.DOTALL))

        for ri, row_match in enumerate(rows):
            cells_html = row_match.group(1)
            cells = list(re.finditer(r"<(td|th)([^>]*)>(.*?)</\1>", cells_html, re.DOTALL))

            # 该行的文本标签（第一列内容）
            row_label = ""
            if cells:
                first_cell_text = re.sub(r"<[^>]+>", "", cells[0].group(3)).strip()
                row_label = first_cell_text

            for ci, cell_match in enumerate(cells):
                cell_text = re.sub(r"<[^>]+>", "", cell_match.group(3)).strip()
                if not cell_text:
                    continue

                # 检测数值
                num_matches = _NUMBER_RE.findall(cell_text)
                for raw in num_matches:
                    raw = raw.strip()
                    if not raw or not _is_financial_number(raw):
                        continue

                    norm = normalize_value(raw)
                    col_header = headers[ci] if ci < len(headers) else ""

                    entry = {
                        "table_index": ti,
                        "table_title": title_ctx,
                        "row": ri,
                        "col": ci,
                        "raw": norm["raw"],
                        "value": norm["value"],
                        "row_label": row_label,
                        "column_header": col_header,
                        "is_negative": norm["is_negative"],
                        "is_percentage": norm["is_percentage"],
                    }

                    all_numbers.append(entry)

                    # 检测格式异常
                    if norm["has_parentheses"]:
                        format_issues.append({
                            "table_index": ti,
                            "row": ri,
                            "col": ci,
                            "raw": norm["raw"],
                            "issue": "parentheses_negative",
                        })
                    if norm["has_thousands_separator"]:
                        format_issues.append({
                            "table_index": ti,
                            "row": ri,
                            "col": ci,
                            "raw": norm["raw"],
                            "issue": "thousands_separator",
                        })

    # 汇总
    tables_with_numbers = len(set(n["table_index"] for n in all_numbers))
    negatives = [n for n in all_numbers if n["is_negative"]]
    percentages = [n for n in all_numbers if n["is_percentage"]]

    return {
        "numbers": all_numbers,
        "unit_detection": {
            "explicit_units": detected_units,
            "primary_unit": max(detected_units, key=detected_units.get) if detected_units else "未知",
        },
        "format_issues": format_issues,
        "summary": {
            "total_numbers": len(all_numbers),
            "tables_with_numbers": tables_with_numbers,
            "total_tables": len(tables),
            "negatives_count": len(negatives),
            "percentages_count": len(percentages),
            "unique_values": len(set(n["value"] for n in all_numbers if n["value"] is not None)),
        },
    }
