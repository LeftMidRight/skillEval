"""批量评测：按 evaluation manifest 对 LAS 输出跑 Module 3 评测（下游任务可用性）。

所有任务类型（fact / indicator / reasoning）均使用 LLM-as-Judge，
从 LAS markdown 提取数值后与 XBRL GT 对比。

需要环境变量：
  - ARK_API_KEY: 火山引擎 Ark API Key
  - ARK_MODEL (可选): 模型端点 ID，默认 ep-20260526173832-2vrr2
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.llm_client import LLMClient
from evaluation.manifest import EvalSample, iter_samples
from evaluation.module3.downstream import evaluate_sample as evaluate_downstream


def _load_finar_records() -> list[dict]:
    from module1.utils import load_xbrl_dataset
    records: list[dict] = []
    xbrl_dir = PROJECT_ROOT / "data" / "FinAR-Bench"
    for split in ["dev.txt", "test.txt"]:
        path = xbrl_dir / split
        if path.exists():
            records.extend(load_xbrl_dataset(path))
    return records


def _select_samples(args) -> list[EvalSample]:
    # Module 3 适用于有正常 PDF + XBRL GT 的样本（core + stress），排除 anomaly
    samples = list(iter_samples(scene=args.scene if args.scene else None))
    samples = [s for s in samples if "module1" in s.eval_modules]
    if args.sample_id:
        wanted = set(args.sample_id)
        samples = [s for s in samples if s.sample_id in wanted]
    return samples


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Run Module 3 evaluation (downstream utility) from manifest samples.",
        epilog="环境变量: ARK_API_KEY (必填), ARK_MODEL (可选)",
    )
    parser.add_argument("--scene", help="Scene key, e.g. cross_page_tables")
    parser.add_argument("--sample-id", action="append", help="Specific sample_id; may be repeated")
    parser.add_argument("--skip-existing", action="store_true", help="Skip samples with existing results")
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "output" / "module3_results"),
                        help="Output directory for results")
    parser.add_argument("--api-key", default=None, help="Ark API key (or set ARK_API_KEY)")
    parser.add_argument("--model", default=None, help="Ark model endpoint (or set ARK_MODEL)")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between LLM calls (seconds)")
    args = parser.parse_args()

    # 初始化 LLM 客户端
    import os
    api_key = args.api_key or os.environ.get("ARK_API_KEY", "")
    if not api_key:
        print("Error: ARK_API_KEY not set. Use --api-key or set ARK_API_KEY env var.")
        return 1

    model = args.model or os.environ.get("ARK_MODEL", "ep-20260526173832-2vrr2")
    llm = LLMClient(api_key=api_key, model=model)

    samples = _select_samples(args)
    if not samples:
        print("No samples match the filter criteria.")
        return 0

    print(f"Module 3 evaluation: {len(samples)} samples\n")

    # 预加载 XBRL 数据
    xbrl_records = _load_finar_records()
    print(f"Loaded {len(xbrl_records)} XBRL records\n")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []

    for idx, sample in enumerate(samples, 1):
        sid = sample.sample_id
        scene = sample.scene
        total = len(samples)
        sample_out = output_dir / sid
        meta_path = sample_out / "_meta.json"

        # 断点续跑
        if args.skip_existing and meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if meta.get("status") == "completed":
                    print(f"[{idx}/{total}] {sid} ({scene}) ... skipped (already done)")
                    results.append(meta)
                    continue
            except (json.JSONDecodeError, OSError):
                pass

        print(f"[{idx}/{total}] {sid} ({scene}) ...")
        start_time = time.time()

        # 加载 LAS markdown
        md_path = sample.las_result_dir / "report.md"
        if not md_path.exists():
            print(f"  SKIP: no report.md found in {sample.las_result_dir}")
            results.append({
                **sample.to_result_metadata(),
                "status": "skipped",
                "error": f"No report.md in {sample.las_result_dir}",
            })
            continue

        try:
            result = evaluate_downstream(
                llm=llm,
                sample=sample,
                xbrl_records=xbrl_records,
            )
        except Exception as exc:
            print(f"  ERROR: {exc}")
            results.append({
                **sample.to_result_metadata(),
                "status": "failed",
                "error": str(exc),
            })
            sample_out.mkdir(parents=True, exist_ok=True)
            meta_path.write_text(json.dumps({
                **sample.to_result_metadata(),
                "status": "failed",
                "error": str(exc),
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            continue

        elapsed = time.time() - start_time

        # 保存结果
        sample_out.mkdir(parents=True, exist_ok=True)
        result["status"] = "completed"
        result["timestamp"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        (sample_out / "downstream_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # 保存元数据（用于断点续跑）
        fact = result.get("fact", {})
        indicator = result.get("indicator", {})
        reasoning = result.get("reasoning", {})
        meta_path.write_text(json.dumps({
            **sample.to_result_metadata(),
            "status": "completed",
            "timestamp": result["timestamp"],
            "fact_accuracy": fact.get("accuracy"),
            "indicator_accuracy": indicator.get("accuracy"),
            "reasoning_accuracy": reasoning.get("accuracy"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"  done ({elapsed:.1f}s) — "
              f"fact={fact.get('accuracy', 'N/A')}, "
              f"indicator={indicator.get('accuracy', 'N/A')}, "
              f"reasoning={reasoning.get('accuracy', 'N/A')}")

        results.append(result)

        # 请求间隔
        if idx < total and args.delay > 0:
            time.sleep(args.delay)

    # 汇总统计
    valid = [r for r in results if "error" not in r or r.get("status") == "completed"]
    if not valid:
        print("No valid results")
        return 1

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
    print(f"MODULE 3 BATCH RESULTS (manifest, n={len(valid)}/{len(samples)})")
    print(f"{'='*60}")
    print(f"  Fact accuracy:        {_avg(['fact', 'accuracy']):.3f}")
    print(f"  Indicator accuracy:   {_avg(['indicator', 'accuracy']):.3f}")
    print(f"  Reasoning accuracy:  {_avg(['reasoning', 'accuracy']):.3f}")

    summary_path = output_dir / "module3_batch_results.json"
    summary_path.write_text(json.dumps({"results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())