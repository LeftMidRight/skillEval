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
    """生成典型多栏排版 PDF（2 栏，含栏间竖线分隔符）。

    布局：
      - 通栏标题（跨全页）
      - 两栏正文，左栏→右栏自然流排
      - 栏间可见竖线
      - 表格带线框（单栏宽度内的薄框表格）
      - 多栏记事 + 财务数据混合排版
    """

    def __init__(self, company_name: str, company_code: str):
        super().__init__("P", "mm", "A4")
        self.set_auto_page_break(True, 18)
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

        # 版面参数
        self.left_margin = 12
        self.right_margin = 12
        self.col_width = 88   # mm per column
        self.col_gap = 8      # 栏间距
        self.right_col_x = self.left_margin + self.col_width + self.col_gap
        # 栏间竖线 X 坐标
        self.divider_x = self.left_margin + self.col_width + self.col_gap / 2

        self._col_top_y = 0.0    # 记录每页两栏内容的起始 Y
        self._left_y = 0.0       # 左栏当前 Y
        self._right_y = 0.0      # 右栏当前 Y

    # ================================================================
    # 通栏元素（跨两栏）
    # ================================================================

    def full_span_title(self, title: str):
        """通栏大标题（跨两栏）。"""
        self.set_font("CN", "", 16)
        self.cell(0, 10, title, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(4)

    def full_span_text(self, text: str, size: int = 9):
        """通栏文本行（跨两栏，如日期/来源）。"""
        self.set_font("CN", "", size)
        self.set_text_color(100, 100, 100)
        self.cell(0, 6, text, align="C", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)
        self.ln(2)

    def draw_divider(self, top_y: float, bottom_y: float):
        """在栏间绘制竖线分隔符。"""
        self.set_draw_color(180, 180, 180)
        self.set_line_width(0.3)
        self.line(self.divider_x, top_y, self.divider_x, bottom_y)
        self.set_line_width(0.2)

    def start_two_column_region(self):
        """标记两栏区域的起始 Y。"""
        self._col_top_y = self.get_y()
        self._left_y = self._col_top_y
        self._right_y = self._col_top_y

    # ================================================================
    # 左栏内容
    # ================================================================

    def left_title(self, title: str):
        self.set_x(self.left_margin)
        self.set_font("CN", "", 11)
        self.cell(self.col_width, 7, title, align="L", new_x="LMARGIN", new_y="NEXT")
        self._left_y = self.get_y()
        self.ln(1)

    def left_body(self, text: str, size: int = 8):
        """左栏正文：在 col_width 宽度内自动换行。"""
        self.set_x(self.left_margin)
        self.set_font("CN", "", size)
        self.multi_cell(self.col_width, 4.2, text, align="L")
        self._left_y = self.get_y()
        self.ln(1)

    def left_table(self, rows: list[list[str]], max_rows: int = 10):
        """左栏带线框小表格。"""
        self.set_x(self.left_margin)
        self.set_font("CN", "", 7)
        ncols = len(rows[0]) if rows else 2
        cw = [self.col_width / ncols] * ncols
        line_h = 4.5

        # 表头
        self.set_fill_color(235, 235, 235)
        for i, h in enumerate(rows[0]):
            self.cell(cw[i], line_h + 1, h, border=1, fill=True, align="C")
        self.ln()
        # 数据
        for row in rows[1:max_rows + 1]:
            for i, cell in enumerate(row):
                align = "R" if i > 0 else "L"
                self.cell(cw[i], line_h, str(cell), border=1, align=align)
            self.ln()
        self._left_y = self.get_y()
        self.ln(3)

    # ================================================================
    # 右栏内容
    # ================================================================

    def _set_right_x(self):
        self.set_x(self.right_col_x)

    def right_title(self, title: str):
        self._set_right_x()
        self.set_font("CN", "", 11)
        self.cell(self.col_width, 7, title, align="L", new_x="LMARGIN", new_y="NEXT")
        self._right_y = self.get_y()

    def right_body(self, text: str, size: int = 8):
        self._set_right_x()
        self.set_font("CN", "", size)
        self.multi_cell(self.col_width, 4.2, text, align="L")
        self._right_y = self.get_y()

    def right_table(self, rows: list[list[str]], max_rows: int = 10):
        """右栏带线框表格。"""
        self._set_right_x()
        self.set_font("CN", "", 7)
        ncols = len(rows[0]) if rows else 2
        cw = [self.col_width / ncols] * ncols
        line_h = 4.5

        # 表头
        self.set_fill_color(235, 235, 235)
        for i, h in enumerate(rows[0]):
            self.cell(cw[i], line_h + 1, h, border=1, fill=True, align="C")
        self.ln()
        for row in rows[1:max_rows + 1]:
            for i, cell in enumerate(row):
                align = "R" if i > 0 else "L"
                self.cell(cw[i], line_h, str(cell), border=1, align=align)
            self.ln()
        self._right_y = self.get_y()

    # ================================================================
    # 完成页面的两栏区域
    # ================================================================

    def finish_two_column_page(self, page_h: int = 297):
        """在页面底部绘制栏间竖线，并将 Y 移到两栏下方的统一位置。"""
        bottom = max(self._left_y, self._right_y)
        if bottom > self._col_top_y + 10:
            self.draw_divider(self._col_top_y, min(bottom, page_h - 20))
        # 将光标移到两栏中更靠下的位置（模拟通栏接续）
        self.set_y(bottom + 6)


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


def generate_multicolumn(code: str, xbrl: dict):
    name = COMPANY_NAMES.get(code, code)
    sections = parse_xbrl_sections(xbrl["table"])
    desc = COMPANY_LONG_DESC.get(code, COMPANY_SNIPPETS.get(code, ""))
    snippet = COMPANY_SNIPPETS.get(code, "")

    # 按表名索引
    tables_by_name: dict[str, list[list[str]]] = {}
    for title, rows in sections:
        tables_by_name[title] = rows

    income_rows = tables_by_name.get("利润表", [])
    balance_rows = tables_by_name.get("资产负债表", [])
    cashflow_rows = tables_by_name.get("现金流量表", [])

    # 构建 "关键财务指标" 摘要表
    key_financial_rows = [["指标", "2023年", "2022年"]]
    for r in income_rows:
        if len(r) >= 3:
            item = r[0]
            if any(kw in item for kw in ["营业收入", "营业成本", "净利润"]):
                key_financial_rows.append(r[:3])

    pdf = MultiColumnPDF(name, code)

    # ================================================================
    # 第 1 页：两栏 — 左栏公司概述 + 右栏关键财务表
    # ================================================================
    pdf.add_page()
    pdf.full_span_title(f"{name} 2023 年度财务报告摘要")
    pdf.full_span_text("来源：上海证券交易所公开披露   |   发布时间：2024年4月   |   本期共 3 页")
    pdf.ln(3)

    pdf.start_two_column_region()

    # 左栏：公司概述
    pdf.left_title("一、公司概况")
    pdf.left_body(desc, size=8)
    pdf.ln(2)
    pdf.left_title("二、主营业务分析")
    pdf.left_body(
        f"报告期内，公司主营业务稳步发展。{snippet}"
        f"2023年度，公司继续加大研发投入力度，推进智能化、数字化转型。"
        f"面对复杂多变的国内外经济形势，公司管理层审慎决策，"
        f"在保持主营业务稳健增长的同时积极拓展新兴市场，"
        f"资产负债结构持续优化，经营性现金流保持健康水平。"
        f"公司治理方面，董事会、监事会依法合规运作，"
        f"独立董事对公司重大事项发表了独立意见。"
        f"2023年度利润分配预案已经董事会审议通过，"
        f"拟向全体股东每10股派发现金红利。",
        size=8,
    )

    # 右栏：关键财务数据表
    pdf.right_title("三、关键财务数据")
    pdf.right_table(key_financial_rows, max_rows=12)
    pdf.ln(3)
    pdf.right_title("四、业务亮点")
    pdf.right_body(
        f"> 全年新签合同金额同比增长超20%\n"
        f"> 研发投入占比持续领先行业均值\n"
        f"> 海外业务收入占比突破10%\n"
        f"> 获得省部级科技进步奖2项\n"
        f"> 新增专利授权32项\n"
        f"> 资产负债率处于行业偏低水平\n"
        f"> 经营性现金流连续三年为正\n"
        f"> 信用评级维持AA+级",
        size=8,
    )

    pdf.finish_two_column_page()

    # ================================================================
    # 第 2 页：两栏 — 左栏利润表 + 右栏资产负债表
    # ================================================================
    pdf.add_page()
    pdf.full_span_title(f"{name} — 合并财务报表（续）")
    pdf.ln(2)

    pdf.start_two_column_region()

    # 左栏：利润表
    if income_rows:
        pdf.left_title("合并利润表（摘要）")
        inc_abbrev = _pick_key_rows(income_rows, 12)
        pdf.left_table(inc_abbrev, max_rows=13)

    # 右栏：资产负债表
    if balance_rows:
        pdf.right_title("合并资产负债表（摘要）")
        bs_abbrev = _pick_key_rows(balance_rows, 18)
        pdf.right_table(bs_abbrev, max_rows=19)

    pdf.finish_two_column_page()

    # ================================================================
    # 第 3 页：两栏 — 左栏现金流量表 + 右栏财务附注
    # ================================================================
    pdf.add_page()
    pdf.full_span_title(f"{name} — 现金流量及附注")
    pdf.ln(2)

    pdf.start_two_column_region()

    # 左栏：现金流量表
    if cashflow_rows:
        pdf.left_title("合并现金流量表（摘要）")
        cf_abbrev = _pick_key_rows(cashflow_rows, 14)
        pdf.left_table(cf_abbrev, max_rows=15)

    # 右栏：附注说明
    pdf.right_title("财务报表附注（摘要）")
    pdf.right_body(
        f"1. 编制基础\n"
        f"本公司财务报表按照财政部颁布的《企业会计准则》编制。\n\n"
        f"2. 重要会计政策\n"
        f"（1）会计年度：公历1月1日至12月31日。\n"
        f"（2）记账本位币：人民币。\n"
        f"（3）应收账款坏账准备：按预期信用损失模型计提。\n"
        f"（4）存货计价：按成本与可变现净值孰低计量。\n"
        f"（5）固定资产折旧：按年限平均法计提。\n\n"
        f"3. 税项\n"
        f"适用企业所得税税率15%（高新技术企业）。\n\n"
        f"4. 或有事项\n"
        f"截至报告期末，无应披露的重大未决诉讼。\n\n"
        f"5. 期后事项\n"
        f"截至本报告签发日，无重大期后事项。\n\n"
        f"6. 审计意见\n"
        f"中正会计师事务所出具了标准无保留意见的审计报告。",
        size=8,
    )

    pdf.finish_two_column_page()

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
