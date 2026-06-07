"""子指标 2.2：节段覆盖度（Section Coverage）。

检测关键财报章节是否在输出中被完整保留。
"""

from __future__ import annotations

import re
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# 关键章节定义
# ---------------------------------------------------------------------------

# 每类章节的检测关键词和是否必须
REQUIRED_SECTIONS = {
    "资产负债表": {
        "keywords": ["资产负债表"],
        "required": True,
    },
    "利润表": {
        "keywords": ["利润表", "损益表"],
        "required": True,
    },
    "现金流量表": {
        "keywords": ["现金流量表"],
        "required": True,
    },
    "审计报告": {
        "keywords": ["审计报告", "审计意见", "审计"],
        "required": False,
    },
}

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)")


# ---------------------------------------------------------------------------
# 节段检测
# ---------------------------------------------------------------------------


def detect_sections(text: str) -> dict[str, bool]:
    """检测文本中包含哪些关键财报章节。

    同时检查 markdown 标题行（### xxx）和纯文本表名行。
    """
    lines = text.split("\n")
    candidates: list[str] = []

    for line in lines:
        stripped = line.strip()

        # Markdown 标题
        m = _HEADING_RE.match(stripped)
        if m:
            candidates.append(m.group(2).strip())
            continue

        # 纯文本行也可能是表名 —— 长度适中、含完整表名关键词、不包含 HTML 标签或表格竖线
        if 4 <= len(stripped) <= 40 and not stripped.startswith("<"):
            if "|" not in stripped:  # 排除 markdown 表格行
                for kw in ["资产负债表", "利润表", "损益表",
                            "现金流量表",
                            "审计报告", "审计意见"]:
                    if kw in stripped:
                        candidates.append(stripped)
                        break

    result: dict[str, bool] = {}
    for section_name, config in REQUIRED_SECTIONS.items():
        found = False
        for c in candidates:
            for kw in config["keywords"]:
                if kw in c:
                    found = True
                    break
            if found:
                break
        result[section_name] = found

    return result


# ---------------------------------------------------------------------------
# 评分
# ---------------------------------------------------------------------------


def section_coverage_to_score(detected: dict[str, bool]) -> int:
    """将节段覆盖结果映射为 1~10 分。

    评分规则：
    - 3 个必须章节全有 → 基准 8 分
    - 审计报告也有 → +2 分（满分 10）
    - 每缺一个必须章节 → -3 分
    - 最低 1 分
    """
    required_sections = {
        k for k, v in REQUIRED_SECTIONS.items() if v["required"]
    }
    optional_sections = {
        k for k, v in REQUIRED_SECTIONS.items() if not v["required"]
    }

    found_required = sum(1 for s in required_sections if detected.get(s, False))
    total_required = len(required_sections)
    found_optional = sum(1 for s in optional_sections if detected.get(s, False))

    # 基准：必须章节覆盖率
    base = 8  # 全部必须章节 → 8 分
    missing = total_required - found_required
    score = base - missing * 3

    # 可选章节加分
    if found_optional > 0 and score >= 8:
        score += 2

    return max(1, min(10, score))
