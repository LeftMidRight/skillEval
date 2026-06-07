# 评测数据集 — Manifest 样本清单

聚焦课题**金融场景**。当前 canonical 样本清单是 `manifest.json`，每条样本都有唯一
`sample_id`，并显式记录 `pdf_path`、`gt_path`、`las_result_dir`、`scene` 和 `source`。所有 canonical
GT 均已整理到 `ground_truth/`，上传整个 `eval_dataset/` 后不再依赖外部 `data/FinAR-Bench` GT 文件。

数据分两层：

- 真实 FinAR-Bench 场景：22 份 PDF，覆盖跨页表格、密集数值、真实无边框表格。
- 合成与鲁棒性专项场景：11 份 PDF，覆盖合成无边框表格、合成多栏排版、超长文档和异常文档。

同一家公司代码可以出现在多个样本中，例如 `600569` 同时用于合成无边框和合成多栏；
评测代码必须以 `sample_id` 区分，不能只用 `company_code`。

## 场景总览

| 目录 | 场景 | 数量 | 挑选信号 | 核心评测指标 |
|------|------|------|----------|-------------|
| `cross_page_tables/` | 跨页表格 | 10 | cross_page_score（连续表格页跨度）最高 | 跨页拼接完整性 |
| `dense_numerical/` | 密集数值提取 | 10 | numeric_density（每页金额型数值数）最高 | 数值 Precision/Recall/F1 |
| `borderless_tables/` | 无边框表格 | 5 | 2 份真实 FinAR + 3 份合成无线条 | TEDS / 表格还原 |
| `synthetic_multicolumn/` | 多栏排版（合成） | 3 | 真实年报双栏专题页生成器 | 阅读顺序 / layout_gt |
| `S5_long_documents/` | 超长文档（合成） | 1 | 40 页长文档压力样本 | 长文档解析稳定性 / XBRL-like GT |
| `anomaly/` | 异常文档 | 4 | 损坏、零页、加密、伪 PDF | 解析鲁棒性 / expected failure |

> 评测体系覆盖 6 类场景（跨页表格、密集数值、无边框表格、多栏排版、超长文档、异常文档）。
> FinAR 可覆盖前 3 项；多栏排版、超长文档和异常文档使用合成/鲁棒性样本补齐。

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

### 超长文档（合成，1）
SYNTH_001_long_document
- 说明：使用 `S5_long_documents/SYNTH_001.pdf` 和 `ground_truth/SYNTH_001_long_document_gt.json`，作为长文档压力评测样本。

### 异常文档（4）
anomaly_corrupted, anomaly_empty, anomaly_encrypted, anomaly_not_a_pdf
- 说明：异常样本进入统一 manifest，但 `gt_kind=expected_parse_failure`，用于评测解析失败处理和错误上报，不参与普通内容质量评分。

## 数据来源

- **PDF**：`../FinAR-Bench/extracted/pdf_data/<code>.pdf`（原始全量 100 份）
- **XBRL 真值来源**：`../FinAR-Bench/dev.txt`（10 家）、`../FinAR-Bench/test.txt`（90 家）
- 每份 PDF 含三张主表（资产负债表/利润表/现金流量表）+ 13 个下游任务
- **Canonical GT**：所有 33 个样本的评测真值统一放在 `ground_truth/<sample_id>_gt.json`；真实 FinAR 样本已抽成 `xbrl_record_json`。

## 选择依据与复现

- 信号扫描：`scripts/analyze_finar_signals.py` → `output/scene_selection/finar_signals.json`
- 无边框排序：`scripts/rank_borderless.py` → `output/scene_selection/borderless_rank.json`
- 三类互斥挑选：`scripts/pick_scenes.py` → `output/scene_selection/pick30.json`
- 候选页渲染（人工核验无边框/多栏）：`scripts/render_candidates.py` → `output/page_renders/`
- 旧版场景目录构建脚本已归档：`scripts/archive/build_scene_selection_legacy.py`

## 文件说明

- `manifest.json`：canonical 样本清单，评测代码和解析调度优先读取它；所有 `eval_dataset` PDF 都应在其中有唯一 `sample_id`
- `ground_truth/`：所有 manifest 样本的 canonical GT，文件名为 `<sample_id>_gt.json`
- `_selection.json`：场景摘要清单，用于人工查看
- `<scene>/selection.json`：各场景详细清单（含每份 PDF 的信号值）
- `_finarb_metadata.json`：FinAR 100 份页数等元数据（参考）

## 更新记录

- 2026-06-08：manifest 扩展为完整评测体系入口，接入合成无边框、多栏、超长文档和异常文档，使用 `eval_modules`/`expected_parse_status` 区分质量评分与解析鲁棒性评测。
- 2026-06-08：将所有 canonical GT 收拢到 `ground_truth/`，真实 FinAR GT 从 dev/test 抽取为每样本独立 JSON，便于直接上传 `eval_dataset/`。
- 2026-06-08：引入 manifest，增加合成无边框和合成多栏专项样本，使用 `sample_id` 避免同公司代码串线。
- 2026-06-04：回归 FinAR 单一数据源，收敛为跨页表格/密集数值/无边框表格三场景（22 份），
  移除依赖 OmniDocBench/OHR-Bench 的旧 S1~S6/E1~E4 体系及旧 A~G 体系。
