"""Canonical evaluation sample manifest helpers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "data" / "eval_dataset" / "manifest.json"

SCENE_TITLES = {
    "cross_page_tables": "跨页表格",
    "dense_numerical": "密集数值",
    "borderless_tables": "无边框表格",
    "synthetic_multicolumn": "多栏排版（合成）",
}


@dataclass(frozen=True)
class EvalSample:
    """One concrete PDF/GT/LAS-result evaluation sample."""

    sample_id: str
    company_code: str
    scene: str
    source: str
    pdf_path: Path
    gt_path: Path
    gt_kind: str
    las_result_dir: Path
    synthetic: bool = False
    parser_reference_code: str | None = None
    notes: str = ""

    @property
    def scene_title(self) -> str:
        return SCENE_TITLES.get(self.scene, self.scene)

    @classmethod
    def from_dict(cls, raw: dict[str, Any], root: Path = PROJECT_ROOT) -> "EvalSample":
        return cls(
            sample_id=raw["sample_id"],
            company_code=raw["company_code"],
            scene=raw["scene"],
            source=raw.get("source", ""),
            pdf_path=_resolve_path(raw["pdf_path"], root),
            gt_path=_resolve_path(raw["gt_path"], root),
            gt_kind=raw.get("gt_kind", "finar_bench"),
            las_result_dir=_resolve_path(raw["las_result_dir"], root),
            synthetic=bool(raw.get("synthetic", False)),
            parser_reference_code=raw.get("parser_reference_code"),
            notes=raw.get("notes", ""),
        )

    def to_result_metadata(self) -> dict[str, Any]:
        return {
            "sample_id": self.sample_id,
            "company_code": self.company_code,
            "scene": self.scene_title,
            "scene_key": self.scene,
            "source": self.source,
            "synthetic": self.synthetic,
            "pdf_path": str(self.pdf_path),
            "gt_path": str(self.gt_path),
            "gt_kind": self.gt_kind,
            "las_result_dir": str(self.las_result_dir),
        }


def _resolve_path(value: str, root: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / path


def load_manifest(path: str | Path | None = None) -> dict[str, Any]:
    """Load the canonical evaluation manifest.

    Returns a dict with metadata fields and a `samples` list of EvalSample objects.
    """
    manifest_path = Path(path) if path else DEFAULT_MANIFEST_PATH
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    samples = [EvalSample.from_dict(item) for item in raw.get("samples", [])]
    return {
        "version": raw.get("version", 1),
        "description": raw.get("description", ""),
        "manifest_path": manifest_path,
        "samples": samples,
    }


def iter_samples(
    *,
    scene: str | None = None,
    source: str | None = None,
    synthetic: bool | None = None,
    manifest_path: str | Path | None = None,
) -> Iterable[EvalSample]:
    """Iterate samples, optionally filtering by scene/source/synthetic flag."""
    for sample in load_manifest(manifest_path)["samples"]:
        if scene is not None and sample.scene != scene:
            continue
        if source is not None and sample.source != source:
            continue
        if synthetic is not None and sample.synthetic != synthetic:
            continue
        yield sample


def get_sample(sample_id: str, manifest_path: str | Path | None = None) -> EvalSample:
    """Return one sample by its unique sample_id."""
    for sample in iter_samples(manifest_path=manifest_path):
        if sample.sample_id == sample_id:
            return sample
    raise KeyError(f"Evaluation sample not found: {sample_id}")


def get_samples_by_company(
    company_code: str,
    manifest_path: str | Path | None = None,
) -> list[EvalSample]:
    """Return all samples for a company code."""
    normalized = company_code.replace(".SH", "").replace(".pdf", "")
    return [
        sample
        for sample in iter_samples(manifest_path=manifest_path)
        if sample.company_code == normalized
    ]


def get_scene_map(use_sample_id: bool = False) -> dict[str, str]:
    """Return identifier -> scene key mapping.

    By default, only unambiguous company codes are included. Pass use_sample_id=True
    for the canonical sample_id mapping.
    """
    samples = list(iter_samples())
    if use_sample_id:
        return {sample.sample_id: sample.scene for sample in samples}

    by_code: dict[str, set[str]] = {}
    for sample in samples:
        by_code.setdefault(sample.company_code, set()).add(sample.scene)
    return {
        code: next(iter(scenes))
        for code, scenes in by_code.items()
        if len(scenes) == 1
    }


def get_scene_label(identifier: str) -> str:
    """Return the scene title for a sample_id or unambiguous company code."""
    by_sample = get_scene_map(use_sample_id=True)
    scene = by_sample.get(identifier)
    if scene:
        return SCENE_TITLES.get(scene, scene)

    by_company = get_scene_map(use_sample_id=False)
    scene = by_company.get(identifier.replace(".SH", "").replace(".pdf", ""))
    if scene:
        return SCENE_TITLES.get(scene, scene)
    return "未知"
