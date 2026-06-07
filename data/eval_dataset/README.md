# 评测数据集 — Manifest 样本清单

聚焦课题**金融场景**。当前 canonical 样本清单是 `manifest.json`，每条样本都有唯一
`sample_id`，并显式记录 `pdf_path`、`gt_path`、`las_result_dir`、`scene` 和 `source`。

数据分两层：

- 真实 FinAR-Bench 场景：22 份 PDF，覆盖跨页表格、密集数值、真实无边框表格。
- 合成专项场景：6 份 PDF，覆盖合成无边框表格和合成多栏排版。

同一家公司代码可以出现在多个样本中，例如 `600569` 同时用于合成无边框和合成多栏；
评测代码必须以 `sample_id` 区分，不能只用 `company_code`。

## 场景总览

| 目录 | 场景 | 数量 | 挑选信号 | 核心评测指标 |
|------|------|------|----------|-------------|
| `cross_page_tables/` | 跨页表格 | 10 | cross_page_score（连续表格页跨度）最高 | 跨页拼接完整性 |
| `dense_numerical/` | 密集数值提取 | 10 | numeric_density（每页金额型数值数）最高 | 数值 Precision/Recall/F1 |
| `borderless_tables/` | 无边框表格 | 5 | 2 份真实 FinAR + 3 份合成无线条 | TEDS / 表格还原 |
| `synthetic_multicolumn/` | 多栏排版（合成） | 3 | 真实年报双栏专题页生成器 | 阅读顺序 / layout_gt |

> 课题金融场景共 4 项（跨页表格、密集数值、无边框表格、多栏排版）。
> FinAR 可覆盖前 3 项；多栏排版使用 XBRL 数据反推的合成专题页单独评测。

## 各场景入选代码

### 跨页表格（10）
603256, 603299, 600933, 601012, 603955, 600100, 600366, 601222, 600082, 600193
- 信号：cross_page_score 12~23，页数 12~36（报表自然跨物理页）

### 密集数值提取（10）
601117, 603630, 601696, 600778, 600679, 603365, 603313, 603439, 600130, 600623
- 信号：numeric_density 88~124/页（短而密的财务报表）

### 无边框表格（5）
601555, 601009
- 信号：竖线/数值比 601555=0.17、601009=1.5，显著低于其余 98 家（均 ≥8.6）
- 说明：FinAR 全量扫描后真正"无边框/少边框"仅此 2 家；另加入 600569、603421、603707 三份合成无线条 PDF。

### 多栏排版（合成，3）
600569_multicolumn, 603421_multicolumn, 603707_multicolumn
- 说明：A 股年报 FinAR 样本为单栏，多栏排版使用 `synthetic_multicolumn/*_multi.pdf` 和对应 `layout_gt`。

## 数据来源

- **PDF**：`../FinAR-Bench/extracted/pdf_data/<code>.pdf`（原始全量 100 份）
- **XBRL 真值**：`../FinAR-Bench/dev.txt`（10 家）、`../FinAR-Bench/test.txt`（90 家）
- 每份 PDF 含三张主表（资产负债表/利润表/现金流量表）+ 13 个下游任务

## 选择依据与复现

- 信号扫描：`scripts/analyze_finar_signals.py` → `output/scene_selection/finar_signals.json`
- 无边框排序：`scripts/rank_borderless.py` → `output/scene_selection/borderless_rank.json`
- 三类互斥挑选：`scripts/pick_scenes.py` → `output/scene_selection/pick30.json`
- 候选页渲染（人工核验无边框/多栏）：`scripts/render_candidates.py` → `output/page_renders/`
- 旧版场景目录构建脚本已归档：`scripts/archive/build_scene_selection_legacy.py`

## 文件说明

- `manifest.json`：canonical 样本清单，评测代码优先读取它
- `_selection.json`：场景摘要清单，用于人工查看
- `<scene>/selection.json`：各场景详细清单（含每份 PDF 的信号值）
- `_finarb_metadata.json`：FinAR 100 份页数等元数据（参考）

## 更新记录

- 2026-06-08：引入 manifest，增加合成无边框和合成多栏专项样本，使用 `sample_id` 避免同公司代码串线。
- 2026-06-04：回归 FinAR 单一数据源，收敛为跨页表格/密集数值/无边框表格三场景（22 份），
  移除依赖 OmniDocBench/OHR-Bench 的旧 S1~S6/E1~E4 体系及旧 A~G 体系。
