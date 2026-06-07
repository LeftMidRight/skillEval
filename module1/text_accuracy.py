"""子指标 1：文本准确率（CER - Character Error Rate）。

参照系：6 个已有解析器的输出（Mineru 为主参照）。
"""

from __future__ import annotations

from pathlib import Path

from module1.utils import clean_text, load_reference_text


def compute_cer(reference: str, hypothesis: str) -> float:
    """计算 Character Error Rate。

    CER = (插入 + 删除 + 替换) / |reference|

    短文本用精确 Levenshtein；长文本用块级对齐（difflib）。

    Args:
        reference: 参照文本
        hypothesis: 待评测文本

    Returns:
        CER: 0.0 ~ 1.0 (或更高，如果假设比参照长很多)
    """
    ref = clean_text(reference)
    hyp = clean_text(hypothesis)

    if not ref:
        return 1.0 if hyp else 0.0
    if not hyp:
        return 1.0

    # 短文本：精确 Levenshtein
    if len(ref) < 3000 and len(hyp) < 3000:
        return _levenshtein_cer(ref, hyp)

    # 长文本：块级近似
    return _block_cer(ref, hyp)


def _levenshtein_cer(ref: str, hyp: str) -> float:
    """O(n*m) Levenshtein —— 仅用于短文本。"""
    len_ref = len(ref)
    len_hyp = len(hyp)

    prev = list(range(len_hyp + 1))
    curr = [0] * (len_hyp + 1)

    for i in range(1, len_ref + 1):
        curr[0] = i
        for j in range(1, len_hyp + 1):
            if ref[i - 1] == hyp[j - 1]:
                curr[j] = prev[j - 1]
            else:
                curr[j] = 1 + min(prev[j], curr[j - 1], prev[j - 1])
        prev, curr = curr, prev

    return prev[len_hyp] / len_ref


def _block_cer(ref: str, hyp: str) -> float:
    """长文本 CER：用 difflib 找匹配块，在非匹配块内做精确 CER。

    将文本按行分组为块，用 SequenceMatcher 快速定位匹配/不匹配区域，
    只对 replace 块做精确 Levenshtein。
    """
    import difflib

    # 按行分块
    ref_blocks = _aggregate_lines(ref.split("\n"), target_size=1000)
    hyp_blocks = _aggregate_lines(hyp.split("\n"), target_size=1000)

    matcher = difflib.SequenceMatcher(None, ref_blocks, hyp_blocks)

    total_errors = 0.0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        elif tag in ("delete",):
            total_errors += sum(len(b) for b in ref_blocks[i1:i2])
        elif tag in ("insert",):
            total_errors += sum(len(b) for b in hyp_blocks[j1:j2])
        elif tag == "replace":
            ref_seg = "\n".join(ref_blocks[i1:i2])
            hyp_seg = "\n".join(hyp_blocks[j1:j2])
            # 小段用精确 CER，大段用 ratio 近似
            if len(ref_seg) < 5000 and len(hyp_seg) < 5000:
                total_errors += _levenshtein_cer(ref_seg, hyp_seg) * len(ref_seg)
            else:
                # 大段：用 difflib ratio 近似
                seg_ratio = difflib.SequenceMatcher(None, ref_seg, hyp_seg).ratio()
                total_errors += (1.0 - seg_ratio) * len(ref_seg)

    return total_errors / len(ref) if ref else 1.0


def _aggregate_lines(lines: list[str], target_size: int = 1500) -> list[str]:
    """将短行聚合为约 target_size 字符的块。"""
    blocks: list[str] = []
    buf: list[str] = []
    buf_len = 0
    for line in lines:
        buf.append(line)
        buf_len += len(line)
        if buf_len >= target_size:
            blocks.append("\n".join(buf))
            buf = []
            buf_len = 0
    if buf:
        blocks.append("\n".join(buf))
    return blocks


def compute_cer_vs_all(
    las_markdown: str,
    reference_texts: dict[str, str],  # parser_name → text
) -> dict[str, float]:
    """计算 LAS 与每个参照解析器的 CER。

    Returns:
        {parser_name: cer, ...}
    """
    results: dict[str, float] = {}
    for name, text in reference_texts.items():
        if text:
            results[name] = compute_cer(text, las_markdown)
        else:
            results[name] = float("nan")
    return results


def compute_pairwise_cer_matrix(
    texts: dict[str, str],  # parser_name → text
) -> dict[str, dict[str, float]]:
    """计算所有解析器两两之间的 CER 矩阵。

    Returns:
        {parser_a: {parser_b: cer, ...}, ...}
    """
    names = list(texts.keys())
    matrix: dict[str, dict[str, float]] = {}
    for a in names:
        matrix[a] = {}
        for b in names:
            if a == b:
                matrix[a][b] = 0.0
            else:
                matrix[a][b] = compute_cer(texts[b], texts[a])
    return matrix


def evaluate_text_accuracy(
    las_markdown: str,
    reference_dir: str | Path,
    company_code: str,
) -> dict:
    """评估 LAS 文本准确率。

    Args:
        las_markdown: LAS 输出的完整 markdown
        reference_dir: 解析器输出根目录 (extracted/pdf_extractor_result/txt_output/)
        company_code: 股票代码

    Returns:
        {
            "cers": {parser_name: cer, ...},
            "median_cer": float,
            "mineru_cer": float | None,
            "cer_vs_mineru": float | None,
            "reference_count": int,
        }
    """
    ref_dir = Path(reference_dir)
    parsers = ["mineru", "pdfminer", "pdfplumber", "pdftotext", "pymupdf", "pypdf"]

    reference_texts: dict[str, str] = {}
    for parser in parsers:
        parser_dir = ref_dir / parser
        if parser_dir.is_dir():
            text = load_reference_text(parser_dir, company_code)
            if text:
                reference_texts[parser] = text

    cers = compute_cer_vs_all(las_markdown, reference_texts)

    # 取中位 CER 作为稳健估计
    valid_cers = [v for v in cers.values() if v == v]  # filter NaN
    median_cer = sorted(valid_cers)[len(valid_cers) // 2] if valid_cers else float("nan")

    return {
        "cers": cers,
        "median_cer": median_cer,
        "mineru_cer": cers.get("mineru", None),
        "reference_count": len(valid_cers),
    }
