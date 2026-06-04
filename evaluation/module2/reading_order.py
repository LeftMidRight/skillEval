"""Module 2.2: 阅读顺序（LLM-as-Judge）。

双级评测：
- 第一级：页内阅读顺序（Per-Page）
- 第二级：跨页连续性（Cross-Page）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import fitz  # PyMuPDF

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
from evaluation.llm_client import LLMClient


# ============================================================================
# Prompt 模板
# ============================================================================

PAGE_LEVEL_PROMPT = """你是一位文档解析质量评审专家。我会提供：
- 一份 PDF 的某一页截图
- 解析系统对该页输出的文字内容

请对该页的阅读顺序做以下三维度的独立判断：

【维度 A：流向一致性】
规则：中文文档应遵循 从上到下 的阅读顺序。
请逐段检查输出文字是否按照截图中的视觉位置（从上到下）排列。
- 截图最上方的内容是否在输出中最先出现？
- 截图最下方的内容是否在输出中最后出现？
- 中间部分有无明显的位置错乱？

【维度 B：元素边界完整性】
规则：标题、正文段落、表格应各自完整连续，不被其他元素从中间切断。
请检查：
- 表格是否被页码/页眉行从中间打断？
- 一个段落是否被拆成两段，中间插入不相关内容？
- 标题和紧随其下的正文是否连在一起未被分隔？

【维度 C：噪声侵入】
规则：页面装饰元素（页码、重复页眉、签名栏）不应插入正文/表格流中。
以下为正常的"噪声在正文之后"：
  正文 → 71 / 212 → 2023 年年度报告
以下为异常的"噪声侵入正文"：
  流动资产：   ← 表格行
  71 / 212    ← 页码插入表格中间
  货币资金    ← 表格行继续

### 输出格式（严格 JSON，不要其他文字）
{
  "page_index": <页码>,
  "flow_consistency": {
    "score": <1-5>,
    "reason": "<若 <5 分，指出第几个文字块位置错乱，否则填 '无'>"
  },
  "element_integrity": {
    "score": <1-5>,
    "issues": ["<具体问题描述，引用原文前10个字定位>"]
  },
  "noise_intrusion": {
    "score": <1-5>,
    "intruded_lines": ["<被侵入位置的前后文字各10字>"]
  },
  "overall_pass": <true/false>
}

评分尺度：
5 = 完全正确，无任何顺序问题
4 = 有轻微瑕疵但不影响阅读
3 = 有可察觉的顺序问题但不影响理解
2 = 有明显顺序错误，影响信息获取
1 = 严重乱序，无法正常阅读"""


CROSS_PAGE_PROMPT = """你是一位文档解析质量评审专家。我会提供两个连续页面的截图和对应的解析输出。

请判断：前一页末尾和后一页开头的内容是否自然连续？

检查要点：
1. 前一页的最后一段/表格是否在后一页自然接续（不被切断）
2. 后一页开头是否有前页已出现过的重复内容（表头复用不算重复）
3. 两页之间不应出现页码/页眉作为正文内容的间隔

### 输出格式（严格 JSON）
{
  "page_pair": "<N>_<N+1>",
  "continuous": <true/false>,
  "issue_type": "<none / truncation / repetition / noise_gap>",
  "detail": "<如有问题，描述具体表现；否则填'无'>"
}"""


# ============================================================================
# 页面渲染
# ============================================================================

def render_page(pdf_path: str | Path, page_idx: int, output_dir: str | Path, dpi: int = 150) -> Path:
    """渲染 PDF 单页为 PNG。

    Args:
        pdf_path: PDF 文件路径。
        page_idx: 页码（0-indexed）。
        output_dir: 输出目录。
        dpi: 渲染 DPI。

    Returns:
        输出的 PNG 文件路径。
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    doc = fitz.open(pdf_path)
    page = doc[page_idx]
    pix = page.get_pixmap(dpi=dpi)
    output_path = output_dir / f"page_{page_idx + 1:03d}.png"
    pix.save(str(output_path))
    doc.close()
    return output_path


# ============================================================================
# 评测函数
# ============================================================================

def evaluate_page_reading_order(
    llm: LLMClient,
    image_path: Path,
    page_md: str,
    page_index: int,
) -> dict[str, Any]:
    """评测单页阅读顺序。

    Args:
        llm: LLM 客户端。
        image_path: 渲染后的页面图片路径。
        page_md: LAS 对该页的输出 markdown。
        page_index: 页码（0-indexed）。

    Returns:
        LLM 评判结果 dict。
    """
    prompt = PAGE_LEVEL_PROMPT + f"\n\n当前页码：{page_index + 1}\n\n解析输出文字：\n{page_md[:4000]}"
    response = llm.chat_with_image(image_path, prompt)
    return llm.extract_json(response)


def evaluate_cross_page_continuity_llm(
    llm: LLMClient,
    image_path_a: Path,
    image_path_b: Path,
    page_md_a: str,
    page_md_b: str,
    page_a: int,
    page_b: int,
) -> dict[str, Any]:
    """评测跨页连续性。

    Args:
        llm: LLM 客户端。
        image_path_a/b: 两页的渲染图片。
        page_md_a/b: 两页的 LAS 输出。
        page_a/b: 页码（0-indexed）。

    Returns:
        LLM 评判结果 dict。
    """
    # 合并两张图片为描述，发送两页内容
    prompt = (
        CROSS_PAGE_PROMPT
        + f"\n\n前一页（第{page_a + 1}页）解析输出：\n{page_md_a[-1500:]}"
        + f"\n\n后一页（第{page_b + 1}页）解析输出：\n{page_md_b[:1500]}"
    )

    # 对于双页判断，分别发送两张图片
    # 使用 base64 编码两张图片
    import base64
    images_content = []
    for ip in [image_path_a, image_path_b]:
        with open(ip, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        ext = ip.suffix.lower()
        mime = "image/png" if ext == ".png" else "image/jpeg"
        images_content.append({
            "type": "input_image",
            "image_url": f"data:{mime};base64,{data}",
        })

    messages = [{
        "role": "user",
        "content": images_content + [{"type": "input_text", "text": prompt}],
    }]

    response = llm.chat(messages)
    return llm.extract_json(response)


def evaluate_reading_order(
    llm: LLMClient,
    company_code: str,
    las_results_dir: str | Path | None = None,
    pdf_dir: str | Path | None = None,
    render_dir: str | Path | None = None,
    skip_cross_page: bool = False,
) -> dict[str, Any]:
    """对一家公司执行完整阅读顺序评测。

    Args:
        llm: LLM 客户端。
        company_code: 股票代码。
        las_results_dir: LAS 解析结果目录。
        pdf_dir: PDF 文件目录。
        render_dir: 渲染图片输出目录。
        skip_cross_page: 跳过跨页评测。

    Returns:
        {
            "company_code": str,
            "page_level": [{...}],
            "cross_page": [{...}],
            "summary": {...},
        }
    """
    if las_results_dir is None:
        las_results_dir = PROJECT_ROOT / "output" / "las_results"
    if pdf_dir is None:
        pdf_dir = PROJECT_ROOT / "data" / "FinAR-Bench" / "extracted" / "pdf_data"
    if render_dir is None:
        render_dir = PROJECT_ROOT / "output" / "eval_renders" / company_code

    # 加载 LAS 响应（含 page_md）
    las_resp_path = Path(las_results_dir) / company_code / "las_response.json"
    with open(las_resp_path, "r", encoding="utf-8") as f:
        las_resp = json.load(f)

    detail = las_resp.get("poll_response", {}).get("data", {}).get("detail", [])
    if not detail:
        raise ValueError("No detail in LAS response")

    pdf_path = Path(pdf_dir) / f"{company_code}.pdf"
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # ---- 第一级：页内评测 ----
    page_results: list[dict[str, Any]] = []
    for page_info in detail:
        page_idx = page_info.get("page_id", 0) - 1  # LAS 的 page_id 从 1 开始
        if page_idx < 0:
            page_idx = 0
        page_md = page_info.get("page_md", "").strip()
        if not page_md:
            continue

        # 渲染
        image_path = render_page(pdf_path, page_idx, Path(render_dir) / "pages")
        # 评测
        try:
            result = evaluate_page_reading_order(llm, image_path, page_md, page_idx)
            page_results.append(result)
        except Exception as e:
            page_results.append({
                "page_index": page_idx,
                "error": str(e),
                "overall_pass": False,
            })

    # ---- 第二级：跨页评测 ----
    cross_results: list[dict[str, Any]] = []
    if not skip_cross_page and len(detail) >= 2:
        for i in range(len(detail) - 1):
            page_md_a = detail[i].get("page_md", "").strip()
            page_md_b = detail[i + 1].get("page_md", "").strip()
            if not page_md_a or not page_md_b:
                continue

            page_a = detail[i].get("page_id", i + 1) - 1
            page_b = detail[i + 1].get("page_id", i + 2) - 1
            img_a = Path(render_dir) / "pages" / f"page_{page_a + 1:03d}.png"
            img_b = Path(render_dir) / "pages" / f"page_{page_b + 1:03d}.png"

            try:
                result = evaluate_cross_page_continuity_llm(
                    llm, img_a, img_b, page_md_a, page_md_b, page_a, page_b
                )
                cross_results.append(result)
            except Exception as e:
                cross_results.append({
                    "page_pair": f"{page_a}_{page_b}",
                    "error": str(e),
                })

    # ---- 汇总 ----
    total_pages = len(page_results)
    passed_pages = sum(1 for r in page_results if r.get("overall_pass", False))

    flow_scores = [r.get("flow_consistency", {}).get("score", 0) for r in page_results if "error" not in r]
    integrity_scores = [r.get("element_integrity", {}).get("score", 0) for r in page_results if "error" not in r]
    noise_scores = [r.get("noise_intrusion", {}).get("score", 0) for r in page_results if "error" not in r]

    total_cross = len(cross_results)
    continuous_cross = sum(1 for r in cross_results if r.get("continuous", False))

    summary = {
        "total_pages": total_pages,
        "passed_pages": passed_pages,
        "pass_rate": round(passed_pages / total_pages, 3) if total_pages > 0 else 0.0,
        "avg_flow_score": round(sum(flow_scores) / len(flow_scores), 1) if flow_scores else 0.0,
        "avg_integrity_score": round(sum(integrity_scores) / len(integrity_scores), 1) if integrity_scores else 0.0,
        "avg_noise_score": round(sum(noise_scores) / len(noise_scores), 1) if noise_scores else 0.0,
        "noise_intruded_pages": sum(1 for r in page_results if r.get("noise_intrusion", {}).get("score", 5) < 5),
        "cross_page_pairs": total_cross,
        "cross_page_continuous": continuous_cross,
        "cross_page_rate": round(continuous_cross / total_cross, 3) if total_cross > 0 else 0.0,
    }

    return {
        "company_code": company_code,
        "page_level": page_results,
        "cross_page": cross_results,
        "summary": summary,
    }
