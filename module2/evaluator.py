"""模块 2 评测主协调器。

用法：
    evaluator = Evaluator()
    result = evaluator.evaluate("output/las_results/600064/report.md")
    print(f"Module 2 Score: {result.module2_score}")
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from module2.content_continuity import (
    ContinuityReport,
    analyze_continuity,
    continuity_to_score,
)
from module2.noise_ratio import NoiseReport, analyze_noise, noise_ratio_to_score
from module2.scorer import compute_module2_score
from module2.section_coverage import detect_sections, section_coverage_to_score


@dataclass
class SubMetricResult:
    """单个子指标的结果。"""
    score: int
    raw_metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class Module2Result:
    """模块 2 完整评测结果。"""
    company_code: str = ""

    # 子指标
    noise: SubMetricResult = field(default_factory=lambda: SubMetricResult(score=0))
    section: SubMetricResult = field(default_factory=lambda: SubMetricResult(score=0))
    continuity: SubMetricResult = field(default_factory=lambda: SubMetricResult(score=0))

    # 汇总
    module2_score: float = 0.0

    # 诊断
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "company_code": self.company_code,
            "noise_ratio": {
                "score": self.noise.score,
                **self.noise.raw_metrics,
            },
            "section_coverage": {
                "score": self.section.score,
                **self.section.raw_metrics,
            },
            "content_continuity": {
                "score": self.continuity.score,
                **self.continuity.raw_metrics,
            },
            "module2_score": self.module2_score,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class Evaluator:
    """模块 2 评测器。"""

    def evaluate(
        self,
        text: str | Path,
        company_code: str = "",
    ) -> Module2Result:
        """评测单份文本的结构质量。

        Args:
            text: LAS 输出的 markdown 文本 或 report.md 文件路径
            company_code: 股票代码

        Returns:
            Module2Result
        """
        if isinstance(text, Path):
            text_str = text.read_text(encoding="utf-8", errors="replace")
        else:
            text_str = text

        result = Module2Result(company_code=company_code)

        if not text_str.strip():
            result.errors.append("Empty input text")
            return result

        # ---- 子指标 2.1：噪声比率 ----
        noise_report = analyze_noise(text_str)
        result.noise = SubMetricResult(
            score=noise_ratio_to_score(noise_report.noise_ratio),
            raw_metrics={
                "noise_ratio": round(noise_report.noise_ratio, 4),
                "noise_chars": noise_report.noise_chars,
                "total_chars": noise_report.total_chars,
                "noise_lines": noise_report.noise_lines,
                "total_lines": noise_report.total_lines,
                "page_numbers": noise_report.page_number_lines,
                "repeated_headers": noise_report.repeated_header_lines,
                "repeated_header_types": noise_report.repeated_header_types,
                "signatory_lines": noise_report.signatory_lines,
                "audit_lines": noise_report.audit_lines,
                "report": _noise_report_to_dict(noise_report),
            },
        )

        # ---- 子指标 2.2：节段覆盖度 ----
        sections = detect_sections(text_str)
        section_score = section_coverage_to_score(sections)
        missing = [k for k, v in sections.items() if not v]
        result.section = SubMetricResult(
            score=section_score,
            raw_metrics={
                "detected_sections": sections,
                "missing_sections": missing,
            },
        )
        if missing:
            result.warnings.append(f"Missing sections: {', '.join(missing)}")

        # ---- 子指标 2.3：内容连续性 ----
        continuity_report = analyze_continuity(text_str)
        result.continuity = SubMetricResult(
            score=continuity_to_score(continuity_report),
            raw_metrics={
                "avg_block_chars": continuity_report.avg_block_chars,
                "max_block_chars": continuity_report.max_block_chars,
                "max_block_ratio": round(continuity_report.max_block_ratio, 3),
                "clean_blocks": continuity_report.clean_blocks,
                "total_clean_chars": continuity_report.total_clean_chars,
                "noise_break_count": continuity_report.noise_break_count,
            },
        )

        # ---- 汇总 ----
        result.module2_score = compute_module2_score(
            result.noise.score,
            result.section.score,
            result.continuity.score,
        )

        return result


def _noise_report_to_dict(report: NoiseReport) -> dict:
    return {
        "total_lines": report.total_lines,
        "total_chars": report.total_chars,
        "page_number_lines": report.page_number_lines,
        "repeated_header_types": report.repeated_header_types,
        "repeated_header_lines": report.repeated_header_lines,
        "signatory_lines": report.signatory_lines,
        "audit_lines": report.audit_lines,
        "noise_lines": report.noise_lines,
        "noise_chars": report.noise_chars,
        "noise_ratio": round(report.noise_ratio, 4),
    }
