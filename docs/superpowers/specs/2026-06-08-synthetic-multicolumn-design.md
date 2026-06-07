# synthetic_multicolumn 真实年报双栏专题页设计

## 背景

`data/eval_dataset/synthetic_multicolumn/` 当前包含 3 份合成多栏 PDF 及对应 XBRL GT：

- `600569_multi.pdf`
- `603421_multi.pdf`
- `603707_multi.pdf`

现有 PDF 的主要问题是：正文虽然使用两栏参数生成，但页面常出现右栏大面积留白；财务表格大量采用通栏布局，视觉上更像“单栏正文加中线”，不足以代表真实年报中的双栏专题页。

本次目标是按“真实年报双栏专题页”重构该数据集，而不是做刻意刁钻的阅读顺序压力测试。

## 目标

1. 每份 `_multi.pdf` 呈现自然、明显的双栏专题页排版。
2. 左栏内容读完后自然进入右栏，右栏填满后再进入下一页左栏。
3. 页面风格接近上市公司年报中的管理层讨论、行业分析、风险提示、经营展望等章节。
4. 保留现有 XBRL GT 和 FinAR 下游任务 GT，不破坏 Module 1/3 的既有输入口径。
5. 新增轻量 `layout_gt`，为 Module 2 阅读顺序评测提供页面和栏目级真值。

## 非目标

1. 不构造极端/对抗式多栏场景，例如故意左右栏交错、乱序标题、复杂跨栏嵌套。
2. 不扩大公司样本数量，仍保持当前 3 家公司。
3. 不改 FinAR 原始 XBRL 数值和下游任务真值。
4. 不重构无边框表格场景，只保证生成脚本不会破坏其输出。

## 页面设计

每份 PDF 生成 4-5 页，结构如下：

| 页型 | 内容 | 排版 |
| --- | --- | --- |
| 专题首页 | 公司名称、证券代码、年度报告摘要、公司概况 | 通栏标题 + 双栏正文 |
| 管理层讨论页 | 经营回顾、行业环境、核心竞争力 | 双栏正文，左右栏填满 |
| 经营与研发页 | 业务亮点、研发投入、供应链或市场拓展 | 双栏正文 + 小型摘要框 |
| 风险与展望页 | 风险提示、治理、利润分配或经营计划 | 双栏正文 + 重点提示框 |
| 财务摘要页 | 与 XBRL 对齐的关键财务摘要表 | 通栏小表，减少大表占比 |

版面规则：

- A4 纵向页面。
- 两栏等宽，栏间距约 8-10mm。
- 栏间分隔线保留，但颜色变浅，避免过于“报纸化”。
- 每页正文尽量填满左右栏，避免右栏空白。
- 通栏元素只用于页首标题、小节分隔和少量财务摘要表。
- 财务表只保留关键科目摘要，不再把完整三张财报表作为主要页面内容。

## 数据内容设计

每家公司保留现有行业和公司叙述，但扩展为更接近年报语气的专题正文：

- 公司概况与主营业务
- 经营回顾与财务表现
- 行业格局与竞争优势
- 研发投入与技术进展
- 市场拓展与供应链管理
- 风险因素与应对措施
- 公司治理与内控
- 利润分配或未来展望

正文应使用公司特定内容，避免三家公司模板化重复。

## GT 设计

`*_multi_gt.json` 继续保留现有字段：

```json
{
  "company_code": "600569",
  "company_name": "安阳钢铁",
  "xbrl_table": "...",
  "instances": []
}
```

新增 `layout_gt` 字段：

```json
{
  "layout_gt": {
    "layout_type": "synthetic_multicolumn_annual_report_topic",
    "reading_order": "left_column_then_right_column",
    "pages": [
      {
        "page": 1,
        "is_multicolumn": true,
        "columns": ["left", "right"],
        "sections": [
          {
            "id": "overview",
            "title": "一、公司概况与经营回顾",
            "column_sequence": ["left", "right"],
            "paragraph_ids": ["overview_p1", "overview_p2"]
          }
        ]
      }
    ]
  }
}
```

字段含义：

- `layout_type`：标识该 GT 属于真实年报双栏专题页。
- `reading_order`：固定为先左栏、后右栏。
- `pages`：逐页标注是否为多栏页。
- `sections`：记录该页出现的小节标题和段落顺序。
- `paragraph_ids`：与生成器中的段落 ID 对齐，用于阅读顺序核验。

## 生成器设计

集中修改 `sandbox/gen_synthetic_scenes.py`。

主要改动：

1. 增强 `MultiColumnPDF` 的正文流排能力，保证同一节内容自然填充左右栏。
2. 增加专题页组件：
   - 通栏章节标题
   - 双栏正文段落
   - 单栏/通栏小型摘要框
   - 通栏关键财务摘要表
3. 为每个写入页面的 section 和 paragraph 同步记录 `layout_gt`。
4. 扩展 `save_gt`，允许写入 `layout_gt`。
5. 重生成 `synthetic_multicolumn` 下 3 份 PDF、3 份 GT 和 `selection.json`。

生成脚本仍可一次生成无边框与多栏两个合成场景，但本次实现只改变多栏输出逻辑和多栏 GT 内容。

## 验证方案

实现后执行以下检查：

1. 运行生成脚本，确认 3 份 `_multi.pdf` 和 3 份 `_multi_gt.json` 重新生成。
2. 渲染每份 PDF 前 3 页为 PNG，人工确认：
   - 左右栏均有正文内容。
   - 页面不像单栏正文加中线。
   - 通栏表格不再主导页面。
3. 校验 GT：
   - 每个 `_multi_gt.json` 均包含 `company_code/company_name/xbrl_table/instances/layout_gt`。
   - `layout_gt.pages` 非空。
   - 至少前 3 页标记为 `is_multicolumn: true`。
   - `paragraph_ids` 顺序与生成器写入顺序一致。
4. 校验 `selection.json`：
   - 3 条记录。
   - `file` 分别指向现有 3 个 `_multi.pdf`。
   - `code` 不带 `_multi` 后缀。
5. 检查无边框场景文件未被意外改坏。

## 风险与处理

| 风险 | 处理 |
| --- | --- |
| PDF 字体/行高导致右栏仍不满 | 用页级段落池补齐，必要时加入公司特定风险提示段 |
| 表格过宽破坏双栏观感 | 财务表只保留关键摘要，并集中放到财务摘要页 |
| GT 与 PDF 内容脱节 | 生成 PDF 时同步构建 `layout_gt`，避免后处理手写 |
| 生成脚本同时触碰无边框场景 | 只提交多栏相关产物；验证无边框 selection/GT 命名未改变 |

## 交付物

1. 更新后的 `sandbox/gen_synthetic_scenes.py`。
2. 重新生成的 `data/eval_dataset/synthetic_multicolumn/*.pdf`。
3. 重新生成的 `data/eval_dataset/synthetic_multicolumn/*_multi_gt.json`。
4. 更新后的 `data/eval_dataset/synthetic_multicolumn/selection.json`。
5. 必要的轻量校验脚本或测试。
