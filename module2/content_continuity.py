"""子指标 2.3：内容连续性（Content Continuity）。

评测正文内容是否被页面噪声频繁打断。连续的正文→高分，碎片化→低分。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable

from module2.noise_ratio import (
    _find_repeated_lines,
    _is_audit_mark,
    _is_page_number,
    _is_signatory,
)


# ---------------------------------------------------------------------------
# 连续性分析
# ---------------------------------------------------------------------------


@dataclass
class ContinuityReport:
    """内容连续性报告。"""
    clean_blocks: int = 0          # 纯净内容块数量
    total_clean_chars: int = 0     # 纯净内容总字符数
    avg_block_chars: float = 0.0   # 平均块长度
    max_block_chars: int = 0       # 最长块长度
    max_block_ratio: float = 0.0   # 最长块 / 总纯净内容
    noise_break_count: int = 0     # 噪声打断次数


def _is_noise_line(stripped: str, repeated_lines: set[str]) -> bool:
    """判断一行是否为噪声行。"""
    if not stripped:
        return False
    if _is_page_number(stripped):
        return True
    if stripped in repeated_lines:
        return True
    if _is_signatory(stripped):
        return True
    if _is_audit_mark(stripped):
        return True
    return False


def analyze_continuity(text: str) -> ContinuityReport:
    """分析文本的内容连续性。

    将噪声行作为分隔符，计算纯净内容块的分布。
    """
    lines = text.split("\n")

    # 预计算重复行
    repeated_lines = _find_repeated_lines([
        l for l in lines
        if l.strip() and not l.strip().startswith("<")
    ], min_repeat=3)

    # 按噪声行切分（连续噪声行 = 1 次打断）
    blocks: list[int] = []  # 每块字符数
    current_block = 0
    noise_breaks = 0
    in_noise = False

    for line in lines:
        stripped = line.strip()

        if _is_noise_line(stripped, repeated_lines):
            if not in_noise:
                # 新的一次打断
                if current_block > 0:
                    blocks.append(current_block)
                    current_block = 0
                noise_breaks += 1
                in_noise = True
        else:
            in_noise = False
            current_block += len(line)

    # 最后一块
    if current_block > 0:
        blocks.append(current_block)

    total_clean = sum(blocks)
    avg = total_clean / len(blocks) if blocks else 0
    max_block = max(blocks) if blocks else 0

    return ContinuityReport(
        clean_blocks=len(blocks),
        total_clean_chars=total_clean,
        avg_block_chars=round(avg, 1),
        max_block_chars=max_block,
        max_block_ratio=max_block / total_clean if total_clean > 0 else 0.0,
        noise_break_count=noise_breaks,
    )


# ---------------------------------------------------------------------------
# 评分
# ---------------------------------------------------------------------------


def continuity_to_score(report: ContinuityReport) -> int:
    """将连续性报告映射为 1~10 分。

    评分逻辑：平均每 300 字符 1 分，满分 10 分。
    即 avg_block ≥ 3000 字符 → 10 分。

    LAS 典型值：30k chars / 10 块 = 3000 avg → ~10 分
    Mineru 典型值：12k chars / 4 块 = 3000 avg → ~10 分
    两者相近，差异不大。差异主要来自噪声打断次数。
    """
    if report.avg_block_chars <= 0:
        return 1
    return min(10, max(1, round(report.avg_block_chars / 300)))
