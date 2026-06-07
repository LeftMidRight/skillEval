"""构建 FinAR 三场景评测集（共 22 份 PDF，三类互不重复）。

场景（课题金融场景，FinAR 可覆盖的 3 个）：
- cross_page_tables   跨页表格     10 份（cross_page_score 最高）
- dense_numerical     密集数值     10 份（numeric_density 最高）
- borderless_tables   无边框表格    2 份（竖线/数值比最低：601555 / 601009）

数据来源：FinAR-Bench（中文 A 股 2023 年报财务报表节选）
Ground Truth：XBRL（FinAR-Bench dev.txt / test.txt）

产出：
- data/eval_dataset/<scene>/<code>.pdf
- data/eval_dataset/<scene>/selection.json
- data/eval_dataset/_selection.json （主清单）
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EVAL_DIR = PROJECT_ROOT / "data" / "eval_dataset"
FINAR_PDF_DIR = PROJECT_ROOT / "data" / "FinAR-Bench" / "extracted" / "pdf_data"
SIGNALS_PATH = PROJECT_ROOT / "output" / "scene_selection" / "finar_signals.json"
PICK_PATH = PROJECT_ROOT / "output" / "scene_selection" / "pick30.json"

SCENES = {
    "cross_page_tables": {
        "key": "cross_page_tables",
        "title": "跨页表格",
        "signal": "cross_page_score（连续表格页跨度）最高",
        "primary_metric": "cross_page_score",
    },
    "dense_numerical": {
        "key": "dense_numerical",
        "title": "密集数值提取",
        "signal": "numeric_density（每页金额型数值数）最高",
        "primary_metric": "numeric_density",
    },
    "borderless_tables": {
        "key": "borderless_tables",
        "title": "无边框表格",
        "signal": "竖线/数值比最低（少边框/无边框）",
        "primary_metric": "borderless",
    },
}


def main() -> int:
    signals = json.loads(SIGNALS_PATH.read_text(encoding="utf-8"))
    picks = json.loads(PICK_PATH.read_text(encoding="utf-8"))

    pick_map = {
        "cross_page_tables": picks["cross_page_tables"],
        "dense_numerical": picks["dense_numerical"],
        "borderless_tables": picks["borderless_tables"],
    }

    master: dict = {}
    total = 0
    for scene, codes in pick_map.items():
        cfg = SCENES[scene]
        scene_dir = EVAL_DIR / scene
        scene_dir.mkdir(parents=True, exist_ok=True)
        # 清掉旧 PDF（仅本目录）
        for old in scene_dir.glob("*.pdf"):
            old.unlink()

        items = []
        for code in codes:
            src = FINAR_PDF_DIR / f"{code}.pdf"
            if not src.exists():
                print(f"  [WARN] {scene}: missing {code}.pdf")
                continue
            shutil.copy2(src, scene_dir / f"{code}.pdf")
            s = signals.get(code, {})
            items.append({
                "code": code,
                "file": f"{code}.pdf",
                "pages": s.get("pages"),
                "numeric_density": s.get("numeric_density"),
                "cross_page_score": s.get("cross_page_score"),
                "bracket_negatives": s.get("bracket_negatives"),
                "units": s.get("units"),
            })

        selection = {
            "scene": scene,
            "title": cfg["title"],
            "source": "FinAR-Bench",
            "ground_truth": "XBRL (FinAR-Bench dev.txt/test.txt)",
            "selection_signal": cfg["signal"],
            "primary_metric": cfg["primary_metric"],
            "count": len(items),
            "items": items,
        }
        (scene_dir / "selection.json").write_text(
            json.dumps(selection, ensure_ascii=False, indent=2), encoding="utf-8")
        master[scene] = {"title": cfg["title"], "count": len(items),
                         "codes": [it["code"] for it in items]}
        total += len(items)
        print(f"  {scene} ({cfg['title']}): {len(items)} PDFs")

    # 互斥校验
    all_codes = [c for v in master.values() for c in v["codes"]]
    assert len(all_codes) == len(set(all_codes)), "三类存在重复代码！"

    summary = {
        "description": "FinAR 三场景评测集（课题金融场景）",
        "source": "FinAR-Bench (中文 A 股 2023 年报财务报表节选)",
        "ground_truth": "XBRL",
        "total_pdf_count": total,
        "scenes_not_overlapping": True,
        "scenes": master,
    }
    (EVAL_DIR / "_selection.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n总计 {total} 份 PDF，三类互不重复 ✓")
    print(f"主清单: {EVAL_DIR / '_selection.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
