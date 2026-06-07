# 评测数据集 — FinAR 三场景分类

聚焦课题**金融场景**，全部样本来自 FinAR-Bench（中文 A 股 2023 年报财务报表节选），
均有 XBRL 标准答案，三类场景**公司代码互不重复**，共 22 份 PDF。

## 场景总览

| 目录 | 场景 | 数量 | 挑选信号 | 核心评测指标 |
|------|------|------|----------|-------------|
| `cross_page_tables/` | 跨页表格 | 10 | cross_page_score（连续表格页跨度）最高 | 跨页拼接完整性 |
| `dense_numerical/` | 密集数值提取 | 10 | numeric_density（每页金额型数值数）最高 | 数值 Precision/Recall/F1 |
| `borderless_tables/` | 无边框表格 | 2 | 竖线/数值比最低（少边框/无边框） | TEDS / 表格还原 |

> 课题金融场景共 4 项（跨页表格、密集数值、无边框表格、多栏排版）。
> FinAR 可覆盖前 3 项；**多栏排版**经全量检测确认 A 股财报为单栏，FinAR 无此类样本，不评测。

## 各场景入选代码

### 跨页表格（10）
603256, 603299, 600933, 601012, 603955, 600100, 600366, 601222, 600082, 600193
- 信号：cross_page_score 12~23，页数 12~36（报表自然跨物理页）

### 密集数值提取（10）
601117, 603630, 601696, 600778, 600679, 603365, 603313, 603439, 600130, 600623
- 信号：numeric_density 88~124/页（短而密的财务报表）

### 无边框表格（2）
601555, 601009
- 信号：竖线/数值比 601555=0.17、601009=1.5，显著低于其余 98 家（均 ≥8.6）
- 说明：FinAR 全量扫描后真正"无边框/少边框"仅此 2 家，为该场景的真实上限

## 数据来源

- **PDF**：`../FinAR-Bench/extracted/pdf_data/<code>.pdf`（原始全量 100 份）
- **XBRL 真值**：`../FinAR-Bench/dev.txt`（10 家）、`../FinAR-Bench/test.txt`（90 家）
- 每份 PDF 含三张主表（资产负债表/利润表/现金流量表）+ 13 个下游任务

## 选择依据与复现

- 信号扫描：`scripts/analyze_finar_signals.py` → `output/scene_selection/finar_signals.json`
- 无边框排序：`scripts/rank_borderless.py` → `output/scene_selection/borderless_rank.json`
- 三类互斥挑选：`scripts/pick_scenes.py` → `output/scene_selection/pick30.json`
- 候选页渲染（人工核验无边框/多栏）：`scripts/render_candidates.py` → `output/page_renders/`
- 构建场景目录：`scripts/build_scene_selection.py` → 各 `<scene>/selection.json` + `_selection.json`

## 文件说明

- `_selection.json`：三场景主清单（含各类代码列表）
- `<scene>/selection.json`：各场景详细清单（含每份 PDF 的信号值）
- `_finarb_metadata.json`：FinAR 100 份页数等元数据（参考）

## 更新记录

- 2026-06-04：回归 FinAR 单一数据源，收敛为跨页表格/密集数值/无边框表格三场景（22 份），
  移除依赖 OmniDocBench/OHR-Bench 的旧 S1~S6/E1~E4 体系及旧 A~G 体系。
