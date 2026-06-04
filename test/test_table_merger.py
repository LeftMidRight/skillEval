"""跨页表格合并单元测试。"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "skill" / "script"))

import table_merger as tm


# ---------------------------------------------------------------------------
# 单元测试：页面噪声检测
# ---------------------------------------------------------------------------

def test_page_number_detection():
    assert tm._is_page_noise("71 / 212", set())
    assert tm._is_page_noise("1 / 10", set())
    assert not tm._is_page_noise("营业收入", set())
    assert not tm._is_page_noise("", set())


def test_repeated_line_detection():
    repeated = tm._find_repeated_lines("A\nB\nA\nC\nA\nD\nB\nB")
    assert "A" in repeated
    assert "B" in repeated
    assert "C" not in repeated


def test_signature_detection():
    assert tm._is_page_noise("公司负责人：张三", set())
    assert tm._is_page_noise("主管会计工作负责人：李四", set())
    assert tm._is_page_noise("会计机构负责人：王五", set())


def test_intratable_page_row_removal():
    html = (
        "<table><tbody>"
        "<tr><td>货币资金</td><td>1,234.56</td></tr>"
        '<tr><td colspan="4">71 / 212</td></tr>'
        "<tr><td>应收账款</td><td>789.01</td></tr>"
        "</tbody></table>"
    )
    cleaned = tm._clean_table_html(html)
    assert "71 / 212" not in cleaned
    assert "货币资金" in cleaned
    assert "应收账款" in cleaned


# ---------------------------------------------------------------------------
# 单元测试：表格解析与合并
# ---------------------------------------------------------------------------

def test_parse_table_basic():
    html = (
        "<table><thead><tr><th>项目</th><th>金额</th></tr></thead>"
        "<tbody><tr><td>货币资金</td><td>100</td></tr></tbody></table>"
    )
    info = tm._parse_table_html(html)
    assert info.col_count == 2


def test_parse_table_with_colspan():
    html = (
        "<table><thead><tr><th>项目</th><th>备注</th><th>2023</th><th>2022</th></tr></thead>"
        '<tbody><tr><td colspan="4">流动资产：</td></tr>'
        "<tr><td>货币资金</td><td></td><td>100</td><td>200</td></tr></tbody></table>"
    )
    info = tm._parse_table_html(html)
    assert info.col_count == 4  # colspan="4" → 4 columns


def test_should_merge_continuation():
    """跨页延续：中间只有页码，table_b 无 thead → 应合并。"""
    table_a = "<table><thead><tr><th>项目</th></tr></thead><tbody><tr><td>A</td></tr></tbody></table>"
    table_b = "<table><tbody><tr><td>B</td></tr></tbody></table>"
    between = "71 / 212\n\n2023 年度报告"
    assert tm._should_merge(between, table_a, table_b, {"2023 年度报告"})


def test_should_not_merge_new_section():
    """新表格：中间有标题，table_b 有 thead → 不合并。"""
    table_a = "<table><thead><tr><th>项目</th></tr></thead><tbody><tr><td>A</td></tr></tbody></table>"
    table_b = "<table><thead><tr><th>项目</th></tr></thead><tbody><tr><td>B</td></tr></tbody></table>"
    between = "公司负责人：张三\n\n合并利润表"
    assert not tm._should_merge(between, table_a, table_b, set())


def test_should_not_merge_new_table_title():
    """中间出现了新表名 → 不合并。"""
    table_a = "<table><thead><tr><th>项目</th></tr></thead><tbody><tr><td>A</td></tr></tbody></table>"
    table_b = "<table><tbody><tr><td>B</td></tr></tbody></table>"
    between = "母公司资产负债表\n2023年12月31日"
    assert not tm._should_merge(between, table_a, table_b, set())


def test_merge_two_tables():
    table_a = (
        "<table><thead><tr><th>项目</th><th>金额</th></tr></thead>"
        "<tbody><tr><td>货币资金</td><td>100</td></tr></tbody></table>"
    )
    table_b = (
        "<table><tbody><tr><td>应收账款</td><td>200</td></tr></tbody></table>"
    )
    merged = tm._merge_two_tables(table_a, table_b)
    assert "货币资金" in merged
    assert "应收账款" in merged
    # thead 1 行 + tbody 2 行 = 3 行
    assert merged.count("<tr>") == 3
    # 只保留一个 thead / table
    assert merged.count("<thead>") == 1
    assert merged.count("<table>") == 1


# ---------------------------------------------------------------------------
# 集成测试：真实 LAS 输出
# ---------------------------------------------------------------------------

def test_merge_on_real_output():
    """用 603256 的真实 LAS 输出验证合并效果。"""
    md_path = PROJECT_ROOT / "output" / "las_results" / "603256" / "report.md"
    if not md_path.exists():
        print("  SKIP: 603256 report.md not found (run batch_las_parse first)")
        return

    original = md_path.read_text(encoding="utf-8")
    merged = tm.merge_cross_page_tables(original)

    # 1. 表格数量减少
    assert merged.count("<table>") < original.count("<table>"), "Tables should be reduced"

    # 2. HTML 标签平衡
    assert merged.count("<table>") == merged.count("</table>"), "Table tag mismatch"
    assert merged.count("<thead>") <= merged.count("</thead>"), "Thead tag mismatch"

    # 3. 表内无页码残留
    tables = re.findall(r"<table>(.*?)</table>", merged, re.DOTALL)
    for t in tables:
        markers = re.findall(r"\d+\s*/\s*\d+", t)
        assert not markers, f"Page marker found inside table: {markers}"

    # 4. 重复页眉应显著减少
    assert merged.count("2023 年度报告") <= 3, "Repeated headers should be cleaned"

    print(f"  PASS: {original.count('<table>')} -> {merged.count('<table>')} tables")


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main() -> int:
    tests = [
        ("page_number_detection", test_page_number_detection),
        ("repeated_line_detection", test_repeated_line_detection),
        ("signature_detection", test_signature_detection),
        ("intratable_page_row_removal", test_intratable_page_row_removal),
        ("parse_table_basic", test_parse_table_basic),
        ("parse_table_with_colspan", test_parse_table_with_colspan),
        ("should_merge_continuation", test_should_merge_continuation),
        ("should_not_merge_new_section", test_should_not_merge_new_section),
        ("should_not_merge_new_table_title", test_should_not_merge_new_table_title),
        ("merge_two_tables", test_merge_two_tables),
        ("merge_on_real_output", test_merge_on_real_output),
    ]

    passed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as e:
            print(f"FAIL {name}: {e}")
        except Exception as e:
            print(f"ERROR {name}: {e}")

    print(f"\n{passed}/{len(tests)} tests passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
