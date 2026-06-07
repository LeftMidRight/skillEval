"""定位 FinAR 中疑似无边框表格 / 多栏排版的具体页面，并渲染候选页为 PNG。

无边框表格判据（页级）：
- 该页有较多金额型数值（≥15 个）→ 说明是表格页
- 但竖线条很少（v_lines 低）→ 说明没有竖线分隔 → 疑似无边框

多栏判据（页级，严格）：
- 把页面竖切成左右两半，各自统计文本块
- 两侧都有较多文本块（各≥4）
- 存在明显的中缝空白带（中线附近 x 区间几乎没有文字）
- 且该页不是高数值表格页（排除"项目在左数字在右"的报表误判）
"""
from __future__ import annotations
import json
import re
from pathlib import Path
import fitz

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "data" / "FinAR-Bench" / "extracted" / "pdf_data"
OUT = ROOT / "output" / "page_renders"
OUT.mkdir(parents=True, exist_ok=True)

RE_THOUSAND = re.compile(r"-?\(?\d{1,3}(?:,\d{3})+(?:\.\d+)?\)?")
RE_DECIMAL2 = re.compile(r"\d+\.\d{2}\b")


def numeric_count(text: str) -> int:
    return len(RE_THOUSAND.findall(text)) + len(RE_DECIMAL2.findall(text))


def page_v_lines(page) -> int:
    v = 0
    try:
        drawings = page.get_drawings()
    except Exception:
        return 0
    for d in drawings:
        for item in d.get("items", []):
            if item[0] == "l":
                p1, p2 = item[1], item[2]
                if abs(p1.x - p2.x) < 1.5 and abs(p1.y - p2.y) > 10:
                    v += 1
            elif item[0] == "re":
                v += 2
    return v


def detect_multicolumn(page):
    """严格多栏检测：返回 (is_multi, detail)。

    真多栏正文特征：左右两栏都是【大段文字】，且【数值很少】（区别于报表的
    项目名在左、数字在右）。报表虽然左右分簇，但数值密集且行跨中缝，需排除。
    """
    blocks = [b for b in page.get_text("blocks") if b[6] == 0 and b[4].strip()]
    if len(blocks) < 8:
        return False, {"reason": "too_few_blocks", "n": len(blocks)}
    text = page.get_text()
    nnum = numeric_count(text)
    # 多栏正文不应有大量金额数值；报表页数值密集，直接排除
    if nnum >= 12:
        return False, {"reason": "numeric_heavy(table)", "numeric": nnum}
    w = page.rect.width
    mid = w / 2
    band = w * 0.05
    left = [b for b in blocks if (b[0] + b[2]) / 2 < mid]
    right = [b for b in blocks if (b[0] + b[2]) / 2 >= mid]
    crossing = [b for b in blocks if b[0] < mid - band and b[2] > mid + band]
    if len(left) < 4 or len(right) < 4:
        return False, {"reason": "one_side_sparse", "left": len(left), "right": len(right)}
    cross_ratio = len(crossing) / len(blocks)
    if cross_ratio > 0.2:
        return False, {"reason": "too_many_crossing", "cross_ratio": round(cross_ratio, 2)}
    # 左右两栏的平均文字长度都要够大（大段文字而非短标签）
    avg_len_left = sum(len(b[4]) for b in left) / len(left)
    avg_len_right = sum(len(b[4]) for b in right) / len(right)
    if avg_len_left < 30 or avg_len_right < 30:
        return False, {"reason": "short_text(labels)",
                       "avg_l": round(avg_len_left), "avg_r": round(avg_len_right)}
    return True, {"left": len(left), "right": len(right),
                  "cross_ratio": round(cross_ratio, 2), "numeric": nnum,
                  "avg_l": round(avg_len_left), "avg_r": round(avg_len_right)}


def render(page, tag):
    pix = page.get_pixmap(matrix=fitz.Matrix(1.6, 1.6))
    path = OUT / f"{tag}.png"
    pix.save(path)
    return path


def main():
    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    borderless = []   # (code, page, numeric, v_lines)
    multicol = []     # (code, page, detail)

    for p in pdfs:
        code = p.stem
        doc = fitz.open(p)
        for i in range(doc.page_count):
            page = doc[i]
            text = page.get_text()
            nnum = numeric_count(text)
            vl = page_v_lines(page)
            # 无边框表格候选：高数值表格页，但竖线相对数值少
            # 用"竖线/数值比"分级：比值越低越像无边框
            if nnum >= 20:
                ratio = vl / nnum
                if ratio < 0.5:  # 竖线远少于数值项
                    borderless.append((code, i, nnum, vl, round(ratio, 2)))
            # 多栏候选：严格判据
            is_multi, detail = detect_multicolumn(page)
            if is_multi:
                multicol.append((code, i, nnum, detail))
        doc.close()

    print("=" * 60)
    print(f"疑似【无边框表格】页：{len(borderless)} 个（竖线/数值比 < 0.5）")
    print("=" * 60)
    for code, pg, nnum, vl, ratio in sorted(borderless, key=lambda x: x[4])[:20]:
        print(f"  {code} p{pg}: 数值={nnum} 竖线={vl} 比值={ratio}")

    print("\n" + "=" * 60)
    print(f"疑似【多栏排版】页：{len(multicol)} 个")
    print("=" * 60)
    for code, pg, nnum, detail in multicol[:30]:
        print(f"  {code} p{pg}: 数值={nnum} {detail}")

    # 渲染候选（无边框取比值最低的前若干，多栏全渲）
    rendered = []
    seen = set()
    for code, pg, nnum, vl, ratio in sorted(borderless, key=lambda x: x[4])[:8]:
        key = (code, pg)
        if key in seen:
            continue
        seen.add(key)
        doc = fitz.open(PDF_DIR / f"{code}.pdf")
        path = render(doc[pg], f"borderless_{code}_p{pg}")
        doc.close()
        rendered.append(str(path.name))

    for code, pg, nnum, detail in multicol[:8]:
        key = ("mc", code, pg)
        if key in seen:
            continue
        seen.add(key)
        doc = fitz.open(PDF_DIR / f"{code}.pdf")
        path = render(doc[pg], f"multicol_{code}_p{pg}")
        doc.close()
        rendered.append(str(path.name))

    summary = {
        "borderless_candidates": [
            {"code": c, "page": pg, "numeric": n, "v_lines": v, "ratio": r}
            for c, pg, n, v, r in sorted(borderless, key=lambda x: x[4])
        ],
        "multicolumn_candidates": [
            {"code": c, "page": pg, "numeric": n, "detail": d}
            for c, pg, n, d in multicol
        ],
        "rendered_pngs": rendered,
    }
    (OUT / "candidates.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n渲染了 {len(rendered)} 张 PNG 到 {OUT}")
    print("候选清单: ", OUT / "candidates.json")


if __name__ == "__main__":
    main()
