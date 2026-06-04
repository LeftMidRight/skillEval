"""从 markdown 提取结构化 JSON 输出。

输入：合并跨页表格后的 markdown
输出：{metadata, elements[{type, content, ...}], reading_order}
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

TITLE_RE = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
TABLE_RE = re.compile(r"<table>.*?</table>", re.DOTALL)
PAGE_MARKER_IN_TABLE = re.compile(
    r"<tr>\s*<td[^>]*colspan\s*=\s*\"\d+\"[^>]*>\s*\d{1,4}\s*/\s*\d{1,4}\s*</td>\s*</tr>",
    re.DOTALL,
)


@dataclass
class TableInfo:
    html: str
    rows: int
    cols: int
    has_thead: bool
    headers: list[str] = field(default_factory=list)


@dataclass
class Element:
    type: str  # title | paragraph | table | page_noise
    content: str
    page: int | None = None

    # 仅 title
    level: int | None = None

    # 仅 table
    table_info: TableInfo | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": self.type, "content": self.content}
        if self.page is not None:
            d["page"] = self.page
        if self.level is not None:
            d["level"] = self.level
        if self.table_info is not None:
            d["table_info"] = asdict(self.table_info)
        return d


# ---------------------------------------------------------------------------
# 表格解析
# ---------------------------------------------------------------------------

def _parse_table(html: str) -> TableInfo:
    rows = len(re.findall(r"<tr>", html))
    has_thead = "<thead>" in html
    headers: list[str] = []
    thead_match = re.search(r"<thead>(.*?)</thead>", html, re.DOTALL)
    if thead_match:
        th_texts = re.findall(r"<th[^>]*>(.*?)</th>", thead_match.group(1), re.DOTALL)
        headers = [re.sub(r"<[^>]+>", "", t).strip() for t in th_texts]

    # 列数：取 thead 或第一个 tbody 行的 td+colspan
    first_tr = re.search(r"<tr>(.*?)</tr>", html, re.DOTALL)
    cols = 0
    if first_tr:
        for cell in re.finditer(r"<(td|th)([^>]*)>", first_tr.group(1)):
            attrs = cell.group(2)
            cm = re.search(r'colspan\s*=\s*"(\d+)"', attrs)
            cols += int(cm.group(1)) if cm else 1

    return TableInfo(html=html, rows=rows, cols=cols, has_thead=has_thead, headers=headers)


# ---------------------------------------------------------------------------
# Markdown 解析
# ---------------------------------------------------------------------------

# 页面边界关键词（用于推测页码归属）
PAGE_BOUNDARY_MARKER = re.compile(r"\d{1,4}\s*/\s*\d{1,4}")


def _estimate_page(content: str, page_breaks: list[tuple[int, int]]) -> int | None:
    """根据内容位置和页面边界估算所属页码。"""
    # 简单实现：根据 page_breaks 判断内容大概在第几页
    # page_breaks: [(char_position, page_number), ...]
    # 这里我们先不做精确映射，后续可从 LAS detail 得到确切页码
    return None


def parse_markdown_to_elements(markdown: str) -> list[Element]:
    """将 markdown 解析为类型化元素列表。

    识别：
    - title：## / ### / #### 开头的标题行
    - table：<table>...</table> 块
    - paragraph：标题和表格以外的连续文本块
    """
    elements: list[Element] = []
    pos = 0

    while pos < len(markdown):
        # 跳过空白
        remaining = markdown[pos:]

        # 查找标题
        title_match = TITLE_RE.match(remaining)
        if title_match:
            hashes = title_match.group(1)
            text = title_match.group(2).strip()
            elements.append(Element(
                type="title",
                content=text,
                level=len(hashes),
            ))
            pos += title_match.end()
            continue

        # 查找表格
        table_match = TABLE_RE.match(remaining)
        if table_match:
            html = table_match.group(0)
            elements.append(Element(
                type="table",
                content=html,
                table_info=_parse_table(html),
            ))
            pos += table_match.end()
            continue

        # 普通文本：累积到下一个标题、表格或文档结尾
        next_title = re.search(TITLE_RE, remaining)
        next_table = re.search(TABLE_RE, remaining)

        boundaries = []
        if next_title:
            boundaries.append(next_title.start())
        if next_table:
            boundaries.append(next_table.start())

        if boundaries:
            end = min(boundaries)
        else:
            end = len(remaining)

        text = remaining[:end].strip()
        if text:
            elements.append(Element(type="paragraph", content=text))

        pos += max(end, 1)

    return elements


# ---------------------------------------------------------------------------
# 页眉页脚 / 噪声检测
# ---------------------------------------------------------------------------

def _find_page_noise_lines(elements: list[Element]) -> set[str]:
    """在段落元素中检测重复的行（页眉页脚）。"""
    from collections import Counter

    line_counts: Counter[str] = Counter()
    for el in elements:
        if el.type == "paragraph":
            for line in el.content.split("\n"):
                stripped = line.strip()
                if stripped:
                    line_counts[stripped] += 1

    return {line for line, cnt in line_counts.items() if cnt >= 3}


def tag_page_noise(elements: list[Element]) -> list[Element]:
    """将检测到的页眉页脚段落标记为 page_noise。"""
    noise_lines = _find_page_noise_lines(elements)
    result: list[Element] = []
    for el in elements:
        if el.type == "paragraph":
            lines = el.content.split("\n")
            noise_parts = []
            text_parts = []
            for line in lines:
                stripped = line.strip()
                if stripped in noise_lines or (stripped and PAGE_BOUNDARY_MARKER.match(stripped)):
                    noise_parts.append(line)
                elif stripped:
                    text_parts.append(line)
                else:
                    text_parts.append(line)

            if noise_parts:
                result.append(Element(type="page_noise", content="\n".join(noise_parts)))
            if text_parts:
                clean_text = "\n".join(text_parts).strip()
                if clean_text:
                    result.append(Element(type="paragraph", content=clean_text))
        else:
            result.append(el)
    return result


# ---------------------------------------------------------------------------
# 主导出
# ---------------------------------------------------------------------------

def build_structured_output(
    markdown: str,
    metadata: dict[str, Any] | None = None,
) -> str:
    """构建结构化 JSON 输出。

    Args:
        markdown: 合并跨页表格后的 markdown。
        metadata: 额外元数据（公司代码、页数等）。

    Returns:
        JSON 字符串。
    """
    elements = parse_markdown_to_elements(markdown)
    elements = tag_page_noise(elements)

    # 构建阅读顺序
    reading_order = list(range(len(elements)))

    # 统计
    type_counts: dict[str, int] = {}
    for el in elements:
        type_counts[el.type] = type_counts.get(el.type, 0) + 1

    result: dict[str, Any] = {
        "metadata": {
            **(metadata or {}),
            "element_counts": type_counts,
            "total_elements": len(elements),
        },
        "elements": [el.to_dict() for el in elements],
        "reading_order": reading_order,
    }

    return json.dumps(result, ensure_ascii=False, indent=2)
