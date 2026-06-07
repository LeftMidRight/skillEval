"""Evaluation manifest contract tests."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.manifest import get_sample, iter_samples, load_manifest
from evaluation.module1.evaluator import evaluate_sample


def test_manifest_sample_ids_are_unique_and_paths_exist():
    manifest = load_manifest()
    samples = manifest["samples"]
    sample_ids = [sample.sample_id for sample in samples]

    assert len(sample_ids) == len(set(sample_ids))
    assert len(samples) >= 28

    for sample in samples:
        assert sample.pdf_path.exists(), sample.pdf_path
        assert sample.gt_path.exists(), sample.gt_path
        assert sample.las_result_dir.name == sample.sample_id or not sample.synthetic


def test_manifest_keeps_synthetic_multicolumn_separate_from_company_code():
    sample = get_sample("600569_multicolumn")

    assert sample.company_code == "600569"
    assert sample.scene == "synthetic_multicolumn"
    assert sample.synthetic
    assert sample.pdf_path.name == "600569_multi.pdf"
    assert sample.gt_path.name == "600569_multi_gt.json"
    assert sample.las_result_dir.name == "600569_multicolumn"


def test_iter_samples_can_filter_by_scene():
    samples = list(iter_samples(scene="synthetic_multicolumn"))
    assert {sample.sample_id for sample in samples} == {
        "600569_multicolumn",
        "603421_multicolumn",
        "603707_multicolumn",
    }


def test_module1_evaluate_sample_preserves_sample_identity_with_inline_markdown():
    sample = get_sample("600569_multicolumn")
    las_markdown = """
<table><tbody>
<tr><td>营业收入</td><td>42,150,904,679.37</td></tr>
</tbody></table>
"""

    result = evaluate_sample(sample, las_markdown=las_markdown)

    assert result["sample_id"] == "600569_multicolumn"
    assert result["company_code"] == "600569"
    assert result["scene"] == "多栏排版（合成）"
    assert result["las_result_dir"].endswith("600569_multicolumn")
    assert result["text_accuracy"]["status"] == "not_applicable"
    assert "xbrl_recall" in result["number_accuracy"]


def main() -> int:
    tests = [
        ("manifest_sample_ids_are_unique_and_paths_exist", test_manifest_sample_ids_are_unique_and_paths_exist),
        ("manifest_keeps_synthetic_multicolumn_separate_from_company_code", test_manifest_keeps_synthetic_multicolumn_separate_from_company_code),
        ("iter_samples_can_filter_by_scene", test_iter_samples_can_filter_by_scene),
        ("module1_evaluate_sample_preserves_sample_identity_with_inline_markdown", test_module1_evaluate_sample_preserves_sample_identity_with_inline_markdown),
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
