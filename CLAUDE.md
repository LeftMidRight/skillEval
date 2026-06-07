# CLAUDE.md — 金融财报 PDF 解析 Skill 评测项目

## 课题目标

开发并评测一个基于火山引擎 LAS（`las_pdf_parse_doubao`）的金融财报 PDF 解析 Skill。

## 课题核心要求

### 1. PDF 解析能力（金融场景）
- 重点攻克：跨页表格、无边框表格、密集数值提取、多栏排版阅读顺序
- 支持精准识别：标题、正文、表格、图片、页眉页脚等元素
- 还原正确的阅读顺序（Reading Order）
- 复杂表格（合并单元格、多级表头）还原为 HTML/Markdown 格式
- 结果标准化输出为 JSON 或 Markdown

### 2. 全流程端到端
- 输入数据 → OpenClaw 调度 → 自定义 Skill 执行 → 结果输出/保存
- 至少 1 组真实样例完成验证，流程可重复执行
- 异常场景兜底：输入不合法、素材缺失、模型返回异常、处理超时等

### 3. 评测体系
- 评测方案：评测指标 + 判断标准
- 评测用例集
- 评测结果
- 典型成功/失败案例分析及优化结论

### 4. 加分项
- 深度行业视野：行业调研、主流开源/商业方案对比、前沿论文梳理
- 严谨量化体系：明确打分标准（公式定义、扣分细则）或 LLM-as-a-Judge 设计
- 自动化评测能力：一键跑通对比打分，输出可视化结果报告

---

## 评测框架（3 模块 + 异常兜底）

```
模块 1: 内容还原（Content Fidelity）
  ├── 1.1 文本准确率（CER vs 6 parsers + Mineru baseline）
  ├── 1.2 表格还原度（XBRL Item Recall + Mineru TEDS/Cell F1）
  ├── 1.3 数值提取率（XBRL Recall + Mineru Jaccard）
  └── 1.4 跨页表格连续性（合并成功率 + 表头保留率）

模块 2: 结构保真（Structure Preservation）— 全部 LLM-as-Judge
  └── 2.1 阅读顺序（页内三维度评分 + 跨页连续性判断）

模块 3: 下游可用性（Downstream Utility）— 全部 LLM-as-Judge
  ├── fact: LLM 提取数值 → 与 XBRL GT 对比（1% 容差）
  ├── indicator: LLM 计算指标 → 与 XBRL GT 对比（2% 容差）
  └── reasoning: LLM 0/1 判断 → 与 GT 对比

异常兜底: 非法输入 / 素材缺失 / 超时等

行业调研: 第零章
  ├── 主流方案横向对比（Mineru/pdfplumber/PaddleOCR/Nougat/Marker）
  └── 各方案在金融财报场景的优劣分析
```

---

## 评测数据集

| 数据集 | 规模 | 用途 |
|--------|------|------|
| FinAR-Bench dev/test.txt | 10+90 家公司 XBRL 三张表 + 13 任务 | Ground Truth |
| eval_dataset/cross_page_tables/ | 10 份年报 PDF | 跨页表格场景 |
| eval_dataset/dense_numerical/ | 10 份年报 PDF | 密集数值提取场景 |
| eval_dataset/borderless_tables/ | 2 份年报 PDF | 无边框表格场景 |
| eval_dataset/anomaly/ | 4 个异常文件 | 鲁棒性测试（损坏/加密/空文件/非PDF） |
| eval_dataset/S5_long_documents/ | 1 份合成 98 页 PDF | 长文档压力测试 |
| extracted/txt_output/ | 6 种解析器对照输出 | CER 交叉参照 |

## 代码提交规则

- **每次修改都必须提交到 git 仓库**，确保变更历史完整。
- 提交信息使用中文，简明描述改动原因和内容。

---

## 行为准则

以下准则优先考虑代码质量和可维护性，避免常见的 LLM 编码问题。

### 1. 三思后行

- 编码前明确假设条件。有疑问先澄清，不要猜。
- 存在多种方案时，列出权衡而非直接选择。
- 有更简单的方案时主动提出。不合理的要求要 push back。
- 遇到模糊不清的地方，停下来，指出困惑点，再问。

### 2. 简洁优先

- 只写需求范围内的代码。不加未要求的功能。
- 不为「可能的未来需求」预留扩展性。
- 一次性代码不抽取抽象层。
- 不可能发生的场景不加错误处理。
- 问自己：「资深工程师会觉得这段代码过度设计吗？」如果是，简化它。

### 3. 精准修改

- 只改与任务直接相关的代码。不顺手重构无关代码。
- 匹配现有代码风格，即使不是你惯用的写法。
- 发现无关的死代码，口头提及即可，不要顺手删。
- 你的改动导致的孤立代码（无用的 import、变量、函数），清理干净。

### 4. 目标驱动

- 把任务转化为可验证的目标：「修复 bug」→「写一个能复现的测试，修到测试通过」。
- 多步骤任务先列计划，每步注明验证方式。
- 验证通过才算完成，不要猜。
- `/goal` 模式下，先读 `docs/goals/` 下的目标文档，以此为实施合同。

### 5. Git 提交纪律

- 仓库文件有改动就提交，除非用户明确要求不提交。

### 6. 沙箱与权限

- `sandbox/` 目录用于临时实验、草稿脚本、中间产物。其内容默认被 git 忽略。
- 仓库内默认允许的非破坏性操作：读写编辑文件、运行本地检查/脚本/测试、创建本地分支/worktree、暂存和提交。
- 破坏性或环境级操作需先确认：hard reset、history rewrite、批量删除、凭证修改、网络安装/下载、仓库外的写入。

---

## 技术栈

- 解析引擎：火山引擎 LAS `las_pdf_parse_doubao` v1
- PDF 存储：火山引擎 TOS（`ark-auto-2108530377-cn-beijing-default`）
- 评测语言：Python 3.12
- Ground Truth：XBRL（来自上海证券交易所，FinAR-Bench 数据集）

## 关键路径

- LAS 配置文件：`skill/script/config.yaml`
- LAS API 客户端：`skill/script/las_client.py`
- 批量解析脚本：`scripts/batch_las_parse.py`
- 批量评测脚本：`scripts/batch_module1_eval.py`（v3）
- 场景拆解脚本：`scripts/scene_breakdown.py`（v3）
- LAS 解析结果：`output/las_results/{股票代码}/`
- 评测模块（v3）：
  - `evaluation/module1/` 内容还原（含跨页表格连续性）
  - `evaluation/module2/` 结构保真（LLM-as-Judge 阅读顺序）
  - `evaluation/module3/` 下游可用性（LLM-as-Judge 三类任务）
- 共用工具函数：`module1/utils.py`
- 评测方案文档：`docs/evaluation_plan_v3.md`
