"""Layout behavior tests for synthetic_multicolumn."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "sandbox"))

from gen_synthetic_scenes import MultiColumnPDF


def test_full_width_page_can_disable_column_divider():
    pdf = MultiColumnPDF("Test Company", "000000")
    pdf._new_page()
    page = pdf.current_page_number()

    assert pdf.page_draws_divider(page)
    pdf.disable_current_divider()
    assert not pdf.page_draws_divider(page)


def main() -> int:
    tests = [
        ("full_width_page_can_disable_column_divider", test_full_width_page_can_disable_column_divider),
    ]
    passed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as exc:
            print(f"FAIL {name}: {exc}")
        except Exception as exc:
            print(f"ERROR {name}: {exc}")

    print(f"\n{passed}/{len(tests)} tests passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
