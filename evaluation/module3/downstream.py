"""Module 3: 下游任务可用性 (v3)。

评测方法:
- fact / indicator: 直接数值对比（从 LAS 表格中定位科目行，与 XBRL GT 数值对比）
- reasoning: LLM-as-Judge（需逻辑推理，无法直接数值对比）

所有任务结果与 XBRL 真值对比。
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from module1.utils import (
    extract_all_tables,
    get_xbrl_for_company,
    load_xbrl_dataset,
    normalize_number,
    parse_xbrl_tables,
)


# ============================================================================
# Prompt 模板（仅 reasoning 使用 LLM）
# ============================================================================

REASONING_PROMPT = """你是一位财务分析师。请根据提供的公司财报内容，对以下判断条件逐一给出是否满足的判断。

对每个条件，仔细阅读财报内容，提取相关数据，判断该条件是否成立。
注意：条件可能涉及变化趋势（如"上升""下降"），需要同时关注2022年和2023年的数据。

### 输出格式（严格 JSON，不要其他文字）
{
  "judgments": [
    {"condition_index": 0, "result": 0或1, "reason": "一句话理由（含计算过程）"}
  ]
}

条件列表和财报内容见下方。"""


# ============================================================================
# GT 解析
# ============================================================================

def _parse_gt_table(gt_markdown: str) -> list[dict[str, str]]:
    """解析 XBRL ground truth markdown 表格为 row dicts。"""
    lines = gt_markdown.strip().split("\n")
    data_lines = []
    header_line = None
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if "---" in stripped:
            continue
        if header_line is None:
            header_line = [c.strip() for c in stripped.strip("|").split("|")]
        else:
            data_lines.append(stripped)

    if header_line is None:
        return []

    rows = []
    for dl in data_lines:
        cells = [c.strip() for c in dl.strip("|").split("|")]
        row = {}
        for i, h in enumerate(header_line):
            row[h] = cells[i] if i < len(cells) else ""
        rows.append(row)
    return rows


# ============================================================================
# 单任务评测
# ============================================================================

def _evaluate_task(
    llm: LLMClient,
    las_markdown: str,
    task_desc: str,
    gt_text: str,
    task_type: str,
) -> dict[str, Any]:
    """评测单个任务。

    Args:
        llm 客户端（仅 reasoning 使用）。
        las_markdown: LAS 输出的 markdown。
        task_desc: 任务描述。
        gt_text: XBRL ground truth markdown 表格。
        task_type: fact | indicator | reasoning

    Returns:
        {"correct": int, "total": int, "accuracy": float}
    """
    gt_rows = _parse_gt_table(gt_text)

    if task_type == "fact":
        return _compare_fact_direct(las_markdown, gt_rows)
    elif task_type == "indicator":
        return _compare_indicator_direct(las_markdown, gt_rows)
    else:
        # reasoning: 仍然使用 LLM
        try:
            response = llm.chat_text(
                REASONING_PROMPT,
                f"财报内容：\n{las_markdown[:8000]}\n\n任务：{task_desc}",
            )
            llm_result = llm.extract_json(response)
        except Exception as e:
            return {"correct": 0, "total": 0, "accuracy": 0.0, "error": str(e)}
        return _compare_reasoning(llm_result, gt_rows, task_desc)


def _extract_las_table_values(las_markdown: str) -> dict[str, dict[str, str]]:
    """从 LAS markdown 的 HTML 表格中提取所有科目及其数值。

    Returns:
        {科目名: {列名: 值, ...}, ...}
    """
    tables = extract_all_tables(las_markdown)
    result: dict[str, dict[str, str]] = {}

    for _title, dict_list, _tree in tables:
        if not dict_list or len(dict_list) < 2:
            continue
        headers = list(dict_list[0].keys())
        if len(headers) < 2:
            continue
        item_col = headers[0]
        for row in dict_list:
            item_name = row.get(item_col, "").strip()
            if not item_name:
                continue
            values = {}
            for col in headers[1:]:
                val = row.get(col, "").strip()
                if val:
                    values[col] = val
            if values:
                result[item_name] = values

    return result


def _normalize_value(val: str) -> float | None:
    """标准化数值：去逗号、括号负数→负号、统一小数。"""
    s = val.replace(",", "").replace(" ", "").strip()
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return None


def _match_item(target: str, candidates: list[str]) -> str | None:
    """模糊匹配科目名。"""
    # 精确匹配
    if target in candidates:
        return target
    # 包含匹配
    for c in candidates:
        if target in c or c in target:
            return c
    return None


def _compare_fact_direct(
    las_markdown: str,
    gt_rows: list[dict[str, str]],
) -> dict[str, Any]:
    """直接数值对比 fact 任务：在 LAS 表格中定位科目，与 XBRL GT 对比。

    不使用 LLM，直接从 LAS 的 HTML 表格中提取数值。
    正确判定：|LAS值 - XBRL真值| / |XBRL真值| <= 0.01（1%容差）。
    """
    las_items = _extract_las_table_values(las_markdown)
    las_item_names = list(las_items.keys())

    correct = 0
    total = 0
    details = []

    for row in gt_rows:
        cols = list(row.keys())
        if len(cols) < 2:
            continue
        item_name = row.get(cols[0], "").strip()

        matched_key = _match_item(item_name, las_item_names)
        las_entry = las_items.get(matched_key, {}) if matched_key else {}

        for col in cols[1:]:
            gt_val = row[col].strip()
            if not gt_val:
                continue
            total += 1

            gt_num = _normalize_value(gt_val)
            # 尝试年份匹配
            las_val_str = None
            if matched_key and las_entry:
                for lc in las_entry:
                    if col in lc or lc in col:
                        las_val_str = las_entry[lc]
                        break
                # fallback: 取第一个数值列
                if las_val_str is None and las_entry:
                    las_val_str = list(las_entry.values())[0]

            if las_val_str is not None and gt_num is not None:
                las_num = _normalize_value(las_val_str)
                if las_num is not None:
                    if gt_num == 0:
                        is_correct = abs(las_num) < 1e-6
                    else:
                        is_correct = abs(las_num - gt_num) / abs(gt_num) <= 0.01
                    if is_correct:
                        correct += 1

        if total <= 5:
            details.append({"item": item_name, "matched": matched_key is not None})

    return {
        "correct": correct,
        "total": total,
        "accuracy": round(correct / total, 3) if total > 0 else 0.0,
        "details": details[:5],
        "method": "direct_table_lookup",
    }


def _compare_indicator_direct(
    las_markdown: str,
    gt_rows: list[dict[str, str]],
) -> dict[str, Any]:
    """直接数值对比 indicator 任务。

    同样从 LAS 表格直接提取，2%容差（indicator 是计算值，允许稍大误差）。
    """
    las_items = _extract_las_table_values(las_markdown)
    las_item_names = list(las_items.keys())

    correct = 0
    total = 0

    for row in gt_rows:
        cols = list(row.keys())
        if len(cols) < 2:
            continue
        item_name = row.get(cols[0], "").strip()

        matched_key = _match_item(item_name, las_item_names)
        las_entry = las_items.get(matched_key, {}) if matched_key else {}

        for col in cols[1:]:
            gt_val = row[col].strip()
            if not gt_val:
                continue
            total += 1

            gt_num = _normalize_value(gt_val)
            las_val_str = None
            if matched_key and las_entry:
                for lc in las_entry:
                    if col in lc or lc in col:
                        las_val_str = las_entry[lc]
                        break
                if las_val_str is None and las_entry:
                    las_val_str = list(las_entry.values())[0]

            if las_val_str is not None and gt_num is not None:
                las_num = _normalize_value(las_val_str)
                if las_num is not None:
                    if gt_num == 0:
                        is_correct = abs(las_num) < 1e-6
                    else:
                        is_correct = abs(las_num - gt_num) / abs(gt_num) <= 0.02
                    if is_correct:
                        correct += 1

    return {
        "correct": correct,
        "total": total,
        "accuracy": round(correct / total, 3) if total > 0 else 0.0,
        "method": "direct_table_lookup",
    }


def _compare_reasoning(
    llm_result: dict[str, Any],
    gt_rows: list[dict[str, str]],
    task_desc: str = "",
) -> dict[str, Any]:
    """对比 reasoning 任务结果。"""
    # 解析真值
    gt_judgments: dict[int, int] = {}
    for row in gt_rows:
        keys = list(row.keys())
        if len(keys) >= 2:
            try:
                idx = int(row.get(keys[0], "-1"))
                val = int(row.get(keys[1], "0"))
                gt_judgments[idx] = val
            except (ValueError, KeyError):
                continue

    llm_judgments = llm_result.get("judgments", []) if isinstance(llm_result, dict) else []
    correct = 0
    total = len(gt_judgments)

    for j in llm_judgments:
        idx = j.get("condition_index", -1)
        result = j.get("result", -1)
        gt_val = gt_judgments.get(idx)
        if gt_val is not None and result == gt_val:
            correct += 1

    return {
        "correct": correct,
        "total": total,
        "accuracy": round(correct / total, 3) if total > 0 else 0.0,
    }


# ============================================================================
# 协调器
# ============================================================================

def evaluate_company(
    llm: LLMClient | None = None,
    company_code: str = "",
    las_markdown: str | None = None,
    las_results_dir: str | Path | None = None,
    xbrl_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """对单家公司执行 Module 3 全部评测。

    Args:
        llm: LLM 客户端（仅 reasoning 任务需要）。
        company_code: 股票代码。
        las_markdown: LAS 输出 markdown。
        las_results_dir: LAS 结果目录。
        xbrl_records: 预加载的 XBRL 数据集。

    Returns:
        {
            "company_code": str,
            "fact": {"correct": int, "total": int, "accuracy": float},
            "indicator": {"correct": int, "total": int, "accuracy": float},
            "reasoning": {"correct": int, "total": int, "accuracy": float},
        }
    """
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
        raise ValueError(f"XBRL record not found for {company_code}")

    instances = xbrl_record.get("instances", [])

    fact_total = 0
    fact_correct = 0
    ind_total = 0
    ind_correct = 0
    reas_total = 0
    reas_correct = 0
    all_details: dict[str, list] = {"fact": [], "indicator": [], "reasoning": []}

    for inst in instances:
        task_type = inst.get("task_type", "")
        task_desc = inst.get("task", "")
        gt_text = inst.get("ground_truth", "")

        if task_type not in ("fact", "indicator", "reasoning"):
            continue

        # reasoning 需要 LLM
        if task_type == "reasoning" and llm is None:
            result = {"correct": 0, "total": 0, "accuracy": 0.0, "error": "LLM client not provided"}
        else:
            print(f"  [{task_type}] {task_desc[:60]}...", end=" ")
            try:
                result = _evaluate_task(llm, las_markdown, task_desc, gt_text, task_type)
                print(f"{result['correct']}/{result['total']}")
            except Exception as e:
                result = {"correct": 0, "total": 0, "accuracy": 0.0, "error": str(e)}
                print(f"ERROR: {e}")

        all_details[task_type].append(result)

        if task_type == "fact":
            fact_correct += result.get("correct", 0)
            fact_total += result.get("total", 0)
        elif task_type == "indicator":
            ind_correct += result.get("correct", 0)
            ind_total += result.get("total", 0)
        else:
            reas_correct += result.get("correct", 0)
            reas_total += result.get("total", 0)

    return {
        "company_code": company_code,
        "fact": {
            "correct": fact_correct,
            "total": fact_total,
            "accuracy": round(fact_correct / fact_total, 3) if fact_total > 0 else 0.0,
            "details": all_details["fact"],
        },
        "indicator": {
            "correct": ind_correct,
            "total": ind_total,
            "accuracy": round(ind_correct / ind_total, 3) if ind_total > 0 else 0.0,
            "details": all_details["indicator"],
        },
        "reasoning": {
            "correct": reas_correct,
            "total": reas_total,
            "accuracy": round(reas_correct / reas_total, 3) if reas_total > 0 else 0.0,
            "details": all_details["reasoning"],
        },
    }
