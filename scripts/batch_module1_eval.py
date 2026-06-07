"""批量评测：对 25 份 LAS 输出跑模块 1 评测，输出汇总。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from module1.evaluator import Evaluator

STOCK_CODES = [
    "600064", "600070", "600082", "600083", "600100",
    "600114", "600130", "600133", "600168", "600193",
    "600225", "600322", "600569", "600597", "600626",
    "600933", "603201", "603228", "603256", "603299",
    "603313", "603316", "603421", "603586", "603707",
]


def main():
    evaluator = Evaluator(
        xbrl_path=PROJECT_ROOT / "data" / "FinAR-Bench" / "dev.txt",
        xbrl_paths=[
            PROJECT_ROOT / "data" / "FinAR-Bench" / "dev.txt",
            PROJECT_ROOT / "data" / "FinAR-Bench" / "test.txt",
        ],
        reference_dir=PROJECT_ROOT / "data" / "FinAR-Bench" / "extracted" / "pdf_extractor_result" / "txt_output",
    )

    output_dir = PROJECT_ROOT / "output" / "las_results"
    results: list[dict] = []

    for code in STOCK_CODES:
        las_path = output_dir / code / "las_response.json"
        if not las_path.exists():
            print(f"[SKIP] {code}: no LAS output")
            continue

        result = evaluator.evaluate(las_path, company_code=code)
        d = result.to_dict()
        results.append(d)

        text_s = d["text_accuracy"]["score"]
        table_s = d["table_fidelity"]["score"]
        num_s = d["number_accuracy"]["score"]
        teds = d["table_fidelity"]["teds"]
        cf1 = d["table_fidelity"]["cell_f1"]

        print(f"  {code} ({d['company_name'][:6]}): Text={text_s} Table={table_s} Number={num_s} "
              f"-> Module1={d['module1_score']}  "
              f"(TEDS={teds:.2f} CellF1={cf1:.2f})")

        if d["errors"]:
            print(f"    ERRORS: {d['errors']}")
        if d["warnings"]:
            print(f"    WARNINGS: {d['warnings']}")

    # 汇总
    scores = [r["module1_score"] for r in results]
    text_scores = [r["text_accuracy"]["score"] for r in results]
    table_scores = [r["table_fidelity"]["score"] for r in results]
    num_scores = [r["number_accuracy"]["score"] for r in results]
    teds_vals = [r["table_fidelity"]["teds"] for r in results]
    cellf1_vals = [r["table_fidelity"]["cell_f1"] for r in results]

    print(f"\n{'='*60}")
    print(f"BATCH RESULTS (n={len(results)})")
    print(f"{'='*60}")
    print(f"Module 1 avg: {sum(scores)/len(scores):.1f}/10  (min={min(scores):.1f} max={max(scores):.1f})")
    print(f"  Text avg:   {sum(text_scores)/len(text_scores):.1f}/10")
    print(f"  Table avg:  {sum(table_scores)/len(table_scores):.1f}/10")
    print(f"  Number avg: {sum(num_scores)/len(num_scores):.1f}/10")
    print(f"  TEDS avg:   {sum(teds_vals)/len(teds_vals):.3f}")
    print(f"  CellF1 avg: {sum(cellf1_vals)/len(cellf1_vals):.3f}")

    dist = {i: 0 for i in range(1, 11)}
    for s in scores:
        dist[int(round(s))] += 1
    print("Score distribution:", {k: v for k, v in dist.items() if v > 0})

    # 保存
    summary_path = output_dir / "module1_batch_results.json"
    data = {
        "results": results,
        "summary": {
            "n": len(results),
            "avg": round(sum(scores)/len(scores), 1),
            "min": round(min(scores), 1),
            "max": round(max(scores), 1),
            "text_avg": round(sum(text_scores)/len(text_scores), 1),
            "table_avg": round(sum(table_scores)/len(table_scores), 1),
            "number_avg": round(sum(num_scores)/len(num_scores), 1),
            "teds_avg": round(sum(teds_vals)/len(teds_vals), 3),
            "cellf1_avg": round(sum(cellf1_vals)/len(cellf1_vals), 3),
            "distribution": {str(k): v for k, v in dist.items() if v > 0},
        },
    }
    summary_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {summary_path}")


if __name__ == "__main__":
    main()
