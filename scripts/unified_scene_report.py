"""统一场景报告：汇总 Module 1/2/3 结果，按场景分组输出对比表。

读取三个模块的批量评测结果 JSON，按跨页表格/密集数值/无边框表格三场景分组，
输出三模块并排对比报告。

用法：
    python scripts/unified_scene_report.py
    python scripts/unified_scene_report.py --m1 path/to/m1.json --m2 path/to/m2.json --m3 path/to/m3.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.scenes import SCENE_LABELS, get_scene_map

DEFAULT_PATHS = {
    "m1": PROJECT_ROOT / "output" / "las_results" / "module1_batch_results_v3.json",
    "m2": PROJECT_ROOT / "output" / "las_results" / "module2_batch_results.json",
    "m3": PROJECT_ROOT / "output" / "las_results" / "module3_batch_results.json",
}


def _load_json(path: Path) -> list[dict[str, Any]]:
    """加载 JSON 结果文件。支持列表格式和 {"results": [...]} 格式。"""
    if not path.exists():
        print(f"  [WARN] Not found: {path}")
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return raw
    return raw.get("results", [])


def _mean(vals: list[float]) -> float:
    clean = [v for v in vals if v == v]
    return sum(clean) / len(clean) if clean else 0.0


def _result_scene_label(
    result_key: str,
    result: dict[str, Any],
    sample_scene_map: dict[str, str],
    company_scene_map: dict[str, str],
) -> str:
    sample_id = result.get("sample_id") or result_key
    scene = sample_scene_map.get(sample_id)
    if not scene:
        company_code = result.get("company_code") or result_key
        scene = company_scene_map.get(str(company_code))
    return SCENE_LABELS_REV.get(scene, "")


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


# ============================================================================
# Module 1 场景统计
# ============================================================================

def compute_m1_scene_stats(results_by_code: dict[str, dict]) -> dict[str, dict]:
    """按场景分组计算 Module 1 指标。"""
    sample_scene_map = get_scene_map(use_sample_id=True)
    company_scene_map = get_scene_map(use_sample_id=False)
    # 按场景分组
    groups: dict[str, list[dict]] = {label: [] for label in SCENE_LABELS}
    for code, r in results_by_code.items():
        label = _result_scene_label(code, r, sample_scene_map, company_scene_map)
        if label:
            groups[label].append(r)

    stats: dict[str, dict] = {}
    for label, items in groups.items():
        if not items:
            stats[label] = {"n": 0}
            continue
        n = len(items)

        # 文本 CER
        median_cers = [
            r["text_accuracy"]["median_cer"]
            for r in items
            if "median_cer" in r.get("text_accuracy", {})
            and r["text_accuracy"]["median_cer"] == r["text_accuracy"]["median_cer"]
        ]
        # XBRL Item Recall
        item_recalls = [_xbrl_item_recall(r) for r in items]
        # Mineru TEDS / Cell F1
        teds_vals = [_mineru_teds(r) for r in items]
        cellf1_vals = [_mineru_cell_f1(r) for r in items]
        # 数值
        num_recalls = [r["number_accuracy"]["xbrl_recall"] for r in items]
        jaccards = [r["number_accuracy"].get("mineru_jaccard", 0) for r in items]
        # 跨页连续性
        merge_rates = [
            r.get("cross_page_continuity", {}).get("merge_success_rate", 0) for r in items
        ]
        header_preserved_count = sum(
            1 for r in items
            if r.get("cross_page_continuity", {}).get("header_preserved", False)
        )

        stats[label] = {
            "n": n,
            "median_cer": round(_mean(median_cers), 3),
            "xbrl_item_recall": round(_mean(item_recalls), 3),
            "mineru_teds": round(_mean(teds_vals), 3),
            "mineru_cell_f1": round(_mean(cellf1_vals), 3),
            "xbrl_num_recall": round(_mean(num_recalls), 3),
            "mineru_num_jaccard": round(_mean(jaccards), 3),
            "merge_success_rate": round(_mean(merge_rates), 3),
            "header_preserved_rate": round(header_preserved_count / n, 3) if n else 0.0,
        }

    return stats


# ============================================================================
# Module 2 场景统计
# ============================================================================

def compute_m2_scene_stats(results_by_code: dict[str, dict]) -> dict[str, dict]:
    """按场景分组计算 Module 2 指标。"""
    sample_scene_map = get_scene_map(use_sample_id=True)
    company_scene_map = get_scene_map(use_sample_id=False)
    groups: dict[str, list[dict]] = {label: [] for label in SCENE_LABELS}
    for code, r in results_by_code.items():
        label = _result_scene_label(code, r, sample_scene_map, company_scene_map)
        if label:
            groups[label].append(r)

    stats: dict[str, dict] = {}
    for label, items in groups.items():
        if not items:
            stats[label] = {"n": 0}
            continue
        n = len(items)
        summaries = [r.get("summary", {}) for r in items]

        pass_rates = [s.get("pass_rate", 0) for s in summaries if s]
        flow_scores = [s.get("avg_flow_score", 0) for s in summaries if s]
        integrity_scores = [s.get("avg_integrity_score", 0) for s in summaries if s]
        noise_scores = [s.get("avg_noise_score", 0) for s in summaries if s]
        cross_rates = [s.get("cross_page_rate", 0) for s in summaries if s]

        stats[label] = {
            "n": n,
            "pass_rate": round(_mean(pass_rates), 3),
            "avg_flow_score": round(_mean(flow_scores), 1),
            "avg_integrity_score": round(_mean(integrity_scores), 1),
            "avg_noise_score": round(_mean(noise_scores), 1),
            "cross_page_rate": round(_mean(cross_rates), 3),
        }

    return stats


# ============================================================================
# Module 3 场景统计
# ============================================================================

def compute_m3_scene_stats(results_by_code: dict[str, dict]) -> dict[str, dict]:
    """按场景分组计算 Module 3 指标。"""
    sample_scene_map = get_scene_map(use_sample_id=True)
    company_scene_map = get_scene_map(use_sample_id=False)
    groups: dict[str, list[dict]] = {label: [] for label in SCENE_LABELS}
    for code, r in results_by_code.items():
        label = _result_scene_label(code, r, sample_scene_map, company_scene_map)
        if label:
            groups[label].append(r)

    stats: dict[str, dict] = {}
    for label, items in groups.items():
        if not items:
            stats[label] = {"n": 0}
            continue
        n = len(items)

        fact_accs = [r.get("fact", {}).get("accuracy", 0) for r in items]
        ind_accs = [r.get("indicator", {}).get("accuracy", 0) for r in items]
        reas_accs = [r.get("reasoning", {}).get("accuracy", 0) for r in items]

        stats[label] = {
            "n": n,
            "fact_accuracy": round(_mean(fact_accs), 3),
            "indicator_accuracy": round(_mean(ind_accs), 3),
            "reasoning_accuracy": round(_mean(reas_accs), 3),
        }

    return stats


# ============================================================================
# 报告输出
# ============================================================================

SCENE_LABELS_REV = {v: k for k, v in SCENE_LABELS.items()}
SCENE_ORDER = ["跨页表格", "密集数值", "无边框表格", "多栏排版（合成）"]


def print_report(
    m1_stats: dict[str, dict],
    m2_stats: dict[str, dict],
    m3_stats: dict[str, dict],
) -> None:
    """打印三模块并排的场景对比报告。"""
    width = 90
    print("=" * width)
    print("统一场景报告：三模块按场景分组")
    print("=" * width)
    print()

    # Module 1
    print("【Module 1 — 内容还原】")
    header = (
        f"  {'场景':<10} {'n':>3} "
        f"{'中位CER':>8} {'ItemRec':>7} {'TEDS':>7} "
        f"{'CellF1':>7} {'NumRec':>7} {'MergeRate':>9} {'HdrPres':>7}"
    )
    print(header)
    print("  " + "-" * (len(header) - 2))
    for s in SCENE_ORDER:
        st = m1_stats.get(s, {})
        if not st or st.get("n", 0) == 0:
            continue
        print(
            f"  {s:<10} {st['n']:>3} "
            f"{st.get('median_cer', 0):>8.3f} {st.get('xbrl_item_recall', 0):>7.3f} "
            f"{st.get('mineru_teds', 0):>7.3f} {st.get('mineru_cell_f1', 0):>7.3f} "
            f"{st.get('xbrl_num_recall', 0):>7.3f} {st.get('merge_success_rate', 0):>9.3f} "
            f"{st.get('header_preserved_rate', 0):>7.3f}"
        )
    print()

    # Module 2
    print("【Module 2 — 结构保真（LLM-as-Judge）】")
    header2 = (
        f"  {'场景':<10} {'n':>3} "
        f"{'通过率':>7} {'流向':>5} {'完整':>5} {'噪声':>5} {'跨页率':>7}"
    )
    print(header2)
    print("  " + "-" * (len(header2) - 2))
    for s in SCENE_ORDER:
        st = m2_stats.get(s, {})
        if not st or st.get("n", 0) == 0:
            continue
        print(
            f"  {s:<10} {st['n']:>3} "
            f"{st.get('pass_rate', 0):>7.3f} {st.get('avg_flow_score', 0):>5.1f} "
            f"{st.get('avg_integrity_score', 0):>5.1f} {st.get('avg_noise_score', 0):>5.1f} "
            f"{st.get('cross_page_rate', 0):>7.3f}"
        )
    print()

    # Module 3
    print("【Module 3 — 下游可用性（LLM-as-Judge）】")
    header3 = (
        f"  {'场景':<10} {'n':>3} "
        f"{'Fact':>7} {'Ind':>7} {'Reas':>7}"
    )
    print(header3)
    print("  " + "-" * (len(header3) - 2))
    for s in SCENE_ORDER:
        st = m3_stats.get(s, {})
        if not st or st.get("n", 0) == 0:
            continue
        print(
            f"  {s:<10} {st['n']:>3} "
            f"{st.get('fact_accuracy', 0):>7.3f} {st.get('indicator_accuracy', 0):>7.3f} "
            f"{st.get('reasoning_accuracy', 0):>7.3f}"
        )
    print()

    # 关键问题
    print("【场景关键问题】")
    print("  跨页表格: 合并不完整是否导致 fact 提取错误？对比 MergeRate vs Fact accuracy")
    print("  密集数值: 数值 Recall 高是否转化为 indicator 计算正确？对比 NumRec vs Ind accuracy")
    print("  无边框:   表结构偏差是否导致整体准确率显著低于其他场景？")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="统一场景报告")
    parser.add_argument("--m1", type=Path, default=DEFAULT_PATHS["m1"])
    parser.add_argument("--m2", type=Path, default=DEFAULT_PATHS["m2"])
    parser.add_argument("--m3", type=Path, default=DEFAULT_PATHS["m3"])
    args = parser.parse_args()

    # 加载结果
    m1_raw = _load_json(args.m1)
    m2_raw = _load_json(args.m2)
    m3_raw = _load_json(args.m3)

    # 按 company_code 索引
    m1_by_code = {r.get("sample_id", r["company_code"]): r for r in m1_raw if "error" not in r}
    m2_by_code = {r.get("sample_id", r["company_code"]): r for r in m2_raw if "error" not in r}
    m3_by_code = {r.get("sample_id", r["company_code"]): r for r in m3_raw if "error" not in r}

    print(f"Module 1: {len(m1_by_code)} companies")
    print(f"Module 2: {len(m2_by_code)} companies")
    print(f"Module 3: {len(m3_by_code)} companies")
    print()

    m1_stats = compute_m1_scene_stats(m1_by_code)
    m2_stats = compute_m2_scene_stats(m2_by_code)
    m3_stats = compute_m3_scene_stats(m3_by_code)

    print_report(m1_stats, m2_stats, m3_stats)

    # 保存
    output_path = PROJECT_ROOT / "output" / "las_results" / "unified_scene_report.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps({
            "module1": m1_stats,
            "module2": m2_stats,
            "module3": m3_stats,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nSaved: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
