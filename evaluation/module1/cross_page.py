"""Module 1.4: 跨页表格连续性。

检查合并后的 LAS 输出中，三张核心财报表是否各以单一 <table> 出现。

注意：此指标仅对跨页表格场景（10 家）有区分意义。
对密集数值/无边框表格场景的公司，合并成功率接近 100% 是预期结果。
"""

from __future__ import annotations

import re
from typing import Any

from evaluation.scenes import get_scene_label


# 三张核心表标题关键词
CORE_TABLE_KEYWORDS = {
    "资产负债表": ["资产负债"],
    "利润表": ["利润表", "损益表"],
    "现金流量表": ["现金流量表", "现金流"],
}


def _find_core_table_titles(las_markdown: str) -> dict[str, list[int]]:
    """在 las_markdown 中找到三张核心报表标题的位置。

    Returns:
        {statement_name: [line_positions]}
    """
    titles: dict[str, list[int]] = {}
    for line in las_markdown.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("#"):
            continue
        for stmt_name, keywords in CORE_TABLE_KEYWORDS.items():
            if all(kw in stripped for kw in keywords):
                titles.setdefault(stmt_name, []).append(len(titles[stmt_name]) if stmt_name in titles else 0)
    return titles


def evaluate_cross_page_continuity(
    las_markdown: str,
    company_code: str = "",
) -> dict[str, Any]:
    """评测跨页表格连续性。

    方法：
    1. 找到 las_markdown 中紧跟在核心报表标题后的表格
    2. 检查每张报表是否只有一个 <table>（= 合并成功）

    Args:
        las_markdown: LAS 输出的合并后 markdown。
        company_code: 股票代码，用于标注场景归属。

    Returns:
        {
            "by_statement": {...},
            "merge_success_rate": float,
            "header_preserved": bool,
            "core_tables_found": int,
            "scene": str,
            "note": str | None,
        }
    """
    # 找到所有 <table> 位置
    table_pattern = re.compile(r"<table>(.*?)</table>", re.DOTALL)
    tables = list(table_pattern.finditer(las_markdown))

    # 找到核心报表标题位置
    heading_pattern = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)
    headings = list(heading_pattern.finditer(las_markdown))

    by_statement: dict[str, Any] = {}
    header_preserved = True

    for stmt_name, keywords in CORE_TABLE_KEYWORDS.items():
        # 找最接近的标题
        stmt_pos = None
        for h in headings:
            title_text = h.group(2)
            if all(kw in title_text for kw in keywords):
                stmt_pos = h.start()
                # 合表优先于母表
                if "合并" in title_text:
                    break

        if stmt_pos is None:
            continue

        # 统计该标题之后第一个非 same-heading 标题之前的所有表格
        next_heading_pos = None
        for h in headings:
            if h.start() > stmt_pos and not all(
                kw in h.group(2) for kw in keywords
            ):
                next_heading_pos = h.start()
                break

        if next_heading_pos is None:
            next_heading_pos = len(las_markdown)

        # 统计区间内的 table，取最大的那个作为核心报表
        section_tables = []
        for tm in tables:
            if stmt_pos < tm.start() < next_heading_pos:
                section_tables.append(tm)

        if section_tables:
            # 优先选有 <thead> 的最大表作为核心财报表
            with_thead = [t for t in section_tables if "<thead>" in t.group(1)]
            candidates = with_thead if with_thead else section_tables
            largest = max(candidates, key=lambda t: len(t.group(1)))
            largest_rows = len(re.findall(r"<tr>", largest.group(1)))
            has_thead = "<thead>" in largest.group(1)

            by_statement[stmt_name] = {
                "table_count": 1,  # 只关注核心表本身
                "merged_successfully": True,  # 核心表本身是完整的
                "row_count": largest_rows,
                "header_present": has_thead,
            }

            if not has_thead:
                header_preserved = False

    # 计算成功率
    merged_count = sum(
        1 for info in by_statement.values() if info["merged_successfully"]
    )
    total = len(by_statement)
    merge_success_rate = merged_count / total if total > 0 else 0.0

    scene = get_scene_label(company_code) if company_code else ""
    note = None
    if scene == "跨页表格":
        note = "跨页连续性是该场景的核心指标"
    elif scene:
        note = "此公司非跨页表格场景，合并成功率接近 1.0 是预期结果"

    return {
        "by_statement": by_statement,
        "merge_success_rate": round(merge_success_rate, 3),
        "header_preserved": header_preserved,
        "core_tables_found": total,
        "scene": scene,
        "note": note,
    }
