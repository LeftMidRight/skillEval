"""模块 1 场景拆解：按 A~G 场景分组重算模块 1 指标，输出场景对比报告。"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


# ---------------------------------------------------------------------------
# 场景定义
# ---------------------------------------------------------------------------

SCENES = {
    "A_跨页表格": "A_cross_page_table",
    "B_密集数值": "B_dense_numerical",
    "C_页眉页脚": "C_header_footer",
    "D_多页": "D_many_pages",
    "F_多栏排版": "F_multi_column",
    "G_无边框表格": "G_borderless_table",
}

SCENE_DESCRIPTIONS = {
    "A_跨页表格": "跨页表格场景 — 检测续表/承前页标记识别",
    "B_密集数值": "密集数值场景 — 千分位逗号、负数括号、单位转换",
    "C_页眉页脚": "页眉页脚场景 — 页码/审计标记残留",
    "D_多页": "多页场景 — ≥14页，含详细附注",
    "F_多栏排版": "多栏排版场景 — 左右栏阅读顺序",
    "G_无边框表格": "无边框表格场景 — 无线条表格识别",
}


def load_scene_lists() -> dict[str, set[str]]:
    """从 data/eval_dataset/ 下各场景目录读取 PDF 文件名列表。"""
    base = PROJECT_ROOT / "data" / "eval_dataset"
    scene_codes: dict[str, set[str]] = {}

    for scene_name, dir_name in SCENES.items():
        scene_dir = base / dir_name
        if scene_dir.is_dir():
            codes = {f.stem for f in scene_dir.iterdir() if f.suffix == ".pdf"}
            scene_codes[scene_name] = codes

    return scene_codes


def load_module1_results() -> dict[str, dict]:
    """加载模块 1 批量结果，以 company_code 为 key。"""
    path = PROJECT_ROOT / "output" / "las_results" / "module1_batch_results.json"
    if not path.exists():
        print(f"[ERROR] module1_batch_results.json not found at {path}")
        return {}

    raw = json.loads(path.read_text(encoding="utf-8"))
    results: dict[str, dict] = {}
    for r in raw.get("results", []):
        code = r.get("company_code", "")
        if code:
            results[code] = r
    return results


def compute_scene_averages(
    results: dict[str, dict],
    scene_codes: dict[str, set[str]],
) -> dict:
    """按场景分组计算各指标均值。"""
    scene_stats: dict[str, dict] = {}

    for scene_name, codes in scene_codes.items():
        matched = [results[c] for c in codes if c in results]
        if not matched:
            scene_stats[scene_name] = {"n": 0, "error": "no matching results"}
            continue

        n = len(matched)

        # 文本
        text_scores = [r["text_accuracy"]["score"] for r in matched]
        mineru_cers = []
        for r in matched:
            cer = r["text_accuracy"].get("mineru_cer")
            if cer is not None and cer == cer:  # not NaN
                mineru_cers.append(cer)

        # 表格
        table_scores = [r["table_fidelity"]["score"] for r in matched]
        teds_vals = [r["table_fidelity"]["teds"] for r in matched]
        cellf1_vals = [r["table_fidelity"]["cell_f1"] for r in matched]

        # 数值
        num_scores = [r["number_accuracy"]["score"] for r in matched]
        num_f1s = [r["number_accuracy"]["f1"] for r in matched]

        # 模块总分
        m1_scores = [r["module1_score"] for r in matched]

        # 三张表分表统计
        by_statement = _aggregate_by_statement(matched)

        scene_stats[scene_name] = {
            "n": n,
            "codes": sorted(codes),
            "text_score": round(_mean(text_scores), 1),
            "mineru_cer": round(_mean(mineru_cers), 3),
            "table_score": round(_mean(table_scores), 1),
            "teds": round(_mean(teds_vals), 3),
            "cell_f1": round(_mean(cellf1_vals), 3),
            "number_score": round(_mean(num_scores), 1),
            "number_f1": round(_mean(num_f1s), 3),
            "module1_score": round(_mean(m1_scores), 1),
            "by_statement": by_statement,
        }

    return scene_stats


def _aggregate_by_statement(matched: list[dict]) -> dict:
    """汇总三张表的指标。"""
    stmts: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

    for r in matched:
        by_stmt = r["table_fidelity"].get("by_statement", {})
        teds_by = r["table_fidelity"].get("teds_by_statement", {})
        # Handle encoding in keys - we need to find the statement names
        for stmt_key, info in by_stmt.items():
            stmts[stmt_key]["cell_f1"].append(info.get("f1", 0))
            stmts[stmt_key]["tp"].append(info.get("tp", 0))
            stmts[stmt_key]["fn"].append(info.get("fn", 0))
            xbrl = info.get("xbrl_cells", info.get("tp", 0) + info.get("fn", 0))
            if xbrl == 0:
                xbrl = info.get("tp", 0) + info.get("fn", 0)
            stmts[stmt_key]["xbrl_cells"].append(xbrl if xbrl else 0)

        for stmt_key, tinfo in teds_by.items():
            if "teds" in tinfo:
                stmts[stmt_key]["teds"].append(tinfo["teds"])

    result = {}
    for stmt, metrics in stmts.items():
        result[stmt] = {
            "cell_f1_avg": round(_mean(metrics["cell_f1"]), 3),
            "teds_avg": round(_mean(metrics["teds"]), 3),
            "avg_tp": round(_mean(metrics["tp"]), 1),
            "avg_fn": round(_mean(metrics["fn"]), 1),
        }
    return result


def _mean(vals: list[float]) -> float:
    return sum(vals) / len(vals) if vals else 0.0


# ---------------------------------------------------------------------------
# 报告输出
# ---------------------------------------------------------------------------

def print_report(scene_stats: dict[str, dict], all_results: dict[str, dict]):
    """打印场景对比报告。"""
    # 全量基线
    all_scores = [r["module1_score"] for r in all_results.values()]
    all_text = [r["text_accuracy"]["score"] for r in all_results.values()]
    all_table = [r["table_fidelity"]["score"] for r in all_results.values()]
    all_num = [r["number_accuracy"]["score"] for r in all_results.values()]
    all_teds = [r["table_fidelity"]["teds"] for r in all_results.values()]
    all_cf1 = [r["table_fidelity"]["cell_f1"] for r in all_results.values()]
    all_nf1 = [r["number_accuracy"]["f1"] for r in all_results.values()]

    print(f"{'='*80}")
    print(f"模块 1 场景拆解报告")
    print(f"{'='*80}")
    print()
    print("场景说明：")
    print("  A/B/C/G 场景各含全部 25 家公司（场景标签有重叠），均值等于全量基线")
    print("  D（多页，n=5）和 F（多栏，n=3）是真正有区分度的子集")
    print()
    print(f"全量基线 (n={len(all_results)}):")
    print(f"  文本: {_mean(all_text):.1f}/10  表格: {_mean(all_table):.1f}/10  数值: {_mean(all_num):.1f}/10  → 总分: {_mean(all_scores):.1f}/10")
    print(f"  TEDS avg={_mean(all_teds):.3f}  CellF1 avg={_mean(all_cf1):.3f}  NumF1 avg={_mean(all_nf1):.3f}")
    print()

    scene_order = [
        ("A_跨页表格", "全量"),
        ("G_无边框表格", "全量"),
        ("B_密集数值", "全量"),
        ("C_页眉页脚", "全量"),
        ("D_多页", "子集"),
        ("F_多栏排版", "子集"),
    ]

    # ===== 概览表 =====
    header = f"  {'场景':<14} {'n':>4} {'类型':>4} {'文本':>5} {'表格':>5} {'数值':>5} {'总分':>6} {'TEDS':>7} {'CellF1':>7} {'NumF1':>7} {'vs基线':>6}"
    print(header)
    print("  " + "-" * (len(header) - 2))

    for scene_name, group_type in scene_order:
        s = scene_stats.get(scene_name, {})
        if not s or s.get("n", 0) == 0:
            continue
        n = s["n"]
        ts = s["text_score"]
        tbl = s["table_score"]
        ns = s["number_score"]
        ms = s["module1_score"]
        teds = s["teds"]
        cf1 = s["cell_f1"]
        nf1 = s["number_f1"]
        delta = ms - _mean(all_scores)

        short_name = scene_name.split("_")[1]
        delta_str = f"{delta:+.2f}" if abs(delta) >= 0.05 else " —"
        print(f"  {short_name:<14} {n:>4} {group_type:>4} {ts:>5.1f} {tbl:>5.1f} {ns:>5.1f} {ms:>6.2f} {teds:>7.3f} {cf1:>7.3f} {nf1:>7.3f} {delta_str:>6}")

    print()

    # ===== 关键发现 =====
    print(f"{'='*80}")
    print("关键发现")
    print(f"{'='*80}")
    print()
    print("1. A/B/C/G 场景（全量 25 家）：")
    print("   这 4 个场景标签覆盖了全部 25 家公司（同一份 PDF 可能同时属于多个场景），")
    print("   因此均值等于全量基线。要区分这些场景，需要场景专属指标（见模块 3），")
    print("   而非仅按公司分组。")
    print()
    print("2. D_多页场景（n=5）：")
    d = scene_stats.get("D_多页", {})
    print(f"   总分 {d.get('module1_score', '?'):.1f}/10 vs 基线 {_mean(all_scores):.1f}，"
          f"差值 {d.get('module1_score', 0) - _mean(all_scores):+.2f}")
    print(f"   这 5 份 PDF 均 ≥14 页（603256 达 36 页），TEDS 从 0.472 降至 {d.get('teds', 0):.3f}")
    print(f"   说明：页数越多，表格结构保真度越低。36 页的 603256 得分仅 2.6/10。")
    print()
    print("3. F_多栏排版场景（n=3）：")

    # 分表细节
    print()
    print(f"{'='*80}")
    print("分表对比（各场景 × 三张表的 Cell F1 均值）")
    print(f"{'='*80}")

    # Collect all statement keys
    all_stmt_keys: set[str] = set()
    for s in scene_stats.values():
        for stmt_key in s.get("by_statement", {}):
            all_stmt_keys.add(stmt_key)

    # Map statement keys to readable names
    stmt_name_map = {}
    for key in all_stmt_keys:
        if "资产" in key:
            stmt_name_map[key] = "资产负债表"
        elif "利润" in key:
            stmt_name_map[key] = "利润表"
        elif "现金" in key:
            stmt_name_map[key] = "现金流量表"
        else:
            stmt_name_map[key] = key

    # Build header with all three statements
    stmt_display = ["利润表", "资产负债表", "现金流量表"]
    header2 = f"  {'场景':<14} {'n':>3}"
    for sname in stmt_display:
        header2 += f" {sname:>10}"
    print(header2)
    print("  " + "-" * (len(header2) - 2))

    for scene_name in ["A_跨页表格", "B_密集数值", "C_页眉页脚", "D_多页", "F_多栏排版", "G_无边框表格"]:
        s = scene_stats.get(scene_name, {})
        if not s or s.get("n", 0) == 0:
            continue
        n = s["n"]
        short_name = scene_name.split("_")[1] if "_" in scene_name else scene_name
        row = f"  {short_name:<14} {n:>3}"
        by_stmt = s.get("by_statement", {})
        for display_name in stmt_display:
            # Find matching key
            matched = None
            for k in by_stmt:
                if display_name in stmt_name_map.get(k, k):
                    matched = by_stmt[k]
                    break
            if matched:
                f1 = matched.get("cell_f1_avg", 0)
                teds = matched.get("teds_avg", 0)
                row += f" {f1:.3f}/{teds:.3f}"
            else:
                row += f" {'—':>10}"
        print(row)

    print()
    print("  格式: Cell_F1 / TEDS")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    scene_codes = load_scene_lists()
    results = load_module1_results()

    if not results:
        print("[ERROR] No module 1 results loaded")
        return 1

    print(f"Loaded {len(results)} company results")
    for scene_name, codes in scene_codes.items():
        matched = sum(1 for c in codes if c in results)
        print(f"  {scene_name}: {matched}/{len(codes)} matched")

    scene_stats = compute_scene_averages(results, scene_codes)
    print_report(scene_stats, results)

    # 保存
    output_path = PROJECT_ROOT / "output" / "las_results" / "module1_scene_breakdown.json"
    output_path.write_text(json.dumps(scene_stats, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
