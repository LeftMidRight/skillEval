"""批量评测：按 evaluation manifest 对 LAS 输出跑 Module 1 评测。

不映射 1-10 分，保留原始指标值。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.manifest import EvalSample, iter_samples
from evaluation.module1.evaluator import evaluate_sample
from module1.utils import load_xbrl_dataset


def _load_finar_records() -> list[dict]:
    records: list[dict] = []
    xbrl_dir = PROJECT_ROOT / "data" / "FinAR-Bench"
    for split in ["dev.txt", "test.txt"]:
        path = xbrl_dir / split
        if path.exists():
            records.extend(load_xbrl_dataset(path))
    return records


def _select_samples(args) -> list[EvalSample]:
    samples = list(iter_samples(scene=args.scene if args.scene else None))
    if args.sample_id:
        wanted = set(args.sample_id)
        samples = [sample for sample in samples if sample.sample_id in wanted]
    if args.source:
        samples = [sample for sample in samples if sample.source == args.source]
    if args.synthetic == "only":
        samples = [sample for sample in samples if sample.synthetic]
    elif args.synthetic == "exclude":
        samples = [sample for sample in samples if not sample.synthetic]
    return samples


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run Module 1 evaluation from manifest samples.")
    parser.add_argument("--scene", help="Scene key, e.g. cross_page_tables or synthetic_multicolumn")
    parser.add_argument("--sample-id", action="append", help="Specific sample_id to evaluate; may be repeated")
    parser.add_argument("--source", help="Filter by source, e.g. FinAR-Bench or synthetic")
    parser.add_argument(
        "--synthetic",
        choices=["all", "only", "exclude"],
        default="all",
        help="Synthetic sample filter",
    )
    args = parser.parse_args()

    output_dir = PROJECT_ROOT / "output" / "las_results"
    samples = _select_samples(args)
    xbrl_records = _load_finar_records()
    results: list[dict] = []

    for i, sample in enumerate(samples):
        print(f"[{i+1}/{len(samples)}] {sample.sample_id}...", end=" ")
        try:
            result = evaluate_sample(sample, xbrl_records=xbrl_records)
            results.append(result)
            ta = result["text_accuracy"]
            xbrl_r = result["table_fidelity"]["xbrl_item_recall"]
            na = result["number_accuracy"]
            print(f"CER={ta['median_cer']:.3f} ItemRecall={xbrl_r.get('overall_recall', 0):.3f} "
                  f"NumRecall={na['xbrl_recall']:.3f}")
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({
                "sample_id": sample.sample_id,
                "company_code": sample.company_code,
                "scene_key": sample.scene,
                "scene": sample.scene_title,
                "error": str(e),
            })

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
                fv = float(v)
                if fv == fv:
                    vals.append(fv)
            except (KeyError, ValueError, TypeError):
                pass
        return sum(vals) / len(vals) if vals else 0.0

    print(f"\n{'='*60}")
    print(f"MODULE 1 BATCH RESULTS (manifest, n={len(valid)}/{len(samples)})")
    print(f"{'='*60}")
    print(f"  Median CER:          {_avg(['text_accuracy', 'median_cer']):.3f}")
    print(f"  Mineru Baseline CER: {_avg(['text_accuracy', 'mineru_median_cer']):.3f}")
    print(f"  XBRL Item Recall:    {_avg(['table_fidelity', 'xbrl_item_recall', 'overall_recall']):.3f}")
    print(f"  Mineru TEDS:         {_avg(['table_fidelity', 'mineru_fidelity', 'avg_teds']):.3f}")
    print(f"  Mineru Cell F1:      {_avg(['table_fidelity', 'mineru_fidelity', 'avg_cell_f1']):.3f}")
    print(f"  XBRL Number Recall:  {_avg(['number_accuracy', 'xbrl_recall']):.3f}")
    print(f"  Mineru Number Jaccard: {_avg(['number_accuracy', 'mineru_jaccard']):.3f}")

    summary_path = output_dir / "module1_batch_results_v3.json"
    data = {"results": results}
    summary_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {summary_path}")


if __name__ == "__main__":
    main()
