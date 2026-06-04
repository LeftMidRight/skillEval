"""Module 1.1: 文本准确率（CER）。

以 6 种开源解析器为参照，计算 LAS 输出与各解析器的中位 CER。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# 复用 module1 的文本清洗和 CER 计算
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from module1.text_accuracy import compute_cer
from module1.utils import normalize_text_for_cer, load_reference_text

REFERENCE_PARSERS = ["mineru", "pdfplumber", "pymupdf", "pypdf", "pdfminer", "pdftotext"]


def evaluate_text_accuracy(
    las_markdown: str,
    company_code: str,
    parser_output_dir: str | Path | None = None,
) -> dict[str, Any]:
    """计算 LAS 与 6 种开源解析器的 CER。

    Args:
        las_markdown: LAS 输出的 markdown 文本（合并跨页表格后的）。
        company_code: 股票代码，如 "603421"。
        parser_output_dir: 6 种解析器 txt 输出的根目录。
            默认使用 FinAR-Bench 路径。

    Returns:
        {
            "cer": {parser: value, ...},
            "median_cer": float,
            "mineru_cer": float,
            "mineru_baseline": {parser: value, ...},  # Mineru 与其余解析器的 CER
            "mineru_median_cer": float,                 # Mineru 的中位 CER（作为基线）
        }
    """
    if parser_output_dir is None:
        parser_output_dir = (
            PROJECT_ROOT / "data" / "FinAR-Bench" / "extracted"
            / "pdf_extractor_result" / "txt_output"
        )

    las_clean = normalize_text_for_cer(las_markdown)

    # LAS vs 各解析器
    cer_results: dict[str, float] = {}
    for parser in REFERENCE_PARSERS:
        ref_text = load_reference_text(
            Path(parser_output_dir) / parser, company_code
        )
        if ref_text is None:
            cer_results[parser] = float("nan")
            continue

        ref_clean = normalize_text_for_cer(ref_text)
        cer = compute_cer(ref_clean, las_clean)
        cer_results[parser] = round(cer, 3)

    # 中位 CER（排除 nan）
    valid_cers = [v for v in cer_results.values() if v == v]
    median_cer = round(sorted(valid_cers)[len(valid_cers) // 2], 3) if valid_cers else float("nan")

    # Mineru 基线：Mineru vs 其余 5 解析器
    mineru_text = load_reference_text(
        Path(parser_output_dir) / "mineru", company_code
    )
    mineru_baseline: dict[str, float] = {}
    if mineru_text:
        mineru_clean = normalize_text_for_cer(mineru_text)
        for parser in REFERENCE_PARSERS:
            if parser == "mineru":
                continue
            ref_text = load_reference_text(
                Path(parser_output_dir) / parser, company_code
            )
            if ref_text is None:
                mineru_baseline[parser] = float("nan")
                continue
            ref_clean = normalize_text_for_cer(ref_text)
            cer = compute_cer(ref_clean, mineru_clean)
            mineru_baseline[parser] = round(cer, 3)

    mineru_valid = [v for v in mineru_baseline.values() if v == v]
    mineru_median = round(sorted(mineru_valid)[len(mineru_valid) // 2], 3) if mineru_valid else float("nan")

    return {
        "cer": cer_results,
        "median_cer": median_cer,
        "mineru_cer": cer_results.get("mineru", float("nan")),
        "mineru_baseline": mineru_baseline,
        "mineru_median_cer": mineru_median,
    }
