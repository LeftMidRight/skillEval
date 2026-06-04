"""密集数值提取单元测试。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "skill" / "script"))

import number_extractor as ne


def test_normalize_positive():
    result = ne.normalize_value("1,234,567.89")
    assert result["value"] == 1234567.89
    assert not result["is_negative"]
    assert result["has_thousands_separator"]


def test_normalize_parentheses_negative():
    result = ne.normalize_value("(1,234.56)")
    assert result["value"] == -1234.56
    assert result["is_negative"]
    assert result["has_parentheses"]


def test_normalize_minus_negative():
    result = ne.normalize_value("-1,234,567.89")
    assert result["value"] == -1234567.89
    assert result["is_negative"]


def test_normalize_zero():
    result = ne.normalize_value("0.00")
    assert result["value"] == 0.0


def test_normalize_percentage():
    result = ne.normalize_value("12.34%")
    assert result["value"] == 12.34
    assert result["is_percentage"]


def test_is_financial_number():
    assert ne._is_financial_number("1,234,567.89")
    assert ne._is_financial_number("(123.45)")
    assert not ne._is_financial_number("2023")  # year
    assert not ne._is_financial_number("12345678901")  # phone-like
    assert not ne._is_financial_number("1")  # sequence number


def test_extract_numbers_from_html():
    markdown = (
        "<table><thead><tr><th>项目</th><th>2023</th></tr></thead>"
        "<tbody><tr><td>货币资金</td><td>1,234.56</td></tr>"
        "<tr><td>净利润</td><td>(789.01)</td></tr></tbody></table>"
    )
    result = ne.extract_numbers_from_markdown(markdown)

    assert result["summary"]["total_numbers"] == 2
    numbers = result["numbers"]
    assert numbers[0]["value"] == 1234.56
    assert numbers[1]["value"] == -789.01


def test_extract_on_real_data():
    """用真实 LAS 输出验证数值提取。"""
    md_path = PROJECT_ROOT / "output" / "las_results" / "603256" / "report.md"
    if not md_path.exists():
        print("  SKIP: 603256 report.md not found")
        return

    sys.path.insert(0, str(PROJECT_ROOT / "skill" / "script"))
    from table_merger import merge_cross_page_tables

    markdown = merge_cross_page_tables(md_path.read_text(encoding="utf-8"))
    result = ne.extract_numbers_from_markdown(markdown)

    s = result["summary"]
    # 603256 has lots of financial numbers
    assert s["total_numbers"] > 500
    assert s["tables_with_numbers"] > 20

    # Negatives should have negative values
    for n in result["numbers"]:
        if n["is_negative"] and n["value"] is not None:
            assert n["value"] < 0, f"{n['raw']} -> {n['value']}"

    # All table refs should be valid
    max_table = s["total_tables"] - 1
    for n in result["numbers"]:
        assert 0 <= n["table_index"] <= max_table

    print(f"  PASS: {s['total_numbers']} numbers from {s['tables_with_numbers']} tables")


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main() -> int:
    tests = [
        ("normalize_positive", test_normalize_positive),
        ("normalize_parentheses_negative", test_normalize_parentheses_negative),
        ("normalize_minus_negative", test_normalize_minus_negative),
        ("normalize_zero", test_normalize_zero),
        ("normalize_percentage", test_normalize_percentage),
        ("is_financial_number", test_is_financial_number),
        ("extract_numbers_from_html", test_extract_numbers_from_html),
        ("extract_on_real_data", test_extract_on_real_data),
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
