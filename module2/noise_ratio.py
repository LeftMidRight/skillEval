"""子指标 2.1：噪声比率（Noise Ratio）。

检测输出中结构噪声的密度——页码、重复页眉、签名栏、审计标记。
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# 噪声检测规则
# ---------------------------------------------------------------------------

_PAGE_NUM_RE = re.compile(r"^\s*\d+\s*/\s*\d+\s*$")

_SIGNATORY_KW = ["公司负责人", "主管会计", "会计机构负责人", "会计机构", "法定代表人"]

_AUDIT_KW = ["审计报告", "会计师事务所", "审计意见", "注册会计师"]


def _is_page_number(line: str) -> bool:
    return bool(_PAGE_NUM_RE.match(line.strip()))


def _is_signatory(line: str) -> bool:
    return any(kw in line for kw in _SIGNATORY_KW)


def _is_audit_mark(line: str) -> bool:
    return any(kw in line for kw in _AUDIT_KW)


def _find_repeated_lines(lines: list[str], min_repeat: int = 3) -> set[str]:
    """找出重复出现 >= min_repeat 次的非空行（页眉候选）。"""
    counter = Counter(l.strip() for l in lines if l.strip())
    return {k for k, v in counter.items() if v >= min_repeat}


# ---------------------------------------------------------------------------
# 噪声分析
# ---------------------------------------------------------------------------


@dataclass
class NoiseReport:
    """噪声分析报告。"""
    total_lines: int = 0
    total_chars: int = 0
    page_number_lines: int = 0
    repeated_header_types: int = 0
    repeated_header_lines: int = 0
    signatory_lines: int = 0
    audit_lines: int = 0
    noise_lines: int = 0
    noise_chars: int = 0
    noise_ratio: float = 0.0  # noise_chars / total_chars


def analyze_noise(text: str) -> NoiseReport:
    """分析文本中的结构噪声。

    Args:
        text: LAS 或参考解析器的输出文本

    Returns:
        NoiseReport
    """
    lines = text.split("\n")
    total_lines = len(lines)
    total_chars = max(1, len(text))

    # 预计算重复行集合
    repeated_lines = _find_repeated_lines([
        l for l in lines
        if l.strip() and not l.strip().startswith("<")  # 跳过 HTML 标签行
    ], min_repeat=3)

    page_num_count = 0
    repeated_header_count = 0
    sig_count = 0
    audit_count = 0
    noise_chars = 0

    for line in lines:
        stripped = line.strip()
        is_noise = False

        if not stripped:
            continue

        if _is_page_number(stripped):
            page_num_count += 1
            is_noise = True
        elif stripped in repeated_lines:
            repeated_header_count += 1
            is_noise = True
        elif _is_signatory(stripped):
            sig_count += 1
            is_noise = True
        elif _is_audit_mark(stripped):
            audit_count += 1
            is_noise = True

        if is_noise:
            noise_chars += len(line)

    noise_lines = page_num_count + repeated_header_count + sig_count + audit_count

    return NoiseReport(
        total_lines=total_lines,
        total_chars=total_chars,
        page_number_lines=page_num_count,
        repeated_header_types=len(repeated_lines),
        repeated_header_lines=repeated_header_count,
        signatory_lines=sig_count,
        audit_lines=audit_count,
        noise_lines=noise_lines,
        noise_chars=noise_chars,
        noise_ratio=noise_chars / total_chars,
    )


# ---------------------------------------------------------------------------
# 评分
# ---------------------------------------------------------------------------


def noise_ratio_to_score(noise_ratio: float) -> int:
    """将噪声比率映射为 1~10 分。

    阈值基于实际数据校准：
    - LAS 噪声比 ~4%（10 页码 + 8 页眉 × 多行 + 18 签名行 / 30000 chars）
    - Mineru 噪声比 ~2-3%（签名栏为主 / 12000 chars）
    """
    if noise_ratio <= 0.005:
        return 10
    elif noise_ratio <= 0.01:
        return 9
    elif noise_ratio <= 0.02:
        return 8
    elif noise_ratio <= 0.03:
        return 7
    elif noise_ratio <= 0.05:
        return 6
    elif noise_ratio <= 0.08:
        return 5
    elif noise_ratio <= 0.12:
        return 4
    elif noise_ratio <= 0.18:
        return 3
    elif noise_ratio <= 0.25:
        return 2
    else:
        return 1
