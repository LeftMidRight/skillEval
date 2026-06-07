"""按公司汇总'竖线/数值比'，给无边框表格场景排序，找第二三梯队候选。"""
from __future__ import annotations
import json
import re
from pathlib import Path
import fitz

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / "data" / "FinAR-Bench" / "extracted" / "pdf_data"

RE_THOUSAND = re.compile(r"-?\(?\d{1,3}(?:,\d{3})+(?:\.\d+)?\)?")
RE_DECIMAL2 = re.compile(r"\d+\.\d{2}\b")


def numeric_count(text):
    return len(RE_THOUSAND.findall(text)) + len(RE_DECIMAL2.findall(text))


def v_lines(page):
    v = 0
    try:
        for d in page.get_drawings():
            for item in d.get("items", []):
                if item[0] == "l":
                    p1, p2 = item[1], item[2]
                    if abs(p1.x - p2.x) < 1.5 and abs(p1.y - p2.y) > 10:
                        v += 1
                elif item[0] == "re":
                    v += 2
    except Exception:
        pass
    return v


rows = []
for p in sorted(PDF_DIR.glob("*.pdf")):
    doc = fitz.open(p)
    tot_num = tot_v = 0
    for i in range(doc.page_count):
        page = doc[i]
        tot_num += numeric_count(page.get_text())
        tot_v += v_lines(page)
    doc.close()
    ratio = tot_v / tot_num if tot_num else 999
    rows.append((p.stem, tot_num, tot_v, round(ratio, 3)))

rows.sort(key=lambda x: x[3])
print(f"{'code':>8} {'numeric':>8} {'v_lines':>8} {'ratio':>7}")
print("-" * 36)
for code, n, v, r in rows[:25]:
    print(f"{code:>8} {n:>8} {v:>8} {r:>7}")

out = ROOT / "output" / "scene_selection" / "borderless_rank.json"
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(
    [{"code": c, "numeric": n, "v_lines": v, "ratio": r} for c, n, v, r in rows],
    ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\nSaved: {out}")
