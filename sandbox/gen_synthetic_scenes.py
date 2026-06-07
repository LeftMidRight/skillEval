"""合成 eval_dataset 场景 PDF：无边框表格 + 多栏排版。

使用 FinAR-Bench 中不在现有评测集的公司的 XBRL 真值数据，
反推生成：

1. 无边框表格 PDF  — 纯空格对齐，无竖线/横线
2. 多栏排版 PDF    — 2 栏版式（报纸风格）

每份 PDF 配 XBRL Ground Truth，均可参与 Module 1/2/3 评测。

用法：
    python sandbox/gen_synthetic_scenes.py
"""

from __future__ import annotations

import json
import re
import sys
import argparse
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fpdf import FPDF

from module1.utils import load_xbrl_dataset

# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

EVAL_ROOT = PROJECT_ROOT / "data" / "eval_dataset"
FINAR_DIR = PROJECT_ROOT / "data" / "FinAR-Bench"
SELECTED = ["603421", "603707", "600569"]

# 场景目录
BORDERLESS_DIR = EVAL_ROOT / "borderless_tables"
MULTICOLUMN_DIR = EVAL_ROOT / "synthetic_multicolumn"


# ---------------------------------------------------------------------------
# XBRL 数据解析
# ---------------------------------------------------------------------------

def load_xbrl_for_company(code: str) -> dict:
    """从 dev.txt / test.txt 中加载某家公司的 XBRL 数据。"""
    for split in ["dev.txt", "test.txt"]:
        path = FINAR_DIR / split
        if path.exists():
            records = load_xbrl_dataset(path)
            for r in records:
                fp = r.get("file_path", "")
                if code in fp:
                    return r
    raise ValueError(f"XBRL not found for {code}")


_XBRL_SECTION_RE = re.compile(r"^#\s*(.+)")
_TABLE_ROW_RE = re.compile(r"^\|.+\|$")
_TABLE_SEP_RE = re.compile(r"^\|[\s\-:|]+\|$")


def parse_xbrl_sections(xbrl_md: str) -> list[tuple[str, list[list[str]]]]:
    """解析 XBRL markdown 为 [(表名, [[cell,...], ...]), ...]。

    返回的 cell 列表以第一行为表头。
    """
    lines = xbrl_md.split("\n")
    sections: list[tuple[str, list[list[str]]]] = []
    current_title = ""
    current_rows: list[list[str]] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            # 保存上一个 section
            if current_title and current_rows:
                sections.append((current_title, current_rows))
            current_title = stripped.lstrip("#").strip()
            current_rows = []
        elif _TABLE_ROW_RE.match(stripped) and not _TABLE_SEP_RE.match(stripped):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            current_rows.append(cells)

    if current_title and current_rows:
        sections.append((current_title, current_rows))

    return sections


# ---------------------------------------------------------------------------
# PDF 生成器
# ---------------------------------------------------------------------------

class BorderlessPDF(FPDF):
    """生成无边框表格 PDF。"""

    def __init__(self, company_name: str, company_code: str):
        super().__init__("P", "mm", "A4")
        self.set_auto_page_break(True, 20)
        self.company_name = company_name
        self.company_code = company_code

        # 注册中文字体 — Windows 系统字体
        import platform
        if platform.system() == "Windows":
            font_candidates = [
                "C:/Windows/Fonts/simhei.ttf",
                "C:/Windows/Fonts/simsun.ttc",
                "C:/Windows/Fonts/msyh.ttc",
            ]
        else:
            font_candidates = [
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            ]
        font_path = None
        for fp in font_candidates:
            if Path(fp).exists():
                font_path = fp
                break
        if font_path is None:
            raise RuntimeError("No Chinese font found")
        self.add_font("CN", "", font_path)

    def header_info(self):
        self.set_font("CN", "", 14)
        self.cell(0, 10, f"{self.company_name} ({self.company_code}.SH)", align="C", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 8, "2023 年度财务报表", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(5)

    def section_title(self, title: str):
        self.set_font("CN", "", 12)
        self.cell(0, 8, title, align="L", new_x="LMARGIN", new_y="NEXT")
        self.ln(3)

    def borderless_table(self, rows: list[list[str]], col_widths: list[int]):
        """渲染无边框表格：纯空格对齐，无任何线条。

        用固定列宽 + 左对齐实现。
        """
        self.set_font("CN", "", 9)

        header = rows[0]
        data = rows[1:] if len(rows) > 1 else []

        # --- 表头 ---
        header_line = ""
        for i, h in enumerate(header):
            header_line += h.ljust(col_widths[i])[: col_widths[i]]
        self.cell(0, 6, header_line, new_x="LMARGIN", new_y="NEXT")

        # --- 分隔空格行 ---
        sep_line = ""
        for i in range(len(header)):
            sep_line += "-" * min(col_widths[i] - 1, 20) + " "
        self.set_font("CN", "", 8)
        self.cell(0, 5, sep_line[: sum(col_widths)], new_x="LMARGIN", new_y="NEXT")

        # --- 数据行 ---
        self.set_font("CN", "", 9)
        for row in data[:25]:  # 限制前 25 行
            line = ""
            for i, cell in enumerate(row):
                line += cell.ljust(col_widths[i])[: col_widths[i]]
            self.cell(0, 5.5, line, new_x="LMARGIN", new_y="NEXT")

    def body_text(self, text: str):
        self.set_font("CN", "", 10)
        self.multi_cell(0, 6, text, align="L")
        self.ln(2)


class MultiColumnPDF(FPDF):
    """生成经典多栏排版 PDF（报纸/年报风格）。

    核心特征：
      - 连续长文本在左栏溢出后自然流入右栏（而非左右独立内容）
      - 栏间可见竖线分隔符
      - 表格嵌入文本流（居中通栏或单栏窄表）
      - 跨页时文本从上一页右栏底部续到下一页左栏顶部
    """

    def __init__(self, company_name: str, company_code: str):
        super().__init__("P", "mm", "A4")
        self.set_auto_page_break(False)  # 手动控制分页
        self.company_name = company_name
        self.company_code = company_code

        import platform
        if platform.system() == "Windows":
            font_candidates = [
                "C:/Windows/Fonts/simhei.ttf",
                "C:/Windows/Fonts/simsun.ttc",
                "C:/Windows/Fonts/msyh.ttc",
            ]
        else:
            font_candidates = [
                "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
                "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            ]
        font_path = None
        for fp in font_candidates:
            if Path(fp).exists():
                font_path = fp
                break
        if font_path is None:
            raise RuntimeError("No Chinese font found")
        self.add_font("CN", "", font_path)

        # 版面参数（经典两栏报纸版式）
        self.lm = 15           # 左边距
        self.rm = 15            # 右边距
        self.col_w = 85         # 单栏宽度
        self.gutter = 8         # 栏间距
        self.page_w = 210       # A4 宽
        self.page_h = 297       # A4 高
        self.top_margin = 15
        self.bottom_margin = 20
        self.usable_h = self.page_h - self.top_margin - self.bottom_margin  # 262mm

        # 两栏 X 坐标
        self.left_x = self.lm
        self.right_x = self.lm + self.col_w + self.gutter
        # 分隔线 X
        self.divider_x = self.lm + self.col_w + self.gutter / 2

        # 流排状态
        self._cur_col = "left"      # 当前栏: "left" | "right"
        self._cur_y = self.top_margin
        self._page_num = 0
        self._page_dividers: dict[int, bool] = {}

    # ================================================================
    # 内部：分页与换栏
    # ================================================================

    def _draw_divider(self):
        """当前页画分隔线（从 _col_top_y 到 usable_bottom）。"""
        if not self.page_draws_divider(self._page_num):
            return
        top = self.top_margin + 2
        bottom = self.page_h - self.bottom_margin
        self.set_draw_color(160, 160, 160)
        self.set_line_width(0.25)
        self.line(self.divider_x, top, self.divider_x, bottom)
        self.set_line_width(0.2)

    def _draw_page_number(self):
        """页眉/页脚。"""
        self.set_font("CN", "", 7)
        self.set_text_color(120, 120, 120)
        self.set_xy(self.lm, self.page_h - 12)
        self.cell(self.page_w - self.lm - self.rm, 5,
                  f"— {self.company_name} ({self.company_code}.SH)  2023 年度报告  第 {self._page_num} 页 —",
                  align="C")
        self.set_text_color(0, 0, 0)

    def _new_page(self):
        """新建一页并重置光标到左栏顶部。"""
        # 完成当前页
        if self._page_num > 0:
            self._draw_divider()
            self._draw_page_number()
        self.add_page()
        self._page_num += 1
        self._page_dividers[self._page_num] = True
        self._cur_col = "left"
        self._cur_y = self.top_margin

    def disable_current_divider(self):
        """关闭当前页的双栏分隔线，用于通栏表格页。"""
        if self._page_num > 0:
            self._page_dividers[self._page_num] = False

    def page_draws_divider(self, page_num: int) -> bool:
        """返回某页是否绘制双栏分隔线。"""
        return self._page_dividers.get(page_num, True)

    def _switch_to_right_col(self):
        """切换到右栏。"""
        self._cur_col = "right"
        self._cur_y = self.top_margin

    def _advance_y(self, h: float):
        """前进 Y，如果超出当前栏则自动换栏/翻页。返回 True 表示成功放置。"""
        self._cur_y += h
        col_bottom = self.page_h - self.bottom_margin
        if self._cur_y > col_bottom:
            if self._cur_col == "left":
                self._switch_to_right_col()
                self._cur_y = self.top_margin + h
                return True
            else:
                self._new_page()
                return self._advance_y(0)  # 递归重置
        return True

    # ================================================================
    # 通栏元素
    # ================================================================

    def full_title(self, title: str):
        """通栏大标题（跨两栏居中）。"""
        if self._page_num == 0 or self._cur_col != "left" or self._cur_y > self.top_margin + 10:
            self._new_page()
        self.set_xy(self.lm, self._cur_y)
        self.set_font("CN", "", 18)
        self.cell(self.page_w - self.lm - self.rm, 12, title, align="C", new_x="LMARGIN", new_y="NEXT")
        self._cur_y = self.get_y() + 3
        # 画标题下划线
        self.set_draw_color(80, 80, 80)
        self.set_line_width(0.6)
        self.line(self.lm, self._cur_y, self.page_w - self.rm, self._cur_y)
        self.set_line_width(0.2)
        self._cur_y += 4

    def full_subtitle(self, text: str):
        """通栏副标题/日期行。"""
        self.set_xy(self.lm, self._cur_y)
        self.set_font("CN", "", 8)
        self.set_text_color(100, 100, 100)
        self.cell(self.page_w - self.lm - self.rm, 5, text, align="C")
        self.set_text_color(0, 0, 0)
        self._cur_y += 7
        # 副标题下细线
        self.set_draw_color(180, 180, 180)
        self.set_line_width(0.15)
        self.line(self.lm, self._cur_y, self.page_w - self.rm, self._cur_y)
        self._cur_y += 4

    def start_topic_document(self, title: str, subtitle: str):
        """开启真实年报专题页。"""
        self._new_page()
        self.full_title(title)
        self.full_subtitle(subtitle)

    def current_page_number(self) -> int:
        """返回当前 PDF 页码（1-based）。"""
        return self._page_num

    def topic_section(
        self,
        title: str,
        left_paragraphs: list[str],
        right_paragraphs: list[str],
        note_title: str | None = None,
        note_lines: list[str] | None = None,
        new_page: bool = False,
    ):
        """渲染一页真实年报双栏专题内容。

        每个专题页采用通栏小节标题 + 左右两栏正文；右栏不依赖左栏溢出，
        从而避免右栏空白，更接近年报专题页排版。
        """
        if new_page:
            self._new_page()

        self.set_xy(self.lm, self._cur_y)
        self.set_font("CN", "", 12)
        self.cell(self.page_w - self.lm - self.rm, 8, title, new_x="LMARGIN", new_y="NEXT")
        self._cur_y = self.get_y() + 1
        self.set_draw_color(150, 150, 150)
        self.set_line_width(0.18)
        self.line(self.lm, self._cur_y, self.page_w - self.rm, self._cur_y)
        self._cur_y += 5

        top_y = self._cur_y
        self._cur_col = "left"
        self._cur_y = top_y
        self._write_column_paragraphs(left_paragraphs)
        left_end = self._cur_y

        self._cur_col = "right"
        self._cur_y = top_y
        self._write_column_paragraphs(right_paragraphs)
        if note_title and note_lines:
            self.note_box(note_title, note_lines)
        right_end = self._cur_y

        self._cur_col = "left"
        self._cur_y = max(left_end, right_end) + 4

    def _write_column_paragraphs(self, paragraphs: list[str]):
        """在当前栏连续写入段落。"""
        for paragraph in paragraphs:
            self.flow_paragraph(paragraph, size=9.2, first_indent=5)

    def note_box(self, title: str, lines: list[str]):
        """在当前栏写入真实年报常见的重点摘要框。"""
        col_x = self.left_x if self._cur_col == "left" else self.right_x
        box_h = 10 + len(lines) * 5
        col_bottom = self.page_h - self.bottom_margin

        if self._cur_y + box_h > col_bottom:
            if self._cur_col == "left":
                self._switch_to_right_col()
                col_x = self.right_x
            else:
                self._draw_divider()
                self._draw_page_number()
                self._new_page()
                col_x = self.left_x

        self.set_xy(col_x, self._cur_y)
        self.set_draw_color(155, 155, 155)
        self.set_fill_color(246, 246, 246)
        self.rect(col_x, self._cur_y, self.col_w, box_h, style="DF")

        self.set_xy(col_x + 3, self._cur_y + 2)
        self.set_font("CN", "", 8.5)
        self.cell(self.col_w - 6, 4, title)

        self._cur_y += 8
        self.set_font("CN", "", 7.5)
        for line in lines:
            self.set_xy(col_x + 3, self._cur_y)
            self.cell(self.col_w - 6, 4, line[:40])
            self._cur_y += 5
        self._cur_y += 4

    def full_section_break(self, title: str):
        """通栏小结标题 + 分隔线。触发换页右栏→新页。"""
        if self._cur_col == "right":
            # 先完成当前页
            self._draw_divider()
            self._draw_page_number()
        self._new_page()
        self.disable_current_divider()
        # 通栏标题
        self.set_xy(self.lm, self._cur_y)
        self.set_font("CN", "", 13)
        self.cell(self.page_w - self.lm - self.rm, 9, title, align="C", new_x="LMARGIN", new_y="NEXT")
        self._cur_y = self.get_y() + 2
        # 标题下划线
        self.set_draw_color(80, 80, 80)
        self.set_line_width(0.4)
        self.line(self.lm, self._cur_y, self.page_w - self.rm, self._cur_y)
        self.set_line_width(0.2)
        self._cur_y += 5

    # ================================================================
    # 流排正文（核心：文本自动流排，左栏→右栏→翻页）
    # ================================================================

    def flow_text(self, text: str, size: int = 8.5, indent: float = 0):
        """将文本流排到当前栏（左/右），自然溢出换栏/翻页。

        这是核心排版方法：文本不指定栏，而是顺延当前流排位置，
        左栏满了就换右栏，右栏满了就翻页续左栏。
        """
        self.set_font("CN", "", size)
        line_h = size * 0.5  # 行高 ≈ 字号的 0.5 倍（mm）
        col_bottom = self.page_h - self.bottom_margin
        col_x = self.left_x if self._cur_col == "left" else self.right_x

        # 段首缩进
        para_indent = indent if indent > 0 else 0

        # 逐字流排
        remaining = text
        first_line = True

        while remaining:
            avail_w = self.col_w - (para_indent if first_line else 0)
            col_x_cur = col_x + (para_indent if first_line else 0)

            # 尝试在当前栏放入尽可能多的文字
            # fpdf2 multi_cell 不方便单行控制，手动逐字测量
            fit = 0
            cur_w = 0.0
            for i, ch in enumerate(remaining):
                cw = self.get_string_width(ch)
                if cur_w + cw > avail_w:
                    # 回退到最后一个空格（中文通常不需要）
                    break
                cur_w += cw
                fit = i + 1

            if fit == 0:
                # 第一个字符就放不下——换栏/翻页
                if self._cur_col == "left":
                    self._switch_to_right_col()
                    col_x = self.right_x
                    col_bottom = self.page_h - self.bottom_margin
                    continue
                else:
                    self._draw_divider()
                    self._draw_page_number()
                    self._new_page()
                    col_x = self.left_x
                    col_bottom = self.page_h - self.bottom_margin
                    continue

            line_text = remaining[:fit]
            remaining = remaining[fit:]

            # 检查当前栏是否还有空间
            if self._cur_y + line_h > col_bottom:
                # 当前栏满了
                if self._cur_col == "left":
                    self._switch_to_right_col()
                    col_x = self.right_x
                    col_bottom = self.page_h - self.bottom_margin
                    # 重排这行到右栏
                    remaining = line_text + remaining
                    first_line = True
                    continue
                else:
                    # 翻页
                    self._draw_divider()
                    self._draw_page_number()
                    self._new_page()
                    col_x = self.left_x
                    col_bottom = self.page_h - self.bottom_margin
                    remaining = line_text + remaining
                    first_line = True
                    continue

            # 画这行
            self.set_xy(col_x_cur, self._cur_y)
            self.cell(self.col_w, line_h, line_text, align="L")
            self._cur_y += line_h
            first_line = False

    def flow_paragraph(self, text: str, size: int = 8.5, first_indent: float = 6):
        """流排一个段落：首行缩进 + 自动换行/换栏。"""
        self.flow_text(text, size=size, indent=first_indent)
        # 段后空行
        self._cur_y += 3

    def flow_heading(self, title: str, size: int = 10.5, level: int = 1):
        """在文本流中插入小标题（通栏 or 单栏）。"""
        # 如果右栏空间不够，先翻页
        if self._cur_col == "right" and self._cur_y > self.page_h - self.bottom_margin - 30:
            self._draw_divider()
            self._draw_page_number()
            self._new_page()
        # 如果左栏已占半页以上，标题尽量在左栏新位置
        self._cur_y += 2
        col_x = self.left_x if self._cur_col == "left" else self.right_x
        self.set_xy(col_x, self._cur_y)
        self.set_font("CN", "", size)
        self.cell(self.col_w, size * 0.55, title, align="L")
        self._cur_y = self.get_y() + size * 0.55 + 1

        # 小标题下划线
        if level == 1:
            self.set_draw_color(120, 120, 120)
            self.set_line_width(0.2)
            self.line(col_x, self._cur_y, col_x + self.col_w, self._cur_y)
            self._cur_y += 2

    # ================================================================
    # 通栏表格（财务报表）
    # ================================================================

    def full_span_table(self, title: str, rows: list[list[str]], max_rows: int = 25):
        """通栏表格（跨两栏），用于完整的财务报表。"""
        # 确保在新页起始
        if self._cur_col == "right":
            self._draw_divider()
            self._draw_page_number()
            self._new_page()

        # 标题
        self.set_xy(self.lm, self._cur_y)
        self.set_font("CN", "", 11)
        self.cell(self.page_w - self.lm - self.rm, 8, title, align="C", new_x="LMARGIN", new_y="NEXT")
        self._cur_y = self.get_y() + 2

        ncols = len(rows[0]) if rows else 2
        total_w = self.page_w - self.lm - self.rm  # 180mm
        # 第一列宽一些（项目名）
        cw_first = min(50, int(total_w * 0.3))
        cw_rest = (total_w - cw_first) / max(ncols - 1, 1)
        col_widths = [cw_first] + [cw_rest] * (ncols - 1)
        line_h = 5.0

        col_bottom = self.page_h - self.bottom_margin
        row_count = 0

        for ri, row in enumerate(rows):
            if row_count >= max_rows:
                break

            # 翻页检测
            if self._cur_y + line_h > col_bottom:
                # 表格续页 —— 先画完当前页表格部分，翻页后续
                self._draw_divider()
                self._draw_page_number()
                self._new_page()
                self.disable_current_divider()
                # 重画表头
                self.set_xy(self.lm, self._cur_y)
                self.set_font("CN", "", 7)
                self.set_fill_color(235, 235, 235)
                for ci, h in enumerate(rows[0]):
                    w = col_widths[ci] if ci < len(col_widths) else cw_rest
                    self.cell(w, line_h + 1, h, border=1, fill=True, align="C")
                self.ln()
                self._cur_y = self.get_y()

            self.set_xy(self.lm, self._cur_y)
            self.set_font("CN", "", 7)
            if ri == 0:
                # 表头
                self.set_fill_color(235, 235, 235)
                for ci, h in enumerate(row):
                    w = col_widths[ci] if ci < len(col_widths) else cw_rest
                    self.cell(w, line_h + 1, h, border=1, fill=True, align="C")
                self.ln()
            else:
                for ci, cell in enumerate(row):
                    w = col_widths[ci] if ci < len(col_widths) else cw_rest
                    align = "L" if ci == 0 else "R"
                    self.cell(w, line_h, str(cell), border=1, align=align)
                self.ln()

            self._cur_y = self.get_y()
            row_count += 1

        self._cur_y += 4
        # 表格后恢复左栏流排
        self._cur_col = "left"

    # ================================================================
    # 单栏小表格（摘要/亮点）
    # ================================================================

    def column_table(self, rows: list[list[str]], max_rows: int = 10):
        """在当前栏内嵌入一个小表格。"""
        col_x = self.left_x if self._cur_col == "left" else self.right_x
        ncols = len(rows[0]) if rows else 2
        cw = self.col_w / ncols
        line_h = 4.5
        col_bottom = self.page_h - self.bottom_margin

        # 检查空间
        needed_h = min(len(rows), max_rows + 1) * line_h + line_h
        if self._cur_y + needed_h > col_bottom:
            if self._cur_col == "left":
                self._switch_to_right_col()
                col_x = self.right_x
            else:
                self._draw_divider()
                self._draw_page_number()
                self._new_page()
                col_x = self.left_x

        for ri, row in enumerate(rows[:max_rows + 1]):
            self.set_xy(col_x, self._cur_y)
            self.set_font("CN", "", 7)
            if ri == 0:
                self.set_fill_color(235, 235, 235)
                for ci, cell in enumerate(row):
                    self.cell(cw, line_h, str(cell), border=1, fill=True, align="C")
            else:
                for ci, cell in enumerate(row):
                    align = "L" if ci == 0 else "R"
                    self.cell(cw, line_h, str(cell), border=1, align=align)
            self.ln()
            self._cur_y = self.get_y()

        self._cur_y += 3

    def finalize(self):
        """完成最后一页的绘制。"""
        if self._page_num > 0:
            self._draw_divider()
            self._draw_page_number()


# ---------------------------------------------------------------------------
# 生成逻辑
# ---------------------------------------------------------------------------

COMPANY_NAMES = {
    "603421": "鼎信通讯",
    "603707": "健友股份",
    "600569": "安阳钢铁",
}

COMPANY_SNIPPETS = {
    "603421": "公司主要从事电力线载波通信产品的研发、生产和销售，是国内领先的电力物联网通信方案提供商。公司产品覆盖用电信息采集、配电自动化、智能电能表、能源管理系统等多个领域，服务于国家电网、南方电网及海外电力市场。",
    "603707": "公司主要从事肝素原料药、低分子肝素制剂等产品的研发、生产和销售，产品覆盖全球多个国家和地区。作为全球肝素产业链的重要参与者，公司拥有从粗品肝素到终端制剂的全产业链布局。",
    "600569": "公司是集炼焦、烧结、炼铁、炼钢、轧钢于一体的钢铁联合企业，是河南省最大的钢铁生产企业。主要产品包括宽厚板、热轧卷板、冷轧薄板、高速线材等，广泛应用于建筑、机械制造、汽车、船舶等下游行业。",
}

# 多栏排版用的详细行业描述
COMPANY_LONG_DESC = {
    "603421": (
        f"鼎信通讯（603421.SH）是国内领先的电力物联网通信方案提供商，"
        f"2023年度实现营业收入约36.3亿元。"
        f"公司核心产品包括HPLC高速电力线载波模块、双模通信单元、"
        f"智能电能表采集终端及能源管理系统，市场占有率连续三年位居行业前三。"
        f"报告期内，公司完成新一代双模（HPLC+RF）通信芯片的量产，"
        f"该芯片支持国网2023版技术标准，已通过中国电科院型式试验认证。"
        f"海外业务方面，公司在东南亚、非洲和拉美市场持续推进电力AMI系统建设。"
    ),
    "603707": (
        f"健友股份（603707.SH）是全球肝素产业链的龙头企业，"
        f"2023年度实现营业收入约39.3亿元。"
        f"公司拥有从粗品肝素钠、低分子肝素原料药到依诺肝素钠制剂、"
        f"那屈肝素钙制剂等终端产品的全产业链能力。"
        f"报告期内，公司3条注射剂生产线通过美国FDA现场检查，"
        f"依诺肝素钠注射液在美国市场份额持续提升，跃居全美前三。"
        f"公司持续加码研发投入，GLP-1类多肽原料药项目进入中试阶段。"
    ),
    "600569": (
        f"安阳钢铁（600569.SH）是河南省最大的钢铁联合企业，"
        f"2023年度实现营业收入约421.5亿元。"
        f"公司拥有从焦化、烧结、炼铁、炼钢到连铸、轧钢的完整长流程生产线，"
        f"具备年产1000万吨钢的综合生产能力。"
        f"报告期内，公司积极响应国家'碳达峰、碳中和'战略，"
        f"完成2号高炉超低排放改造并通过环保绩效A级企业认定。"
        f"公司持续推进产品结构升级，汽车用钢、桥梁钢等高端品种占比升至38%。"
    ),
}


def generate_borderless(code: str, xbrl: dict):
    name = COMPANY_NAMES.get(code, code)
    sections = parse_xbrl_sections(xbrl["table"])

    pdf = BorderlessPDF(name, code)
    pdf.add_page()
    pdf.header_info()

    # 公司简介
    snippet = COMPANY_SNIPPETS.get(code, "")
    pdf.body_text(f"公司简介：{snippet}")

    for title, rows in sections:
        pdf.section_title(title)
        if len(rows) < 2:
            continue
        # 计算列宽
        ncols = len(rows[0])
        usable = 180
        col_widths = []
        for i in range(ncols):
            max_w = max((len(r[i]) for r in rows if i < len(r)), default=10)
            col_widths.append(min(max(12, max_w + 4), usable // max(ncols, 1)))
        pdf.borderless_table(rows, col_widths)
        pdf.ln(8)

    out_path = BORDERLESS_DIR / f"{code}.pdf"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_path))
    print(f"  Borderless PDF → {out_path}")


def _pick_key_rows(rows: list[list[str]], n: int = 8) -> list[list[str]]:
    """取表头 + 前 n 行数据。"""
    result = [rows[0]]
    for r in rows[1:n + 1]:
        result.append(r)
    return result


# 多栏排版用的年报正文（长文本，模拟真实年报的连续叙述风格）
COMPANY_REPORT_BODY = {
    "603421": [
        "鼎信通讯股份有限公司（以下简称「公司」或「本公司」）是国内领先的电力物联网通信方案提供商，专注于电力线载波通信技术的研发与应用。公司自成立以来，始终坚持以技术创新为核心驱动力，深耕电力物联网通信领域近二十年，形成了从芯片设计到系统集成的完整技术链条。",
        "2023年度，公司实现营业收入约36.3亿元，归属于上市公司股东的净利润约3.1亿元。在宏观经济承压的大背景下，公司主营业务保持稳健增长态势，核心业务板块毛利率同比提升1.8个百分点，体现出产品结构的持续优化和规模效应的逐步释放。",
        "公司核心产品包括HPLC高速电力线载波通信模块、双模（HPLC+RF）通信单元、智能电能表数据采集终端及能源管理综合系统。根据国家电网公开招标数据，公司产品市场占有率连续三年位居行业前三，HPLC模块在国网统标市场的份额稳定在25%以上。",
        "报告期内完成的两项重大技术突破值得关注：一是新一代双模通信芯片DT7z的量产，该芯片同时支持HPLC和微功率无线RF双模通信，符合国家电网2023版技术标准，已通过中国电力科学研究院型式试验认证；二是面向低压台区智能融合终端的软件平台V3.0发布，集成边缘计算和AI分析能力，实现从数据采集到智能决策的闭环。",
        "海外业务板块增速显著：东南亚地区通过泰国、越南的智能电表AMI项目落地，累计部署超过50万只智能终端；非洲市场与东非电力公司签署长期合作协议；拉美市场在巴西、哥伦比亚建立本地化运营团队。全年海外收入同比增长34%，收入占比从上年的7%提升至10%以上。",
        "研发方面，公司全年研发投入4.2亿元，占营业收入的11.6%，较上年增加0.9个百分点。研发人员达到860人，占比超过公司总人数的40%。在芯片设计、通信协议、嵌入式软件和云端平台四大方向持续深耕，拥有授权发明专利287项、实用新型专利156项。",
        "公司治理方面，董事会由9名董事组成，其中独立董事3名。监事会设监事3名。2023年度董事会共召开12次会议，审议通过重大事项35项。公司已建立完善的内部控制体系，经审计机构评估，内部控制有效性评价为良好。",
        "2023年度利润分配预案：以总股本5.43亿股为基数，向全体股东每10股派发现金红利1.50元（含税），合计派发8,145万元，占当年归母净利润的26.3%。该分配预案已经董事会和监事会审议通过，尚需提交股东大会审议。",
    ],
    "603707": [
        "健友生化制药股份有限公司（以下简称「公司」）是全球肝素产业链的龙头企业，主营业务涵盖肝素原料药、低分子肝素制剂及高端注射剂产品的研发、生产和销售。公司成立于1997年，2017年在上交所上市，经过二十余年的发展，已形成从粗品肝素钠到终端制剂产品的全产业链布局。",
        "2023年度，公司实现营业收入约39.3亿元，归属于上市公司股东的净利润约5.7亿元。面对全球肝素市场周期性调整和价格波动，公司通过优化产品结构、扩大高端制剂出口等举措，成功对冲了原料药价格下行的影响，综合毛利率维持在48%以上的较高水平。",
        "公司产品线覆盖三大板块：（1）标准肝素原料药，主要销往欧美大型制药企业，年收入约18亿元；（2）低分子肝素制剂，包括依诺肝素钠注射液、那屈肝素钙注射液等，年收入约15亿元；（3）高端注射剂出口，涵盖预灌封注射器及无菌粉针产品，年收入约6亿元。",
        "制剂出口业务是公司最大的增长引擎。报告期内，依诺肝素钠注射液在美国市场持续放量，按处方量计跃居全美前三，市场份额突破15%。公司3条注射剂生产线顺利通过美国FDA现场检查（零483观察项），进一步夯实了高端制剂出海的基础。欧洲市场方面，那屈肝素钙在德国、法国的上市申请已获受理。",
        "研发方面，公司全年研发投入3.8亿元，占营业收入的9.7%，聚焦三大方向：一是GLP-1类多肽原料药及制剂，目前已进入中试阶段，有望成为第二增长曲线；二是新型抗凝药物的研发，公司拥有自主知识产权的磺达肝癸钠仿制药已提交ANDA申请；三是生物类似药，注射用曲妥珠单抗的III期临床试验已接近尾声。",
        "质量和合规方面，公司建立了完善的质量管理体系，通过了美国FDA、欧盟EDQM、巴西ANVISA等多国监管机构的认证。全年共接受17次国内外监管检查，未发生重大质量事故。公司严格执行cGMP标准，确保从原料到成品的全过程质量受控。",
        "公司积极响应国家集中带量采购政策，主要产品依诺肝素钠注射液、那屈肝素钙注射液在中标集采区域实现了以价换量。尽管集采降价幅度较大，但通过规模效应和供应链优化，制剂业务的单位成本下降12%，有效维护了利润空间。",
        "2023年度利润分配预案：以总股本15.72亿股为基数，向全体股东每10股派发现金红利2.00元（含税），合计派发3.14亿元，占当年归母净利润的55.1%。该分配预案已经董事会审议通过。",
    ],
    "600569": [
        "安阳钢铁股份有限公司（以下简称「公司」）是河南省最大的钢铁联合企业，隶属于安钢集团，拥有从焦化、烧结、炼铁、炼钢到连铸、轧钢的完整长流程生产线，具备年产约1,000万吨钢的综合生产能力。公司主要产品涵盖宽厚板、热轧卷板、冷轧薄板、中厚板、高速线材、型钢等多个品类，广泛应用于建筑、机械制造、汽车、船舶、桥梁、压力容器等下游行业。",
        "2023年度，受国内钢材市场价格持续走低和原材料成本高企的双重挤压，公司实现营业收入约421.5亿元，归属于上市公司股东的净利润约-12.8亿元。尽管行业整体处于周期底部，公司通过深入推进降本增效、优化产品结构和加快超低排放改造等多项举措，四季度经营性现金流已实现转正，生产经营呈现出筑底企稳的积极信号。",
        "产品结构方面，公司持续推动「普转特、特转优」战略。2023年，高附加值品种钢占比达到38%，较上年提升5个百分点。其中，汽车用钢完成认证品种12个，供货量同比增长28%；桥梁钢先后中标川藏铁路、深中通道等国家级重大工程，公司品牌影响力进一步巩固。此外，容器板、高强结构板等优势品种的市场占有率稳居国内前三。",
        "绿色低碳转型方面，公司积极响应国家「碳达峰、碳中和」战略，2023年累计投入环保改造资金超过25亿元。2号高炉超低排放改造项目顺利完工并通过河南省生态环境厅验收，公司整体通过环保绩效A级企业认定。在节能降碳方面，吨钢综合能耗同比下降3.2%，自发电比例提升至65%，余热余能回收利用率达到行业领先水平。",
        "公司持续推进智能制造和数字化转型。报告期内，炼钢二车间智能集控中心投入使用，实现从铁水预处理到连铸的全流程远程集中管控；冷轧智慧物流系统上线运行，厂区内物流周转效率提升18%。此外，公司与北京科技大学、东北大学等科研院所建立了产学研深度合作关系，全年获得授权发明专利42项。",
        "供应链方面，铁矿石采购坚持「长协+现货」双轨制，长协比例保持在70%以上，有效对冲矿价波动风险。焦炭自给率维持在85%，焦化副产品综合利用创效超过4亿元。合金、耐火材料等辅料实施集中采购，全年节约采购成本2.3亿元。公司原材料库存周转天数保持在合理区间，确保了生产的连续性。",
        "2023年度，面对行业周期性低谷，公司采取了多项应对措施：一是大幅压缩非生产性支出，管理费用同比下降15%；二是优化融资结构，长期借款占比提升至60%，财务费用率降至1.8%；三是积极争取政策支持，获得环保超低排放改造专项补助1.2亿元、高新技术企业税收优惠2,800万元。",
        "2023年度利润分配预案：鉴于2023年度亏损，公司拟不进行利润分配，不派发现金红利，不送红股，不以公积金转增股本。该预案已经董事会审议通过，尚需提交股东大会审议。公司管理层表示，将把有限资金优先用于环保改造和产品升级，为下一轮行业回升积蓄力量。",
    ],
}


def _topic_sections_for_company(code: str) -> list[dict[str, Any]]:
    """构造真实年报双栏专题页内容。"""
    name = COMPANY_NAMES[code]
    body = COMPANY_REPORT_BODY[code]
    snippet = COMPANY_SNIPPETS[code]
    long_desc = COMPANY_LONG_DESC[code]

    sections = [
        {
            "id": "overview",
            "title": "一、公司概况与经营回顾",
            "left": [
                ("overview_p1", body[0]),
                ("overview_p2", body[1]),
                ("overview_p3", f"从年度报告口径看，{snippet} 公司围绕主营业务稳定运行、重点客户维护和组织效率提升开展经营管理，报告期内主要业务模式和收入来源保持连续。"),
            ],
            "right": [
                ("overview_p4", body[2]),
                ("overview_p5", long_desc),
                ("overview_p6", "管理层认为，稳定的产业基础、持续的客户合作和围绕主业形成的技术积累，是公司穿越行业周期的重要支撑。公司将继续把资源投向核心产品、关键项目和现金流质量改善。"),
            ],
        },
        {
            "id": "operation",
            "title": "二、业务亮点与研发投入",
            "left": [
                ("operation_p1", body[3]),
                ("operation_p2", body[4]),
                ("operation_p3", "报告期内，公司将年度经营计划分解到市场、研发、生产和供应链等关键环节，通过项目制管理跟踪重点事项进度。各业务单元围绕客户需求变化及时调整交付节奏，提升订单履约能力。"),
            ],
            "right": [
                ("operation_p4", body[5]),
                ("operation_p5", "公司持续完善研发立项、预算控制和成果转化机制，重点项目由管理层定期复盘。研发团队围绕产品可靠性、成本控制和场景适配开展专项攻关，形成多项可复用技术成果。"),
                ("operation_p6", "在供应链管理方面，公司强化核心原材料采购计划和库存周转管理，提升关键供应商协同效率。针对市场波动，公司建立滚动预测机制，降低交付周期和成本波动对经营结果的影响。"),
            ],
            "note_title": "年度经营摘要",
        },
        {
            "id": "risk_outlook",
            "title": "三、风险因素与经营展望",
            "left": [
                ("risk_p1", body[6]),
                ("risk_p2", "公司面临的主要风险包括宏观需求波动、行业竞争加剧、原材料或关键组件价格变化、技术路线迭代以及海外市场政策环境变化。公司将通过预算管理、客户结构优化和研发储备降低不确定性影响。"),
                ("risk_p3", "内部控制方面，公司继续完善授权审批、资金管理、合同管理和信息披露流程。董事会、监事会及管理层按规则履职，重大经营事项均履行必要审议程序。"),
            ],
            "right": [
                ("risk_p4", body[7]),
                ("risk_p5", "展望下一年度，公司将坚持稳健经营原则，在保持主营业务韧性的同时推进产品升级、市场拓展和成本精细化管理。管理层将重点关注现金流质量、盈利能力恢复和可持续投入能力。"),
                ("risk_p6", "本专题页为合成多栏排版样本，文本顺序遵循左栏读完后进入右栏的真实年报阅读习惯。财务数据仍以 XBRL 真值为准，后续分析不得脱离 GT 中的标准表格和任务答案。"),
            ],
        },
    ]
    sections[0]["left"].append((
        "overview_p7",
        f"报告期内，{name}围绕年度经营目标持续优化组织机制，强化预算约束、项目复盘和重点客户跟踪。公司管理层按月分析订单、成本、回款和存货周转情况，及时调整资源投放节奏。",
    ))
    sections[0]["right"].append((
        "overview_p8",
        "在信息披露和投资者沟通方面，公司保持审慎、及时和一致的原则，围绕经营进展、行业变化和重大事项向市场传递稳定预期。相关安排有助于外部使用者理解公司年度经营脉络。",
    ))
    sections[1]["left"].append((
        "operation_p7",
        "为提升经营质量，公司进一步细化产品、项目和客户维度的经营分析，推动生产计划、采购计划和销售计划联动。重点项目由业务部门、财务部门和管理层共同跟踪，确保资源投入与收益目标相匹配。",
    ))
    sections[1]["right"].append((
        "operation_p8",
        "公司还通过数字化系统沉淀运营数据，提升对交付周期、质量波动和成本变化的识别能力。相关数据被用于改进预算编制、绩效考核和供应链协同，形成持续改进闭环。",
    ))
    sections[2]["left"].append((
        "risk_p7",
        "针对外部环境变化，公司将持续关注主要客户需求、行业政策、汇率和原材料价格等因素。管理层将根据经营计划执行情况动态调整预算，保持资产负债结构和现金流安排的稳健性。",
    ))
    sections[2]["right"].append((
        "risk_p8",
        "未来，公司将继续围绕主业能力建设开展投资和管理改善，优先支持能够提升客户粘性、产品质量和经营效率的项目。上述安排将作为下一年度经营计划的重要组成部分。",
    ))
    return sections


def _new_layout_gt(code: str, company_name: str) -> dict[str, Any]:
    return {
        "layout_type": "synthetic_multicolumn_annual_report_topic",
        "company_code": code,
        "company_name": company_name,
        "reading_order": "left_column_then_right_column",
        "pages": [],
    }


def _append_layout_section(
    layout_gt: dict[str, Any],
    page: int,
    section_id: str,
    title: str,
    paragraph_ids: list[str],
):
    page_entry = next((p for p in layout_gt["pages"] if p["page"] == page), None)
    if page_entry is None:
        page_entry = {
            "page": page,
            "is_multicolumn": True,
            "columns": ["left", "right"],
            "sections": [],
        }
        layout_gt["pages"].append(page_entry)

    page_entry["sections"].append({
        "id": section_id,
        "title": title,
        "column_sequence": ["left", "right"],
        "paragraph_ids": paragraph_ids,
    })


def _find_row(sections: list[tuple[str, list[list[str]]]], item_name: str) -> list[str] | None:
    for _, rows in sections:
        for row in rows[1:]:
            if row and row[0] == item_name:
                return row
    return None


def _build_metric_box_lines(code: str, sections: list[tuple[str, list[list[str]]]]) -> list[str]:
    lines: list[str] = []
    for item in ["营业收入", "净利润", "资产总计"]:
        row = _find_row(sections, item)
        if row and len(row) >= 2:
            lines.append(f"{item}：{row[1]}")
    if code == "600569":
        lines.append("专题关注：产品结构升级与绿色制造")
    elif code == "603421":
        lines.append("专题关注：电力物联网与双模通信")
    elif code == "603707":
        lines.append("专题关注：制剂出口与质量合规")
    return lines[:4]


def _build_financial_summary_rows(sections: list[tuple[str, list[list[str]]]]) -> list[list[str]]:
    rows = [["指标", "2023年", "2022年"]]
    for item in ["营业收入", "营业成本", "净利润", "资产总计", "负债合计", "经营活动现金流量净额"]:
        row = _find_row(sections, item)
        if row and len(row) >= 3:
            rows.append([row[0], row[1], row[2]])
    return rows


def _add_financial_summary_page(
    pdf: MultiColumnPDF,
    sections: list[tuple[str, list[list[str]]]],
    layout_gt: dict[str, Any],
):
    pdf.full_section_break("财务摘要")
    page = pdf.current_page_number()
    rows = _build_financial_summary_rows(sections)
    pdf.full_span_table("关键财务摘要", rows, max_rows=12)
    layout_gt["pages"].append({
        "page": page,
        "is_multicolumn": False,
        "columns": ["full_width"],
        "sections": [
            {
                "id": "financial_summary",
                "title": "财务摘要",
                "column_sequence": ["full_width"],
                "paragraph_ids": ["financial_summary_table"],
            }
        ],
    })


def generate_multicolumn(code: str, xbrl: dict) -> dict[str, Any]:
    name = COMPANY_NAMES.get(code, code)
    sections = parse_xbrl_sections(xbrl["table"])
    topic_sections = _topic_sections_for_company(code)

    pdf = MultiColumnPDF(name, code)
    layout_gt = _new_layout_gt(code, name)

    pdf.start_topic_document(
        f"{name} 2023 年度报告专题节选",
        f"管理层讨论与分析  |  证券代码：{code}.SH  |  合成双栏排版样本",
    )

    for idx, section in enumerate(topic_sections):
        pdf.topic_section(
            section["title"],
            [text for _, text in section["left"]],
            [text for _, text in section["right"]],
            note_title=section.get("note_title"),
            note_lines=_build_metric_box_lines(code, sections) if section.get("note_title") else None,
            new_page=idx > 0,
        )
        paragraph_ids = [pid for pid, _ in section["left"]] + [pid for pid, _ in section["right"]]
        if section.get("note_title"):
            paragraph_ids.append("operation_metric_box")
        _append_layout_section(
            layout_gt,
            pdf.current_page_number(),
            section["id"],
            section["title"],
            paragraph_ids,
        )

    _add_financial_summary_page(pdf, sections, layout_gt)
    pdf.finalize()

    out_path = MULTICOLUMN_DIR / f"{code}_multi.pdf"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_path))
    print(f"  MultiColumn PDF → {out_path}")
    return layout_gt


# ---------------------------------------------------------------------------
# Ground Truth 文件生成
# ---------------------------------------------------------------------------

def save_gt(
    code: str,
    xbrl: dict,
    scene_dir: Path,
    suffix: str = "",
    layout_gt: dict[str, Any] | None = None,
):
    """为合成 PDF 保存 XBRL GT。

    格式与现有 eval_dataset 对齐：
      {scene}/<code><suffix>_gt.json → {"xbrl_table": ..., "instances": ..., "company": ...}
    """
    stem = f"{code}{suffix}"
    gt = {
        "company_code": code,
        "company_name": COMPANY_NAMES.get(code, code),
        "xbrl_table": xbrl["table"],
        "instances": xbrl.get("instances", []),
    }
    if layout_gt is not None:
        gt["layout_gt"] = layout_gt
    out_path = scene_dir / f"{stem}_gt.json"
    out_path.write_text(json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  GT saved → {out_path}")

    # 同时生成 selection.json
    sel_path = scene_dir / "selection.json"
    entries = []
    for pdf_file in sorted(scene_dir.glob("*.pdf")):
        # 从文件名提取纯股票代码（去掉 _multi / _synth 等后缀）
        code = re.sub(r"_(multi|synth)$", "", pdf_file.stem)
        entries.append({"code": code, "file": pdf_file.name})
    sel_path.write_text(json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  Selection → {sel_path}")


# ---------------------------------------------------------------------------
# 更新 _selection.json
# ---------------------------------------------------------------------------

def update_selection():
    """将新场景注册到 _selection.json。"""
    sel_path = EVAL_ROOT / "_selection.json"
    sel = json.loads(sel_path.read_text(encoding="utf-8"))

    sel["scenes"]["synthetic_borderless"] = {
        "title": "无边框表格（合成）",
        "count": len(SELECTED),
        "codes": sorted(SELECTED),
        "synthetic": True,
        "note": "XBRL 数据反推生成，纯空格对齐无线条；GT 即 XBRL 本身",
    }
    sel["scenes"]["synthetic_multicolumn"] = {
        "title": "多栏排版（合成）",
        "count": len(SELECTED),
        "codes": sorted(SELECTED),
        "synthetic": True,
        "note": "XBRL 数据反推生成，真实年报双栏专题页；GT 包含 XBRL 与 layout_gt",
    }
    sel["total_pdf_count"] = (
        sum(s["count"] for s in sel["scenes"].values())
    )

    sel_path.write_text(json.dumps(sel, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nUpdated _selection.json: {len(sel['scenes'])} scenes, {sel['total_pdf_count']} PDFs total")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Generate synthetic eval_dataset scene PDFs.")
    parser.add_argument(
        "--scene",
        choices=["all", "borderless", "multicolumn"],
        default="all",
        help="选择生成全部场景、仅无边框场景或仅多栏场景。",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Generating Synthetic Scene PDFs")
    print("=" * 60)
    print(f"Scene: {args.scene}")

    # Setup dirs
    BORDERLESS_DIR.mkdir(parents=True, exist_ok=True)
    MULTICOLUMN_DIR.mkdir(parents=True, exist_ok=True)

    for code in SELECTED:
        print(f"\n--- {code} ({COMPANY_NAMES.get(code, '')}) ---")
        xbrl = load_xbrl_for_company(code)

        print(f"  XBRL loaded: {len(xbrl.get('instances', []))} task instances")

        if args.scene in {"all", "borderless"}:
            # Borderless
            generate_borderless(code, xbrl)
            save_gt(code, xbrl, BORDERLESS_DIR, suffix="_synth")

        if args.scene in {"all", "multicolumn"}:
            # Multi-column
            layout_gt = generate_multicolumn(code, xbrl)
            save_gt(code, xbrl, MULTICOLUMN_DIR, suffix="_multi", layout_gt=layout_gt)

    update_selection()
    scene_count = 2 if args.scene == "all" else 1
    print(f"\nDone: {len(SELECTED)} companies × {scene_count} scene(s)")


if __name__ == "__main__":
    main()
