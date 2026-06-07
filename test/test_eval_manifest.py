"""Evaluation manifest contract tests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from evaluation.manifest import get_sample, iter_samples, load_manifest
from evaluation.module1.evaluator import _load_xbrl_record_for_sample, evaluate_sample
from scripts.batch_module1_eval import _select_samples


def test_manifest_sample_ids_are_unique_and_paths_exist():
    manifest = load_manifest()
    samples = manifest["samples"]
    sample_ids = [sample.sample_id for sample in samples]

    assert len(sample_ids) == len(set(sample_ids))
    assert len(samples) == 33

    for sample in samples:
        assert sample.pdf_path.exists(), sample.pdf_path
        assert sample.gt_path.exists(), sample.gt_path
        assert sample.las_result_dir.name == sample.sample_id or not sample.synthetic


def test_manifest_covers_every_eval_dataset_pdf():
    manifest = load_manifest()
    manifest_pdfs = {
        sample.pdf_path.relative_to(PROJECT_ROOT).as_posix()
        for sample in manifest["samples"]
    }
    eval_pdfs = {
        path.relative_to(PROJECT_ROOT).as_posix()
        for path in (PROJECT_ROOT / "data" / "eval_dataset").glob("**/*.pdf")
    }

    assert eval_pdfs == manifest_pdfs


def test_manifest_ground_truth_is_packaged_with_eval_dataset():
    gt_root = PROJECT_ROOT / "data" / "eval_dataset" / "ground_truth"

    for sample in load_manifest()["samples"]:
        assert sample.gt_path.is_relative_to(gt_root), sample.gt_path
        assert sample.gt_path.name == f"{sample.sample_id}_gt.json"

        data = json.loads(sample.gt_path.read_text(encoding="utf-8"))
        assert data["sample_id"] == sample.sample_id
        assert data["gt_kind"] == sample.gt_kind


def test_long_document_sample_is_part_of_evaluation_system():
    sample = get_sample("SYNTH_001_long_document")

    assert sample.scene == "S5_long_documents"
    assert sample.gt_kind == "synthetic_gt_json"
    assert sample.gt_path.name == "SYNTH_001_long_document_gt.json"
    assert sample.expected_parse_status == "success"
    assert "module1" in sample.eval_modules
    assert "long_document" in sample.eval_modules


def test_anomaly_samples_are_expected_failure_evaluations():
    samples = list(iter_samples(scene="anomaly"))

    assert {sample.sample_id for sample in samples} == {
        "anomaly_corrupted",
        "anomaly_empty",
        "anomaly_encrypted",
        "anomaly_not_a_pdf",
    }
    for sample in samples:
        assert sample.gt_kind == "expected_parse_failure"
        assert sample.expected_parse_status == "failure"
        assert sample.eval_role == "anomaly"
        assert sample.eval_modules == ["parse_robustness"]


def test_module1_batch_selection_excludes_non_module1_samples():
    class Args:
        scene = None
        sample_id = None
        source = None
        synthetic = "all"

    selected_ids = {sample.sample_id for sample in _select_samples(Args())}

    assert "SYNTH_001_long_document" in selected_ids
    assert "anomaly_corrupted" not in selected_ids
    assert "anomaly_empty" not in selected_ids
    assert "anomaly_encrypted" not in selected_ids
    assert "anomaly_not_a_pdf" not in selected_ids


def test_module1_loads_packaged_xbrl_record_ground_truth():
    sample = get_sample("603256")

    assert sample.gt_kind == "xbrl_record_json"
    record = _load_xbrl_record_for_sample(sample)
    assert record["table"]
    assert record["instances"]


def test_manifest_keeps_synthetic_multicolumn_separate_from_company_code():
    sample = get_sample("600569_multicolumn")

    assert sample.company_code == "600569"
    assert sample.scene == "synthetic_multicolumn"
    assert sample.synthetic
    assert sample.pdf_path.name == "600569_multi.pdf"
    assert sample.gt_path.name == "600569_multicolumn_gt.json"
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
        ("manifest_covers_every_eval_dataset_pdf", test_manifest_covers_every_eval_dataset_pdf),
        ("manifest_ground_truth_is_packaged_with_eval_dataset", test_manifest_ground_truth_is_packaged_with_eval_dataset),
        ("long_document_sample_is_part_of_evaluation_system", test_long_document_sample_is_part_of_evaluation_system),
        ("anomaly_samples_are_expected_failure_evaluations", test_anomaly_samples_are_expected_failure_evaluations),
        ("module1_batch_selection_excludes_non_module1_samples", test_module1_batch_selection_excludes_non_module1_samples),
        ("module1_loads_packaged_xbrl_record_ground_truth", test_module1_loads_packaged_xbrl_record_ground_truth),
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
