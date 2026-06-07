"""模块 2 评分器 —— 三个子指标 → 1~10 分 → 加权汇总。"""

from __future__ import annotations


# ---------------------------------------------------------------------------
# 模块 2 总分权重
# ---------------------------------------------------------------------------

WEIGHTS = {
    "noise_ratio": 0.40,       # 噪声是最直观的结构问题
    "section_coverage": 0.30,  # 章节完整性
    "content_continuity": 0.30, # 连续性
}


def compute_module2_score(
    noise_score: int,
    section_score: int,
    continuity_score: int,
    weights: dict[str, float] | None = None,
) -> float:
    """计算模块 2 加权总分。

    Args:
        noise_score: 噪声比率 1-10 分
        section_score: 节段覆盖 1-10 分
        continuity_score: 内容连续性 1-10 分
        weights: 可选自定义权重

    Returns:
        module2_score: 0.0 ~ 10.0
    """
    w = weights or WEIGHTS
    score = (
        w["noise_ratio"] * noise_score
        + w["section_coverage"] * section_score
        + w["content_continuity"] * continuity_score
    )
    return round(score, 1)
