"""扫描 FinAR-Bench 100 份 PDF，提取各场景挑选所需的量化信号。

输出: output/scene_selection/finar_signals.json

信号说明：
- pages: 物理页数（用于 S5 超长文档）
- numeric_tokens / numeric_density: 金额型数值 token 总数与每页密度（用于 S1 密集数值）
- bracket_negatives: 括号负数 (1,234.56) 出现次数（用于 E2 特殊数值）
- minus_negatives: 负号数值 -1,234.56 出现次数
- units: 出现的金额单位集合（元/千元/万元/亿元）（用于 E2 多单位）
- statement_pages: 三大合并报表标题命中的页号
- table_pages: 高数值密度页（疑似表格页）的页号
- cross_page_score: 三大报表跨物理页的总跨度（用于 S3 跨页表格）
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import fitz  # PyMuPDF

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = PROJECT_ROOT / "data" / "FinAR-Bench" / "extracted" / "pdf_data"
OUT_DIR = PROJECT_ROOT / "output" / "scene_selection"

# 金额型数值：带千分位逗号，或带两位小数
RE_THOUSAND = re.compile(r"-?\(?\d{1,3}(?:,\d{3})+(?:\.\d+)?\)?")
RE_DECIMAL2 = re.compile(r"\d+\.\d{2}\b")
RE_BRACKET_NEG = re.compile(r"\(\s*\d[\d,]*\.?\d*\s*\)")
RE_MINUS_NEG = re.compile(r"-\s*\d{1,3}(?:,\d{3})+(?:\.\d+)?")

UNIT_PATTERNS = {
    "元": re.compile(r"单位\s*[:：]\s*(?:人民币)?元"),
    "千元": re.compile(r"单位\s*[:：]\s*(?:人民币)?千元"),
    "万元": re.compile(r"(?:单位\s*[:：]\s*(?:人民币)?万元)|万元"),
    "亿元": re.compile(r"亿元"),
}

# 三大合并报表标题（去空格后匹配）
STATEMENT_TITLES = {
    "balance_sheet": ["合并资产负债表", "资产负债表"],
    "income_stmt": ["合并利润表", "利润表"],
    "cash_flow": ["合并现金流量表", "现金流量表"],
}

NUMERIC_PAGE_THRESHOLD = 15  # 一页金额 token 数 ≥ 该值视为表格页


def count_numeric_tokens(text: str) -> int:
    return len(RE_THOUSAND.findall(text)) + len(RE_DECIMAL2.findall(text))


def analyze_pdf(path: Path) -> dict:
    doc = fitz.open(path)
    pages_text = [doc[i].get_text() for i in range(doc.page_count)]
    doc.close()

    page_count = len(pages_text)
    full_text = "\n".join(pages_text)
    nospace = full_text.replace(" ", "").replace("\u3000", "")

    numeric_tokens = sum(count_numeric_tokens(t) for t in pages_text)
    bracket_neg = len(RE_BRACKET_NEG.findall(full_text))
    minus_neg = len(RE_MINUS_NEG.findall(full_text))

    units = sorted({u for u, pat in UNIT_PATTERNS.items() if pat.search(nospace)})

    # 表格页（高数值密度）
    table_pages = [i for i, t in enumerate(pages_text) if count_numeric_tokens(t) >= NUMERIC_PAGE_THRESHOLD]

    # 报表标题命中页
    statement_pages: dict[str, list[int]] = {}
    for key, titles in STATEMENT_TITLES.items():
        hits = []
        for i, t in enumerate(pages_text):
            tt = t.replace(" ", "").replace("\u3000", "")
            if any(title in tt for title in titles):
                hits.append(i)
        statement_pages[key] = hits

    # 跨页跨度：连续表格页的最长连段长度之和（粗略代理跨页拼接难度）
    cross_page_score = _consecutive_table_span(table_pages)

    return {
        "pages": page_count,
        "numeric_tokens": numeric_tokens,
        "numeric_density": round(numeric_tokens / page_count, 1) if page_count else 0,
        "bracket_negatives": bracket_neg,
        "minus_negatives": minus_neg,
        "units": units,
        "n_table_pages": len(table_pages),
        "table_pages": table_pages,
        "statement_pages": statement_pages,
        "cross_page_score": cross_page_score,
    }


def _consecutive_table_span(table_pages: list[int]) -> int:
    """统计连续表格页构成的所有连段（长度≥2）的总跨度，作为跨页拼接难度代理。"""
    if not table_pages:
        return 0
    spans = []
    run = 1
    for prev, cur in zip(table_pages, table_pages[1:]):
        if cur == prev + 1:
            run += 1
        else:
            if run >= 2:
                spans.append(run)
            run = 1
    if run >= 2:
        spans.append(run)
    return sum(spans)


def main() -> int:
    if not PDF_DIR.is_dir():
        print(f"[ERROR] PDF dir not found: {PDF_DIR}")
        return 1

    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    print(f"Scanning {len(pdfs)} PDFs in {PDF_DIR}")

    signals: dict[str, dict] = {}
    for i, p in enumerate(pdfs, 1):
        code = p.stem
        try:
            signals[code] = analyze_pdf(p)
        except Exception as e:  # noqa: BLE001
            signals[code] = {"error": str(e)}
            print(f"  [{code}] ERROR {e}")
        if i % 20 == 0:
            print(f"  ...{i}/{len(pdfs)}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "finar_signals.json"
    out_path.write_text(json.dumps(signals, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved signals: {out_path}")

    # 排序摘要
    valid = {c: s for c, s in signals.items() if "error" not in s}

    def top(key, n=12, reverse=True):
        return sorted(valid.items(), key=lambda kv: kv[1].get(key, 0), reverse=reverse)[:n]

    print("\n== S5 超长文档 (pages 降序) ==")
    for c, s in top("pages"):
        print(f"  {c}  pages={s['pages']:>3}  tables={s['n_table_pages']}")

    print("\n== S3 跨页表格 (cross_page_score 降序) ==")
    for c, s in top("cross_page_score"):
        print(f"  {c}  cps={s['cross_page_score']:>3}  pages={s['pages']:>3}  table_pages={s['table_pages']}")

    print("\n== S1 密集数值 (numeric_density 降序) ==")
    for c, s in top("numeric_density"):
        print(f"  {c}  density={s['numeric_density']:>6}  tokens={s['numeric_tokens']:>4}  pages={s['pages']}")

    print("\n== E2 括号负数 (bracket_negatives 降序) ==")
    for c, s in top("bracket_negatives"):
        print(f"  {c}  bracket_neg={s['bracket_negatives']:>3}  minus_neg={s['minus_negatives']:>3}  units={s['units']}")

    # 单位分布
    from collections import Counter
    unit_counter = Counter()
    for s in valid.values():
        for u in s.get("units", []):
            unit_counter[u] += 1
    print("\n== 单位出现公司数 ==")
    for u, n in unit_counter.most_common():
        print(f"  {u}: {n}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
