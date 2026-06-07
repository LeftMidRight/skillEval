"""Shared scene mapping helpers backed by the evaluation manifest."""

from __future__ import annotations

import json
from pathlib import Path

from evaluation.manifest import (
    SCENE_TITLES,
    get_scene_label as _manifest_scene_label,
    get_scene_map as _manifest_scene_map,
    iter_samples,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

SCENE_LABELS = {title: scene for scene, title in SCENE_TITLES.items()}

SCENE_LABELS_REV = {v: k for k, v in SCENE_LABELS.items()}

_SELECTION_PATH = PROJECT_ROOT / "data" / "eval_dataset" / "_selection.json"


def load_selection() -> dict:
    """加载 _selection.json。"""
    if _SELECTION_PATH.exists():
        return json.loads(_SELECTION_PATH.read_text(encoding="utf-8"))
    return {}


def get_scene_map(use_sample_id: bool = False) -> dict[str, str]:
    """返回 identifier → 场景目录名 的映射。

    Returns:
        {"603256": "cross_page_tables", "600569_multicolumn": "synthetic_multicolumn", ...}
    """
    return _manifest_scene_map(use_sample_id=use_sample_id)


def get_scene_label(company_code: str) -> str:
    """返回 sample_id 或不歧义 company_code 所属场景的中文名。"""
    return _manifest_scene_label(company_code)


def get_scene_companies(scene_dir: str) -> list[str]:
    """返回指定场景目录下的 sample_id 列表。"""
    return [sample.sample_id for sample in iter_samples(scene=scene_dir)]
