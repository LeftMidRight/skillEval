"""模块 1 场景拆解：按 manifest 场景分组重算模块 1 指标，输出对比报告。

场景映射统一使用 evaluation.scenes 模块。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.scenes import SCENE_LABELS, get_scene_map

SCENE_LABELS_REV = {v: k for k, v in SCENE_LABELS.items()}
SCENE_ORDER = ["跨页表格", "密集数值", "无边框表格", "多栏排版（合成）"]


def load_scene_lists() -> dict[str, set[str]]:
    """从 evaluation.scenes 获取场景映射，返回 {中文名: {sample_id集合}}。"""
    scene_map = get_scene_map(use_sample_id=True)
    result: dict[str, set[str]] = {label: set() for label in SCENE_LABELS}
    for sample_id, dir_name in scene_map.items():
        label = SCENE_LABELS_REV.get(dir_name)
        if label:
            result[label].add(sample_id)
    return result


def load_results(json_path: str | None = None) -> dict[str, dict]:
    """加载模块 1 批量结果（v3 格式），以 company_code 为 key。"""
    if json_path is None:
        json_path = PROJECT_ROOT / "output" / "las_results" / "module1_batch_results_v3.json"
    path = Path(json_path)
    if not path.exists():
        print(f"[ERROR] Results not found at {path}")
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    results: dict[str, dict] = {}
    for r in raw.get("results", []):
        code = r.get("sample_id") or r.get("company_code", "")
        if code and "error" not in r:
            results[code] = r
    return results


def _mean(vals: list[float]) -> float:
    clean = [v for v in vals if v == v]
    return sum(clean) / len(clean) if clean else 0.0


def _xbrl_item_recall(result: dict[str, Any]) -> float:
    data = result.get("table_fidelity", {}).get("xbrl_item_recall", {})
    if "overall_recall" in data:
        return data.get("overall_recall", 0)
    return data.get("overall", {}).get("recall", 0)


def _mineru_teds(result: dict[str, Any]) -> float:
    data = result.get("table_fidelity", {}).get("mineru_fidelity", {})
    if "avg_teds" in data:
        return data.get("avg_teds", 0)
    return data.get("teds", {}).get("overall", 0)


def _mineru_cell_f1(result: dict[str, Any]) -> float:
    data = result.get("table_fidelity", {}).get("mineru_fidelity", {})
    if "avg_cell_f1" in data:
        return data.get("avg_cell_f1", 0)
    return data.get("cell_f1", {}).get("overall", {}).get("f1", 0)


def compute_scene_stats(
    results: dict[str, dict],
    scene_codes: dict[str, set[str]],
) -> dict:
    """按场景分组计算各原始指标均值。"""
    scene_stats: dict[str, dict] = {}

    for scene_name, codes in scene_codes.items():
        matched = [results[c] for c in codes if c in results]
        if not matched:
            scene_stats[scene_name] = {"n": 0}
            continue

        n = len(matched)

        # 文本 CER
        median_cers = [
            r["text_accuracy"]["median_cer"] for r in matched
            if r["text_accuracy"].get("median_cer", float("nan")) == r["text_accuracy"].get("median_cer", float("nan"))
        ]
        mineru_cers = [r["text_accuracy"]["mineru_cer"] for r in matched]
        mineru_baselines = [r["text_accuracy"]["mineru_median_cer"] for r in matched]

        # XBRL Item Recall
        item_recalls = [_xbrl_item_recall(r) for r in matched]

        # Mineru TEDS / Cell F1
        teds_vals = [_mineru_teds(r) for r in matched]
        cellf1_vals = [_mineru_cell_f1(r) for r in matched]

        # 数值
        xbrl_num_recalls = [r["number_accuracy"]["xbrl_recall"] for r in matched]
        mineru_jaccards = [
            r["number_accuracy"].get("mineru_jaccard", float("nan"))
            for r in matched
        ]
        mineru_jaccards = [v for v in mineru_jaccards if v == v]

        scene_stats[scene_name] = {
            "n": n,
            "codes": sorted(codes),
            "median_cer": round(_mean(median_cers), 3),
            "mineru_cer": round(_mean(mineru_cers), 3),
            "mineru_baseline_cer": round(_mean(mineru_baselines), 3),
            "xbrl_item_recall": round(_mean(item_recalls), 3),
            "mineru_teds": round(_mean(teds_vals), 3),
            "mineru_cell_f1": round(_mean(cellf1_vals), 3),
            "xbrl_num_recall": round(_mean(xbrl_num_recalls), 3),
            "mineru_num_jaccard": round(_mean(mineru_jaccards), 3),
        }

    return scene_stats


def print_report(scene_stats: dict[str, dict]):
    """打印场景对比报告。"""
    print(f"{'='*90}")
    print("模块 1 场景拆解报告 (v3)")
    print(f"{'='*90}")
    print()
    print("按 manifest 样本分组，直接按原始指标值对比。")
    print()

    header = (
        f"  {'场景':<10} {'n':>3} "
        f"{'中位CER':>8} {'Mineru CER':>10} {'ItemRec':>7} "
        f"{'TEDS':>7} {'CellF1':>7} {'NumRec':>7} {'NumJac':>7}"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))

    for scene_name in SCENE_ORDER:
        s = scene_stats.get(scene_name, {})
        if not s or s.get("n", 0) == 0:
            continue
        print(
            f"  {scene_name:<10} {s['n']:>3} "
            f"{s['median_cer']:>8.3f} {s['mineru_cer']:>10.3f} {s['xbrl_item_recall']:>7.3f} "
            f"{s['mineru_teds']:>7.3f} {s['mineru_cell_f1']:>7.3f} "
            f"{s['xbrl_num_recall']:>7.3f} {s['mineru_num_jaccard']:>7.3f}"
        )

    print()
    print("指标说明:")
    print("  中位CER: LAS vs 6解析器的中位字符错误率 (越低越好)")
    print("  Mineru CER: LAS vs Mineru 的 CER (越低越好)")
    print("  ItemRec: XBRL 科目在 LAS 表格中的召回率")
    print("  TEDS: LAS vs Mineru 的表格结构相似度")
    print("  CellF1: LAS vs Mineru 的单元格 F1")
    print("  NumRec: XBRL 数值在 LAS 中的召回率")
    print("  NumJac: LAS vs Mineru 数值集合的 Jaccard 系数")


def main():
    scene_codes = load_scene_lists()
    results = load_results()

    if not results:
        print("[ERROR] No results loaded. Run batch_module1_eval.py first.")
        return 1

    print(f"Loaded {len(results)} company results")
    for scene_name, codes in scene_codes.items():
        matched = sum(1 for c in codes if c in results)
        print(f"  {scene_name}: {matched}/{len(codes)} matched")

    scene_stats = compute_scene_stats(results, scene_codes)
    print_report(scene_stats)

    output_path = PROJECT_ROOT / "output" / "las_results" / "module1_scene_breakdown_v3.json"
    output_path.write_text(json.dumps(scene_stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
