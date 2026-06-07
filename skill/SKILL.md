---
name: financial-report-analyzer-skill
description: 使用 LAS 解析金融行业财报 PDF，生成 Markdown、结构化 JSON、数值提取结果，支持跨页表格合并、表格校验和批量处理。
---

# 金融财报 PDF LAS 解析

## 描述

使用火山引擎 LAS PDF 解析能力，将金融行业财报 PDF 转换为多格式输出：

| 输出 | 文件 | 说明 |
|------|------|------|
| 原始响应 | `las_response.json` | LAS API 原始返回 |
| Markdown | `report.md` | 合并跨页表格、清除页面噪声后的 Markdown |
| 结构化 JSON | `report_structured.json` | 元素分类（标题/正文/表格/页眉）、阅读顺序、表格元数据 |
| 数值提取 | `report_numbers.json` | 标准化数值、单位检测、格式异常标记 |

## 核心能力

- **跨页表格合并**：检测并合并跨物理页断裂的表格，清除页码/重复页眉/签名栏噪声
- **结构化输出**：识别标题、正文、表格、页眉页脚，输出阅读顺序
- **密集数值提取**：从表格提取金融数值，标准化格式（千分位、括号负数、百分号）
- **表格结构校验**：检测列错位、空列等问题，标记无边框表风险等级
- **合并单元格识别**：检测 colspan/rowspan、多级表头、分组标题行
- **异常兜底**：统一错误码（输入/API/解析三级），输入校验，友好报错
- **批量处理**：URL 列表批量解析，自动生成批量汇总

## 触发条件

- 当用户需要解析上市公司年报、财报、半年报、季报、招股书、审计报告、财务公告等金融 PDF 时。
- 当用户请求包含”财报解析””PDF 转 Markdown””LAS 解析””解析年报””解析财务报告”等意图时。
- 当用户需要先获取 PDF 的正文、表格、页级 Markdown 或文本块，为后续财务字段抽取和评测做准备时。

## 工具依赖

- `script/config.yaml`：LAS 请求配置文件，用于填写 PDF URL、任务 ID、输出路径等参数。
- `script/las_client.py`：LAS API 客户端，负责调用 `/submit` 和 `/poll`。
- `script/las_pdf_parse.py`：工具入口脚本，负责读取配置、调用 LAS 客户端并保存响应。
- Python 运行环境。

## 工作流

### 重要：认证已预配置

- **LAS API Key 已通过环境变量 `LAS_API_KEY` 配置**，无需修改 `config.yaml` 中的 `api_key` 字段。
- `config.yaml` 中 `api_key: "${LAS_API_KEY}"` 会在运行时自动读取环境变量。
- **不要** 修改 `las:` 段的任何字段（base_url / api_key / operator_id / operator_version / timeout）。
- **不要** 索要 AK/SK 或新密钥——使用 Bearer token 方式认证，已经就绪。
- 你只需要：**修改 PDF URL、运行脚本、返回结果路径**。

### 单文件解析

1. 确认用户提供的 PDF URL 是可访问的 http/https 链接。
2. 仅修改 `script/config.yaml` 中以下字段：
   - `request.url` — 设为用户提供的 PDF URL
   - `request.wait` — 设为 `true`
   - `output.path` / `output.markdown_path` / `output.json_path` / `output.numbers_path` — 按需调整输出路径

   **不要修改任何其他字段**，特别是 `las:` 段。

3. 运行：

```powershell
python script/las_pdf_parse.py --config script/config.yaml
```

4. 工具执行流程：

```text
输入校验 → submit PDF → poll 任务 → 跨页表格合并 → 保存 markdown
                                                        → 结构化 JSON 输出
                                                        → 数值提取输出
                                                        → 错误/警告保存
```

### 批量解析

1. 准备 URL 列表文件（每行一个 URL，`#` 开头为注释）。
2. 运行：

```powershell
python script/batch_processor.py urls.txt --output-dir output/batch_results
```

3. 每份 PDF 生成独立子目录，目录下包含完整的 4 种输出文件。
4. 批量汇总保存在 `output/batch_results/batch_summary.json`。

## 输出文件

| 文件 | 内容 |
|------|------|
| `las_response.json` | LAS API 原始 submit/poll 响应 |
| `report.md` | 合并跨页表、清除噪声后的 Markdown |
| `report_structured.json` | `{metadata, elements[{type,content,table_info}], reading_order, table_validation}` |
| `report_numbers.json` | `{numbers[{raw,value,row_label,column_header}], unit_detection, format_issues, summary}` |
| `*_errors.json` | 错误信息（仅在出错时生成） |
| `*_warnings.json` | 警告信息（有警告时生成） |
| `batch_summary.json` | 批量汇总（仅批量模式） |

## 输出要求

- 返回 LAS 是否调用成功。
- 返回 `task_id`、`task_status`、`business_code` 和 `error_msg`。
- 返回输出文件路径，例如 `output/<task-name>/las_response.json`。
- 明确说明 Markdown 结果位于 `poll_response.data.markdown`。
- 如存在，返回 `billable_pages`。
- 对金融财报中的金额、单位、日期、公司名称、表格内容，不得自行编造或补全。
- 后续财务分析必须基于 LAS 返回的 Markdown、page Markdown 或 text blocks 作为证据。
