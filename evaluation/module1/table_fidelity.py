"""Module 1.2: 表格还原度。

双参照系：
- XBRL: Item Recall（关键科目覆盖）
- Mineru: TEDS + Cell F1（完整结构对比）
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from module1.utils import (
    TableTree,
    _TableHTMLParser,
    extract_numbers,
    fuzzy_match_row,
    fuzzy_similarity,
    load_reference_text,
    normalize_number,
    parse_html_tables,
    parse_xbrl_tables,
)

# 三张核心财报表标题关键词
STATEMENT_KEYWORDS = {
    "balance_sheet": ["资产负债", "负债表"],
    "income_stmt": ["利润表", "损益表"],
    "cash_flow": ["现金流量表", "现金流"],
}

# 行匹配常用别名
ROW_ALIASES = {
    "应收账款": ["应收帐款", "应收款项"],
    "应付账款": ["应付帐款", "应付款项"],
    "营业收入": ["营业总收入", "营业总营收"],
    "营业成本": ["营业总成本"],
    "归母净利润": ["归属于母公司所有者的净利润", "归属于母公司股东的净利润"],
}


def _normalize_item_name(name: str) -> str:
    """标准化科目名。"""
    name = re.sub(r"[（(].*?[)）]", "", name)  # 去括号注释
    name = re.sub(r"\s+", "", name)
    return name.strip()


def _expand_aliases(item_name: str) -> list[str]:
    """展开别名，用于宽松匹配。"""
    name = _normalize_item_name(item_name)
    candidates = [name]
    for key, aliases in ROW_ALIASES.items():
        if key in name or any(a in name for a in aliases):
            candidates.extend(aliases)
    return candidates


# ---------------------------------------------------------------------------
# XBRL Item Recall
# ---------------------------------------------------------------------------


def compute_xbrl_item_recall(
    las_markdown: str,
    xbrl_record: dict[str, Any],
) -> dict[str, Any]:
    """计算 XBRL 关键科目在 LAS 输出中的召回率。

    方法：从 XBRL 中提取所有数值 → 检查每个值是否在 LAS 表格中出现。
    不做科目名匹配，直接做数值匹配（XBRL 和 LAS 数字一致 = 找到）。
    """
    xbrl_tables = parse_xbrl_tables(xbrl_record.get("table", ""))

    # 从 LAS 表格提取所有标准化数值（直接内联，避免导入私有变量）
    _td_re = re.compile(r"<td[^>]*>([^<]*)</td>", re.DOTALL)
    las_numbers: set[str] = set()
    for td_match in _td_re.finditer(las_markdown):
        text = td_match.group(1).strip()
        if text:
            for num in extract_numbers(text):
                norm = normalize_number(num)
                if norm and norm != num:
                    las_numbers.add(norm)

    by_statement: dict[str, Any] = {}
    total_found = 0
    total_xbrl = 0

    for stmt_name, xbrl_rows in xbrl_tables.items():
        found = 0
        total = 0
        missing: list[str] = []

        for row in xbrl_rows:
            # XBRL 行格式: {"项目": "货币资金", "2023": "1,234.56", "2022": "..."}
            item = row.get("项目", "") or (list(row.values())[0] if row else "")
            for key, val in row.items():
                if key == "项目" or not val.strip():
                    continue
                total += 1
                norm = normalize_number(val)
                # 零值匹配：XBRL 的 0.00 在 LAS 中对应空单元格 → 视为找到
                is_zero = norm == "0.00"
                if norm in las_numbers:
                    found += 1
                elif is_zero:
                    found += 1  # XBRL 的 0.00，LAS 空单元格 = 等价
                else:
                    if len(missing) < 10:
                        missing.append(f"{item}:{key}={val}")

        recall = found / total if total > 0 else 1.0
        by_statement[stmt_name] = {
            "recall": round(recall, 3),
            "found": found,
            "total": total,
            "missing": missing,
        }
        total_found += found
        total_xbrl += total

    overall = total_found / total_xbrl if total_xbrl > 0 else 1.0
    return {
        "by_statement": by_statement,
        "overall_recall": round(overall, 3),
    }


# ---------------------------------------------------------------------------
# Mineru TEDS + Cell F1
# ---------------------------------------------------------------------------

_MINERU_TABLE_RE = re.compile(
    r"<html><body><table>(.*?)</table></body></html>", re.DOTALL
)


def _extract_mineru_tables(mineru_text: str) -> list[TableTree]:
    """从 Mineru 输出中提取 HTML 表格。"""
    tables: list[TableTree] = []
    parser = _TableHTMLParser()

    for match in _MINERU_TABLE_RE.finditer(mineru_text):
        html = f"<table>{match.group(1)}</table>"
        parser.feed(html)

    parser.close()
    tables = parser.trees

    # 过滤：至少 2 行 2 列
    return [t for t in tables if t.row_count >= 2 and t.get_logical_width() >= 2]


def _classify_table_by_context(
    tree_index: int,
    table_positions: list[int],
    full_text: str,
) -> str | None:
    """根据表格前的文本判断表类型。搜索表格前的 markdown 标题或明文表名。"""
    pos = table_positions[tree_index] if tree_index < len(table_positions) else 0
    preceding = full_text[max(0, pos - 800):pos]  # 取表格前 800 字符

    # 先尝试 markdown 标题
    headings = list(re.finditer(r"^(#{1,3})\s+(.+)$", preceding, re.MULTILINE))
    search_text = headings[-1].group(2) if headings else preceding

    for stmt_type, keywords in STATEMENT_KEYWORDS.items():
        if all(kw in search_text for kw in keywords):
            return stmt_type
    return None


def _match_tables(
    las_trees: list[TableTree],
    las_markdown: str,
    mineru_trees: list[TableTree],
    mineru_text: str,
) -> list[tuple[TableTree, TableTree, str]]:
    """按表类型匹配 LAS 和 Mineru 的表格。"""
    # 找到每个表格在全文中的位置
    las_positions = [m.start() for m in re.finditer(r"<table>", las_markdown)]
    mineru_positions = [m.start() for m in re.finditer(r"<table>", mineru_text)]

    # 按表类型分组
    las_by_type: dict[str, list[tuple[int, TableTree]]] = {}
    mineru_by_type: dict[str, list[tuple[int, TableTree]]] = {}

    for i, tree in enumerate(las_trees):
        st = _classify_table_by_context(i, las_positions, las_markdown)
        if st:
            las_by_type.setdefault(st, []).append((i, tree))

    for i, tree in enumerate(mineru_trees):
        st = _classify_table_by_context(i, mineru_positions, mineru_text)
        if st:
            mineru_by_type.setdefault(st, []).append((i, tree))

    matches: list[tuple[TableTree, TableTree, str]] = []
    for st in ["balance_sheet", "income_stmt", "cash_flow"]:
        las_list = las_by_type.get(st, [])
        mineru_list = mineru_by_type.get(st, [])

        for _li, lt in las_list:
            best_mt = None
            best_score = 0
            for _mi, mt in mineru_list:
                # 表头相似度 + 行数接近度
                lt_header = " ".join(
                    c.content for c in lt.rows[0][:min(4, len(lt.rows[0]))]
                ) if lt.rows else ""
                mt_header = " ".join(
                    c.content for c in mt.rows[0][:min(4, len(mt.rows[0]))]
                ) if mt.rows else ""
                header_sim = fuzzy_similarity(lt_header, mt_header)
                row_ratio = min(lt.row_count, mt.row_count) / max(lt.row_count, mt.row_count, 1)
                score = header_sim * 0.4 + row_ratio * 0.6
                if score > best_score:
                    best_score = score
                    best_mt = mt
            if best_mt and best_score > 0.3:
                matches.append((lt, best_mt, st))

    return matches


def _compute_teds(tree_a: TableTree, tree_b: TableTree) -> float:
    """计算简化 TEDS：以行匹配为基础的结构编辑距离。

    将两个树展开为逻辑单元格矩阵后比较。
    """
    width_a = tree_a.get_logical_width()
    width_b = tree_b.get_logical_width()

    # 取较大宽度对齐
    width = max(width_a, width_b)
    rows_a = tree_a.row_count
    rows_b = tree_b.row_count

    # 对每行做行匹配
    item_names_a = tree_a.get_item_names()
    item_names_b = tree_b.get_item_names()

    matched_rows = 0
    cell_mismatches = 0
    total_cells = 0

    for ia, name_a in enumerate(item_names_a):
        match = fuzzy_match_row(name_a, item_names_b, threshold=0.55)
        if match is not None:
            matched_rows += 1
            ib = match[0]
            # 比较该行各列
            for col in range(min(width, 4)):
                val_a = normalize_number(tree_a.get_cell_text(ia, col))
                val_b = normalize_number(tree_b.get_cell_text(ib, col))
                total_cells += 1
                if val_a != val_b:
                    cell_mismatches += 1

    # TEDS = 1 - (未匹配行代价 + 单元格错误代价) / max_cells
    max_cells = max(rows_a * width, rows_b * width, 1)
    row_penalty = (max(rows_a, rows_b) - matched_rows) * width
    edit_cost = row_penalty + cell_mismatches
    teds = max(0.0, 1.0 - edit_cost / max_cells)
    return round(teds, 3)


def _compute_cell_f1(tree_a: TableTree, tree_b: TableTree) -> float:
    """计算 Cell F1: 单元格级匹配。"""
    width = max(tree_a.get_logical_width(), tree_b.get_logical_width())
    item_names_a = tree_a.get_item_names()
    item_names_b = tree_b.get_item_names()

    tp = 0
    fp = 0  # tree_a 有 tree_b 没有
    fn = 0  # tree_b 有 tree_a 没有

    matched_b_indices: set[int] = set()

    for ia, name_a in enumerate(item_names_a):
        match = fuzzy_match_row(name_a, item_names_b, threshold=0.55)
        if match is not None:
            ib = match[0]
            matched_b_indices.add(ib)
            for col in range(width):
                val_a = normalize_number(tree_a.get_cell_text(ia, col))
                val_b = normalize_number(tree_b.get_cell_text(ib, col))
                if val_a == val_b:
                    tp += 1
                else:
                    fp += 1  # LAS 和 Mineru 不一致
        else:
            fp += width  # LAS 多出的行

    # Mineru 有 LAS 没有的行
    for ib in range(len(item_names_b)):
        if ib not in matched_b_indices:
            fn += width

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return round(f1, 3)


def compute_mineru_fidelity(
    las_markdown: str,
    company_code: str,
    parser_output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """计算 LAS vs Mineru 的 TEDS 和 Cell F1。

    Returns:
        {
            "by_statement": {stmt_type: {"teds": float, "cell_f1": float, "las_rows": int, "mineru_rows": int}},
            "avg_teds": float,
            "avg_cell_f1": float,
        }
    """
    if parser_output_dir is None:
        parser_output_dir = (
            PROJECT_ROOT / "data" / "FinAR-Bench" / "extracted"
            / "pdf_extractor_result" / "txt_output"
        )

    las_trees = parse_html_tables(las_markdown)
    mineru_text = load_reference_text(
        Path(parser_output_dir) / "mineru", company_code
    )

    if not mineru_text:
        return {"by_statement": {}, "avg_teds": float("nan"), "avg_cell_f1": float("nan")}

    mineru_trees = _extract_mineru_tables(mineru_text)
    matches = _match_tables(las_trees, las_markdown, mineru_trees, mineru_text)

    by_statement: dict[str, Any] = {}
    teds_vals: list[float] = []
    f1_vals: list[float] = []

    stmt_names = {"balance_sheet": "资产负债表", "income_stmt": "利润表", "cash_flow": "现金流量表"}
    for lt, mt, st in matches:
        teds = _compute_teds(lt, mt)
        f1 = _compute_cell_f1(lt, mt)
        teds_vals.append(teds)
        f1_vals.append(f1)

        by_statement[stmt_names.get(st, st)] = {
            "teds": teds,
            "cell_f1": f1,
            "las_rows": lt.row_count,
            "mineru_rows": mt.row_count,
        }

    avg_teds = round(sum(teds_vals) / len(teds_vals), 3) if teds_vals else float("nan")
    avg_f1 = round(sum(f1_vals) / len(f1_vals), 3) if f1_vals else float("nan")

    return {
        "by_statement": by_statement,
        "avg_teds": avg_teds,
        "avg_cell_f1": avg_f1,
    }
