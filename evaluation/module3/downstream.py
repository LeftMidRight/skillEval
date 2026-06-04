"""Module 3: 下游任务可用性。

- fact / indicator: 从 LAS markdown 中提取数值，与 XBRL 真值直接对比
- reasoning: LLM-as-Judge，基于 LAS markdown 做逻辑推理
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
    extract_numbers,
    get_xbrl_for_company,
    load_xbrl_dataset,
    normalize_number,
)
from evaluation.llm_client import LLMClient


# ============================================================================
# Fact / Indicator: 直接数值对比
# ============================================================================

def _parse_gt_table(gt_markdown: str) -> list[dict[str, str]]:
    """解析 ground truth markdown 表格为 row dicts。"""
    lines = gt_markdown.strip().split("\n")
    # 跳过表头行和分隔行
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


def _compare_values(
    las_value: str | None,
    gt_value: str,
    tolerance: float = 0.01,
) -> bool:
    """比较两个数值是否在容差范围内一致。

    Args:
        las_value: LAS 中提取的值（可能为 None）。
        gt_value: XBRL 真值。
        tolerance: 相对容差。

    Returns:
        True 如果一致。
    """
    if las_value is None:
        return False

    try:
        v1 = float(las_value.replace(",", ""))
        v2 = float(gt_value.replace(",", ""))
    except ValueError:
        return las_value.strip() == gt_value.strip()

    if v2 == 0:
        return abs(v1) < 1e-6
    return abs(v1 - v2) / abs(v2) <= tolerance


def evaluate_fact_indicator(
    las_markdown: str,
    xbrl_record: dict[str, Any],
) -> dict[str, Any]:
    """评测 fact 和 indicator 任务。

    对每个 fact/indicator 任务，从 LAS markdown 中提取对应数值，
    与 XBRL 真值对比。

    Returns:
        {
            "fact": {"correct": int, "total": int, "accuracy": float, "details": [...]},
            "indicator": {"correct": int, "total": int, "accuracy": float, "details": [...]},
        }
    """
    instances = xbrl_record.get("instances", [])

    fact_correct = 0
    fact_total = 0
    fact_details: list[dict] = []

    ind_correct = 0
    ind_total = 0
    ind_details: list[dict] = []

    # 从 LAS markdown 中提取所有标准化数值
    las_numbers: set[str] = set()
    for td in re.finditer(r"<td[^>]*>([^<]*)</td>", las_markdown, re.DOTALL):
        text = td.group(1).strip()
        for num in extract_numbers(text):
            norm = normalize_number(num)
            if norm and norm != num:
                las_numbers.add(norm)

    for inst in instances:
        task_type = inst.get("task_type", "")
        gt = inst.get("ground_truth", "")
        task_desc = inst.get("task", "")

        if task_type not in ("fact", "indicator"):
            continue

        gt_rows = _parse_gt_table(gt)
        task_correct = 0
        task_total = 0

        for row in gt_rows:
            cols = list(row.keys())
            if len(cols) < 2:
                continue

            item_name = row.get(cols[0], "")
            for col in cols[1:]:
                gt_val = row[col].strip()
                if not gt_val:
                    continue
                task_total += 1

                gt_norm = normalize_number(gt_val)
                found = gt_norm in las_numbers
                if found:
                    task_correct += 1

        if task_type == "fact":
            fact_correct += task_correct
            fact_total += task_total
            fact_details.append({
                "task": task_desc[:100],
                "correct": task_correct,
                "total": task_total,
            })
        else:
            # indicator 任务：真值是计算结果，不能直接从 LAS 中查找
            # 标记为需要 LLM 评估
            ind_total += task_total
            ind_details.append({
                "task": task_desc[:100],
                "total": task_total,
                "requires_llm": True,
            })

    return {
        "fact": {
            "correct": fact_correct,
            "total": fact_total,
            "accuracy": round(fact_correct / fact_total, 3) if fact_total > 0 else 0.0,
            "details": fact_details,
        },
        "indicator": {
            "correct": ind_correct,
            "total": ind_total,
            "accuracy": round(ind_correct / ind_total, 3) if ind_total > 0 else 0.0,
            "details": ind_details,
        },
    }


# ============================================================================
# Reasoning: LLM-as-Judge
# ============================================================================

INDICATOR_PROMPT = """你是一位财务分析师。请根据提供的公司财报内容，完成以下指标计算任务。

仔细从财报中提取所需的原始数值，计算得到最终结果。所有计算结果保留4位小数。
输出格式（严格 JSON）：
{
  "results": [
    {"item": "指标名称", "value": 0.1234}
  ]
}

财报内容和计算任务见下方。"""


REASONING_PROMPT = """你是一位财务分析师。请根据提供的公司财报内容，对以下判断条件逐一给出是/否的判断。

对每个条件，仔细阅读财报内容，判断该条件是否成立。
输出格式（严格 JSON）：
{
  "judgments": [
    {"condition_index": 0, "result": 0或1, "reason": "一句话理由"},
    ...
  ]
}

条件列表和财报内容见下方。"""


def evaluate_indicators_llm(
    llm: LLMClient,
    las_markdown: str,
    xbrl_record: dict[str, Any],
) -> dict[str, Any]:
    """用 LLM 评测 indicator 任务（需要计算能力）。

    Args:
        llm: LLM 客户端。
        las_markdown: LAS 输出的 markdown。
        xbrl_record: XBRL 记录。

    Returns:
        {"correct": int, "total": int, "accuracy": float, "details": [...]}
    """
    indicator_tasks = [
        inst for inst in xbrl_record.get("instances", [])
        if inst.get("task_type") == "indicator"
    ]

    if not indicator_tasks:
        return {"correct": 0, "total": 0, "accuracy": 0.0, "note": "no indicator tasks"}

    total_correct = 0
    total_items = 0
    all_details = []

    for inst in indicator_tasks:
        task_desc = inst.get("task", "")
        gt = inst.get("ground_truth", "")

        user_prompt = (
            f"财报内容：\n{las_markdown[:8000]}\n\n"
            f"计算任务：{task_desc}\n\n"
            f"请计算并返回所有要求的指标值。"
        )

        response = llm.chat_text("", INDICATOR_PROMPT + "\n" + user_prompt)
        llm_result = llm.extract_json(response)

        gt_rows = _parse_gt_table(gt)
        llm_values = {}
        if isinstance(llm_result, dict):
            for r in llm_result.get("results", []):
                name = r.get("item", "")
                val = r.get("value", 0)
                llm_values[name] = val

        correct = 0
        total = 0
        for row in gt_rows:
            cols = list(row.keys())
            item_name = row.get(cols[0], "")
            for col in cols[1:]:
                gt_val = row[col].strip()
                if not gt_val:
                    continue
                total += 1
                llm_val = llm_values.get(item_name)
                if llm_val is not None:
                    try:
                        gt_f = float(gt_val)
                        is_correct = abs(float(llm_val) - gt_f) / max(abs(gt_f), 0.001) <= 0.02
                        if is_correct:
                            correct += 1
                    except (ValueError, TypeError):
                        pass

        total_correct += correct
        total_items += total
        all_details.append({
            "task": task_desc[:100],
            "correct": correct,
            "total": total,
        })

    return {
        "correct": total_correct,
        "total": total_items,
        "accuracy": round(total_correct / total_items, 3) if total_items > 0 else 0.0,
        "details": all_details,
    }


def evaluate_reasoning(
    llm: LLMClient,
    las_markdown: str,
    xbrl_record: dict[str, Any],
) -> dict[str, Any]:
    """用 LLM 评测 reasoning 任务。

    Args:
        llm: LLM 客户端。
        las_markdown: LAS 输出的 markdown。
        xbrl_record: XBRL 记录（含 reasoning 任务定义和真值）。

    Returns:
        {"correct": int, "total": int, "accuracy": float, "details": [...]}
    """
    # 找到 reasoning 任务
    reasoning_task = None
    for inst in xbrl_record.get("instances", []):
        if inst.get("task_type") == "reasoning":
            reasoning_task = inst
            break

    if reasoning_task is None:
        return {"correct": 0, "total": 0, "accuracy": 0.0, "error": "no reasoning task"}

    task_desc = reasoning_task.get("task", "")
    conditions = reasoning_task.get("conditions", "")
    gt_text = reasoning_task.get("ground_truth", "")

    # 构建 prompt
    user_prompt = (
        f"财报内容：\n{las_markdown[:8000]}\n\n"
        f"任务：{task_desc}\n\n"
    )
    if conditions:
        user_prompt += f"参考条件：{conditions}\n"

    full_prompt = REASONING_PROMPT + "\n" + user_prompt

    response = llm.chat_text("", full_prompt)
    llm_result = llm.extract_json(response)

    # 解析真值
    gt_rows = _parse_gt_table(gt_text)
    gt_judgments: dict[int, int] = {}
    for row in gt_rows:
        # 格式: {"序号": "0", "是否满足": "1"} 或类似
        keys = list(row.keys())
        if len(keys) >= 2:
            try:
                idx = int(row.get(keys[0], "-1"))
                val = int(row.get(keys[1], "0"))
                gt_judgments[idx] = val
            except (ValueError, KeyError):
                continue

    # 对比
    llm_judgments = llm_result.get("judgments", []) if isinstance(llm_result, dict) else []
    correct = 0
    total = len(gt_judgments)
    details = []

    for j in llm_judgments:
        idx = j.get("condition_index", -1)
        result = j.get("result", -1)
        gt_val = gt_judgments.get(idx)
        if gt_val is not None:
            is_correct = result == gt_val
            if is_correct:
                correct += 1
            details.append({
                "condition_index": idx,
                "llm_result": result,
                "gt_result": gt_val,
                "correct": is_correct,
                "reason": j.get("reason", ""),
            })

    # GT 中有但 LLM 没判断的
    for idx, gt_val in gt_judgments.items():
        if not any(j.get("condition_index") == idx for j in llm_judgments):
            total = max(total, len(gt_judgments))

    if total == 0:
        total = len(gt_judgments)

    return {
        "correct": correct,
        "total": total,
        "accuracy": round(correct / total, 3) if total > 0 else 0.0,
        "details": details,
    }


# ============================================================================
# 协调器
# ============================================================================

def evaluate_company(
    llm: LLMClient | None,
    company_code: str,
    las_markdown: str | None = None,
    las_results_dir: str | Path | None = None,
    xbrl_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """对单家公司执行 Module 3 全部评测。

    Args:
        llm: LLM 客户端（reasoning 需要，fact/indicator 不需要）。
        company_code: 股票代码。
        las_markdown: LAS 输出 markdown。
        las_results_dir: LAS 结果目录。
        xbrl_records: 预加载的 XBRL 数据集。

    Returns:
        {"company_code": str, "fact_indicator": {...}, "reasoning": {...}}
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

    # Fact（直接数值对比）
    fi_result = evaluate_fact_indicator(las_markdown, xbrl_record)

    # Indicator（LLM 计算）+ Reasoning（LLM 推理）
    indicator_result: dict[str, Any] = {"error": "LLM client not provided"}
    reasoning_result: dict[str, Any] = {"error": "LLM client not provided"}
    if llm is not None:
        try:
            indicator_result = evaluate_indicators_llm(llm, las_markdown, xbrl_record)
        except Exception as e:
            indicator_result = {"error": str(e)}
        try:
            reasoning_result = evaluate_reasoning(llm, las_markdown, xbrl_record)
        except Exception as e:
            reasoning_result = {"error": str(e)}

    return {
        "company_code": company_code,
        "fact": fi_result["fact"],
        "indicator": indicator_result,
        "reasoning": reasoning_result,
    }
