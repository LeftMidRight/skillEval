"""共享场景映射。

三场景互不重叠：
  - 跨页表格 (cross_page_tables): 10 家
  - 密集数值 (dense_numerical): 10 家
  - 无边框表格 (borderless_tables): 2 家

数据源：data/eval_dataset/_selection.json
"""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# 场景中文名 → 目录名
SCENE_LABELS = {
    "跨页表格": "cross_page_tables",
    "密集数值": "dense_numerical",
    "无边框表格": "borderless_tables",
    "无边框表格（合成）": "synthetic_borderless",
    "多栏排版（合成）": "synthetic_multicolumn",
}

# 目录名 → 中文名
SCENE_LABELS_REV = {v: k for k, v in SCENE_LABELS.items()}

_SELECTION_PATH = PROJECT_ROOT / "data" / "eval_dataset" / "_selection.json"


def load_selection() -> dict:
    """加载 _selection.json。"""
    if _SELECTION_PATH.exists():
        return json.loads(_SELECTION_PATH.read_text(encoding="utf-8"))
    return {}


def get_scene_map() -> dict[str, str]:
    """返回 company_code → 场景目录名 的映射。

    Returns:
        {"603256": "cross_page_tables", "601117": "dense_numerical", ...}
    """
    sel = load_selection()
    scenes = sel.get("scenes", {})
    mapping: dict[str, str] = {}
    for dir_name, info in scenes.items():
        for code in info.get("codes", []):
            mapping[code] = dir_name
    return mapping


def get_scene_label(company_code: str) -> str:
    """返回公司所属场景的中文名，找不到则返回 "未知"。"""
    scene_map = get_scene_map()
    dir_name = scene_map.get(company_code)
    if dir_name:
        return SCENE_LABELS_REV.get(dir_name, "未知")
    return "未知"


def get_scene_companies(scene_dir: str) -> list[str]:
    """返回指定场景目录下的公司代码列表。"""
    sel = load_selection()
    for dir_name, info in sel.get("scenes", {}).items():
        if dir_name == scene_dir:
            return list(info.get("codes", []))
    return []