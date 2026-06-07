"""Unified scene report tests."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.unified_scene_report import compute_m1_scene_stats


def test_m1_scene_stats_use_sample_id_and_current_metric_schema():
    results = {
        "600569_multicolumn": {
            "sample_id": "600569_multicolumn",
            "company_code": "600569",
            "text_accuracy": {"median_cer": 0.25},
            "table_fidelity": {
                "xbrl_item_recall": {"overall_recall": 0.5},
                "mineru_fidelity": {"avg_teds": 0.6, "avg_cell_f1": 0.7},
            },
            "number_accuracy": {"xbrl_recall": 0.8, "mineru_jaccard": 0.9},
            "cross_page_continuity": {"merge_success_rate": 1.0, "header_preserved": True},
        }
    }

    stats = compute_m1_scene_stats(results)
    synthetic = stats["多栏排版（合成）"]

    assert synthetic["n"] == 1
    assert synthetic["xbrl_item_recall"] == 0.5
    assert synthetic["mineru_teds"] == 0.6
    assert synthetic["mineru_cell_f1"] == 0.7


def main() -> int:
    tests = [
        ("m1_scene_stats_use_sample_id_and_current_metric_schema", test_m1_scene_stats_use_sample_id_and_current_metric_schema),
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
