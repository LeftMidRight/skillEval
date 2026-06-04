"""Module 3: 下游任务可用性。

全部使用 LLM-as-Judge：
- fact: LLM 根据 LAS markdown 提取指定科目数值
- indicator: LLM 根据 LAS markdown 计算财务指标
- reasoning: LLM 根据 LAS markdown + 条件做逻辑推理

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
from module1.utils import get_xbrl_for_company, load_xbrl_dataset
from evaluation.llm_client import LLMClient


# ============================================================================
# Prompt 模板
# ============================================================================

FACT_PROMPT = """你是一位财务数据分析师。请根据提供的公司财报内容，完成以下信息提取任务。

仔细阅读财报中的合并财务报表（资产负债表、利润表、现金流量表），
找到任务要求的所有财务科目的2022年和2023年数值。

### 输出格式（严格 JSON，不要其他文字）
{
  "results": [
    {"item": "科目名称", "2022": 数值, "2023": 数值}
  ]
}

财报内容和提取任务见下方。"""


INDICATOR_PROMPT = """你是一位财务分析师。请根据提供的公司财报内容，完成以下财务指标计算任务。

仔细从财报中提取所需的原始数值，按照标准财务公式计算各指标。
所有计算结果保留4位小数。

### 输出格式（严格 JSON，不要其他文字）
{
  "results": [
    {"item": "指标名称", "value": 0.1234}
  ]
}

财报内容和计算任务见下方。"""


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
        llm: LLM 客户端。
        las_markdown: LAS 输出的 markdown（截取前 8000 字符）。
        task_desc: 任务描述。
        gt_text: XBRL ground truth markdown 表格。
        task_type: fact | indicator | reasoning

    Returns:
        {"correct": int, "total": int, "accuracy": float}
    """
    if task_type == "fact":
        system_prompt = FACT_PROMPT
    elif task_type == "indicator":
        system_prompt = INDICATOR_PROMPT
    else:
        system_prompt = REASONING_PROMPT

    user_prompt = (
        f"财报内容：\n{las_markdown[:8000]}\n\n"
        f"任务：{task_desc}"
    )

    try:
        response = llm.chat_text(system_prompt, user_prompt)
        llm_result = llm.extract_json(response)
    except Exception as e:
        return {"correct": 0, "total": 0, "accuracy": 0.0, "error": str(e)}

    gt_rows = _parse_gt_table(gt_text)

    if task_type == "fact":
        return _compare_fact(llm_result, gt_rows)
    elif task_type == "indicator":
        return _compare_indicator(llm_result, gt_rows)
    else:
        return _compare_reasoning(llm_result, gt_rows, task_desc)


def _compare_fact(
    llm_result: dict[str, Any],
    gt_rows: list[dict[str, str]],
) -> dict[str, Any]:
    """对比 fact 任务结果。"""
    llm_items = {}
    if isinstance(llm_result, dict):
        for r in llm_result.get("results", []):
            name = r.get("item", "").strip()
            v2022 = r.get("2022", 0)
            v2023 = r.get("2023", 0)
            llm_items[name] = {"2022": v2022, "2023": v2023}

    correct = 0
    total = 0
    details = []

    for row in gt_rows:
        cols = list(row.keys())
        if len(cols) < 2:
            continue
        item_name = row.get(cols[0], "").strip()
        for col in cols[1:]:
            gt_val = row[col].strip()
            if not gt_val:
                continue
            total += 1

            llm_entry = llm_items.get(item_name)
            if llm_entry is None:
                # 尝试模糊匹配
                for k in llm_items:
                    if item_name in k or k in item_name:
                        llm_entry = llm_items[k]
                        break

            if llm_entry is not None:
                year_key = col.strip()
                # 匹配年份列: "2022" / "2023" / "2022年" 等
                llm_val = None
                for yk in llm_entry:
                    if "2022" in str(year_key) and "2022" in str(yk):
                        llm_val = llm_entry[yk]
                    elif "2023" in str(year_key) and "2023" in str(yk):
                        llm_val = llm_entry[yk]

                if llm_val is not None:
                    try:
                        v1 = float(llm_val)
                        v2 = float(gt_val.replace(",", ""))
                        if v2 == 0:
                            is_correct = abs(v1) < 1e-6
                        else:
                            is_correct = abs(v1 - v2) / abs(v2) <= 0.01
                        if is_correct:
                            correct += 1
                    except (ValueError, TypeError):
                        pass

            details.append({"item": item_name, "gt": gt_val})

    return {
        "correct": correct,
        "total": total,
        "accuracy": round(correct / total, 3) if total > 0 else 0.0,
        "details": details[:5],
    }


def _compare_indicator(
    llm_result: dict[str, Any],
    gt_rows: list[dict[str, str]],
) -> dict[str, Any]:
    """对比 indicator 任务结果。"""
    llm_values = {}
    if isinstance(llm_result, dict):
        for r in llm_result.get("results", []):
            name = r.get("item", "").strip()
            val = r.get("value", 0)
            llm_values[name] = val

    correct = 0
    total = 0

    for row in gt_rows:
        cols = list(row.keys())
        if len(cols) < 2:
            continue
        item_name = row.get(cols[0], "").strip()
        for col in cols[1:]:
            gt_val = row[col].strip()
            if not gt_val:
                continue
            total += 1

            # 精确匹配 or 模糊匹配
            llm_val = llm_values.get(item_name)
            if llm_val is None:
                for k in llm_values:
                    if item_name[:4] in k or k[:4] in item_name:
                        llm_val = llm_values[k]
                        break

            if llm_val is not None:
                try:
                    gt_f = float(gt_val)
                    if gt_f == 0:
                        is_correct = abs(float(llm_val)) < 1e-6
                    else:
                        is_correct = abs(float(llm_val) - gt_f) / abs(gt_f) <= 0.02
                    if is_correct:
                        correct += 1
                except (ValueError, TypeError):
                    pass

    return {
        "correct": correct,
        "total": total,
        "accuracy": round(correct / total, 3) if total > 0 else 0.0,
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
    company_code: str,
    las_markdown: str | None = None,
    las_results_dir: str | Path | None = None,
    xbrl_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """对单家公司执行 Module 3 全部评测。

    Args:
        llm: LLM 客户端（必需，三项任务都依赖 LLM）。
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
