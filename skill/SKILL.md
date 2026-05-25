---
name: financial-report-analyzer-skill
description: 使用 LAS 解析金融行业财报 PDF，生成 Markdown 和结构化解析结果，供后续财务分析或评测使用。
---

# 金融财报 PDF LAS 解析

## 描述

使用火山引擎 LAS PDF 解析能力，将金融行业财报 PDF 转换为 Markdown 和页级结构化解析结果。

## 触发条件

- 当用户需要解析上市公司年报、财报、半年报、季报、招股书、审计报告、财务公告等金融 PDF 时。
- 当用户请求包含“财报解析”“PDF 转 Markdown”“LAS 解析”“解析年报”“解析财务报告”等意图时。
- 当用户需要先获取 PDF 的正文、表格、页级 Markdown 或文本块，为后续财务字段抽取和评测做准备时。

## 工具依赖

- `script/config.yaml`：LAS 请求配置文件，用于填写 PDF URL、任务 ID、输出路径等参数。
- `script/las_client.py`：LAS API 客户端，负责调用 `/submit` 和 `/poll`。
- `script/las_pdf_parse.py`：工具入口脚本，负责读取配置、调用 LAS 客户端并保存响应。
- Python 运行环境。

## 工作流

1. 确认用户提供的是可访问的 PDF URL，例如公开 URL、预签名 URL、TOS URL 或 ArkClaw 上传文件后生成的 URL。
2. 如果用户只提供本地 PDF 路径，先提醒用户需要上传为可访问 URL，不要直接把本地路径传给 LAS。
3. 修改 `script/config.yaml`：

```yaml
request:
  url: "<pdf-url>"
  task_id: ""
  wait: true

output:
  path: "output/<task-name>/las_response.json"
```

4. 调用工具脚本：

```powershell
python script/las_pdf_parse.py --config script/config.yaml
```

5. 工具会执行：

```text
submit PDF URL -> 获取 task_id -> poll 任务状态 -> 保存 LAS 原始响应
```

6. 解析完成后，从输出 JSON 中读取：

```text
poll_response.data.markdown
```

作为整份财报 PDF 的 Markdown 解析结果。

7. 如需页级信息，读取：

```text
poll_response.data.detail[].page_md
poll_response.data.detail[].text_blocks
```

用于定位页码、检查表格、验证阅读顺序和后续评测。

## 输出要求

- 返回 LAS 是否调用成功。
- 返回 `task_id`、`task_status`、`business_code` 和 `error_msg`。
- 返回输出文件路径，例如 `output/<task-name>/las_response.json`。
- 明确说明 Markdown 结果位于 `poll_response.data.markdown`。
- 如存在，返回 `billable_pages`。
- 对金融财报中的金额、单位、日期、公司名称、表格内容，不得自行编造或补全。
- 后续财务分析必须基于 LAS 返回的 Markdown、page Markdown 或 text blocks 作为证据。
