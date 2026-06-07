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
BORDERLESS_DIR = EVAL_ROOT / "synthetic_borderless"
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
    """生成多栏排版 PDF（2 栏报纸风格）。"""

    def __init__(self, company_name: str, company_code: str):
        super().__init__("P", "mm", "A4")
        self.set_auto_page_break(True, 20)
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

        self.col_width = 85  # mm per column
        self.col_gap = 10
        self.left_margin = 15
        self.right_col_x = self.left_margin + self.col_width + self.col_gap

    def header_info(self):
        self.set_x(self.left_margin)
        self.set_font("CN", "", 14)
        self.cell(0, 10, f"{self.company_name} ({self.company_code}.SH)", align="C", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 8, "2023 年度财务报表（多栏版式）", align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(8)

    def section_title(self, title: str):
        self.set_x(self.left_margin)
        self.set_font("CN", "", 11)
        self.cell(self.col_width, 7, title, align="L", new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def column_text(self, text: str):
        self.set_x(self.left_margin)
        self.set_font("CN", "", 8)
        self.multi_cell(self.col_width, 4.5, text, align="L")

    def column_table(self, rows: list[list[str]], max_rows: int = 12):
        """在单栏宽度内渲染表格。"""
        self.set_x(self.left_margin)
        self.set_font("CN", "", 7)

        width_per_cell = self.col_width / len(rows[0]) if rows else 20

        # 表头
        for cell in rows[0]:
            self.cell(width_per_cell, 5, cell[: int(width_per_cell // 2)], border=0, align="L")
        self.ln()

        # 数据行
        for row in rows[1 : max_rows + 1]:
            for cell in row:
                self.cell(width_per_cell, 4.5, cell[: int(width_per_cell // 2)], border=0, align="L")
            self.ln()

    def right_column_text(self, text: str):
        self.set_x(self.right_col_x)
        self.set_font("CN", "", 8)
        self.multi_cell(self.col_width, 4.5, text, align="L")

    def right_column_table(self, rows: list[list[str]], max_rows: int = 12):
        self.set_x(self.right_col_x)
        self.set_font("CN", "", 7)
        width_per_cell = self.col_width / len(rows[0]) if rows else 20

        for cell in rows[0]:
            self.cell(width_per_cell, 5, cell[: int(width_per_cell // 2)], border=0, align="L")
        self.ln()
        for row in rows[1 : max_rows + 1]:
            for cell in row:
                self.cell(width_per_cell, 4.5, cell[: int(width_per_cell // 2)], border=0, align="L")
            self.ln()


# ---------------------------------------------------------------------------
# 生成逻辑
# ---------------------------------------------------------------------------

COMPANY_NAMES = {
    "603421": "鼎信通讯",
    "603707": "健友股份",
    "600569": "安阳钢铁",
}

COMPANY_SNIPPETS = {
    "603421": "公司主要从事电力线载波通信产品的研发、生产和销售，是国内领先的电力物联网通信方案提供商。",
    "603707": "公司主要从事肝素原料药、低分子肝素制剂等产品的研发、生产和销售，产品覆盖全球多个国家和地区。",
    "600569": "公司是集炼焦、烧结、炼铁、炼钢、轧钢于一体的钢铁联合企业，是河南省最大的钢铁生产企业。",
}


def _rows_to_text(rows: list[list[str]], max_rows: int = 15) -> str:
    """将表格行转为纯文字段落（用于多栏文本块）。"""
    lines = []
    for row in rows[:max_rows]:
        lines.append("、".join(row))
    return "；\n".join(lines)


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


def generate_multicolumn(code: str, xbrl: dict):
    name = COMPANY_NAMES.get(code, code)
    sections = parse_xbrl_sections(xbrl["table"])

    pdf = MultiColumnPDF(name, code)
    pdf.add_page()
    pdf.header_info()

    snippet = COMPANY_SNIPPETS.get(code, "")

    # 多栏布局：左栏正文+表格，右栏表格
    for i, (title, rows) in enumerate(sections):
        if i % 2 == 0:
            # 左栏
            pdf.section_title(title)
            pdf.column_text(f"{snippet}\n{_rows_to_text(rows, 8)}")
            pdf.ln(4)
        else:
            # 右栏
            pdf.right_column_text(f"（续）{title}")
            pdf.right_column_table(rows, 12)
            pdf.ln(8)

    out_path = MULTICOLUMN_DIR / f"{code}.pdf"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_path))
    print(f"  MultiColumn PDF → {out_path}")


# ---------------------------------------------------------------------------
# Ground Truth 文件生成
# ---------------------------------------------------------------------------

def save_gt(code: str, xbrl: dict, scene_dir: Path):
    """为合成 PDF 保存 XBRL GT。

    格式与现有 eval_dataset 对齐：
      {scene}/<code>_gt.json → {"xbrl_table": ..., "instances": ..., "company": ...}
    """
    gt = {
        "company_code": code,
        "company_name": COMPANY_NAMES.get(code, code),
        "xbrl_table": xbrl["table"],
        "instances": xbrl.get("instances", []),
    }
    out_path = scene_dir / f"{code}_gt.json"
    out_path.write_text(json.dumps(gt, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  GT saved → {out_path}")

    # 同时生成 selection.json
    sel_path = scene_dir / "selection.json"
    entries = []
    for pdf_file in sorted(scene_dir.glob("*.pdf")):
        c = pdf_file.stem
        entries.append({"code": c, "file": pdf_file.name})
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
        "note": "XBRL 数据反推生成，2 栏报纸版式；GT 即 XBRL 本身",
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
    print("=" * 60)
    print("Generating Synthetic Scene PDFs")
    print("=" * 60)

    # Setup dirs
    BORDERLESS_DIR.mkdir(parents=True, exist_ok=True)
    MULTICOLUMN_DIR.mkdir(parents=True, exist_ok=True)

    for code in SELECTED:
        print(f"\n--- {code} ({COMPANY_NAMES.get(code, '')}) ---")
        xbrl = load_xbrl_for_company(code)

        print(f"  XBRL loaded: {len(xbrl.get('instances', []))} task instances")

        # Borderless
        generate_borderless(code, xbrl)
        save_gt(code, xbrl, BORDERLESS_DIR)

        # Multi-column
        generate_multicolumn(code, xbrl)
        save_gt(code, xbrl, MULTICOLUMN_DIR)

    update_selection()
    print("\nDone: 3 companies × 2 scenes = 6 PDFs + GT")


if __name__ == "__main__":
    main()
