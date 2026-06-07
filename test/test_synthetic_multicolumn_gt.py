"""synthetic_multicolumn GT 契约测试。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.manifest import iter_samples

SCENE_DIR = PROJECT_ROOT / "data" / "eval_dataset" / "synthetic_multicolumn"


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_multicolumn_gt_contains_layout_gt():
    samples = list(iter_samples(scene="synthetic_multicolumn"))
    assert len(samples) == 3

    for sample in samples:
        data = _load_json(sample.gt_path)
        assert data["company_code"]
        assert data["company_name"]
        assert data["xbrl_table"]
        assert isinstance(data["instances"], list)

        layout_gt = data["layout_gt"]
        assert layout_gt["layout_type"] == "synthetic_multicolumn_annual_report_topic"
        assert layout_gt["reading_order"] == "left_column_then_right_column"
        assert len(layout_gt["pages"]) >= 4

        multicol_pages = [p for p in layout_gt["pages"] if p["is_multicolumn"]]
        assert len(multicol_pages) >= 3
        for page in multicol_pages[:3]:
            assert page["columns"] == ["left", "right"]
            assert page["sections"]
            for section in page["sections"]:
                assert section["id"]
                assert section["title"]
                assert section["column_sequence"] == ["left", "right"]
                assert section["paragraph_ids"]


def test_multicolumn_selection_matches_files():
    selection = _load_json(SCENE_DIR / "selection.json")
    assert len(selection) == 3

    for entry in selection:
        code = entry["code"]
        file_name = entry["file"]
        assert code in {"600569", "603421", "603707"}
        assert file_name == f"{code}_multi.pdf"
        assert (SCENE_DIR / file_name).exists()

        sample_id = f"{code}_multicolumn"
        sample = next(s for s in iter_samples(scene="synthetic_multicolumn") if s.sample_id == sample_id)
        assert sample.gt_path.name == f"{sample_id}_gt.json"
        assert sample.gt_path.exists()


def main() -> int:
    tests = [
        ("multicolumn_gt_contains_layout_gt", test_multicolumn_gt_contains_layout_gt),
        ("multicolumn_selection_matches_files", test_multicolumn_selection_matches_files),
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
