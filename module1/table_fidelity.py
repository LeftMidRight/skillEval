"""子指标 2：表格还原度（TEDS + Cell F1）。

TEDS: Tree Edit Distance based on Structure
Cell F1: Cell-level Precision / Recall / F1

参照系：XBRL markdown 表格（来自 FinAR-Bench dev.txt / test.txt）。
"""

from __future__ import annotations

import math
import re
from difflib import SequenceMatcher
from typing import Any

from module1.utils import (
    TableCell,
    TableTree,
    extract_all_tables,
    fuzzy_match_row,
    parse_html_tables,
    parse_xbrl_tables,
    table_tree_to_dict_list,
)

# ---------------------------------------------------------------------------
# 行名映射表
# ---------------------------------------------------------------------------

ROW_NAME_ALIASES: dict[str, list[str]] = {
    "营业收入": ["营业总收入", "营业收入"],
    "营业总收入": ["营业总收入", "营业收入"],
    "应收帐款": ["应收帐款", "应收账款", "应收款项"],
    "应收账款": ["应收帐款", "应收账款", "应收款项"],
    "应付帐款": ["应付帐款", "应付账款", "应付款项"],
    "应付账款": ["应付帐款", "应付账款", "应付款项"],
    "固定资产净额": ["固定资产净额", "固定资产", "固定资产净值"],
    "固定资产": ["固定资产净额", "固定资产", "固定资产净值"],
    "经营活动现金流量净额": ["经营活动现金流量净额", "经营活动产生的现金流量净额"],
    "经营活动产生的现金流量净额": ["经营活动现金流量净额", "经营活动产生的现金流量净额"],
    "投资活动现金流量净额": ["投资活动产生的现金流量净额", "投资活动现金流量净额"],
    "投资活动产生的现金流量净额": ["投资活动产生的现金流量净额", "投资活动现金流量净额"],
    "筹资活动现金流量净额": ["筹资活动产生的现金流量净额", "筹资活动现金流量净额"],
    "筹资活动产生的现金流量净额": ["筹资活动产生的现金流量净额", "筹资活动现金流量净额"],
    "归属于母公司所有者的净利润": ["归属于母公司所有者的净利润", "归属于母公司股东的净利润"],
    "股东权益合计": ["股东权益合计", "所有者权益合计", "所有者权益（或股东权益）合计"],
    "所有者权益合计": ["股东权益合计", "所有者权益合计", "所有者权益（或股东权益）合计"],
    "利润总额": ["利润总额"],
    "净利润": ["净利润"],
    "负债合计": ["负债合计"],
    "资产总计": ["资产总计"],
    "无形资产": ["无形资产"],
    "商誉": ["商誉"],
    "在建工程": ["在建工程"],
    "短期借款": ["短期借款"],
    "长期借款": ["长期借款"],
    "应付债券": ["应付债券"],
    "货币资金": ["货币资金"],
    "存货": ["存货"],
    "流动资产合计": ["流动资产合计"],
    "非流动资产合计": ["非流动资产合计"],
    "流动负债合计": ["流动负债合计"],
    "营业总成本": ["营业总成本"],
    "营业成本": ["营业成本"],
    "销售费用": ["销售费用"],
    "管理费用": ["管理费用"],
    "财务费用": ["财务费用"],
    "营业利润": ["营业利润"],
    "经营活动现金流量净额": ["经营活动现金流量净额"],
    "投资活动产生的现金流量净额": ["投资活动产生的现金流量净额"],
    "筹资活动产生的现金流量净额": ["筹资活动产生的现金流量净额"],
    "归属于母公司所有者权益合计": ["归属于母公司所有者权益合计"],
    "应收帐款": ["应收帐款", "应收账款"],
    "应付帐款": ["应付帐款", "应付账款"],
}

# 空值标记（不参与数值比较）
_EMPTY_VALS = {"", "-", "—", "——", "–", "0.00", "0.0", "0"}


def _expand_aliases(name: str) -> set[str]:
    aliases = {name}
    for key, values in ROW_NAME_ALIASES.items():
        if name in values:
            aliases.update(values)
    return aliases


def _match_row_name(
    target: str, candidates: list[str], threshold: float = 0.70
) -> tuple[int, float] | None:
    # 1. 别名精确匹配
    target_aliases = _expand_aliases(target)
    for i, cand in enumerate(candidates):
        cand_aliases = _expand_aliases(cand)
        if target_aliases & cand_aliases:
            return (i, 1.0)

    # 2. 模糊匹配
    return fuzzy_match_row(target, candidates, threshold)


# ---------------------------------------------------------------------------
# 数值处理
# ---------------------------------------------------------------------------

def _clean_number_for_comparison(raw: str) -> str:
    s = raw.replace(",", "").replace(" ", "")
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        val = float(s)
        return f"{val:.2f}"
    except ValueError:
        return s


def _is_empty_value(val: str) -> bool:
    return val.strip() in _EMPTY_VALS


# content_similarity 用于 TEDS 中判断两个 cell 内容是否匹配
def _content_similarity(c1: str, c2: str) -> float:
    """0-1 相似度，用于 TEDS 中的 cell 替换成本。"""
    c1 = c1.replace(",", "").replace(" ", "")
    c2 = c2.replace(",", "").replace(" ", "")
    if c1 == c2:
        return 1.0
    # 数值近似匹配
    try:
        v1 = float(c1)
        v2 = float(c2)
        if v2 == 0:
            return 1.0 if abs(v1) < 1e-6 else 0.0
        rel_err = abs(v1 - v2) / abs(v2)
        if rel_err < 0.001:
            return 1.0
        return max(0.0, 1.0 - rel_err * 10)
    except ValueError:
        return SequenceMatcher(None, c1, c2).ratio()


# ---------------------------------------------------------------------------
# TEDS 计算
# ---------------------------------------------------------------------------

def compute_teds(
    tree1: TableTree,
    tree2: TableTree,
) -> dict:
    """计算两个表格树之间的 TEDS。

    TEDS = 1 - EditDist / max(|T1|, |T2|)

    编辑操作：
    - Insert/Delete row: cost = 该行的 cell 数
    - Insert/Delete cell（对齐行内）: cost = 1
    - Substitute cell: cost = 1 - content_similarity

    先按第一列对齐行，再在每行内对齐列。

    Returns:
        {"teds": float, "edit_distance": float, "max_nodes": int, ...}
    """
    if not tree1.rows and not tree2.rows:
        return {"teds": 1.0, "edit_distance": 0, "max_nodes": 0,
                "aligned_rows": 0, "insertions": 0, "deletions": 0, "substitutions": 0}

    max_nodes = max(tree1.node_count, tree2.node_count)
    if max_nodes == 0:
        return {"teds": 1.0, "edit_distance": 0, "max_nodes": 0,
                "aligned_rows": 0, "insertions": 0, "deletions": 0, "substitutions": 0}

    # 行对齐
    items1 = tree1.get_item_names()
    items2 = tree2.get_item_names()

    # 贪心行匹配
    matched_pairs: list[tuple[int, int, float]] = []  # (idx1, idx2, similarity)
    used2: set[int] = set()

    for i1, name1 in enumerate(items1):
        result = _match_row_name(name1, items2, threshold=0.55)
        if result is not None:
            i2, sim = result
            if i2 not in used2:
                matched_pairs.append((i1, i2, sim))
                used2.add(i2)

    edit_distance = 0.0
    deletions = 0
    insertions = 0
    substitutions = 0.0

    # 未匹配的 T1 行 = 删除了
    matched_t1 = {p[0] for p in matched_pairs}
    for i1 in range(len(tree1.rows)):
        if i1 not in matched_t1:
            # 只计有内容的行
            row_cells = sum(
                c.colspan * c.rowspan
                for c in tree1.rows[i1]
                if not _is_empty_value(c.content)
            )
            edit_distance += row_cells
            deletions += 1

    # 未匹配的 T2 行 = LAS 多出的行，XBRL 里没有 → 不扣分
    # （XBRL 是 gold standard，只测 XBRL 里有的项目 LAS 是否对）

    # 对已匹配的行对，做列级对齐 + 内容比较
    for i1, i2, _ in matched_pairs:
        row1 = tree1.rows[i1]
        row2 = tree2.rows[i2]

        # 展开 colspan → 逻辑单元格序列
        cells1: list[tuple[str, int, int]] = []  # (content, colspan, rowspan)
        cells2: list[tuple[str, int, int]] = []

        for c in row1:
            for _ in range(c.colspan):
                cells1.append((c.content, c.colspan, c.rowspan))
        for c in row2:
            for _ in range(c.colspan):
                cells2.append((c.content, c.colspan, c.rowspan))

        # 对逻辑单元格序列做编辑距离
        n1, n2 = len(cells1), len(cells2)
        dp = [[0.0] * (n2 + 1) for _ in range(n1 + 1)]
        for i in range(n1 + 1):
            dp[i][0] = float(i)
        for j in range(n2 + 1):
            dp[0][j] = float(j)

        for i in range(1, n1 + 1):
            for j in range(1, n2 + 1):
                content1, _, _ = cells1[i - 1]
                content2, _, _ = cells2[j - 1]

                # 跳过空值比较
                both_empty = _is_empty_value(content1) and _is_empty_value(content2)
                if both_empty:
                    dp[i][j] = dp[i - 1][j - 1]  # 空值匹配无成本
                else:
                    sim = _content_similarity(content1, content2)
                    sub_cost = (1.0 - sim)  # content match → cost 0; mismatch → cost 1
                    dp[i][j] = min(
                        dp[i - 1][j] + 1,       # delete
                        dp[i][j - 1] + 1,       # insert
                        dp[i - 1][j - 1] + sub_cost,  # substitute
                    )

        edit_distance += dp[n1][n2]
        substitutions += dp[n1][n2]

    teds = max(0.0, 1.0 - edit_distance / max_nodes)

    return {
        "teds": round(teds, 4),
        "edit_distance": round(edit_distance, 2),
        "max_nodes": max_nodes,
        "aligned_rows": len(matched_pairs),
        "insertions": insertions,
        "deletions": deletions,
        "substitutions": round(substitutions, 2),
    }


# ---------------------------------------------------------------------------
# Cell F1 计算
# ---------------------------------------------------------------------------

def _get_numeric_cells_from_tree(tree: TableTree) -> list[str]:
    """从 TableTree 中提取所有非空数值单元格。"""
    vals: list[str] = []
    for row in tree.rows:
        for cell in row:
            content = cell.content.strip()
            if content and not _is_empty_value(content):
                vals.append(content)
    return vals


def _get_numeric_columns_from_dict_list(rows: list[dict[str, str]]) -> list[str]:
    if not rows:
        return []
    cols = list(rows[0].keys())
    numeric_cols = [c for c in cols if any(ch.isdigit() for ch in c)]
    if not numeric_cols and len(cols) > 1:
        numeric_cols = cols[1:]
    return numeric_cols


def _get_item_names_from_dict_list(rows: list[dict[str, str]]) -> list[str]:
    if not rows:
        return []
    first_col = list(rows[0].keys())[0]
    return [row.get(first_col, "") for row in rows]


def _get_row_values_from_dict(row: dict[str, str], cols: list[str]) -> list[str]:
    vals = []
    for col in cols:
        val = row.get(col, "").strip()
        if val and val != "-" and val != "—":
            vals.append(val)
    return vals


def _count_numeric_cells_in_dict_list(rows: list[dict[str, str]]) -> int:
    cols = _get_numeric_columns_from_dict_list(rows)
    count = 0
    for row in rows:
        count += len(_get_row_values_from_dict(row, cols))
    return count


def compute_cell_f1(
    las_tables: list[tuple[str, list[dict[str, str]], TableTree | None]],
    xbrl_tables: dict[str, list[dict[str, str]]],
) -> dict:
    """计算 Cell-level F1（XBRL 为 gold standard）。

    Precision 按 XBRL 项目数计算，不惩罚 LAS 多提取的内容。
    XBRL 中的每一项如果在 LAS 中找到且数值正确 → TP，否则 → FN。
    """
    all_tp = 0
    all_fn = 0
    all_xbrl_cells = 0
    by_statement: dict[str, dict] = {}

    for xbrl_name, xbrl_rows in xbrl_tables.items():
        las_table, las_tree = _find_matching_las_table(las_tables, xbrl_name)

        xbrl_cols = _get_numeric_columns_from_dict_list(xbrl_rows)
        xbrl_items = _get_item_names_from_dict_list(xbrl_rows)

        tp = 0
        fn = 0
        total_xbrl = 0

        if las_tree is not None:
            las_items = las_tree.get_item_names()
            matched_las: set[int] = set()

            for xbrl_idx, xbrl_row in enumerate(xbrl_rows):
                xbrl_item = xbrl_items[xbrl_idx] if xbrl_idx < len(xbrl_items) else ""
                if not xbrl_item:
                    continue
                xbrl_vals = _get_row_values_from_dict(xbrl_row, xbrl_cols)
                if not xbrl_vals:
                    continue
                total_xbrl += len(xbrl_vals)

                result = _match_row_name(xbrl_item, las_items, threshold=0.55)
                if result is None:
                    # 尝试纯数值匹配
                    found = False
                    for las_idx, las_row in enumerate(las_tree.rows):
                        if las_idx in matched_las:
                            continue
                        las_vals = [c.content for c in las_row if c.content.strip() and not _is_empty_value(c.content)]
                        if _values_sets_match(xbrl_vals, las_vals):
                            tp += len(xbrl_vals)
                            matched_las.add(las_idx)
                            found = True
                            break
                    if not found:
                        fn += len(xbrl_vals)
                else:
                    las_idx, _ = result
                    las_row = las_tree.rows[las_idx]
                    las_vals = [c.content for c in las_row if c.content.strip() and not _is_empty_value(c.content)]

                    matched_count = 0
                    for xv in xbrl_vals:
                        for lv in las_vals:
                            if _content_similarity(xv, lv) >= 0.999:
                                matched_count += 1
                                break
                    tp += matched_count
                    fn += len(xbrl_vals) - matched_count
                    matched_las.add(las_idx)

        elif las_table is not None:
            las_items = _get_item_names_from_dict_list(las_table)
            las_cols = _get_numeric_columns_from_dict_list(las_table)
            matched_las: set[int] = set()

            for xbrl_idx, xbrl_row in enumerate(xbrl_rows):
                xbrl_item = xbrl_items[xbrl_idx] if xbrl_idx < len(xbrl_items) else ""
                if not xbrl_item:
                    continue
                xbrl_vals = _get_row_values_from_dict(xbrl_row, xbrl_cols)
                if not xbrl_vals:
                    continue
                total_xbrl += len(xbrl_vals)

                result = _match_row_name(xbrl_item, las_items, threshold=0.55)
                if result is None:
                    found = False
                    for las_idx, las_row in enumerate(las_table):
                        if las_idx in matched_las:
                            continue
                        las_vals = _get_row_values_from_dict(las_row, las_cols)
                        if _values_sets_match(xbrl_vals, las_vals):
                            tp += len(xbrl_vals)
                            matched_las.add(las_idx)
                            found = True
                            break
                    if not found:
                        fn += len(xbrl_vals)
                else:
                    las_idx, _ = result
                    las_row = las_table[las_idx]
                    las_vals = _get_row_values_from_dict(las_row, las_cols)
                    matched_count = 0
                    for xv in xbrl_vals:
                        for lv in las_vals:
                            if _content_similarity(xv, lv) >= 0.999:
                                matched_count += 1
                                break
                    tp += matched_count
                    fn += len(xbrl_vals) - matched_count
                    matched_las.add(las_idx)
        else:
            # 完全没找到对应表
            for xbrl_row in xbrl_rows:
                xbrl_vals = _get_row_values_from_dict(xbrl_row, xbrl_cols)
                if xbrl_vals:
                    fn += len(xbrl_vals)
                    total_xbrl += len(xbrl_vals)

        # Precision = TP / XBRL_total (不惩罚 LAS 多出的)
        precision = tp / total_xbrl if total_xbrl > 0 else 0.0
        recall = tp / total_xbrl if total_xbrl > 0 else 0.0  # 在此策略下 P = R
        f1 = tp / total_xbrl if total_xbrl > 0 else 0.0

        by_statement[xbrl_name] = {
            "tp": tp, "fn": fn, "xbrl_cells": total_xbrl,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
        }
        all_tp += tp
        all_fn += fn
        all_xbrl_cells += total_xbrl

    overall = all_tp / all_xbrl_cells if all_xbrl_cells > 0 else 0.0

    return {
        "overall": {
            "precision": round(overall, 4),
            "recall": round(overall, 4),
            "f1": round(overall, 4),
            "tp": all_tp, "fn": all_fn,
            "xbrl_total": all_xbrl_cells,
        },
        "by_statement": by_statement,
    }


def _find_matching_las_table(
    las_tables: list[tuple[str, list[dict[str, str]], TableTree | None]],
    xbrl_name: str,
) -> tuple[list[dict[str, str]] | None, TableTree | None]:
    """在 LAS 表格列表中查找匹配 XBRL 表名的表格。

    支持模糊匹配（合并/母公司/无前缀），fallback 到大小匹配。
    """
    keywords = {
        "利润表": ["利润表", "损益表", "合并利润表", "母公司利润表"],
        "资产负债表": ["资产负债表", "合并资产负债表", "母公司资产负债表"],
        "现金流量表": ["现金流量表", "现金流", "合并现金流量表", "母公司现金流量表"],
    }
    kw_list = keywords.get(xbrl_name, [xbrl_name])

    # 1. 精确关键词匹配
    for title, table, tree in las_tables:
        for kw in kw_list:
            if kw in title:
                return (table, tree)

    # 2. 模糊匹配：利润表→利润, 资产负债表→资产, 现金流→现金
    fuzzy_map = {
        "利润表": ["利润"],
        "资产负债表": ["资产负债", "资产"],
        "现金流量表": ["现金流量", "现金"],
    }
    fuzzy_kw = fuzzy_map.get(xbrl_name, [])
    for title, table, tree in las_tables:
        for kw in fuzzy_kw:
            if kw in title:
                return (table, tree)

    # 3. Fallback: 按行数匹配（大表优先）
    candidates = [
        (title, table, tree)
        for title, table, tree in las_tables
        if (tree is not None and tree.row_count > 8) or (table is not None and len(table) > 8)
    ]
    if candidates:
        # 选行数最多的
        best = max(candidates, key=lambda x: (x[2].row_count if x[2] else len(x[1])))
        return (best[1], best[2])

    return (None, None)


# ──────────────────────────────────────────────────────────────
# 辅助函数
# ──────────────────────────────────────────────────────────────

def _values_sets_match(vals1: list[str], vals2: list[str]) -> bool:
    if not vals1 or not vals2:
        return False
    c1 = [_clean_number_for_comparison(v) for v in vals1]
    c2 = [_clean_number_for_comparison(v) for v in vals2]
    return sorted(c1) == sorted(c2)


# ---------------------------------------------------------------------------
# 一站式评测
# ---------------------------------------------------------------------------

def evaluate_table_fidelity(
    las_text: str,
    xbrl_record: dict[str, Any],
) -> dict:
    """评估 LAS 表格还原度（TEDS + Cell F1）。

    Args:
        las_text: LAS 输出的完整文本（HTML + markdown）
        xbrl_record: FinAR-Bench 的一条记录（含 XBRL table）

    Returns:
        {
            "overall": {cell_f1, teds_scores, ...},
            "by_statement": {...},
        }
    """
    xbrl_tables = parse_xbrl_tables(xbrl_record["table"])
    las_raw = extract_all_tables(las_text)

    # 按 XBRL 表名匹配对应的 LAS 表
    teds_results: dict[str, dict] = {}

    for xbrl_name, xbrl_rows in xbrl_tables.items():
        _, las_tree = _find_matching_las_table(las_raw, xbrl_name)

        if las_tree is not None:
            # 构建 XBRL 的 TableTree 用于 TEDS
            xbrl_tree = _dict_list_to_tree(xbrl_rows)
            teds_results[xbrl_name] = compute_teds(las_tree, xbrl_tree)
        else:
            teds_results[xbrl_name] = {"teds": 0.0, "edit_distance": 1.0, "max_nodes": 1,
                                          "aligned_rows": 0, "insertions": 0, "deletions": 0,
                                          "substitutions": 0, "error": "no_matching_las_table"}

    # Cell F1（使用统一接口）
    cell_f1_result = compute_cell_f1(las_raw, xbrl_tables)

    # 汇总 TEDS 全局分
    all_edit = sum(r.get("edit_distance", 0) for r in teds_results.values())
    all_max = sum(r.get("max_nodes", 0) for r in teds_results.values())
    overall_teds = max(0.0, 1.0 - all_edit / all_max) if all_max > 0 else 0.0

    cell_f1_result["teds"] = {
        "overall": round(overall_teds, 4),
        "by_statement": teds_results,
    }

    return cell_f1_result


def _dict_list_to_tree(rows: list[dict[str, str]]) -> TableTree:
    """将 XBRL dict_list 转为 TableTree（用于 TEDS 跨格式对比）。"""
    if not rows:
        return TableTree()

    tree_rows: list[list[TableCell]] = []
    headers = list(rows[0].keys())
    # Header row
    tree_rows.append([TableCell(content=h, colspan=1, rowspan=1, tag="th") for h in headers])

    for row in rows:
        tree_cells = [TableCell(content=row.get(h, ""), colspan=1, rowspan=1, tag="td") for h in headers]
        tree_rows.append(tree_cells)

    return TableTree(tree_rows)
