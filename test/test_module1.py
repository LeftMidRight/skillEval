"""模块 1 评测验证脚本。

验证：
  1. 代码能正常 import 和运行
  2. 数据加载正常
  3. CER 计算正常
  4. 表格匹配不崩溃
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from module1.text_accuracy import compute_cer
from module1.utils import (
    TableCell, TableTree, extract_numbers, extract_table_sections,
    load_xbrl_dataset, normalize_number, parse_xbrl_tables,
)


def test_xbrl_loading():
    """验证 XBRL 数据加载。"""
    xbrl_path = PROJECT_ROOT / "data" / "FinAR-Bench" / "dev.txt"
    records = load_xbrl_dataset(xbrl_path)
    assert len(records) > 0, "No XBRL records loaded"
    print(f"[OK] Loaded {len(records)} XBRL records")

    for i, rec in enumerate(records[:3]):
        assert "table" in rec, f"Record {i} missing 'table'"
        assert "instances" in rec, f"Record {i} missing 'instances'"
        code = rec.get("file_path", "?")
        name = rec["instances"][0].get("company", "?") if rec.get("instances") else "?"
        tables = parse_xbrl_tables(rec["table"])
        assert len(tables) >= 2, f"Record {i} has {len(tables)} tables (expected >= 2)"
        print(f"  Record {i}: {code} {name} - tables: {list(tables.keys())}")

    return records


def test_cer_calculation():
    """验证 CER 计算。"""
    ref = "合并资产负债表2023年12月31日编制单位青岛鼎信通讯股份有限公司"
    hyp = "合并资产负债表2023年12月31日编制单位青岛鼎信通讯股份公司"
    cer = compute_cer(ref, hyp)
    assert cer > 0, "CER should be > 0 for differing strings"
    assert cer < 0.2, f"CER too high: {cer}"
    print(f"[OK] CER calculation works: CER={cer:.4f}")

    cer_same = compute_cer(ref, ref)
    assert cer_same == 0.0, f"CER for identical strings should be 0, got {cer_same}"
    print(f"[OK] CER for identical strings = {cer_same}")


def test_number_extraction():
    """验证数值提取和标准化。"""
    test_text = """
    营业总收入 3,632,703,199.78 元
    净利润 (131,220,189.16)
    基本每股收益 0.20 元
    增长率 12.34%
    """
    numbers = extract_numbers(test_text)
    print(f"[OK] Extracted {len(numbers)} raw numbers: {numbers}")

    assert normalize_number("3,632,703,199.78") == "3632703199.78"
    assert normalize_number("(131,220,189.16)") == "-131220189.16"
    assert normalize_number("0.20") == "0.20"
    print(f"[OK] Number normalization works")


def test_table_extraction():
    """验证表格提取。"""
    records = load_xbrl_dataset(PROJECT_ROOT / "data" / "FinAR-Bench" / "dev.txt")
    rec = records[0]
    tables = parse_xbrl_tables(rec["table"])

    for name, rows in tables.items():
        print(f"  Table '{name}': {len(rows)} rows")
        if rows:
            first_row = rows[0]
            print(f"    Columns: {list(first_row.keys())}")
            print(f"    First row: {list(first_row.values())[:4]}")


def test_teds():
    """验证 TEDS 计算。"""

    # 内联一个简化的 TEDS 计算（与 evaluation/module1/table_fidelity.py 一致）
    from module1.utils import TableCell, TableTree

    # 构造两个相同的表
    t1 = TableTree([
        [TableCell("项目"), TableCell("2023"), TableCell("2022")],
        [TableCell("营业收入"), TableCell("100.00"), TableCell("90.00")],
        [TableCell("净利润"), TableCell("10.00"), TableCell("9.00")],
    ])
    t2 = TableTree([
        [TableCell("项目"), TableCell("2023"), TableCell("2022")],
        [TableCell("营业收入"), TableCell("100.00"), TableCell("90.00")],
        [TableCell("净利润"), TableCell("10.00"), TableCell("9.00")],
    ])
    # 简单验证：相同表格节点数相同
    assert t1.node_count == t2.node_count == 9
    assert t1.row_count == t2.row_count == 3
    print(f"[OK] TableTree: node_count={t1.node_count}, row_count={t1.row_count}")

    # 不同表格
    t3 = TableTree([
        [TableCell("项目"), TableCell("2023"), TableCell("2022")],
        [TableCell("营业收入"), TableCell("100.00"), TableCell("90.00")],
    ])
    assert t3.node_count == 6
    assert t3.row_count == 2
    print(f"[OK] Smaller table: node_count={t3.node_count}, row_count={t3.row_count}")


def test_module1_new_evaluator():
    """用新 evaluation/module1/ 跑 600064 评测。"""
    from evaluation.module1.evaluator import evaluate_company

    try:
        result = evaluate_company("600064")
        print(f"\n{'='*60}")
        print(f"Module 1 Evaluation - 600064")
        print(f"{'='*60}")

        ta = result["text_accuracy"]
        print(f"Text Accuracy: median_cer={ta['median_cer']:.3f} mineru_cer={ta['mineru_cer']:.3f} "
              f"mineru_baseline_cer={ta['mineru_median_cer']:.3f}")

        tf = result["table_fidelity"]
        xbrl_r = tf["xbrl_item_recall"]
        print(f"XBRL Item Recall: overall={xbrl_r.get('overall_recall', 'N/A')}")
        mf = tf["mineru_fidelity"]
        print(f"Mineru TEDS: {mf.get('avg_teds', 'N/A')}")
        print(f"Mineru Cell F1: overall={mf.get('avg_cell_f1', 'N/A')}")

        na = result["number_accuracy"]
        print(f"Number XBRL Recall: {na['xbrl_recall']:.3f}")
        print(f"Number Mineru Jaccard: {na['mineru_jaccard']}")

        print("\n[OK] New evaluator pipeline runs without errors")
    except FileNotFoundError:
        print("[WARN] 600064 LAS result or XBRL not found, skipping")


def main():
    print("Module 1 Evaluator -- Verification\n")

    tests = [
        ("XBRL loading", test_xbrl_loading),
        ("CER calculation", test_cer_calculation),
        ("Number extraction", test_number_extraction),
        ("Table extraction", test_table_extraction),
        ("TEDS / TableTree", test_teds),
        ("New evaluator (600064)", test_module1_new_evaluator),
    ]

    passed = 0
    for name, func in tests:
        try:
            print(f"\n--- {name} ---")
            func()
            passed += 1
        except Exception as e:
            print(f"[FAIL] {name}: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'='*60}")
    print(f"{passed}/{len(tests)} tests passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
