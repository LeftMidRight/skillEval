"""Module 3: 下游任务可用性 (v3)。

评测方法:
- fact / indicator: LLM 从 LAS 输出中提取数值，与 XBRL GT 数值对比（容差判定）
- reasoning: LLM-as-Judge（逻辑推理判断，0/1 对比）

所有任务结果与 XBRL 真值对比。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from evaluation.llm_client import LLMClient
from evaluation.scenes import get_scene_label
from module1.utils import get_xbrl_for_company, load_xbrl_dataset


# ============================================================================
# Prompt 模板（全部使用 LLM-as-Judge）
# ============================================================================

FACT_PROMPT = """你是一位财务数据提取专家。请根据提供的公司财报内容，提取以下科目的数值。

对每个科目，仔细在财报内容中查找对应数值。注意：
- 数值可能以"1,234,567"或"(567)"（表示负数）的格式出现
- 如果同一个科目有多年数据，提取所有年份的数值
- 如果在财报中找不到某个科目，填 null

### 输出格式（严格 JSON，不要其他文字）
{
  "extractions": [
    {"item": "科目名", "values": {"年份": 数值, ...}, "found": true/false}
  ]
}

科目列表和财报内容见下方。"""

INDICATOR_PROMPT = """你是一位财务指标计算专家。请根据提供的公司财报内容，计算以下指标。

对每个指标，根据财报中的原始数据计算得出。注意：
- 指标通常是比率或百分比，需要从财报中提取相关原始数据后计算
- 计算过程请写在 reason 字段中
- 如果无法计算某个指标，填 null

### 输出格式（严格 JSON，不要其他文字）
{
  "extractions": [
    {"item": "指标名", "values": {"年份": 数值, ...}, "found": true/false, "reason": "计算过程"}
  ]
}

指标列表和财报内容见下方。"""

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

    所有任务类型均使用 LLM-as-Judge。

    Args:
        llm: LLM 客户端。
        las_markdown: LAS 输出的 markdown。
        task_desc: 任务描述。
        gt_text: XBRL ground truth markdown 表格。
        task_type: fact | indicator | reasoning

    Returns:
        {"correct": int, "total": int, "accuracy": float}
    """
    gt_rows = _parse_gt_table(gt_text)

    if task_type == "reasoning":
        prompt = REASONING_PROMPT
    elif task_type == "indicator":
        prompt = INDICATOR_PROMPT
    else:
        prompt = FACT_PROMPT

    try:
        response = llm.chat_text(
            prompt,
            f"财报内容：\n{las_markdown[:8000]}\n\n任务：{task_desc}",
        )
        llm_result = llm.extract_json(response)
    except Exception as e:
        return {"correct": 0, "total": 0, "accuracy": 0.0, "error": str(e)}

    if task_type == "reasoning":
        return _compare_reasoning(llm_result, gt_rows, task_desc)
    elif task_type == "indicator":
        return _compare_indicator_llm(llm_result, gt_rows)
    else:
        return _compare_fact_llm(llm_result, gt_rows)


def _normalize_value(val: str) -> float | None:
    """标准化数值：去逗号、括号负数→负号、统一小数。"""
    s = val.replace(",", "").replace(" ", "").strip()
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return None


def _extract_llm_numbers(llm_result: dict[str, Any]) -> dict[str, dict[str, float]]:
    """从 LLM extraction 结果中提取科目→年份→数值的映射。

    Returns:
        {科目名: {年份: 数值, ...}, ...}
    """
    items: dict[str, dict[str, float]] = {}
    extractions = llm_result.get("extractions", [])
    for ext in extractions:
        item_name = ext.get("item", "").strip()
        if not item_name:
            continue
        if not ext.get("found", True):
            continue
        values = ext.get("values", {})
        num_values: dict[str, float] = {}
        for key, val in values.items():
            if val is None:
                continue
            if isinstance(val, (int, float)):
                num_values[key] = float(val)
            elif isinstance(val, str):
                n = _normalize_value(val)
                if n is not None:
                    num_values[key] = n
        if num_values:
            items[item_name] = num_values
    return items


def _match_item(target: str, candidates: list[str]) -> str | None:
    """模糊匹配科目名。"""
    if target in candidates:
        return target
    for c in candidates:
        if target in c or c in target:
            return c
    return None


def _compare_fact_llm(
    llm_result: dict[str, Any],
    gt_rows: list[dict[str, str]],
) -> dict[str, Any]:
    """LLM 提取 + 数值对比 fact 任务。

    LLM 从 LAS markdown 提取科目数值，与 XBRL GT 数值对比。
    容差：1%。
    """
    llm_items = _extract_llm_numbers(llm_result)
    llm_item_names = list(llm_items.keys())

    correct = 0
    total = 0

    for row in gt_rows:
        cols = list(row.keys())
        if len(cols) < 2:
            continue
        item_name = row.get(cols[0], "").strip()

        matched_key = _match_item(item_name, llm_item_names)
        llm_entry = llm_items.get(matched_key, {}) if matched_key else {}

        for col in cols[1:]:
            gt_val = row[col].strip()
            if not gt_val:
                continue
            total += 1

            gt_num = _normalize_value(gt_val)
            llm_val = None
            if matched_key and llm_entry:
                for lc in llm_entry:
                    if col in lc or lc in col:
                        llm_val = llm_entry[lc]
                        break
                if llm_val is None and llm_entry:
                    llm_val = list(llm_entry.values())[0]

            if llm_val is not None and gt_num is not None:
                if gt_num == 0:
                    is_correct = abs(llm_val) < 1e-6
                else:
                    is_correct = abs(llm_val - gt_num) / abs(gt_num) <= 0.01
                if is_correct:
                    correct += 1

    return {
        "correct": correct,
        "total": total,
        "accuracy": round(correct / total, 3) if total > 0 else 0.0,
        "method": "llm_extraction",
    }


def _compare_indicator_llm(
    llm_result: dict[str, Any],
    gt_rows: list[dict[str, str]],
) -> dict[str, Any]:
    """LLM 提取 + 数值对比 indicator 任务。

    容差：2%（indicator 是计算值，允许稍大误差）。
    """
    llm_items = _extract_llm_numbers(llm_result)
    llm_item_names = list(llm_items.keys())

    correct = 0
    total = 0

    for row in gt_rows:
        cols = list(row.keys())
        if len(cols) < 2:
            continue
        item_name = row.get(cols[0], "").strip()

        matched_key = _match_item(item_name, llm_item_names)
        llm_entry = llm_items.get(matched_key, {}) if matched_key else {}

        for col in cols[1:]:
            gt_val = row[col].strip()
            if not gt_val:
                continue
            total += 1

            gt_num = _normalize_value(gt_val)
            llm_val = None
            if matched_key and llm_entry:
                for lc in llm_entry:
                    if col in lc or lc in col:
                        llm_val = llm_entry[lc]
                        break
                if llm_val is None and llm_entry:
                    llm_val = list(llm_entry.values())[0]

            if llm_val is not None and gt_num is not None:
                if gt_num == 0:
                    is_correct = abs(llm_val) < 1e-6
                else:
                    is_correct = abs(llm_val - gt_num) / abs(gt_num) <= 0.02
                if is_correct:
                    correct += 1

    return {
        "correct": correct,
        "total": total,
        "accuracy": round(correct / total, 3) if total > 0 else 0.0,
        "method": "llm_extraction",
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
    llm: LLMClient,
    company_code: str = "",
    las_markdown: str | None = None,
    las_results_dir: str | Path | None = None,
    xbrl_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """对单家公司执行 Module 3 全部评测。

    所有任务类型（fact/indicator/reasoning）均使用 LLM-as-Judge。

    Args:
        llm: LLM 客户端。
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

    scene = get_scene_label(company_code)

    return {
        "company_code": company_code,
        "scene": scene,
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
