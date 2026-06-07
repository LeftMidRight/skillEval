"""评分器 —— 将原始指标映射为 1~10 分，并按权重汇总模块 1 总分。"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# 子指标 1：文本 CER → 1-10 分
# ---------------------------------------------------------------------------

def text_cer_to_score(cer: float) -> int:
    """将 CER 映射为 1~10 分（财报场景调整版）。

    财报 PDF 文本复杂、含中文+数字混合、跨解析器 CER 天然偏高，
    此处阈值比通用场景宽松。"""
    if cer <= 0.03:
        return 10
    elif cer <= 0.06:
        return 9
    elif cer <= 0.10:
        return 8
    elif cer <= 0.15:
        return 7
    elif cer <= 0.22:
        return 6
    elif cer <= 0.30:
        return 5
    elif cer <= 0.40:
        return 4
    elif cer <= 0.55:
        return 3
    elif cer <= 0.70:
        return 2
    else:
        return 1


# ---------------------------------------------------------------------------
# 子指标 2：表格还原度 → 1-10 分
# ---------------------------------------------------------------------------

def teds_to_score(teds: float) -> int:
    """将 TEDS 映射为 1~10 分。"""
    if teds >= 0.98:
        return 10
    elif teds >= 0.95:
        return 9
    elif teds >= 0.90:
        return 8
    elif teds >= 0.85:
        return 7
    elif teds >= 0.75:
        return 6
    elif teds >= 0.65:
        return 5
    elif teds >= 0.55:
        return 4
    elif teds >= 0.40:
        return 3
    elif teds >= 0.20:
        return 2
    else:
        return 1


def cell_f1_to_score(f1: float) -> int:
    """将 Cell F1 映射为 1~10 分。"""
    if f1 >= 0.98:
        return 10
    elif f1 >= 0.95:
        return 9
    elif f1 >= 0.90:
        return 8
    elif f1 >= 0.85:
        return 7
    elif f1 >= 0.75:
        return 6
    elif f1 >= 0.65:
        return 5
    elif f1 >= 0.55:
        return 4
    elif f1 >= 0.40:
        return 3
    elif f1 >= 0.20:
        return 2
    else:
        return 1


def table_composite_score(teds: float, cell_f1: float) -> float:
    """表格还原度综合得分 = 0.6 * TEDS_score + 0.4 * Cell_F1_score。

    输入是原始指标值（0-1），内部先各自转 1-10 分再加权。
    TEDS 权重更高，因为它捕获了结构差异（colspan 丢失、行错位等）。
    """
    ts = teds_to_score(teds)
    cs = cell_f1_to_score(cell_f1)
    return round(0.6 * ts + 0.4 * cs, 1)


# ---------------------------------------------------------------------------
# 子指标 3：数字匹配 F1 → 1-10 分
# ---------------------------------------------------------------------------

def number_f1_to_score(f1: float) -> int:
    """将数字匹配 F1 映射为 1~10 分。"""
    if f1 >= 0.99:
        return 10
    elif f1 >= 0.97:
        return 9
    elif f1 >= 0.93:
        return 8
    elif f1 >= 0.88:
        return 7
    elif f1 >= 0.80:
        return 6
    elif f1 >= 0.70:
        return 5
    elif f1 >= 0.60:
        return 4
    elif f1 >= 0.45:
        return 3
    elif f1 >= 0.30:
        return 2
    else:
        return 1


# ---------------------------------------------------------------------------
# 模块 1 总分
# ---------------------------------------------------------------------------

# 权重配置
WEIGHTS = {
    "text_accuracy": 0.30,
    "table_fidelity": 0.40,
    "number_accuracy": 0.30,
}


def compute_module1_score(
    text_score: int,
    table_score: int,
    number_score: int,
    weights: dict[str, float] | None = None,
) -> float:
    """计算模块 1 加权总分（保留 1 位小数）。

    Args:
        text_score: 文本准确率 1-10 分
        table_score: 表格还原度 1-10 分
        number_score: 数值匹配率 1-10 分
        weights: 可选自定义权重

    Returns:
        module1_score: 0.0 ~ 10.0
    """
    w = weights or WEIGHTS
    score = (
        w["text_accuracy"] * text_score
        + w["table_fidelity"] * table_score
        + w["number_accuracy"] * number_score
    )
    return round(score, 1)


def evaluate_and_score(
    text_result: dict,
    table_result: dict,
    number_result: dict,
) -> dict:
    """一站式：根据三个子指标的原始结果，计算得分和汇总。

    Returns:
        {
            "text": {"cer": ..., "score": ...},
            "table": {"teds": ..., "cell_f1": ..., "table_score": ..., "by_statement": ...},
            "number": {"f1": ..., "score": ...},
            "module1_score": float,
        }
    """
    text_cer = text_result.get("mineru_cer")
    if text_cer is None or text_cer != text_cer:  # None or NaN
        text_cer = text_result.get("median_cer", 1.0)
        if text_cer is None or text_cer != text_cer:
            text_cer = 1.0
    text_score = text_cer_to_score(text_cer)

    # 表格：TEDS + Cell F1
    teds_overall = table_result.get("teds", {}).get("overall", 0.0)
    cell_f1 = table_result["overall"]["f1"]
    table_teds_score = teds_to_score(teds_overall)
    table_f1_score = cell_f1_to_score(cell_f1)
    table_score_combined = table_composite_score(teds_overall, cell_f1)

    num_f1 = number_result["f1"]
    num_score = number_f1_to_score(num_f1)

    return {
        "text": {
            "cer": text_cer,
            "score": text_score,
            "cers_by_parser": text_result.get("cers", {}),
        },
        "table": {
            "teds": teds_overall,
            "teds_score": table_teds_score,
            "cell_f1": cell_f1,
            "cell_f1_score": table_f1_score,
            "table_score": table_score_combined,
            "by_statement": table_result.get("by_statement", {}),
            "teds_by_statement": table_result.get("teds", {}).get("by_statement", {}),
        },
        "number": {
            "f1": num_f1,
            "score": num_score,
            "precision": number_result.get("precision", 0),
            "recall": number_result.get("recall", 0),
            "matched_examples": number_result.get("matched_examples", []),
            "missing_examples": number_result.get("missing_examples", []),
            "extra_examples": number_result.get("extra_examples", []),
        },
        "module1_score": compute_module1_score(text_score, int(round(table_score_combined)), num_score),
    }
