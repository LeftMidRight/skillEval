"""批量 OpenClaw 评测脚本：通过 ArkClaw 网关提交 PDF 解析请求。

读取 manifest.json 中的评测样本，将 PDF URL 发送给 OpenClaw 上的
financial-report-analyzer-skill，保存结果到 output/las_results/{sample_id}/。

用法：
    # 干跑：列出所有待处理样本
    python scripts/batch_openclaw_eval.py --dry-run

    # 按场景过滤
    python scripts/batch_openclaw_eval.py --scene anomaly

    # 断点续跑
    python scripts/batch_openclaw_eval.py --skip-existing

    # 全量跑
    python scripts/batch_openclaw_eval.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.manifest import EvalSample, load_manifest
from scripts.arkclaw_client import ArkClawClient

# ---------------------------------------------------------------------------
# TOS URL 映射
# ---------------------------------------------------------------------------

TOS_BASE = "https://ark-auto-2108530377-cn-beijing-default.tos-cn-beijing.volces.com"
TOS_PREFIX = "myEvalDataset"


def pdf_path_to_url(pdf_path: str) -> str:
    """将本地 pdf_path 转为 TOS 可访问 URL。

    data/eval_dataset/cross_page_tables/603256.pdf
    → https://.../myEvalDataset/eval_dataset/cross_page_tables/603256.pdf
    """
    relative = str(pdf_path).replace("\\", "/").removeprefix("data/")
    return f"{TOS_BASE}/{TOS_PREFIX}/{relative}"


# ---------------------------------------------------------------------------
# 单样本处理
# ---------------------------------------------------------------------------

DEFAULT_PROMPT = "请解析这份财报 PDF：{pdf_url}"
DEFAULT_SYSTEM_PROMPT = (
    "你是一个金融财报 PDF 解析工具。请解析用户提供的 PDF URL，"
    "返回完整的 Markdown 解析结果。"
)


def is_auth_error(exc: Exception) -> bool:
    return "401" in str(exc) or "403" in str(exc)


def process_sample(
    client: ArkClawClient,
    sample: EvalSample,
    output_dir: Path,
    prompt_template: str,
    system_prompt: str | None,
    retries: int,
    delay: float,
) -> dict[str, Any]:
    """处理单个评测样本，返回结果 dict。"""
    sample_id = sample.sample_id
    sample_dir = output_dir / sample_id
    sample_dir.mkdir(parents=True, exist_ok=True)

    pdf_url = pdf_path_to_url(str(sample.pdf_path))
    prompt = prompt_template.format(pdf_url=pdf_url)

    result: dict[str, Any] = {
        "sample_id": sample_id,
        "company_code": sample.company_code,
        "scene": sample.scene,
        "pdf_url": pdf_url,
        "status": "unknown",
        "error": None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    messages: list[dict[str, Any]] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    last_exc: Exception | None = None
    for attempt in range(1, retries + 2):  # 1 + retries 次
        try:
            response = client.chat(messages=messages, stream=False)
            break
        except RuntimeError as exc:
            last_exc = exc
            if is_auth_error(exc):
                result["status"] = "failed"
                result["error"] = f"Auth error: {exc}"
                _save_meta(sample_dir, result, sample)
                return result
            if attempt < retries + 1:
                wait = delay * (2 ** (attempt - 1))
                print(f"    retry {attempt}/{retries} in {wait:.0f}s: {exc}")
                time.sleep(wait)
    else:
        result["status"] = "failed"
        result["error"] = f"All retries exhausted: {last_exc}"
        _save_meta(sample_dir, result, sample)
        return result

    # 保存响应
    if isinstance(response, dict):
        (sample_dir / "openclaw_response.json").write_text(
            json.dumps(response, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        # 提取 assistant 文本
        content = ""
        choices = response.get("choices", [])
        if choices:
            content = choices[0].get("message", {}).get("content", "")
    else:
        # 流式时返回纯文本（不会走到这里，因为 stream=False）
        content = str(response)
        (sample_dir / "openclaw_response.json").write_text(
            json.dumps({"content": content}, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # 保存 markdown
    if content:
        (sample_dir / "report.md").write_text(content, encoding="utf-8")

    # 判定状态
    is_expected_failure = sample.expected_parse_status == "failure"
    if not content and is_expected_failure:
        result["status"] = "expected_failure"
    elif content:
        result["status"] = "completed"
    elif is_expected_failure:
        result["status"] = "expected_failure"
    else:
        result["status"] = "failed"
        result["error"] = "Empty response from skill"

    result["has_markdown"] = bool(content)
    _save_meta(sample_dir, result, sample)
    return result


def _save_meta(sample_dir: Path, result: dict, sample: EvalSample) -> None:
    """保存 _meta.json。"""
    meta = {
        **sample.to_result_metadata(),
        "status": result["status"],
        "timestamp": result["timestamp"],
        "pdf_url": result["pdf_url"],
        "error": result.get("error"),
        "has_markdown": result.get("has_markdown"),
    }
    (sample_dir / "_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# 断点续跑
# ---------------------------------------------------------------------------

def is_completed(sample_id: str, output_dir: Path) -> bool:
    """检查样本是否已成功处理。"""
    meta_path = output_dir / sample_id / "_meta.json"
    if not meta_path.exists():
        return False
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return meta.get("status") in ("completed", "expected_failure")
    except (json.JSONDecodeError, OSError):
        return False


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="批量 OpenClaw 评测：通过 ArkClaw 网关提交 PDF 解析请求",
        epilog="环境变量: ARKCLAW_BASE_URL, ARKCLAW_TOKEN, ARKCLAW_COOKIE",
    )
    parser.add_argument("--manifest", default=str(PROJECT_ROOT / "data" / "eval_dataset" / "manifest.json"),
                        help="manifest.json 路径")
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "output" / "las_results"),
                        help="输出目录")
    parser.add_argument("--scene", default=None,
                        help="按场景过滤: cross_page_tables, dense_numerical, borderless_tables, "
                             "synthetic_multicolumn, S5_long_documents, anomaly")
    parser.add_argument("--sample-id", action="append", default=None,
                        help="指定样本 ID（可重复）")
    parser.add_argument("--skip-existing", action="store_true",
                        help="跳过已完成的样本（断点续跑）")
    parser.add_argument("--dry-run", action="store_true",
                        help="只列出待处理样本，不实际提交")
    parser.add_argument("--skill", default="financial-report-analyzer-skill",
                        help="OpenClaw skill 名称")
    parser.add_argument("--prompt-template", default=DEFAULT_PROMPT,
                        help="提示词模板，{pdf_url} 占位符")
    parser.add_argument("--system-prompt", default=DEFAULT_SYSTEM_PROMPT,
                        help="系统提示词")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="请求间隔秒数")
    parser.add_argument("--retry", type=int, default=2,
                        help="失败重试次数")
    parser.add_argument("--base-url", default=None,
                        help="覆盖 ArkClaw 网关地址")
    parser.add_argument("--token", default=None,
                        help="覆盖 ArkClaw token")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # 加载 manifest
    manifest = load_manifest(args.manifest)
    all_samples: list[EvalSample] = manifest["samples"]

    # 过滤
    samples = all_samples
    if args.scene:
        samples = [s for s in samples if s.scene == args.scene]
    if args.sample_id:
        id_set = set(args.sample_id)
        samples = [s for s in samples if s.sample_id in id_set]

    if not samples:
        print("No samples match the filter criteria.")
        return 0

    output_dir = Path(args.output_dir)

    # 干跑模式
    if args.dry_run:
        print(f"Dry run: {len(samples)} samples would be processed\n")
        for s in samples:
            url = pdf_path_to_url(str(s.pdf_path))
            expected = " (expected failure)" if s.expected_parse_status == "failure" else ""
            existing = " [DONE]" if is_completed(s.sample_id, output_dir) else ""
            print(f"  {s.sample_id:30s} {s.scene:25s} {url[:80]}{expected}{existing}")
        return 0

    # 初始化客户端
    client = ArkClawClient(
        base_url=args.base_url,
        token=args.token,
        model=f"openclaw/{args.skill}",
    )

    # 验证连接
    print(f"Connecting to {client.base_url} (skill: {args.skill}) ...")
    try:
        models = client.list_models()
        skill_names = [m.get("id", m.get("name", "")) for m in models.get("data", models.get("models", []))]
        print(f"  Available: {skill_names[:5]}{'...' if len(skill_names) > 5 else ''}")
    except RuntimeError as exc:
        print(f"  Warning: cannot list models: {exc}")
        print("  Continuing anyway...")

    # 处理
    completed = failed = expected_failures = skipped = 0
    results: list[dict[str, Any]] = []

    for idx, sample in enumerate(samples, 1):
        sid = sample.sample_id
        scene = sample.scene
        total = len(samples)

        # 断点续跑
        if args.skip_existing and is_completed(sid, output_dir):
            print(f"[{idx}/{total}] {sid} ({scene}) ... skipped (already done)")
            skipped += 1
            results.append({
                "sample_id": sid, "company_code": sample.company_code,
                "scene": scene, "status": "skipped",
                "pdf_url": pdf_path_to_url(str(sample.pdf_path)),
            })
            continue

        expected_failure = sample.expected_parse_status == "failure"
        label = f"[{idx}/{total}] {sid} ({scene})"
        print(f"{label} ... ", end="", flush=True)

        start = time.time()
        result = process_sample(
            client=client,
            sample=sample,
            output_dir=output_dir,
            prompt_template=args.prompt_template,
            system_prompt=args.system_prompt,
            retries=args.retry,
            delay=args.delay,
        )
        elapsed = time.time() - start

        status = result["status"]
        if status == "completed":
            completed += 1
            print(f"done ({elapsed:.1f}s)")
        elif status == "expected_failure":
            expected_failures += 1
            print(f"expected failure ({elapsed:.1f}s)")
        elif status == "failed":
            failed += 1
            err = result.get("error", "unknown")
            print(f"FAILED ({elapsed:.1f}s): {err[:120]}")
        else:
            print(f"unknown status: {status}")

        results.append(result)

        # 请求间隔
        if idx < total and args.delay > 0:
            time.sleep(args.delay)

    # 保存汇总
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": {
            "skill": args.skill,
            "prompt_template": args.prompt_template,
            "scene_filter": args.scene,
            "skip_existing": args.skip_existing,
        },
        "total": len(samples),
        "completed": completed,
        "failed": failed,
        "expected_failures": expected_failures,
        "skipped": skipped,
        "results": results,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_path = output_dir / "batch_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\nDone: {completed} completed, {failed} failed, "
          f"{expected_failures} expected failures, {skipped} skipped")
    print(f"Summary: {summary_path}")
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())