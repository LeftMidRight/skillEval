"""跨页表格合并与页面噪声清理。

输入 LAS 返回的原始 markdown，输出合并跨页表格、清除页面噪声后的 markdown。
"""

from __future__ import annotations

import re
from collections import Counter
from html.parser import HTMLParser


# ---------------------------------------------------------------------------
# 页面噪声检测
# ---------------------------------------------------------------------------

PAGE_NUMBER_RE = re.compile(r"^\d{1,4}\s*/\s*\d{1,4}$")
# 表内页码行：<tr><td colspan="N">71 / 212</td></tr>
INTRATABLE_PAGE_ROW_RE = re.compile(
    r"<tr>\s*<td[^>]*colspan\s*=\s*\"\d+\"[^>]*>\s*\d{1,4}\s*/\s*\d{1,4}\s*</td>\s*</tr>\s*",
    re.DOTALL,
)
SIGNATURE_KEYWORDS = [
    "公司负责人", "主管会计", "会计机构", "会计师事务所",
    "审计报告", "注册会计师", "审计意见",
]
NEW_TABLE_TITLE_RE = re.compile(
    r"(合并|母公司)?\s*(资产负债|利润|现金流量|所有者权益|股东权益).*表"
)


def _find_repeated_lines(text: str, min_occurrences: int = 3) -> set[str]:
    """找出全文中出现次数 ≥ min_occurrences 的非空行。"""
    lines = [l.strip() for l in text.split("\n")]
    counts = Counter(l for l in lines if l)
    return {line for line, cnt in counts.items() if cnt >= min_occurrences}


def _is_page_noise(line: str, repeated_lines: set[str]) -> bool:
    """判断单行是否为页面噪声（页码/重复页眉/签名栏）。"""
    stripped = line.strip()
    if not stripped:
        return False
    # 页码： "71 / 212" 格式
    if PAGE_NUMBER_RE.match(stripped):
        return True
    # 重复行：全文出现 ≥3 次的页眉
    if stripped in repeated_lines:
        return True
    # 签名栏关键词
    if any(kw in stripped for kw in SIGNATURE_KEYWORDS):
        return True
    return False


# ---------------------------------------------------------------------------
# HTML 表格结构解析
# ---------------------------------------------------------------------------

class _TableInfo:
    """解析后的表格结构信息。"""

    __slots__ = ("thead", "tbody_rows", "col_count", "header_text")

    def __init__(self):
        self.thead: str = ""
        self.tbody_rows: list[str] = []
        self.col_count: int = 0
        self.header_text: str = ""


class _TableParser(HTMLParser):
    """提取 <thead> HTML 和 <tbody> 行列表。"""

    def __init__(self):
        super().__init__()
        self._in_thead = False
        self._in_tbody = False
        self._in_tr = False
        self._current_row: str = ""
        self._depth: int = 0
        self._thead_depth: int = 0
        self._tbody_depth: int = 0
        self._tr_depth: int = 0
        self.result = _TableInfo()

    def handle_starttag(self, tag, attrs):
        if tag == "thead":
            self._in_thead = True
            self._thead_depth = self._depth
        elif tag == "tbody":
            self._in_tbody = True
            self._tbody_depth = self._depth
        elif tag == "tr" and self._in_tbody:
            self._in_tr = True
            self._tr_depth = self._depth
            self._current_row = ""
        self._depth += 1

    def handle_endtag(self, tag):
        self._depth -= 1
        if tag == "thead" and self._depth == self._thead_depth:
            self._in_thead = False
        elif tag == "tbody" and self._depth == self._tbody_depth:
            self._in_tbody = False
        elif tag == "tr" and self._in_tr and self._depth == self._tr_depth:
            self._in_tr = False
            self.result.tbody_rows.append(self._current_row)

    def handle_data(self, data):
        if self._in_thead:
            self.result.thead += data
        if self._in_tr:
            self._current_row += data


def _parse_table_html(html: str) -> _TableInfo:
    """解析 <table> HTML，提取结构信息。"""
    parser = _TableParser()
    parser.feed(html)
    info = parser.result

    # 计算列数：考虑 colspan
    first_tr_match = re.search(r"<tr>(.*?)</tr>", html, re.DOTALL)
    if first_tr_match:
        first_tr = first_tr_match.group(1)
        total_cols = 0
        for cell in re.finditer(r"<(td|th)([^>]*)>", first_tr):
            attrs = cell.group(2)
            colspan_match = re.search(r'colspan\s*=\s*"(\d+)"', attrs)
            span = int(colspan_match.group(1)) if colspan_match else 1
            total_cols += span
        info.col_count = total_cols
    info.header_text = info.thead.strip()
    return info


# ---------------------------------------------------------------------------
# 表格合并
# ---------------------------------------------------------------------------

def _should_merge(
    between_text: str,
    table_a_html: str,
    table_b_html: str,
    repeated_lines: set[str],
) -> bool:
    """判断 table_b 是否属于 table_a 的跨页延续。"""

    # 条件 1：中间不包含新的表格标题
    if NEW_TABLE_TITLE_RE.search(between_text):
        return False

    # 条件 2：table_b 无 <thead>（LAS 跨页延续不带表头）
    if "<thead>" in table_b_html:
        return False

    return True


def _merge_two_tables(table_a_html: str, table_b_html: str) -> str:
    """将 table_b 的 tbody 行合并到 table_a 中。"""
    info_b = _parse_table_html(table_b_html)

    # 提取 table_b 的 tbody 行 HTML
    new_rows_html = []
    tbody_match = re.search(r"<tbody>(.*?)</tbody>", table_b_html, re.DOTALL)
    if tbody_match:
        tbody_content = tbody_match.group(1)
        # 提取每行 <tr>...</tr>
        for tr_match in re.finditer(r"<tr>(.*?)</tr>", tbody_content, re.DOTALL):
            new_rows_html.append(f"<tr>{tr_match.group(1)}</tr>")

    if not new_rows_html:
        return table_a_html

    # 插入到 table_a 的 </tbody> 之前
    insert_pos = table_a_html.rfind("</tbody>")
    if insert_pos == -1:
        # table_a 没有 tbody？直接追加到 </table> 之前
        insert_pos = table_a_html.rfind("</table>")
        if insert_pos == -1:
            return table_a_html

    merged = table_a_html[:insert_pos] + "\n".join(new_rows_html) + "\n" + table_a_html[insert_pos:]
    return merged


def _clean_text_segment(text: str, repeated_lines: set[str]) -> str:
    """清理文本段落中的页面噪声行。"""
    lines = text.split("\n")
    kept = [l for l in lines if not _is_page_noise(l, repeated_lines)]
    # 去除首尾空行
    while kept and not kept[0].strip():
        kept.pop(0)
    while kept and not kept[-1].strip():
        kept.pop()
    return "\n".join(kept)


def _clean_table_html(html: str) -> str:
    """清理表格 HTML 内部的页面噪声（表内页码行）。"""
    return INTRATABLE_PAGE_ROW_RE.sub("", html)


# ---------------------------------------------------------------------------
# 主导出函数
# ---------------------------------------------------------------------------

TABLE_START_RE = re.compile(r"<table>")
TABLE_END_RE = re.compile(r"</table>")


def merge_cross_page_tables(markdown: str) -> str:
    """跨页表格合并 + 页面噪声清理的主入口。

    Args:
        markdown: LAS 返回的原始 markdown 文本。

    Returns:
        合并跨页表格并清除页面噪声后的 markdown 文本。
    """
    # 1. 预扫描：找出全文重复行
    repeated_lines = _find_repeated_lines(markdown)

    # 2. 切分文档为段落序列
    segments: list[tuple[str, str]] = []  # [(type, content), ...]
    pos = 0

    for start_m in TABLE_START_RE.finditer(markdown):
        start = start_m.start()
        # 找到对应的 </table>
        end_match = TABLE_END_RE.search(markdown, start_m.end())
        if not end_match:
            continue
        end = end_match.end()

        # 前面的文本段落
        if pos < start:
            text = markdown[pos:start]
            if text.strip():
                segments.append(("text", text))

        # 表格段落
        segments.append(("table", markdown[start:end]))
        pos = end

    # 尾部文本
    if pos < len(markdown):
        text = markdown[pos:]
        if text.strip():
            segments.append(("text", text))

    # 3. 遍历合并
    merged_segments: list[tuple[str, str]] = []
    i = 0

    while i < len(segments):
        typ, content = segments[i]

        if typ != "table":
            merged_segments.append((typ, content))
            i += 1
            continue

        # 当前是表格，尝试合并后续的同一逻辑表
        current_table_html = content
        i += 1

        while i < len(segments):
            next_typ, next_content = segments[i]

            if next_typ == "text":
                # 文本段后是表格 → 判断是否跨页延续
                if i + 1 < len(segments) and segments[i + 1][0] == "table":
                    between_text = next_content
                    next_table = segments[i + 1][1]

                    if _should_merge(between_text, current_table_html, next_table, repeated_lines):
                        # 合并
                        current_table_html = _merge_two_tables(current_table_html, next_table)
                        i += 2  # 跳过 text + table
                        continue
                    else:
                        # 不合并，清理文本噪声
                        cleaned = _clean_text_segment(between_text, repeated_lines)
                        if cleaned:
                            merged_segments.append(("text", cleaned))
                        i += 1
                        break
                else:
                    # 文本段后无表格，清理文本
                    cleaned = _clean_text_segment(next_content, repeated_lines)
                    if cleaned:
                        merged_segments.append(("text", cleaned))
                    i += 1
                    break
            else:
                # 连续两个 table（无中间文本）→ 直接判断
                if _should_merge("", current_table_html, next_content, repeated_lines):
                    current_table_html = _merge_two_tables(current_table_html, next_content)
                    i += 1
                    continue
                else:
                    break

        merged_segments.append(("table", current_table_html))

    # 4. 重建 markdown
    result_parts: list[str] = []
    for typ, content in merged_segments:
        if typ == "text":
            # 清理文本段落中的噪声
            cleaned = _clean_text_segment(content, repeated_lines)
            if cleaned:
                result_parts.append(cleaned)
        else:
            # 清理表格内部的页面噪声（表内页码行等）
            cleaned_table = _clean_table_html(content)
            if cleaned_table.strip():
                result_parts.append(cleaned_table)

    return "\n\n".join(result_parts)
