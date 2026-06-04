"""结构化 JSON 输出单元测试。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "skill" / "script"))

import structured_output as so


# ---------------------------------------------------------------------------
# 基础解析
# ---------------------------------------------------------------------------

SAMPLE_MD = """## 审计报告

本报告针对公司2023年度财务报表进行审计。

### 合并资产负债表

2023年12月31日

<table><thead><tr><th>项目</th><th>金额</th></tr></thead><tbody><tr><td>货币资金</td><td>1,234.56</td></tr></tbody></table>

上述财务报表已按照企业会计准则编制。
"""


def test_parse_title():
    elements = so.parse_markdown_to_elements("## 合并资产负债表\n\n### 流动资产")
    titles = [e for e in elements if e.type == "title"]
    assert len(titles) == 2
    assert titles[0].level == 2
    assert titles[0].content == "合并资产负债表"
    assert titles[1].level == 3


def test_parse_table():
    html = "<table><thead><tr><th>项目</th><th>金额</th></tr></thead><tbody><tr><td>现金</td><td>100</td></tr></tbody></table>"
    elements = so.parse_markdown_to_elements(html)
    tables = [e for e in elements if e.type == "table"]
    assert len(tables) == 1
    assert tables[0].table_info is not None
    assert tables[0].table_info.rows == 2  # 1 header + 1 data
    assert tables[0].table_info.cols == 2
    assert tables[0].table_info.headers == ["项目", "金额"]


def test_parse_paragraph():
    elements = so.parse_markdown_to_elements("这是一段正文。\n包含两行。\n\n## 下一节")
    paras = [e for e in elements if e.type == "paragraph"]
    assert len(paras) == 1
    assert "这是一段正文" in paras[0].content


def test_full_parse():
    elements = so.parse_markdown_to_elements(SAMPLE_MD)
    types = [e.type for e in elements]
    assert "title" in types
    assert "table" in types
    assert "paragraph" in types
    # 验证顺序：标题 → 段落 → 标题 → 段落 → 表格 → 段落
    assert types[0] == "title"
    assert types[-1] == "paragraph"


def test_table_info():
    html = '<table><thead><tr><th>A</th><th>B</th><th>C</th></tr></thead><tbody><tr><td>1</td><td>2</td><td>3</td></tr><tr><td colspan="3">小计</td></tr></tbody></table>'
    info = so._parse_table(html)
    assert info.rows == 3
    assert info.cols == 3  # colspan="3"
    assert info.has_thead
    assert info.headers == ["A", "B", "C"]


# ---------------------------------------------------------------------------
# 页眉页脚检测
# ---------------------------------------------------------------------------

def test_find_page_noise():
    elements = [
        so.Element(type="paragraph", content="2023 年年度报告\n正文内容"),
        so.Element(type="paragraph", content="2023 年年度报告\n更多内容"),
        so.Element(type="paragraph", content="2023 年年度报告\n其他"),
    ]
    noise = so._find_page_noise_lines(elements)
    assert "2023 年年度报告" in noise


def test_tag_page_noise():
    elements = [
        so.Element(type="paragraph", content="2023 年年度报告\n71 / 212\n正文内容"),
        so.Element(type="paragraph", content="2023 年年度报告\n72 / 212\n更多内容"),
        so.Element(type="paragraph", content="2023 年年度报告\n其他"),
    ]
    result = so.tag_page_noise(elements)
    noise_els = [e for e in result if e.type == "page_noise"]
    assert len(noise_els) >= 1


# ---------------------------------------------------------------------------
# 完整输出
# ---------------------------------------------------------------------------

def test_build_structured_output():
    result_json = so.build_structured_output(SAMPLE_MD, metadata={"company_code": "600001"})
    result = json.loads(result_json)

    assert "metadata" in result
    assert "elements" in result
    assert "reading_order" in result
    assert result["metadata"]["company_code"] == "600001"
    assert len(result["reading_order"]) == len(result["elements"])

    # 验证元素结构
    for el in result["elements"]:
        assert "type" in el
        assert "content" in el
        assert el["type"] in ("title", "table", "paragraph", "page_noise")


def test_output_on_real_data():
    """用真实 LAS 输出验证结构化 JSON。"""
    md_path = PROJECT_ROOT / "output" / "las_results" / "603256" / "report.md"
    if not md_path.exists():
        print("  SKIP: 603256 report.md not found")
        return

    sys.path.insert(0, str(PROJECT_ROOT / "skill" / "script"))
    from table_merger import merge_cross_page_tables

    markdown = merge_cross_page_tables(md_path.read_text(encoding="utf-8"))
    result_json = so.build_structured_output(markdown)
    result = json.loads(result_json)

    # 基本完整性
    assert result["metadata"]["total_elements"] > 0
    assert len(result["elements"]) == result["metadata"]["total_elements"]
    assert result["reading_order"] == list(range(len(result["elements"])))

    # 三类元素都必须存在
    types = {el["type"] for el in result["elements"]}
    assert "title" in types, "Missing titles"
    assert "table" in types, "Missing tables"
    assert "paragraph" in types, "Missing paragraphs"

    # 表格必须有 table_info
    tables = [el for el in result["elements"] if el["type"] == "table"]
    for t in tables:
        assert "table_info" in t
        assert t["table_info"]["rows"] > 0

    print(f"  PASS: {result['metadata']['total_elements']} elements, "
          f"{result['metadata']['element_counts']}")


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main() -> int:
    tests = [
        ("parse_title", test_parse_title),
        ("parse_table", test_parse_table),
        ("parse_paragraph", test_parse_paragraph),
        ("full_parse", test_full_parse),
        ("table_info", test_table_info),
        ("find_page_noise", test_find_page_noise),
        ("tag_page_noise", test_tag_page_noise),
        ("build_structured_output", test_build_structured_output),
        ("output_on_real_data", test_output_on_real_data),
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
