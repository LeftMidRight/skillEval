"""批量评测：对 25 份 LAS 输出跑模块 1 评测（v3 方案），输出汇总。

不映射 1-10 分，保留原始指标值。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.module1.evaluator import evaluate_company

STOCK_CODES = [
    "600064", "600070", "600082", "600083", "600100",
    "600114", "600130", "600133", "600168", "600193",
    "600225", "600322", "600569", "600597", "600626",
    "600933", "603201", "603228", "603256", "603299",
    "603313", "603316", "603421", "603586", "603707",
]


def main():
    output_dir = PROJECT_ROOT / "output" / "las_results"
    results: list[dict] = []

    for i, code in enumerate(STOCK_CODES):
        print(f"[{i+1}/{len(STOCK_CODES)}] {code}...", end=" ")
        try:
            result = evaluate_company(code)
            results.append(result)
            ta = result["text_accuracy"]
            xbrl_r = result["table_fidelity"]["xbrl_item_recall"]
            na = result["number_accuracy"]
            print(f"CER={ta['median_cer']:.3f} ItemRecall={xbrl_r.get('overall', {}).get('recall', 0):.3f} "
                  f"NumRecall={na['xbrl_recall']:.3f}")
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({"company_code": code, "error": str(e)})

    # 汇总统计
    valid = [r for r in results if "error" not in r]
    if not valid:
        print("No valid results")
        return

    def _avg(key_path: list[str]) -> float:
        vals = []
        for r in valid:
            v = r
            try:
                for k in key_path:
                    v = v[k]
                vals.append(float(v))
            except (KeyError, ValueError, TypeError):
                pass
        return sum(vals) / len(vals) if vals else 0.0

    print(f"\n{'='*60}")
    print(f"MODULE 1 BATCH RESULTS (v3, n={len(valid)})")
    print(f"{'='*60}")
    print(f"  Median CER:          {_avg(['text_accuracy', 'median_cer']):.3f}")
    print(f"  Mineru Baseline CER: {_avg(['text_accuracy', 'mineru_median_cer']):.3f}")
    print(f"  XBRL Item Recall:    {_avg(['table_fidelity', 'xbrl_item_recall', 'overall', 'recall']):.3f}")
    print(f"  Mineru TEDS:         {_avg(['table_fidelity', 'mineru_fidelity', 'teds', 'overall']):.3f}")
    print(f"  Mineru Cell F1:      {_avg(['table_fidelity', 'mineru_fidelity', 'cell_f1', 'overall', 'f1']):.3f}")
    print(f"  XBRL Number Recall:  {_avg(['number_accuracy', 'xbrl_recall']):.3f}")
    print(f"  Mineru Number Jaccard: {_avg(['number_accuracy', 'mineru_jaccard']):.3f}")

    summary_path = output_dir / "module1_batch_results_v3.json"
    data = {"results": results}
    summary_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {summary_path}")


if __name__ == "__main__":
    main()
