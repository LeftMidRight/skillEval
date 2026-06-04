"""表格结构校验器。

检测 LAS 输出的表格结构一致性，标记可能存在解析问题的表
（无边框表/少边框表更容易出现列错位、行合并等结构问题）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class TableIssue:
    type: str  # column_mismatch | empty_columns | irregular_rowspan | empty_table
    severity: str  # warning | error
    detail: str
    row: int | None = None


@dataclass
class ValidationResult:
    table_index: int
    is_valid: bool
    row_count: int
    col_count: int
    col_counts_per_row: list[int] = field(default_factory=list)
    issues: list[dict[str, Any]] = field(default_factory=list)
    borderless_risk: str = "unknown"  # low | medium | high | unknown

    def to_dict(self) -> dict[str, Any]:
        return {
            "table_index": self.table_index,
            "is_valid": self.is_valid,
            "row_count": self.row_count,
            "col_count": self.col_count,
            "col_counts_per_row": self.col_counts_per_row,
            "issues": self.issues,
            "borderless_risk": self.borderless_risk,
        }


# ---------------------------------------------------------------------------
# 校验逻辑
# ---------------------------------------------------------------------------

def _count_cells_in_row(tr_html: str) -> int:
    """计算一行中的单元格数（含 colspan 展开）。"""
    total = 0
    for cell in re.finditer(r"<(td|th)([^>]*)>", tr_html):
        attrs = cell.group(2)
        cm = re.search(r'colspan\s*=\s*"(\d+)"', attrs)
        total += int(cm.group(1)) if cm else 1
    return total


def validate_table(html: str, table_index: int = 0) -> ValidationResult:
    """校验单张表格的结构一致性。

    Args:
        html: 完整的 <table>...</table> HTML。
        table_index: 表格编号，用于标记。

    Returns:
        ValidationResult 含校验结果和问题列表。
    """
    issues: list[dict[str, Any]] = []
    col_counts: list[int] = []

    # 提取所有行
    row_pattern = re.compile(r"<tr>(.*?)</tr>", re.DOTALL)
    rows = row_pattern.findall(html)
    row_count = len(rows)

    if row_count == 0:
        return ValidationResult(
            table_index=table_index,
            is_valid=False,
            row_count=0,
            col_count=0,
            issues=[{"type": "empty_table", "severity": "error",
                     "detail": "表格为空，无任何行", "row": None}],
            borderless_risk="unknown",
        )

    for ri, tr_html in enumerate(rows):
        ncols = _count_cells_in_row(tr_html)
        col_counts.append(ncols)

    # 多数派的列数
    from collections import Counter
    col_freq = Counter(col_counts)
    majority_cols = col_freq.most_common(1)[0][0]

    # 检测结构问题
    # 1. 列数不一致
    mismatched_rows = [i for i, c in enumerate(col_counts) if c != majority_cols]
    if mismatched_rows:
        # 排除 section header 行（如 <td colspan="N">流动资产：</td>）
        real_mismatches = []
        for ri in mismatched_rows:
            tr_html = rows[ri]
            td_count = len(re.findall(r"<td[^>]*>", tr_html))
            if td_count == 1 and "colspan" in tr_html:
                continue  # section header，不算错
            real_mismatches.append(ri)

        if real_mismatches:
            issues.append({
                "type": "column_mismatch",
                "severity": "warning",
                "detail": f"行 {real_mismatches[:5]} 列数与大多数行 ({majority_cols}) 不一致",
                "row": real_mismatches[0] if len(real_mismatches) == 1 else None,
            })

    # 2. 空列检测：排除备注栏后，某列 ≥80% 为空 → 可能是无边框表列错位
    if row_count > 3 and majority_cols >= 3:
        # 先识别备注列（表头含"备注/注释/附注"）
        note_columns: set[int] = set()
        thead_match = re.search(r"<thead>(.*?)</thead>", html, re.DOTALL)
        if thead_match:
            col_idx = 0
            for m in re.finditer(r"<th([^>]*)>(.*?)</th>", thead_match.group(1), re.DOTALL):
                header_text = re.sub(r"<[^>]+>", "", m.group(2)).strip()
                attrs = m.group(1)
                cm = re.search(r'colspan\s*=\s*"(\d+)"', attrs)
                span = int(cm.group(1)) if cm else 1
                if any(kw in header_text for kw in ["备注", "注释", "附注", "注"]):
                    for c in range(span):
                        note_columns.add(col_idx + c)
                col_idx += span

        col_empty: dict[int, int] = {}
        col_total: dict[int, int] = {}
        for tr_html in rows:
            col_idx = 0
            for m in re.finditer(r"<(td|th)([^>]*)>(.*?)</\1>", tr_html, re.DOTALL):
                content = m.group(3).strip()
                attrs = m.group(2)
                cm = re.search(r'colspan\s*=\s*"(\d+)"', attrs)
                span = int(cm.group(1)) if cm else 1
                for c in range(span):
                    col = col_idx + c
                    if col not in note_columns:
                        col_total[col] = col_total.get(col, 0) + 1
                        if not content:
                            col_empty[col] = col_empty.get(col, 0) + 1
                col_idx += span

        empty_cols = [c for c in col_total
                      if col_total[c] >= 3 and col_empty.get(c, 0) / col_total[c] >= 0.8]
        if empty_cols:
            issues.append({
                "type": "empty_columns",
                "severity": "warning",
                "detail": f"列 {empty_cols[:3]} (不含备注列) 空值率 ≥80%，可能是无边框表导致数据错位",
                "row": None,
            })

    # 3. 判断无边框风险等级
    borderless_risk = "low"
    if any(i["type"] == "column_mismatch" for i in issues):
        borderless_risk = "medium"
    if any(i["type"] == "empty_columns" for i in issues):
        borderless_risk = "high"
    if len(issues) >= 2:
        borderless_risk = "high"

    return ValidationResult(
        table_index=table_index,
        is_valid=len(issues) == 0,
        row_count=row_count,
        col_count=majority_cols,
        col_counts_per_row=col_counts,
        issues=issues,
        borderless_risk=borderless_risk,
    )


# ---------------------------------------------------------------------------
# 批量校验入口
# ---------------------------------------------------------------------------

TABLE_RE = re.compile(r"<table>(.*?)</table>", re.DOTALL)


def validate_all_tables(markdown: str) -> dict[str, Any]:
    """校验 markdown 中所有表格的结构。

    Returns:
        {
            "total_tables": int,
            "valid_tables": int,
            "results": [ValidationResult.to_dict(), ...],
            "summary": {
                "borderless_high_risk": int,
                "borderless_medium_risk": int,
                "borderless_low_risk": int,
            }
        }
    """
    tables = TABLE_RE.findall(markdown)
    results: list[dict[str, Any]] = []

    for ti, html in enumerate(tables):
        vr = validate_table(f"<table>{html}</table>", ti)
        results.append(vr.to_dict())

    valid = sum(1 for r in results if r["is_valid"])
    high = sum(1 for r in results if r["borderless_risk"] == "high")
    medium = sum(1 for r in results if r["borderless_risk"] == "medium")
    low = sum(1 for r in results if r["borderless_risk"] == "low")

    return {
        "total_tables": len(tables),
        "valid_tables": valid,
        "results": results,
        "summary": {
            "borderless_high_risk": high,
            "borderless_medium_risk": medium,
            "borderless_low_risk": low,
        },
    }
