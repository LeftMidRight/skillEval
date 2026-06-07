"""批量处理器单元测试。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "skill" / "script"))

from batch_processor import _derive_code, _extract_markdown


def test_derive_code_from_url():
    code = _derive_code("https://example.com/pdf/603256.pdf", 0)
    assert code == "603256"


def test_derive_code_from_complex_url():
    code = _derive_code(
        "https://tos.volces.com/bucket/path/600082_2023_annual.pdf?sign=abc",
        0,
    )
    assert code == "600082"


def test_derive_code_preserves_multicolumn_sample_suffix():
    code = _derive_code("https://example.com/pdf/600569_multi.pdf", 0)
    assert code == "600569_multi"


def test_derive_code_preserves_synthetic_sample_suffix():
    code = _derive_code("https://example.com/pdf/603421_synth.pdf?sign=abc", 0)
    assert code == "603421_synth"


def test_derive_code_fallback_filename():
    code = _derive_code("https://example.com/reports/annual_report.pdf", 0)
    assert code == "annual_report"


def test_derive_code_fallback_index():
    code = _derive_code("https://example.com/", 0)
    assert code == "task_000"


def test_extract_markdown_valid():
    response = {"poll_response": {"data": {"markdown": "# Report"}}}
    assert _extract_markdown(response) == "# Report"


def test_extract_markdown_empty():
    response = {"poll_response": {"data": {"markdown": ""}}}
    assert _extract_markdown(response) == ""


def test_extract_markdown_missing():
    response = {"poll_response": {}}
    assert _extract_markdown(response) == ""


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main() -> int:
    tests = [
        ("derive_code_from_url", test_derive_code_from_url),
        ("derive_code_from_complex_url", test_derive_code_from_complex_url),
        ("derive_code_preserves_multicolumn_sample_suffix", test_derive_code_preserves_multicolumn_sample_suffix),
        ("derive_code_preserves_synthetic_sample_suffix", test_derive_code_preserves_synthetic_sample_suffix),
        ("derive_code_fallback_filename", test_derive_code_fallback_filename),
        ("derive_code_fallback_index", test_derive_code_fallback_index),
        ("extract_markdown_valid", test_extract_markdown_valid),
        ("extract_markdown_empty", test_extract_markdown_empty),
        ("extract_markdown_missing", test_extract_markdown_missing),
    ]

    passed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as e:
            print(f"FAIL {name}: {e}")

    print(f"\n{passed}/{len(tests)} tests passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
