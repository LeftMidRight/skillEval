"""批量评测：按 evaluation manifest 对 LAS 输出跑 Module 2 评测（阅读顺序）。

调用 LLM-as-Judge 评判页内阅读顺序和跨页连续性。
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
from evaluation.module2.reading_order import (
    evaluate_cross_page_continuity_llm,
    evaluate_page_reading_order,
    evaluate_reading_order,
    render_page,
)


def _select_samples(args) -> list[EvalSample]:
    # Module 2 适用于有正常 PDF 的样本（core + stress），排除 anomaly
    samples = list(iter_samples(scene=args.scene if args.scene else None))
    samples = [s for s in samples if "module1" in s.eval_modules]
    if args.sample_id:
        wanted = set(args.sample_id)
        samples = [s for s in samples if s.sample_id in wanted]
    return samples


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Run Module 2 evaluation (reading order) from manifest samples.",
        epilog="环境变量: ARK_API_KEY (必填), ARK_MODEL (可选)",
    )
    parser.add_argument("--scene", help="Scene key, e.g. cross_page_tables")
    parser.add_argument("--sample-id", action="append", help="Specific sample_id; may be repeated")
    parser.add_argument("--skip-existing", action="store_true", help="Skip samples with existing results")
    parser.add_argument("--skip-cross-page", action="store_true", help="Skip cross-page evaluation")
    parser.add_argument("--render-dir", default=str(PROJECT_ROOT / "output" / "eval_renders"),
                        help="Directory for rendered page images")
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "output" / "module2_results"),
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

    print(f"Module 2 evaluation: {len(samples)} samples\n")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    render_dir = Path(args.render_dir)
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

        # 加载 LAS 响应
        las_resp_path = sample.las_result_dir / "las_response.json"
        if not las_resp_path.exists():
            # 尝试 openclaw 格式
            las_resp_path = sample.las_result_dir / "openclaw_response.json"
        if not las_resp_path.exists():
            print(f"  SKIP: no LAS/OpenClaw response found in {sample.las_result_dir}")
            results.append({
                **sample.to_result_metadata(),
                "status": "skipped",
                "error": f"No response file in {sample.las_result_dir}",
            })
            continue

        try:
            result = evaluate_reading_order(
                llm=llm,
                company_code=sample.sample_id,
                las_results_dir=sample.las_result_dir.parent,
                pdf_dir=sample.pdf_path.parent,
                render_dir=render_dir / sid,
                skip_cross_page=args.skip_cross_page,
            )
        except Exception as exc:
            print(f"  ERROR: {exc}")
            results.append({
                **sample.to_result_metadata(),
                "status": "failed",
                "error": str(exc),
            })
            # 保存错误元数据
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
        (sample_out / "reading_order_result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # 保存元数据（用于断点续跑）
        summary = result.get("summary", {})
        meta_path.write_text(json.dumps({
            **sample.to_result_metadata(),
            "status": "completed",
            "timestamp": result["timestamp"],
            "pass_rate": summary.get("pass_rate"),
            "avg_flow_score": summary.get("avg_flow_score"),
            "avg_integrity_score": summary.get("avg_integrity_score"),
            "avg_noise_score": summary.get("avg_noise_score"),
            "cross_page_rate": summary.get("cross_page_rate"),
        }, ensure_ascii=False, indent=2), encoding="utf-8")

        print(f"  done ({elapsed:.1f}s) — pass_rate={summary.get('pass_rate', 'N/A')}, "
              f"flow={summary.get('avg_flow_score', 'N/A')}, "
              f"cross_page={summary.get('cross_page_rate', 'N/A')}")

        results.append(result)

        # 请求间隔
        if idx < total and args.delay > 0:
            time.sleep(args.delay)

    # 汇总统计
    valid = [r for r in results if "error" not in r or r.get("status") == "completed"]
    if not valid:
        print("No valid results")
        return 1

    def _avg(key: str) -> float:
        vals = [r.get("summary", {}).get(key) for r in valid if isinstance(r.get("summary"), dict)]
        vals = [v for v in vals if isinstance(v, (int, float))]
        return sum(vals) / len(vals) if vals else 0.0

    print(f"\n{'='*60}")
    print(f"MODULE 2 BATCH RESULTS (manifest, n={len(valid)}/{len(samples)})")
    print(f"{'='*60}")
    print(f"  Page pass rate:       {_avg('pass_rate'):.3f}")
    print(f"  Avg flow score:       {_avg('avg_flow_score'):.1f}")
    print(f"  Avg integrity score:  {_avg('avg_integrity_score'):.1f}")
    print(f"  Avg noise score:      {_avg('avg_noise_score'):.1f}")
    print(f"  Cross-page rate:      {_avg('cross_page_rate'):.3f}")

    summary_path = output_dir / "module2_batch_results.json"
    summary_path.write_text(json.dumps({"results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())