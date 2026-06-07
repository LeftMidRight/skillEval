"""共用工具函数 —— 文本清理、数值提取、模糊匹配、表格解析、XBRL 加载。"""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# 文本清理
# ---------------------------------------------------------------------------

_WHITESPACE_RE = re.compile(r"\s+")
_FULLWIDTH_MAP = str.maketrans(
    "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ（），。；：？！—",
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz(),.;:?!-",
)


def clean_text(text: str) -> str:
    """统一空白字符、全角转半角。"""
    text = text.translate(_FULLWIDTH_MAP)
    text = _WHITESPACE_RE.sub("", text)
    return text


def normalize_text_for_cer(text: str) -> str:
    """CER 比对用：去空白 + 全角转半角，保留大小写和标点。"""
    return clean_text(text)


# ---------------------------------------------------------------------------
# 数值提取与标准化
# ---------------------------------------------------------------------------

# 匹配金融数值的各种形态
_NUMBER_PATTERNS = [
    # 标准带千分位金额: 1,234,567.89 或 -1,234,567.89
    re.compile(r"-?[\d,]+\.\d{1,6}"),
    # 括号负数: (1,234.56)
    re.compile(r"\([\d,]+\.\d{1,6}\)"),
    # 纯整数金额（含千分位）: 1,234,567
    re.compile(r"(?<![\.\d])-?[\d,]{2,}(?![\.\d])"),
    # 百分比: 12.34%
    re.compile(r"-?[\d,]+\.\d{1,4}%"),
    # 年份: 2023
    re.compile(r"\b20[12]\d\b"),
]


def extract_numbers(text: str) -> list[str]:
    """从文本中提取所有金融数值（保持原格式字符串）。"""
    found: list[str] = []
    seen: set[str] = set()
    for pattern in _NUMBER_PATTERNS:
        for m in pattern.finditer(text):
            raw = m.group()
            if raw not in seen:
                seen.add(raw)
                found.append(raw)
    return found


def normalize_number(raw: str) -> str:
    """标准化一个数值字符串。

    规则：
    - 去掉千分位逗号
    - 括号负数 → 负号前缀
    - 去掉末尾 %
    - 统一去除多余空格
    """
    s = raw.replace(" ", "")
    # 括号负数
    is_negative = False
    if s.startswith("(") and s.endswith(")"):
        s = s[1:-1]
        is_negative = True
    # 去逗号
    s = s.replace(",", "")
    # 去百分号
    s = s.rstrip("%")
    # 检测负号
    if s.startswith("-"):
        is_negative = True
        s = s[1:]

    try:
        val = float(s)
    except ValueError:
        return raw  # 无法解析则返回原值

    if is_negative:
        val = -val
    # 标准化到 2 位小数
    return f"{val:.2f}"


# ---------------------------------------------------------------------------
# 模糊匹配
# ---------------------------------------------------------------------------

def fuzzy_similarity(a: str, b: str) -> float:
    """返回 0-1 的相似度。"""
    return SequenceMatcher(None, a, b).ratio()


def fuzzy_match_row(
    target: str, candidates: list[str], threshold: float = 0.75
) -> tuple[int, float] | None:
    """在候选行中查找与 target 最匹配的行。

    Returns:
        (index, similarity) 或 None（无匹配达到阈值）
    """
    best_idx = -1
    best_sim = 0.0
    for i, cand in enumerate(candidates):
        sim = fuzzy_similarity(target, cand)
        if sim > best_sim:
            best_sim = sim
            best_idx = i
    if best_sim >= threshold:
        return (best_idx, best_sim)
    return None


# ---------------------------------------------------------------------------
# Markdown 表格解析
# ---------------------------------------------------------------------------

_MD_TABLE_ROW_RE = re.compile(r"^\|.+\|$")
_MD_TABLE_SEP_RE = re.compile(r"^\|[\s\-:|]+\|$")


def parse_markdown_table(md: str) -> list[dict[str, str]]:
    """解析单个 markdown 表格为 list[dict]。

    第一行为表头，第二行为分隔线，后续为数据行。
    """
    lines = [l.strip() for l in md.split("\n") if l.strip()]
    rows: list[list[str]] = []
    for line in lines:
        if not _MD_TABLE_ROW_RE.match(line):
            continue
        if _MD_TABLE_SEP_RE.match(line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        rows.append(cells)

    if len(rows) < 2:
        return []

    headers = rows[0]
    result: list[dict[str, str]] = []
    for row in rows[1:]:
        entry: dict[str, str] = {}
        for i, h in enumerate(headers):
            entry[h] = row[i] if i < len(row) else ""
        result.append(entry)
    return result


def extract_table_sections(markdown: str) -> list[tuple[str, list[dict[str, str]]]]:
    """从整个 markdown 中提取所有表格段。

    Returns:
        [(section_title, parsed_table), ...]
        例如 [("# 利润表", [{...}, ...]), ("# 资产负债表", [{...}, ...])]
    """
    tables: list[tuple[str, list[dict[str, str]]]] = []
    lines = markdown.split("\n")

    current_title = ""
    table_lines: list[str] = []
    in_table = False
    prev_blank = True  # 上一行是空行，可能接标题

    for line in lines:
        stripped = line.strip()

        # 检测标题 (## 或 # 开头)
        if stripped.startswith("#") and not stripped.startswith("####"):
            if in_table and table_lines:
                tables.append((current_title, parse_markdown_table("\n".join(table_lines))))
                table_lines = []
                in_table = False
            current_title = stripped
            prev_blank = False
            continue

        # 检测表格行
        if _MD_TABLE_ROW_RE.match(stripped) or _MD_TABLE_SEP_RE.match(stripped):
            table_lines.append(stripped)
            in_table = True
            prev_blank = False
        else:
            if in_table:
                if table_lines:
                    tables.append((current_title, parse_markdown_table("\n".join(table_lines))))
                table_lines = []
                in_table = False
            prev_blank = (stripped == "")

    # 文件末尾可能还有未关闭的表格
    if in_table and table_lines:
        tables.append((current_title, parse_markdown_table("\n".join(table_lines))))

    return tables


# ---------------------------------------------------------------------------
# XBRL 数据加载
# ---------------------------------------------------------------------------


def load_xbrl_dataset(jsonl_path: str | Path) -> list[dict[str, Any]]:
    """加载 FinAR-Bench 的 dev.txt / test.txt。

    每行是一个 JSON，包含 table（XBRL 三张表 markdown）和 instances。
    """
    records: list[dict[str, Any]] = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # 格式：行号\t{json}
            if "\t" in line and line.split("\t", 1)[0].isdigit():
                line = line.split("\t", 1)[1]
            records.append(json.loads(line))
    return records


def get_xbrl_for_company(
    records: list[dict[str, Any]], company_code: str
) -> dict[str, Any] | None:
    """按股票代码查找 XBRL 记录。

    company_code 可以是 "603421" 或 "603421.SH" 或 "603421.pdf"。
    """
    code = company_code.replace(".SH", "").replace(".pdf", "")

    for rec in records:
        # 从 file_path 提取代码
        fp = rec.get("file_path", "")
        if code in fp:
            return rec

        # 从 instances 中提取
        instances = rec.get("instances", [])
        if instances:
            ic = instances[0].get("company_code", "")
            if code == ic.replace(".SH", ""):
                return rec

    return None


# ---------------------------------------------------------------------------
# 单位检测与转换
# ---------------------------------------------------------------------------

_UNIT_PATTERNS = [
    (re.compile(r"单位[：:]\s*万元"), 10_000),
    (re.compile(r"单位[：:]\s*亿元"), 100_000_000),
    (re.compile(r"单位[：:]\s*元[^万\亿]"), 1),
]


def detect_unit_in_text(text: str) -> int:
    """检测文本中的金额单位，返回乘数（使得结果统一为"元"）。"""
    for pattern, multiplier in _UNIT_PATTERNS:
        if pattern.search(text):
            return multiplier
    return 1  # 默认为元


def convert_to_yuan(value_str: str, source_unit_multiplier: int) -> str:
    """将数值从 source_unit 转为元。"""
    try:
        val = float(value_str.replace(",", ""))
        val *= source_unit_multiplier
        return f"{val:.2f}"
    except ValueError:
        return value_str


# ---------------------------------------------------------------------------
# 其他解析器输出加载
# ---------------------------------------------------------------------------


def load_reference_text(parser_dir: str | Path, company_code: str) -> str | None:
    """加载某个解析器的 txt 输出。"""
    path = Path(parser_dir) / f"{company_code}.txt"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# XBRL table 解析（专门处理 FinAR-Bench 的 XBRL markdown 格式）
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# HTML 表格解析
# ---------------------------------------------------------------------------

import html
from html.parser import HTMLParser


class TableCell:
    """表格单元格。"""
    __slots__ = ("content", "colspan", "rowspan", "tag")

    def __init__(self, content: str = "", colspan: int = 1, rowspan: int = 1, tag: str = "td"):
        self.content = content.strip()
        self.colspan = colspan
        self.rowspan = rowspan
        self.tag = tag

    def __repr__(self):
        return f"Cell({self.content[:20]!r}, cs={self.colspan}, rs={self.rowspan})"


class TableTree:
    """表格树结构 —— 用于 TEDS 计算。

    rows: list[list[TableCell]]
    """

    def __init__(self, rows: list[list[TableCell]] | None = None):
        self.rows: list[list[TableCell]] = rows or []

    @property
    def node_count(self) -> int:
        """树中所有单元格总数（展开 colspan/rowspan 后的逻辑单元格数）。"""
        total = 0
        for row in self.rows:
            for cell in row:
                total += cell.colspan * cell.rowspan
        return total

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def get_cell_text(self, row_idx: int, col_idx: int) -> str:
        """按逻辑坐标获取单元格文本。"""
        if row_idx < len(self.rows):
            logical_col = 0
            for cell in self.rows[row_idx]:
                if logical_col <= col_idx < logical_col + cell.colspan:
                    return cell.content
                logical_col += cell.colspan
        return ""

    def get_item_names(self) -> list[str]:
        """获取每行第一列文本（用于行匹配）。"""
        return [row[0].content if row else "" for row in self.rows]

    def get_logical_width(self) -> int:
        """表格的逻辑列数（以 header 行为准）。"""
        if not self.rows:
            return 0
        return sum(c.colspan for c in self.rows[0])


class _TableHTMLParser(HTMLParser):
    """将 HTML <table> 解析为 TableTree。"""

    def __init__(self):
        super().__init__()
        self.trees: list[TableTree] = []
        self._in_table = False
        self._in_row = False
        self._current_rows: list[list[TableCell]] = []
        self._current_row: list[TableCell] = []
        self._current_cell: TableCell | None = None
        self._cell_tag = "td"

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]):
        attr_dict = {k: v for k, v in attrs}
        if tag == "table":
            self._in_table = True
            self._current_rows = []
        elif tag in ("tr",):
            if self._in_table:
                self._in_row = True
                self._current_row = []
        elif tag in ("td", "th"):
            if self._in_row:
                colspan = int(attr_dict.get("colspan", "1"))
                rowspan = int(attr_dict.get("rowspan", "1"))
                self._current_cell = TableCell(colspan=colspan, rowspan=rowspan, tag=tag)
                self._cell_tag = tag

    def handle_endtag(self, tag: str):
        if tag == "table" and self._in_table:
            if self._current_rows:
                self.trees.append(TableTree(self._current_rows))
            self._in_table = False
            self._current_rows = []
        elif tag in ("tr",) and self._in_row:
            if self._current_row:
                self._current_rows.append(self._current_row)
            self._in_row = False
            self._current_row = []
        elif tag in ("td", "th") and self._current_cell is not None:
            self._current_row.append(self._current_cell)
            self._current_cell = None

    def handle_data(self, data: str):
        if self._current_cell is not None:
            self._current_cell.content += data


def parse_html_tables(text: str) -> list[TableTree]:
    """从 HTML 文本中解析所有 <table>。

    去除了页面数据等非表格杂物。
    """
    parser = _TableHTMLParser()
    parser.feed(text)
    parser.close()

    # 过滤掉过小的"表格"（可能是页面残片）
    return [t for t in parser.trees if t.row_count >= 2 and t.get_logical_width() >= 2]


def table_tree_to_dict_list(tree: TableTree) -> list[dict[str, str]]:
    """将 TableTree 转为 list[dict] 格式（兼容旧接口）。

    以第一行作为 header。
    """
    if not tree.rows:
        return []
    headers = [cell.content for cell in tree.rows[0]]
    result: list[dict[str, str]] = []
    for row in tree.rows[1:]:
        entry: dict[str, str] = {}
        col_idx = 0
        for cell in row:
            for h_idx in range(col_idx, col_idx + cell.colspan):
                if h_idx < len(headers):
                    # 每个 colspan 列拿到同一个 header 的映射
                    entry[headers[h_idx]] = cell.content
            col_idx += cell.colspan
        result.append(entry)
    return result


# ---------------------------------------------------------------------------
# 混合表格提取：支持 HTML 和 Markdown 两种格式
# ---------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)")
_PAGE_NUM_RE = re.compile(r"^\s*\d+\s*/\s*\d+\s*$")  # "71 / 205" 页码


def extract_all_tables(text: str) -> list[tuple[str, list[dict[str, str]], TableTree | None]]:
    """从文本中提取所有表格（HTML + markdown），附带所在 section 标题。

    支持跨页表格：同一 section 标题下的多个 <table> 片段会被合并为一个逻辑表格。

    Returns:
        [(section_title, list_of_dicts, table_tree_or_None), ...]
    """
    lines = text.split("\n")

    # 1. 定位所有 heading 和 HTML table 的位置
    heading_positions: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        m = _HEADING_RE.match(line.strip())
        if m:
            heading_positions.append((i, line.strip()))

    # 2. 找到所有 <table>...</table> 的位置
    table_ranges: list[tuple[int, int]] = []  # (start_line, end_line)
    in_table = False
    table_start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if '<table' in stripped and not in_table:
            in_table = True
            table_start = i
        if '</table>' in stripped and in_table:
            table_ranges.append((table_start, i))
            in_table = False

    if not table_ranges:
        # Fallback: markdown 表格
        md_tables = extract_table_sections(text)
        return [(title, table, None) for title, table in md_tables]

    # 3. 将 table_ranges 分配到最近的 heading
    # 初始化 section: [heading_title, [table_indices]]
    sections: list[tuple[str, list[int]]] = []
    if heading_positions:
        # 每个 heading 一个 section
        for pos, h in heading_positions:
            sections.append((h, []))
        # 为第一个 heading 之前的内容创建 section
        first_heading_line = heading_positions[0][0]
        pre_heading_tables = [ti for ti, (s, e) in enumerate(table_ranges) if s < first_heading_line]
        if pre_heading_tables:
            sections.insert(0, ("", pre_heading_tables))
    else:
        sections.append(("", []))

    # 分配每个 table 到 section
    for ti, (t_start, t_end) in enumerate(table_ranges):
        # 检查是否已被预分配
        already_assigned = any(ti in si for _, si in sections)
        if already_assigned:
            continue

        # 找最接近的 heading（往前找）
        assigned = False
        for si in range(len(sections) - 1, -1, -1):
            h_pos = heading_positions[si][0] if si < len(heading_positions) else -1
            if h_pos >= 0 and t_start >= h_pos:
                sections[si][1].append(ti)
                assigned = True
                break
        if not assigned and sections:
            sections[-1][1].append(ti)

    # 4. 对每个 section，合并其下的所有 table
    results: list[tuple[str, list[dict[str, str]], TableTree | None]] = []
    for heading, table_indices in sections:
        if not table_indices:
            continue

        # 按顺序拼接
        merged_tree = _merge_table_ranges(lines, table_ranges, table_indices)
        if merged_tree and merged_tree.row_count >= 2:
            dict_list = table_tree_to_dict_list(merged_tree)
            results.append((heading, dict_list, merged_tree))

    return results


def _merge_table_ranges(
    lines: list[str],
    table_ranges: list[tuple[int, int]],
    indices: list[int],
) -> TableTree | None:
    """合并多个 <table> 片段为一个 TableTree。

    去重表头行、去除页面数据等杂物。
    """
    parser = _TableHTMLParser()

    for idx in sorted(indices):
        start, end = table_ranges[idx]
        fragment = "\n".join(lines[start:end + 1])
        parser.feed(fragment)

    parser.close()

    trees = parser.trees
    if not trees:
        return None

    # 合并多个树的行
    all_rows: list[list[TableCell]] = []
    for tree in trees:
        for row in tree.rows:
            # 如果和 all_rows 中已有行同名且全空，跳过（去重跨页表头）
            if row:
                first_text = row[0].content.strip() if row else ""
                # 检查是否是页码残片
                if _PAGE_NUM_RE.match(first_text):
                    continue
            all_rows.append(row)

    # 去重连续重复的表头
    deduped: list[list[TableCell]] = []
    header_key = ""
    for row in all_rows:
        if not row:
            continue
        row_key = "|".join(c.content.strip() for c in row)
        if row_key == header_key and len(deduped) > 0:
            continue  # 跳过重复表头
        header_key = row_key
        deduped.append(row)

    return TableTree(deduped) if deduped else None


# ---------------------------------------------------------------------------
# XBRL table 解析
# ---------------------------------------------------------------------------


_XBRL_SECTION_RE = re.compile(r"^#\s*(.+)")


def parse_xbrl_tables(xbrl_markdown: str) -> dict[str, list[dict[str, str]]]:
    """解析 XBRL markdown 中的三张表。

    FinAR-Bench 的 XBRL 格式：
    # 利润表
    | 项目 | 2023年12月31日 | 2022年12月31日 |
    ...
    # 资产负债表
    ...
    # 现金流量表
    ...

    Returns:
        {"利润表": [{...}, ...], "资产负债表": [{...}, ...], "现金流量表": [{...}, ...]}
    """
    result: dict[str, list[dict[str, str]]] = {}
    raw_tables = extract_table_sections(xbrl_markdown)

    for title, table in raw_tables:
        # 提取表名
        m = _XBRL_SECTION_RE.match(title)
        if m:
            name = m.group(1).strip()
        else:
            name = title.strip("# ").strip()
        result[name] = table

    return result
