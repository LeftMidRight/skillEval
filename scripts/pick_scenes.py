"""三类互斥挑选：无边框2 + 密集数值10 + 跨页表格10。"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sig = json.loads((ROOT / "output/scene_selection/finar_signals.json").read_text(encoding="utf-8"))

# 1) 无边框固定
borderless = ["601555", "601009"]
used = set(borderless)

# 2) 密集数值：numeric_density 最高，排除已用
dense_sorted = sorted(
    ((c, s) for c, s in sig.items() if "error" not in s and c not in used),
    key=lambda kv: kv[1].get("numeric_density", 0), reverse=True,
)
dense = []
for c, s in dense_sorted:
    if len(dense) >= 10:
        break
    dense.append(c)
    used.add(c)

# 3) 跨页表格：cross_page_score 最高，排除已用
cross_sorted = sorted(
    ((c, s) for c, s in sig.items() if "error" not in s and c not in used),
    key=lambda kv: (kv[1].get("cross_page_score", 0), kv[1].get("pages", 0)), reverse=True,
)
cross = []
for c, s in cross_sorted:
    if len(cross) >= 10:
        break
    cross.append(c)
    used.add(c)

def show(name, codes):
    print(f"\n== {name} ({len(codes)}) ==")
    for c in codes:
        s = sig[c]
        print(f"  {c}  density={s.get('numeric_density'):>6}  cps={s.get('cross_page_score'):>3}  "
              f"pages={s.get('pages'):>3}  bracket_neg={s.get('bracket_negatives'):>3}  ratio_units={s.get('units')}")

show("无边框表格 borderless", borderless)
show("密集数值 dense_numerical", dense)
show("跨页表格 cross_page", cross)

# 重复校验
allc = borderless + dense + cross
assert len(allc) == len(set(allc)), "存在重复！"
print(f"\n总计 {len(allc)} 个，无重复 ✓")

result = {"borderless_tables": borderless, "dense_numerical": dense, "cross_page_tables": cross}
(ROOT / "output/scene_selection/pick30.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
print("Saved: output/scene_selection/pick30.json")
