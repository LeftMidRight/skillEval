"""模块 1 评测验证脚本。

用已有数据跑一遍完整评测链路：
  - LAS 输出：output/las_pdf_parse_sample/las_test_response.json （示例 PDF 的解析结果）
  - XBRL 数据：data/FinAR-Bench/dev.txt

由于示例 PDF 不是财报，表格/数值指标对示例 PDF 意义有限，
本脚本主要验证：
  1. 代码能正常 import 和运行
  2. 数据加载正常
  3. CER 计算正常（有实际文本）
  4. 表格匹配不至于崩溃（即使无匹配也有合理的输出）
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 确保项目根路径在 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from module1.evaluator import Evaluator, Module1Result
from module1.text_accuracy import compute_cer
from module1.number_matcher import _extract_numbers_from_markdown, _extract_xbrl_numbers
from module1.utils import load_xbrl_dataset, parse_xbrl_tables, extract_table_sections


def test_imports():
    """验证所有模块可导入。"""
    print("[OK] All modules imported successfully")


def test_xbrl_loading():
    """验证 XBRL 数据加载。"""
    xbrl_path = PROJECT_ROOT / "data" / "FinAR-Bench" / "dev.txt"
    records = load_xbrl_dataset(xbrl_path)
    assert len(records) > 0, "No XBRL records loaded"
    print(f"[OK] Loaded {len(records)} XBRL records")

    # 检查每条记录的结构
    for i, rec in enumerate(records[:3]):
        assert "table" in rec, f"Record {i} missing 'table'"
        assert "instances" in rec, f"Record {i} missing 'instances'"
        # company_code 在 instances[0] 中
        code = rec.get("file_path", "?")
        name = rec["instances"][0].get("company", "?") if rec.get("instances") else "?"
        tables = parse_xbrl_tables(rec["table"])
        assert len(tables) >= 2, f"Record {i} has {len(tables)} tables (expected >= 2)"
        print(f"  Record {i}: {code} {name} - tables: {list(tables.keys())}")

    return records


def test_las_output_loading():
    """验证 LAS 输出加载。"""
    las_path = PROJECT_ROOT / "output" / "las_pdf_parse_sample" / "las_test_response.json"
    if not las_path.exists():
        print("[WARN] LAS test output not found, skipping LAS-specific tests")
        return None

    data = json.loads(las_path.read_text(encoding="utf-8"))
    poll = data.get("poll_response", {})
    assert "data" in poll, "poll_response missing 'data'"
    markdown = poll["data"].get("markdown", "")
    assert markdown, "No markdown in LAS output"
    print(f"[OK] LAS output loaded: {len(markdown)} chars of markdown")
    snippet = markdown[:80].replace('\n', '\\n')
    print(f"  First 80 chars: {snippet}...")
    return data


def test_cer_calculation():
    """验证 CER 计算。"""
    ref = "合并资产负债表2023年12月31日编制单位青岛鼎信通讯股份有限公司"
    hyp = "合并资产负债表2023年12月31日编制单位青岛鼎信通讯股份公司"  # 少了 "有限"
    cer = compute_cer(ref, hyp)
    assert cer > 0, "CER should be > 0 for differing strings"
    assert cer < 0.2, f"CER too high: {cer}"
    print(f"[OK] CER calculation works: CER={cer:.4f} (expected ~0.05)")

    # 完全相同的文本
    cer_same = compute_cer(ref, ref)
    assert cer_same == 0.0, f"CER for identical strings should be 0, got {cer_same}"
    print(f"[OK] CER for identical strings = {cer_same}")


def test_number_extraction():
    """验证数值提取和标准化。"""
    from module1.utils import normalize_number, extract_numbers

    test_text = """
    营业总收入 3,632,703,199.78 元
    净利润 (131,220,189.16)
    基本每股收益 0.20 元
    增长率 12.34%
    """
    numbers = extract_numbers(test_text)
    print(f"[OK] Extracted {len(numbers)} raw numbers: {numbers}")

    # 测试标准化
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

    # 验证数值提取
    xbrl_nums = _extract_xbrl_numbers(rec)
    print(f"[OK] Extracted {len(xbrl_nums)} unique XBRL numbers")
    print(f"  Examples: {list(xbrl_nums)[:5]}")


def test_teds():
    """验证 TEDS 计算。"""
    from module1.table_fidelity import compute_teds
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
    result = compute_teds(t1, t2)
    assert result["teds"] == 1.0, f"Identical tables should have TEDS=1.0, got {result['teds']}"
    print(f"[OK] TEDS identical tables = {result['teds']}")

    # 少一行
    t3 = TableTree([
        [TableCell("项目"), TableCell("2023"), TableCell("2022")],
        [TableCell("营业收入"), TableCell("100.00"), TableCell("90.00")],
    ])
    result2 = compute_teds(t1, t3)
    assert 0.6 < result2["teds"] < 1.0, f"Missing row TEDS should be 0.6-1.0, got {result2['teds']}"
    print(f"[OK] TEDS with missing row = {result2['teds']} (edit_dist={result2['edit_distance']})")

    # 数值有差异
    t4 = TableTree([
        [TableCell("项目"), TableCell("2023"), TableCell("2022")],
        [TableCell("营业收入"), TableCell("100.00"), TableCell("90.00")],
        [TableCell("净利润"), TableCell("99.99"), TableCell("9.00")],  # 10.00 → 99.99
    ])
    result3 = compute_teds(t1, t4)
    assert 0.8 < result3["teds"] < 1.0, f"Mismatched value TEDS should be < 1.0, got {result3['teds']}"
    print(f"[OK] TEDS with value mismatch = {result3['teds']} (edit_dist={result3['edit_distance']})")

    # 多一列 (colspan)
    t5 = TableTree([
        [TableCell("项目"), TableCell("2023", colspan=2)],  # colspan=2
        [TableCell("营业收入"), TableCell("100.00"), TableCell("95.00")],  # extra col
        [TableCell("净利润"), TableCell("10.00"), TableCell("9.00")],
    ])
    result4 = compute_teds(t1, t5)
    print(f"[OK] TEDS with colspan diff = {result4['teds']} (edit_dist={result4['edit_distance']}, aligned_rows={result4['aligned_rows']})")


def test_evaluator_real_600064():
    """用真实 LAS 输出 (600064) + XBRL 跑完整评测。"""
    from module1.evaluator import Evaluator

    evaluator = Evaluator(
        xbrl_path=PROJECT_ROOT / "data" / "FinAR-Bench" / "test.txt",
        reference_dir=PROJECT_ROOT / "data" / "FinAR-Bench" / "extracted" / "pdf_extractor_result" / "txt_output",
    )

    las_path = PROJECT_ROOT / "output" / "las_results" / "600064" / "las_response.json"
    if not las_path.exists():
        print("[WARN] 600064 LAS output not found, skipping")
        return

    result = evaluator.evaluate(las_path, company_code="600064")
    print(f"\n{'='*60}")
    print(f"Module 1 Evaluation - 600064 ({result.company_name})")
    print(f"{'='*60}")
    print(f"Errors: {result.errors}")
    print(f"Warnings: {result.warnings}")

    cer_info = result.text_accuracy.raw_metrics.get('mineru_cer', 'N/A')
    teds_info = result.table_fidelity.raw_metrics.get('teds', {}).get('overall', 'N/A')
    f1_info = result.table_fidelity.raw_metrics.get('overall', {}).get('f1', 'N/A')
    num_info = result.number_accuracy.raw_metrics.get('f1', 'N/A')

    print(f"Text Accuracy:     {result.text_accuracy.score}/10  (CER vs Mineru={cer_info})")
    print(f"Table Fidelity:    {result.table_fidelity.score}/10  (TEDS={teds_info:.4f}, Cell F1={f1_info:.4f})")
    print(f"Number Accuracy:   {result.number_accuracy.score}/10  (F1={num_info:.4f})")
    print(f">>> Module 1 Score: {result.module1_score}/10 <<<")

    # 分表详情
    teds_by = result.table_fidelity.raw_metrics.get('teds', {}).get('by_statement', {})
    f1_by = result.table_fidelity.raw_metrics.get('by_statement', {})
    if teds_by:
        print("\nBy statement:")
        for stmt in sorted(teds_by.keys()):
            t = teds_by.get(stmt, {})
            f = f1_by.get(stmt, {})
            print(f"  {stmt}: TEDS={t.get('teds', 0):.4f} Cell_F1={f.get('f1', 0):.4f}")

    assert not result.errors, f"Errors: {result.errors}"
    print("\n[OK] Real evaluation pipeline with TEDS passes")
    """用 XBRL 数据 + LAS 输出跑完整评测。"""
    las_path = PROJECT_ROOT / "output" / "las_pdf_parse_sample" / "las_test_response.json"
    if not las_path.exists():
        print("[WARN] Skipping evaluator test (no LAS output available)")
        return

    evaluator = Evaluator(
        xbrl_path=PROJECT_ROOT / "data" / "FinAR-Bench" / "dev.txt",
        reference_dir=PROJECT_ROOT / "data" / "FinAR-Bench" / "extracted" / "pdf_extractor_result" / "txt_output",
    )

    result = evaluator.evaluate(las_path, company_code="603421")
    print(f"\n{'='*60}")
    print(f"Module 1 Evaluation Result")
    print(f"{'='*60}")
    print(f"Company: {result.company_name} ({result.company_code})")
    print(f"Task ID: {result.task_id}")
    print(f"Errors: {result.errors}")
    print(f"Warnings: {result.warnings}")
    print(f"\n--- Sub-metric Scores ---")
    cer_info = result.text_accuracy.raw_metrics.get('mineru_cer', 'N/A')
    teds_info = result.table_fidelity.raw_metrics.get('teds', {}).get('overall', 'N/A')
    f1_info = result.table_fidelity.raw_metrics.get('overall', {}).get('f1', 'N/A')
    num_info = result.number_accuracy.raw_metrics.get('f1', 'N/A')
    print(f"Text Accuracy:     {result.text_accuracy.score}/10  (CER vs Mineru={cer_info})")
    print(f"Table Fidelity:    {result.table_fidelity.score}/10  (TEDS={teds_info}, Cell F1={f1_info})")
    print(f"Number Accuracy:   {result.number_accuracy.score}/10  (F1={num_info})")
    print(f"\n>>> Module 1 Overall Score: {result.module1_score}/10 <<<")

    # 检查没有严重错误（但允许 warnings，因为示例 PDF 不是财报）
    assert not result.errors, f"Unexpected errors: {result.errors}"
    print(f"\n[OK] Evaluator pipeline runs without errors")


def main():
    print("Module 1 Evaluator -- Verification\n")

    tests = [
        ("imports", test_imports),
        ("XBRL loading", test_xbrl_loading),
        ("LAS output loading", test_las_output_loading),
        ("CER calculation", test_cer_calculation),
        ("Number extraction", test_number_extraction),
        ("Table extraction", test_table_extraction),
        ("TEDS calculation", test_teds),
        ("Full evaluator pipeline", test_evaluator_real_600064),
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
