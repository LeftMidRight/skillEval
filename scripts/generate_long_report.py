"""生成一份 ~60 页的充实版长文档金融年报 PDF + XBRL GT。

改进点：
- 使用 fpdf2 绘制带边框的真实表格（而非线间距文本）
- 内容充实：封面、目录、审计报告、三张主表、10+ 节附注
- 表格含 borders/headers/cells，LAS 可识别
- XBRL GT 与实际 PDF 数据完全一致
- company_code 保持 900001，与原有评测逻辑兼容
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from fpdf import FPDF

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_ROOT / "data" / "eval_dataset" / "S5_long_documents"
OUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================================
# 1. 虚构公司财务数据（内部一致）
# ============================================================================

COMPANY = {
    "name": "中鼎智能制造股份有限公司",
    "code": "900001",
    "year": 2023,
    "prev_year": 2022,
    "currency": "人民币元",
}

# ---- 资产负债表 ----
BS_CA = {  # 流动资产
    "货币资金": (892_456_789.12, 756_234_567.89),
    "交易性金融资产": (345_678_901.23, 298_765_432.10),
    "应收票据": (123_456_789.45, 98_765_432.10),
    "应收账款": (1_567_890_123.45, 1_234_567_890.12),
    "预付款项": (234_567_890.12, 198_765_432.10),
    "其他应收款": (89_012_345.67, 76_543_210.98),
    "存货": (987_654_321.09, 876_543_210.98),
    "合同资产": (45_678_901.23, 34_567_890.12),
    "其他流动资产": (56_789_012.34, 45_678_901.23),
}
BS_NCA = {  # 非流动资产
    "长期股权投资": (345_678_901.23, 298_765_432.10),
    "其他权益工具投资": (89_012_345.67, 76_543_210.98),
    "固定资产": (2_345_678_901.23, 2_123_456_789.01),
    "在建工程": (567_890_123.45, 456_789_012.34),
    "使用权资产": (89_012_345.67, 76_543_210.98),
    "无形资产": (456_789_012.34, 398_765_432.10),
    "开发支出": (34_567_890.12, 28_765_432.10),
    "商誉": (123_456_789.45, 123_456_789.45),
    "递延所得税资产": (45_678_901.23, 38_765_432.10),
}
BS_CL = {  # 流动负债
    "短期借款": (456_789_012.34, 398_765_432.10),
    "应付票据": (234_567_890.12, 198_765_432.10),
    "应付账款": (987_654_321.09, 876_543_210.98),
    "合同负债": (89_012_345.67, 76_543_210.98),
    "应付职工薪酬": (145_678_901.23, 134_567_890.12),
    "应交税费": (56_789_012.34, 45_678_901.23),
    "其他应付款": (67_890_123.45, 56_789_012.34),
    "一年内到期的非流动负债": (34_567_890.12, 28_765_432.10),
}
BS_NCL = {  # 非流动负债
    "长期借款": (567_890_123.45, 498_765_432.10),
    "应付债券": (345_678_901.23, 345_678_901.23),
    "租赁负债": (56_789_012.34, 45_678_901.23),
    "长期应付款": (34_567_890.12, 28_765_432.10),
    "递延收益": (45_678_901.23, 38_765_432.10),
    "递延所得税负债": (23_456_789.01, 19_876_543.21),
}


def _sum_section(s, idx=0):
    return sum(v[idx] for v in s.values())


CA = _sum_section(BS_CA)
NCA = _sum_section(BS_NCA)
TA = CA + NCA
CL = _sum_section(BS_CL)
NCL = _sum_section(BS_NCL)
TL = CL + NCL
EQUITY = TA - TL  # 约 58.7 亿

CA_PREV = _sum_section(BS_CA, 1)
NCA_PREV = _sum_section(BS_NCA, 1)
TA_PREV = CA_PREV + NCA_PREV
CL_PREV = _sum_section(BS_CL, 1)
NCL_PREV = _sum_section(BS_NCL, 1)
TL_PREV = CL_PREV + NCL_PREV

# ---- 利润表 ----
REVENUE = 3_456_789_012.34
REVENUE_PREV = 2_987_654_321.09
COST = 2_345_678_901.23
COST_PREV = 2_012_345_678.90
TAX_SURCHARGE = 12_345_678.90
TAX_SURCHARGE_PREV = 10_987_654.32
SELLING_EXP = 234_567_890.12
SELLING_EXP_PREV = 198_765_432.10
ADMIN_EXP = 189_012_345.67
ADMIN_EXP_PREV = 167_890_123.45
RD_EXP = 145_678_901.23
RD_EXP_PREV = 123_456_789.01
FINANCE_EXP = 56_789_012.34
FINANCE_EXP_PREV = 45_678_901.23
OTHER_INCOME = 8_765_432.10
OTHER_INCOME_PREV = 6_543_210.98
INVEST_INCOME = 3_456_789.01
INVEST_INCOME_PREV = 2_345_678.90
CREDIT_LOSS = -2_345_678.90
CREDIT_LOSS_PREV = -1_987_654.32
ASSET_LOSS = -1_234_567.89
ASSET_LOSS_PREV = -987_654.32

OP_PROFIT = (REVENUE - COST - TAX_SURCHARGE - SELLING_EXP - ADMIN_EXP
             - RD_EXP - FINANCE_EXP + OTHER_INCOME + INVEST_INCOME
             + CREDIT_LOSS + ASSET_LOSS)
OP_PROFIT_PREV = (REVENUE_PREV - COST_PREV - TAX_SURCHARGE_PREV - SELLING_EXP_PREV
                  - ADMIN_EXP_PREV - RD_EXP_PREV - FINANCE_EXP_PREV
                  + OTHER_INCOME_PREV + INVEST_INCOME_PREV
                  + CREDIT_LOSS_PREV + ASSET_LOSS_PREV)

NONOP_INCOME = 1_234_567.89
NONOP_INCOME_PREV = 987_654.32
NONOP_EXPENSE = 345_678.90
NONOP_EXPENSE_PREV = 234_567.89

TOTAL_PROFIT = OP_PROFIT + NONOP_INCOME - NONOP_EXPENSE
TOTAL_PROFIT_PREV = OP_PROFIT_PREV + NONOP_INCOME_PREV - NONOP_EXPENSE_PREV
TAX_RATE = 0.15
TAX_EXPENSE = round(TOTAL_PROFIT * TAX_RATE, 2)
TAX_EXPENSE_PREV = round(TOTAL_PROFIT_PREV * TAX_RATE, 2)
NET_PROFIT = round(TOTAL_PROFIT - TAX_EXPENSE, 2)
NET_PROFIT_PREV = round(TOTAL_PROFIT_PREV - TAX_EXPENSE_PREV, 2)

# ---- 现金流量表 ----
CF_OPERATING = 567_890_123.45
CF_OPERATING_PREV = 456_789_012.34
CF_INVESTING = -345_678_901.23
CF_INVESTING_PREV = -298_765_432.10
CF_FINANCING = -123_456_789.01
CF_FINANCING_PREV = -98_765_432.10
CASH_BEGIN = 756_234_567.89
CASH_BEGIN_PREV = 556_234_567.89
CASH_END = CASH_BEGIN + CF_OPERATING + CF_INVESTING + CF_FINANCING
CASH_END_PREV = CASH_BEGIN

# ---- 现金流量推导值（XBRL GT 共用） ----
cash_in_op = REVENUE * 1.13 + 58_024_679.13
cash_in_op_p = REVENUE_PREV * 1.13 + 48_641_975.31
cash_out_op = COST * 1.1 + 345_678_901.23 + TAX_EXPENSE + 102_457_913.57
cash_out_op_p = COST_PREV * 1.1 + 298_765_432.10 + TAX_EXPENSE_PREV + 85_554_442.44


# ============================================================================
# 2. PDF 构建器
# ============================================================================

def _fmt(val):
    if val == int(val):
        return f"{int(val):,}"
    return f"{val:,.2f}"


class ReportPDF(FPDF):
    """自定义 PDF 生成器，含页眉页脚 + 边框表格。"""

    def __init__(self):
        super().__init__("P", "mm", "A4")
        self.set_auto_page_break(True, 20)

        # 注册中文字体
        import platform
        if platform.system() == "Windows":
            font_path = "C:/Windows/Fonts/simhei.ttf"
        else:
            font_path = "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"
        if not Path(font_path).exists():
            raise RuntimeError("No Chinese font found")
        self.add_font("CN", "", font_path)

        self.page_num = 0
        self.total_pages = 58  # 预估

    def header(self):
        if self.page_no() <= 2:
            return
        self.set_font("CN", "", 7)
        self.set_text_color(128, 128, 128)
        self.cell(0, 5, f"{COMPANY['name']} {COMPANY['year']}年年度报告", align="L")
        self.cell(0, 5, f"{self.page_no()} / {self.total_pages}", align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)

    def footer(self):
        if self.page_no() <= 2:
            return
        self.set_y(-15)
        self.set_font("CN", "", 6)
        self.set_text_color(160, 160, 160)
        self.cell(0, 8, "公司负责人：张明华    主管会计工作负责人：李建国    会计机构负责人：王芳",
                  align="C")
        self.set_text_color(0, 0, 0)

    # ---- 常用排版 ----
    def title_page(self, text, subtitle=""):
        self.add_page()
        self.ln(60)
        self.set_font("CN", "", 24)
        self.cell(0, 14, text, align="C", new_x="LMARGIN", new_y="NEXT")
        if subtitle:
            self.ln(5)
            self.set_font("CN", "", 16)
            self.cell(0, 10, subtitle, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(10)

    def section_title(self, text, level=1):
        self.ln(4)
        size = 14 if level == 1 else 12
        self.set_font("CN", "", size)
        self.cell(0, 8, text, new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def body_text(self, text):
        self.set_font("CN", "", 10)
        self.multi_cell(0, 6, text, align="L")
        self.ln(1)

    def body_lines(self, lines):
        self.set_font("CN", "", 10)
        for line in lines:
            self.cell(0, 6.5, line, new_x="LMARGIN", new_y="NEXT")

    def bordered_table(self, headers, rows, col_widths, fontsize=8, title=""):
        """绘制带边框的表格。"""
        if title:
            self.set_font("CN", "", 10)
            self.cell(0, 7, title, new_x="LMARGIN", new_y="NEXT")
            self.ln(2)

        self.set_font("CN", "", fontsize)
        line_h = fontsize * 0.6  # mm per line

        # 表头 — 深灰底色
        self.set_fill_color(220, 220, 220)
        for i, h in enumerate(headers):
            self.cell(col_widths[i], line_h + 2, h, border=1, fill=True, align="C")
        self.ln()

        # 数据行
        for row in rows:
            # 检查是否需要换页
            if self.get_y() > 260:
                self.add_page()
                self.set_font("CN", "", fontsize)
                self.set_fill_color(220, 220, 220)
                for i, h in enumerate(headers):
                    self.cell(col_widths[i], line_h + 2, h, border=1, fill=True, align="C")
                self.ln()
                self.set_fill_color(255, 255, 255)

            for i, val in enumerate(row):
                align = "R" if i >= 2 else "L"
                self.cell(col_widths[i], line_h + 1, str(val), border=1, align=align)
            self.ln()
        self.ln(3)

    def separator(self):
        self.ln(2)
        self.set_draw_color(180, 180, 180)
        self.line(self.l_margin, self.get_y(), self.w - self.r_margin, self.get_y())
        self.ln(3)
        self.set_draw_color(0, 0, 0)


# ============================================================================
# 3. 生成 PDF
# ============================================================================

def build_pdf():
    pdf = ReportPDF()

    # ---- 封面 ----
    pdf.title_page(COMPANY["name"], f"{COMPANY['year']}年年度报告")
    pdf.set_font("CN", "", 11)
    pdf.cell(0, 8, f"股票代码：{COMPANY['code']}.SH", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 8, f"报告日期：{COMPANY['year']}年4月25日", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(30)
    pdf.set_font("CN", "", 9)
    pdf.set_text_color(128, 128, 128)
    pdf.cell(0, 6, "本报告依据中国企业会计准则编制", align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)

    # ---- 目录 ----
    pdf.add_page()
    pdf.section_title("目    录")
    toc = [
        ("第一节", "重要提示及释义"),
        ("第二节", "公司简介和主要财务指标"),
        ("第三节", "管理层讨论与分析"),
        ("第四节", "公司治理"),
        ("第五节", "环境与社会责任"),
        ("第六节", "重要事项"),
        ("第七节", "股份变动及股东情况"),
        ("第八节", "财务报告"),
        ("  ", "  — 审计报告"),
        ("  ", "  — 合并资产负债表"),
        ("  ", "  — 合并利润表"),
        ("  ", "  — 合并现金流量表"),
        ("  ", "  — 财务报表附注"),
    ]
    for section, title in toc:
        pdf.set_font("CN", "", 10)
        line = f"{section}    {title}"
        dots = "." * max(2, 65 - len(line))
        pdf.cell(0, 7, f"{line} {dots}", new_x="LMARGIN", new_y="NEXT")

    # ---- 第一节：重要提示 ----
    pdf.add_page()
    pdf.section_title("第一节  重要提示及释义")
    pdf.body_lines([
        "本公司董事会、监事会及董事、监事、高级管理人员保证年度报告内容的真实、准确、完整，",
        "不存在虚假记载、误导性陈述或重大遗漏，并承担个别和连带的法律责任。",
        "",
        f"公司{COMPANY['year']}年度财务报告已经中正会计师事务所（特殊普通合伙）审计，",
        "并出具了标准无保留意见的审计报告。",
        "",
        "本年度报告涉及未来计划等前瞻性陈述，不构成公司对投资者的实质承诺，投资者及相关人士",
        "均应当对此保持足够的风险认识，并且应当理解计划、预测与承诺之间的差异。",
        "",
        f"公司经本次董事会审议通过的利润分配预案为：以{COMPANY['year']}年12月31日总股本",
        "1,000,000,000股为基数，向全体股东每10股派发现金红利1.50元（含税），送红股0股（含税），",
        "不以公积金转增股本。",
    ])
    pdf.separator()
    pdf.body_text("释义：本报告中，除非文义另有所指，下列词语具有如下含义：")
    pdf.body_lines([
        "  本公司/公司/中鼎智造：指中鼎智能制造股份有限公司",
        "  报告期：指2023年1月1日至2023年12月31日",
        "  元/万元/亿元：指人民币元/万元/亿元",
        "  中国证监会：指中国证券监督管理委员会",
        "  上交所：指上海证券交易所",
        "  LAS：指Layout Analysis System（版面分析系统）",
    ])

    # ---- 第二节：主要财务指标 ----
    pdf.add_page()
    pdf.section_title("第二节  公司简介和主要财务指标")
    pdf.body_text("一、主要会计数据和财务指标")

    pdf.bordered_table(
        ["指标", f"{COMPANY['year']}年", f"{COMPANY['prev_year']}年", "同比增减(%)"],
        [
            ["营业收入（元）", _fmt(REVENUE), _fmt(REVENUE_PREV), f"{(REVENUE/REVENUE_PREV-1)*100:.2f}"],
            ["归属于上市公司股东的净利润（元）", _fmt(NET_PROFIT), _fmt(NET_PROFIT_PREV),
             f"{(NET_PROFIT/NET_PROFIT_PREV-1)*100:.2f}"],
            ["扣除非经常性损益的净利润（元）", _fmt(NET_PROFIT*0.92), _fmt(NET_PROFIT_PREV*0.91),
             f"{((NET_PROFIT*0.92)/(NET_PROFIT_PREV*0.91)-1)*100:.2f}"],
            ["经营活动产生的现金流量净额（元）", _fmt(CF_OPERATING), _fmt(CF_OPERATING_PREV),
             f"{(CF_OPERATING/CF_OPERATING_PREV-1)*100:.2f}"],
            ["基本每股收益（元/股）", f"{NET_PROFIT/1e9:.2f}", f"{NET_PROFIT_PREV/1e9:.2f}",
             f"{(NET_PROFIT/NET_PROFIT_PREV-1)*100:.2f}"],
            ["稀释每股收益（元/股）", f"{NET_PROFIT/1e9:.2f}", f"{NET_PROFIT_PREV/1e9:.2f}",
             f"{(NET_PROFIT/NET_PROFIT_PREV-1)*100:.2f}"],
            ["加权平均净资产收益率(%)", f"{NET_PROFIT/EQUITY*100:.2f}",
             f"{NET_PROFIT_PREV/(TA_PREV-TL_PREV)*100:.2f}",
             f"{(NET_PROFIT/EQUITY/(NET_PROFIT_PREV/(TA_PREV-TL_PREV))-1)*100:.2f}"],
            [f"{COMPANY['year']}年末总资产（元）", _fmt(TA), _fmt(TA_PREV),
             f"{(TA/TA_PREV-1)*100:.2f}"],
        ],
        [60, 44, 44, 30], fontsize=8,
    )

    # ---- 第三节：管理层讨论与分析 ----
    pdf.add_page()
    pdf.section_title("第三节  管理层讨论与分析")
    pdf.body_text("一、经营情况讨论与分析")
    pdf.body_lines([
        f"报告期内，公司实现营业收入{_fmt(REVENUE)}元，较上年同期增长{(REVENUE/REVENUE_PREV-1)*100:.2f}%；",
        f"实现归属于上市公司股东的净利润{_fmt(NET_PROFIT)}元，较上年同期增长{(NET_PROFIT/NET_PROFIT_PREV-1)*100:.2f}%。",
        "",
        "公司坚持'创新驱动、质量为先'的发展战略，持续加大研发投入。报告期内研发费用为",
        f"{_fmt(RD_EXP)}元，占营业收入的{RD_EXP/REVENUE*100:.2f}%。公司新获得专利授权",
        "87项，其中发明专利32项，累计拥有有效专利586项。",
        "",
        "在智能制造装备领域，公司完成了新一代智能工厂解决方案的研发和试点应用，",
        "在汽车零部件、3C电子和新能源行业取得了突破性进展。全年新签合同金额超过52亿元，",
        "同比增长23.6%。",
        "",
        "在国际市场方面，公司积极拓展'一带一路'沿线市场，全年实现境外收入",
        f"{_fmt(REVENUE*0.10)}元，占营业收入的10%。公司在东南亚、中东和非洲市场的",
        "业务布局已初步形成。",
    ])

    pdf.body_text("二、主营业务分析")
    pdf.bordered_table(
        ["产品类别", "营业收入（元）", "营业成本（元）", "毛利率(%)"],
        [
            ["智能制造装备", _fmt(REVENUE*0.45), _fmt(COST*0.42),
             f"{(REVENUE*0.45-COST*0.42)/(REVENUE*0.45)*100:.1f}"],
            ["工业机器人系统", _fmt(REVENUE*0.30), _fmt(COST*0.32),
             f"{(REVENUE*0.30-COST*0.32)/(REVENUE*0.30)*100:.1f}"],
            ["智能工厂解决方案", _fmt(REVENUE*0.15), _fmt(COST*0.16),
             f"{(REVENUE*0.15-COST*0.16)/(REVENUE*0.15)*100:.1f}"],
            ["软件及技术服务", _fmt(REVENUE*0.10), _fmt(COST*0.10),
             f"{(REVENUE*0.10-COST*0.10)/(REVENUE*0.10)*100:.1f}"],
            ["合  计", _fmt(REVENUE), _fmt(COST),
             f"{(REVENUE-COST)/REVENUE*100:.1f}"],
        ],
        [60, 44, 44, 30], fontsize=8,
    )

    # ---- 第八节：财务报告 ----
    pdf.add_page()
    pdf.section_title("第八节  财务报告")
    pdf.body_text("一、审计报告")
    pdf.body_lines([
        f"中正审字[2024]第00128号",
        "",
        f"{COMPANY['name']}全体股东：",
        "",
        f"我们审计了{COMPANY['name']}（以下简称'贵公司'）的财务报表，包括{COMPANY['year']}年12月31日",
        "的合并及母公司资产负债表，2023年度的合并及母公司利润表、合并及母公司现金流量表、",
        "合并及母公司股东权益变动表以及相关财务报表附注。",
        "",
        "我们认为，后附的财务报表在所有重大方面按照企业会计准则的规定编制，公允反映了贵公司",
        f"{COMPANY['year']}年12月31日的合并及母公司财务状况以及{COMPANY['year']}年度的合并及母公司经营成果和现金流量。",
        "",
        "中正会计师事务所（特殊普通合伙）",
        "中国注册会计师：陈文斌",
        f"中国·上海     {COMPANY['year']+1}年4月25日",
    ])

    # ---- 合并资产负债表 ----
    pdf.add_page()
    pdf.section_title("二、合并资产负债表")
    pdf.set_font("CN", "", 8)
    pdf.cell(0, 5, f"编制单位：{COMPANY['name']}    单位：元    币种：人民币",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    bs_h = ["项    目", "附注", f"{COMPANY['year']}年12月31日", f"{COMPANY['prev_year']}年12月31日"]
    bs_w = [68, 18, 44, 44]

    # --- 资产部分 ---
    bs_rows_asset = []
    def add_sec(title):
        bs_rows_asset.append([f"  {title}", "", "", ""])
    def add_item(name, v, pv, n=""):
        bs_rows_asset.append([f"    {name}", n, _fmt(v), _fmt(pv)])

    add_sec("流动资产：")
    add_item("货币资金", BS_CA["货币资金"][0], BS_CA["货币资金"][1])
    add_item("交易性金融资产", BS_CA["交易性金融资产"][0], BS_CA["交易性金融资产"][1])
    add_item("应收票据", BS_CA["应收票据"][0], BS_CA["应收票据"][1])
    add_item("应收账款", BS_CA["应收账款"][0], BS_CA["应收账款"][1])
    add_item("预付款项", BS_CA["预付款项"][0], BS_CA["预付款项"][1])
    add_item("其他应收款", BS_CA["其他应收款"][0], BS_CA["其他应收款"][1])
    add_item("存货", BS_CA["存货"][0], BS_CA["存货"][1])
    add_item("合同资产", BS_CA["合同资产"][0], BS_CA["合同资产"][1])
    add_item("其他流动资产", BS_CA["其他流动资产"][0], BS_CA["其他流动资产"][1])
    add_item("流动资产合计", CA, CA_PREV)

    add_sec("非流动资产：")
    add_item("长期股权投资", BS_NCA["长期股权投资"][0], BS_NCA["长期股权投资"][1])
    add_item("其他权益工具投资", BS_NCA["其他权益工具投资"][0], BS_NCA["其他权益工具投资"][1])
    add_item("固定资产", BS_NCA["固定资产"][0], BS_NCA["固定资产"][1])
    add_item("在建工程", BS_NCA["在建工程"][0], BS_NCA["在建工程"][1])
    add_item("使用权资产", BS_NCA["使用权资产"][0], BS_NCA["使用权资产"][1])
    add_item("无形资产", BS_NCA["无形资产"][0], BS_NCA["无形资产"][1])
    add_item("开发支出", BS_NCA["开发支出"][0], BS_NCA["开发支出"][1])
    add_item("商誉", BS_NCA["商誉"][0], BS_NCA["商誉"][1])
    add_item("递延所得税资产", BS_NCA["递延所得税资产"][0], BS_NCA["递延所得税资产"][1])
    add_item("非流动资产合计", NCA, NCA_PREV)
    add_item("资产总计", TA, TA_PREV)

    pdf.bordered_table(bs_h, bs_rows_asset, bs_w, fontsize=7.5)

    # --- 负债及权益部分（新页）---
    pdf.add_page()
    pdf.section_title("合并资产负债表（续）")
    pdf.set_font("CN", "", 8)
    pdf.cell(0, 5, f"编制单位：{COMPANY['name']}    单位：元    币种：人民币",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    bs_rows_liab = []
    add_sec2 = lambda t: bs_rows_liab.append([f"  {t}", "", "", ""])

    add_sec2("流动负债：")
    add_item("短期借款", BS_CL["短期借款"][0], BS_CL["短期借款"][1])
    add_item("应付票据", BS_CL["应付票据"][0], BS_CL["应付票据"][1])
    add_item("应付账款", BS_CL["应付账款"][0], BS_CL["应付账款"][1])
    add_item("合同负债", BS_CL["合同负债"][0], BS_CL["合同负债"][1])
    add_item("应付职工薪酬", BS_CL["应付职工薪酬"][0], BS_CL["应付职工薪酬"][1])
    add_item("应交税费", BS_CL["应交税费"][0], BS_CL["应交税费"][1])
    add_item("其他应付款", BS_CL["其他应付款"][0], BS_CL["其他应付款"][1])
    add_item("一年内到期的非流动负债", BS_CL["一年内到期的非流动负债"][0], BS_CL["一年内到期的非流动负债"][1])
    add_item("流动负债合计", CL, CL_PREV)

    add_sec2("非流动负债：")
    add_item("长期借款", BS_NCL["长期借款"][0], BS_NCL["长期借款"][1])
    add_item("应付债券", BS_NCL["应付债券"][0], BS_NCL["应付债券"][1])
    add_item("租赁负债", BS_NCL["租赁负债"][0], BS_NCL["租赁负债"][1])
    add_item("长期应付款", BS_NCL["长期应付款"][0], BS_NCL["长期应付款"][1])
    add_item("递延收益", BS_NCL["递延收益"][0], BS_NCL["递延收益"][1])
    add_item("递延所得税负债", BS_NCL["递延所得税负债"][0], BS_NCL["递延所得税负债"][1])
    add_item("非流动负债合计", NCL, NCL_PREV)
    add_item("负债合计", TL, TL_PREV)

    add_sec2("所有者权益：")
    add_item("实收资本", 1_000_000_000.00, 1_000_000_000.00)
    add_item("资本公积", 500_000_000.00, 500_000_000.00)
    add_item("盈余公积", round(EQUITY*0.1, 2), round((TA_PREV-TL_PREV)*0.1, 2))
    add_item("未分配利润", round(EQUITY - 1e9 - 5e8 - EQUITY*0.1, 2),
             round((TA_PREV-TL_PREV) - 1e9 - 5e8 - (TA_PREV-TL_PREV)*0.1, 2))
    add_item("归属于母公司所有者权益合计", EQUITY, TA_PREV - TL_PREV)
    add_item("少数股东权益", 0.00, 0.00)
    add_item("所有者权益合计", EQUITY, TA_PREV - TL_PREV)
    add_item("负债和所有者权益总计", TA, TA_PREV)

    pdf.bordered_table(bs_h, bs_rows_liab, bs_w, fontsize=7.5)

    # ---- 合并利润表 ----
    pdf.add_page()
    pdf.section_title("三、合并利润表")
    pdf.set_font("CN", "", 8)
    pdf.cell(0, 5, f"编制单位：{COMPANY['name']}    单位：元    币种：人民币",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    pl_rows = [
        ["一、营业收入", "", _fmt(REVENUE), _fmt(REVENUE_PREV)],
        ["减：营业成本", "", _fmt(COST), _fmt(COST_PREV)],
        ["    税金及附加", "", _fmt(TAX_SURCHARGE), _fmt(TAX_SURCHARGE_PREV)],
        ["    销售费用", "", _fmt(SELLING_EXP), _fmt(SELLING_EXP_PREV)],
        ["    管理费用", "", _fmt(ADMIN_EXP), _fmt(ADMIN_EXP_PREV)],
        ["    研发费用", "", _fmt(RD_EXP), _fmt(RD_EXP_PREV)],
        ["    财务费用", "", _fmt(FINANCE_EXP), _fmt(FINANCE_EXP_PREV)],
        ["    其中：利息费用", "", _fmt(45_678_901.23), _fmt(38_765_432.10)],
        ["          利息收入", "", _fmt(5_678_901.23), _fmt(4_567_890.12)],
        ["加：其他收益", "", _fmt(OTHER_INCOME), _fmt(OTHER_INCOME_PREV)],
        ["    投资收益", "", _fmt(INVEST_INCOME), _fmt(INVEST_INCOME_PREV)],
        ["    信用减值损失", "", _fmt(CREDIT_LOSS), _fmt(CREDIT_LOSS_PREV)],
        ["    资产减值损失", "", _fmt(ASSET_LOSS), _fmt(ASSET_LOSS_PREV)],
        ["二、营业利润", "", _fmt(OP_PROFIT), _fmt(OP_PROFIT_PREV)],
        ["加：营业外收入", "", _fmt(NONOP_INCOME), _fmt(NONOP_INCOME_PREV)],
        ["减：营业外支出", "", _fmt(NONOP_EXPENSE), _fmt(NONOP_EXPENSE_PREV)],
        ["三、利润总额", "", _fmt(TOTAL_PROFIT), _fmt(TOTAL_PROFIT_PREV)],
        ["减：所得税费用", "", _fmt(TAX_EXPENSE), _fmt(TAX_EXPENSE_PREV)],
        ["四、净利润", "", _fmt(NET_PROFIT), _fmt(NET_PROFIT_PREV)],
        ["    归属于母公司所有者的净利润", "", _fmt(NET_PROFIT), _fmt(NET_PROFIT_PREV)],
        ["五、每股收益", "", "", ""],
        ["    基本每股收益", "", f"{NET_PROFIT/1e9:.2f}", f"{NET_PROFIT_PREV/1e9:.2f}"],
        ["    稀释每股收益", "", f"{NET_PROFIT/1e9:.2f}", f"{NET_PROFIT_PREV/1e9:.2f}"],
    ]
    pdf.bordered_table(bs_h, pl_rows, bs_w, fontsize=7.5)

    # ---- 合并现金流量表 ----
    pdf.add_page()
    pdf.section_title("四、合并现金流量表")
    pdf.set_font("CN", "", 8)
    pdf.cell(0, 5, f"编制单位：{COMPANY['name']}    单位：元    币种：人民币",
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)

    cf_h = ["项    目", f"{COMPANY['year']}年度", f"{COMPANY['prev_year']}年度"]
    cf_w = [80, 44, 44]
    cash_out_op_p = COST_PREV * 1.1 + 298_765_432.10 + TAX_EXPENSE_PREV + 85_554_442.44

    cf_rows = [
        ["一、经营活动产生的现金流量：", "", ""],
        ["  销售商品、提供劳务收到的现金", _fmt(REVENUE*1.13), _fmt(REVENUE_PREV*1.13)],
        ["  收到的税费返还", _fmt(23_456_789.01), _fmt(19_876_543.21)],
        ["  收到其他与经营活动有关的现金", _fmt(34_567_890.12), _fmt(28_765_432.10)],
        ["  经营活动现金流入小计", _fmt(cash_in_op), _fmt(cash_in_op_p)],
        ["  购买商品、接受劳务支付的现金", _fmt(COST*1.1), _fmt(COST_PREV*1.1)],
        ["  支付给职工以及为职工支付的现金", _fmt(345_678_901.23), _fmt(298_765_432.10)],
        ["  支付的各项税费", _fmt(TAX_EXPENSE+34_567_890.12), _fmt(TAX_EXPENSE_PREV+28_765_432.10)],
        ["  支付其他与经营活动有关的现金", _fmt(67_890_123.45), _fmt(56_789_012.34)],
        ["  经营活动现金流出小计", _fmt(cash_out_op), _fmt(cash_out_op_p)],
        ["  经营活动产生的现金流量净额", _fmt(CF_OPERATING), _fmt(CF_OPERATING_PREV)],
        ["二、投资活动产生的现金流量：", "", ""],
        ["  收回投资收到的现金", _fmt(234_567_890.12), _fmt(198_765_432.10)],
        ["  取得投资收益收到的现金", _fmt(5_678_901.23), _fmt(4_567_890.12)],
        ["  处置固定资产收回的现金净额", _fmt(2_345_678.90), _fmt(1_234_567.89)],
        ["  投资活动现金流入小计", _fmt(242_592_470.25), _fmt(204_567_890.11)],
        ["  购建固定资产支付的现金", _fmt(567_890_123.45), _fmt(456_789_012.34)],
        ["  投资支付的现金", _fmt(20_000_000.00), _fmt(15_000_000.00)],
        ["  投资活动现金流出小计", _fmt(587_890_123.45), _fmt(471_789_012.34)],
        ["  投资活动产生的现金流量净额", _fmt(CF_INVESTING), _fmt(CF_INVESTING_PREV)],
        ["三、筹资活动产生的现金流量：", "", ""],
        ["  取得借款收到的现金", _fmt(345_678_901.23), _fmt(298_765_432.10)],
        ["  筹资活动现金流入小计", _fmt(345_678_901.23), _fmt(298_765_432.10)],
        ["  偿还债务支付的现金", _fmt(298_765_432.10), _fmt(234_567_890.12)],
        ["  分配股利、利润或偿付利息支付的现金", _fmt(170_370_258.14), _fmt(162_962_542.08)],
        ["  筹资活动现金流出小计", _fmt(469_135_690.24), _fmt(397_530_432.20)],
        ["  筹资活动产生的现金流量净额", _fmt(CF_FINANCING), _fmt(CF_FINANCING_PREV)],
        ["四、汇率变动对现金的影响", _fmt(0.00), _fmt(0.00)],
        ["五、现金及现金等价物净增加额", _fmt(CASH_END-CASH_BEGIN), _fmt(200_000_000.00)],
        ["  加：期初现金及现金等价物余额", _fmt(CASH_BEGIN), _fmt(CASH_BEGIN_PREV)],
        ["六、期末现金及现金等价物余额", _fmt(CASH_END), _fmt(CASH_END_PREV)],
    ]
    pdf.bordered_table(cf_h, cf_rows, cf_w, fontsize=7.5)

    # ---- 财务报表附注（多页） ----
    notes = [
        ("五、合并财务报表项目附注", None, [
            "以下附注金额单位除非特别注明，均为人民币元。",
        ]),
        ("5.1 货币资金", bs_w, [
            ["项    目", "", f"{COMPANY['year']}年", f"{COMPANY['prev_year']}年"],
            ["库存现金", "", _fmt(123_456.78), _fmt(98_765.43)],
            ["银行存款", "", _fmt(856_789_012.34), _fmt(723_456_789.01)],
            ["其他货币资金", "", _fmt(35_544_320.00), _fmt(32_679_013.45)],
            ["合    计", "", _fmt(BS_CA["货币资金"][0]), _fmt(BS_CA["货币资金"][1])],
        ]),
        ("5.2 应收账款", bs_w, [
            ["类    别", "", f"{COMPANY['year']}年", f"{COMPANY['prev_year']}年"],
            ["按单项计提坏账准备", "", _fmt(12_345_678.90), _fmt(10_987_654.32)],
            ["按组合计提坏账准备", "", _fmt(1_555_544_444.55), _fmt(1_223_579_235.80)],
            ["合    计", "", _fmt(BS_CA["应收账款"][0]), _fmt(BS_CA["应收账款"][1])],
        ]),
        ("5.2.1 应收账款账龄分析", bs_w, [
            ["账    龄", "", f"{COMPANY['year']}年", f"{COMPANY['prev_year']}年"],
            ["1年以内", "", _fmt(1_234_567_890.12), _fmt(987_654_321.09)],
            ["1至2年", "", _fmt(234_567_890.12), _fmt(156_789_012.34)],
            ["2至3年", "", _fmt(67_890_123.45), _fmt(45_678_901.23)],
            ["3年以上", "", _fmt(30_864_219.76), _fmt(44_444_555.46)],
            ["合    计", "", _fmt(BS_CA["应收账款"][0]), _fmt(BS_CA["应收账款"][1])],
        ]),
        ("5.3 存货", bs_w, [
            ["项    目", "", f"{COMPANY['year']}年", f"{COMPANY['prev_year']}年"],
            ["原材料", "", _fmt(234_567_890.12), _fmt(198_765_432.10)],
            ["在产品", "", _fmt(345_678_901.23), _fmt(298_765_432.10)],
            ["库存商品", "", _fmt(345_678_901.23), _fmt(312_345_678.90)],
            ["周转材料", "", _fmt(23_456_789.01), _fmt(19_876_543.21)],
            ["发出商品", "", _fmt(38_271_839.50), _fmt(46_790_124.47)],
            ["合    计", "", _fmt(BS_CA["存货"][0]), _fmt(BS_CA["存货"][1])],
        ]),
        ("5.4 固定资产", bs_w, [
            ["类    别", "", f"{COMPANY['year']}年", f"{COMPANY['prev_year']}年"],
            ["房屋及建筑物", "", _fmt(1_358_024_679.13), _fmt(1_234_567_890.12)],
            ["机器设备", "", _fmt(762_234_679.00), _fmt(678_901_234.56)],
            ["运输工具", "", _fmt(49_012_123.56), _fmt(45_678_901.23)],
            ["电子设备", "", _fmt(97_901_235.56), _fmt(89_012_345.67)],
            ["其他设备", "", _fmt(78_506_183.98), _fmt(75_296_417.43)],
            ["合    计", "", _fmt(BS_NCA["固定资产"][0]), _fmt(BS_NCA["固定资产"][1])],
        ]),
        ("5.5 在建工程", bs_w, [
            ["项目名称", "", "期末余额", "工程进度"],
            ["智能制造基地一期", "", _fmt(358_024_679.13), "72%"],
            ["研发中心大楼", "", _fmt(134_691_246.90), "67%"],
            ["智慧物流系统", "", _fmt(46_913_569.02), "59%"],
            ["其他零星工程", "", _fmt(28_260_628.40), "—"],
            ["合    计", "", _fmt(BS_NCA["在建工程"][0]), "—"],
        ]),
        ("5.6 短期借款", bs_w, [
            ["借款类别", "", "期末余额", "利率区间"],
            ["信用借款", "", _fmt(234_567_890.12), "3.20%-3.85%"],
            ["保证借款", "", _fmt(123_456_789.01), "3.45%-4.15%"],
            ["抵押借款", "", _fmt(56_789_012.34), "3.65%-4.35%"],
            ["质押借款", "", _fmt(41_975_320.87), "3.55%-4.05%"],
            ["合    计", "", _fmt(BS_CL["短期借款"][0]), "—"],
        ]),
        ("5.7 应付账款", bs_w, [
            ["账    龄", "", f"{COMPANY['year']}年", f"{COMPANY['prev_year']}年"],
            ["1年以内", "", _fmt(789_012_345.67), _fmt(678_901_234.56)],
            ["1至2年", "", _fmt(123_456_789.01), _fmt(98_765_432.10)],
            ["2至3年", "", _fmt(45_678_901.23), _fmt(56_789_012.34)],
            ["3年以上", "", _fmt(29_506_285.18), _fmt(42_087_531.98)],
            ["合    计", "", _fmt(BS_CL["应付账款"][0]), _fmt(BS_CL["应付账款"][1])],
        ]),
    ]

    for title, widths, rows in notes:
        pdf.add_page()
        pdf.section_title(title, level=2)
        if isinstance(rows, list) and len(rows) > 0:
            if isinstance(rows[0], list):
                pdf.bordered_table(rows[0], rows[1:], widths, fontsize=8)
            elif isinstance(rows[0], str):
                pdf.body_lines(rows)

    # ---- 填充剩余附注（保证 ~55+ 页）----
    filler_topics = [
        "研发费用明细", "销售费用明细", "管理费用明细",
        "财务费用明细", "其他收益", "投资收益",
        "公允价值变动损益", "信用减值损失",
        "所有权或使用权受到限制的资产",
        "政府补助", "所得税费用", "每股收益",
        "现金流量表补充资料", "关联方关系及其交易",
        "合并范围的变更", "在其他主体中的权益",
        "金融工具及其风险", "公允价值的披露",
        "资本管理", "股份支付",
    ]
    for fi, topic in enumerate(filler_topics):
        pdf.add_page()
        pdf.section_title(f"附注{len(notes)+fi+6}：{topic}", level=2)
        pdf.body_lines([
            f"本附注披露了{COMPANY['name']}截至{COMPANY['year']}年12月31日{topic}的相关信息。",
            "",
            "根据企业会计准则的相关规定，公司管理层对上述项目进行了审慎的评估与计量。",
            f"截至{COMPANY['year']}年12月31日，相关项目和金额已按照企业会计准则的要求进行确认",
            "和计量，在所有重大方面公允反映了公司的财务状况和经营成果。",
            "",
            "公司持续监控相关风险，并采取适当的风险管理措施。报告期内，未发生对财务报表",
            "产生重大影响的异常事项。",
        ])
        # 每个附注加一个简单数据表
        pdf.ln(3)
        pdf.bordered_table(
            ["项    目", "本期发生额", "上期发生额"],
            [
                [f"{topic}—总额", _fmt(12_345_678.90 * (fi+1)), _fmt(10_987_654.32 * (fi+1))],
                ["其中：经常性", _fmt(8_765_432.10 * (fi+1)), _fmt(7_654_321.09 * (fi+1))],
                ["      非经常性", _fmt(3_580_246.80 * (fi+1)), _fmt(3_333_333.23 * (fi+1))],
            ],
            [60, 44, 44], fontsize=8,
        )

    # ---- 末页 ----
    pdf.add_page()
    pdf.ln(120)
    pdf.set_font("CN", "", 12)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 10, "（此页无正文，为年度报告签署页）", align="C")

    # 保存
    pdf_path = OUT_DIR / "SYNTH_001.pdf"
    pdf.output(str(pdf_path))
    actual_pages = pdf.page_no()
    print(f"PDF saved: {pdf_path} ({os.path.getsize(pdf_path)/1024:.0f} KB, {actual_pages} pages)")
    return actual_pages
    return actual_pages


# ============================================================================
# 4. 生成 XBRL Ground Truth（与 PDF 完全一致）
# ============================================================================

def build_xbrl_json():
    """GT 数据与 PDF 中的数值保持 100% 一致。"""

    # ---- XBRL 三张表 Markdown ----
    xbrl_table = f"""# 利润表
| 项目 | 2023年12月31日 | 2022年12月31日 |
|------|-------------|-------------|
| 营业收入 | {REVENUE:.2f} | {REVENUE_PREV:.2f} |
| 营业成本 | {COST:.2f} | {COST_PREV:.2f} |
| 税金及附加 | {TAX_SURCHARGE:.2f} | {TAX_SURCHARGE_PREV:.2f} |
| 销售费用 | {SELLING_EXP:.2f} | {SELLING_EXP_PREV:.2f} |
| 管理费用 | {ADMIN_EXP:.2f} | {ADMIN_EXP_PREV:.2f} |
| 研发费用 | {RD_EXP:.2f} | {RD_EXP_PREV:.2f} |
| 财务费用 | {FINANCE_EXP:.2f} | {FINANCE_EXP_PREV:.2f} |
| 其他收益 | {OTHER_INCOME:.2f} | {OTHER_INCOME_PREV:.2f} |
| 投资收益 | {INVEST_INCOME:.2f} | {INVEST_INCOME_PREV:.2f} |
| 信用减值损失 | {CREDIT_LOSS:.2f} | {CREDIT_LOSS_PREV:.2f} |
| 资产减值损失 | {ASSET_LOSS:.2f} | {ASSET_LOSS_PREV:.2f} |
| 营业利润 | {OP_PROFIT:.2f} | {OP_PROFIT_PREV:.2f} |
| 营业外收入 | {NONOP_INCOME:.2f} | {NONOP_INCOME_PREV:.2f} |
| 营业外支出 | {NONOP_EXPENSE:.2f} | {NONOP_EXPENSE_PREV:.2f} |
| 利润总额 | {TOTAL_PROFIT:.2f} | {TOTAL_PROFIT_PREV:.2f} |
| 所得税费用 | {TAX_EXPENSE:.2f} | {TAX_EXPENSE_PREV:.2f} |
| 净利润 | {NET_PROFIT:.2f} | {NET_PROFIT_PREV:.2f} |

# 资产负债表
| 项目 | 2023年12月31日 | 2022年12月31日 |
|------|-------------|-------------|
| 货币资金 | {BS_CA["货币资金"][0]:.2f} | {BS_CA["货币资金"][1]:.2f} |
| 交易性金融资产 | {BS_CA["交易性金融资产"][0]:.2f} | {BS_CA["交易性金融资产"][1]:.2f} |
| 应收票据 | {BS_CA["应收票据"][0]:.2f} | {BS_CA["应收票据"][1]:.2f} |
| 应收账款 | {BS_CA["应收账款"][0]:.2f} | {BS_CA["应收账款"][1]:.2f} |
| 预付款项 | {BS_CA["预付款项"][0]:.2f} | {BS_CA["预付款项"][1]:.2f} |
| 其他应收款 | {BS_CA["其他应收款"][0]:.2f} | {BS_CA["其他应收款"][1]:.2f} |
| 存货 | {BS_CA["存货"][0]:.2f} | {BS_CA["存货"][1]:.2f} |
| 合同资产 | {BS_CA["合同资产"][0]:.2f} | {BS_CA["合同资产"][1]:.2f} |
| 其他流动资产 | {BS_CA["其他流动资产"][0]:.2f} | {BS_CA["其他流动资产"][1]:.2f} |
| 流动资产合计 | {CA:.2f} | {CA_PREV:.2f} |
| 长期股权投资 | {BS_NCA["长期股权投资"][0]:.2f} | {BS_NCA["长期股权投资"][1]:.2f} |
| 其他权益工具投资 | {BS_NCA["其他权益工具投资"][0]:.2f} | {BS_NCA["其他权益工具投资"][1]:.2f} |
| 固定资产 | {BS_NCA["固定资产"][0]:.2f} | {BS_NCA["固定资产"][1]:.2f} |
| 在建工程 | {BS_NCA["在建工程"][0]:.2f} | {BS_NCA["在建工程"][1]:.2f} |
| 使用权资产 | {BS_NCA["使用权资产"][0]:.2f} | {BS_NCA["使用权资产"][1]:.2f} |
| 无形资产 | {BS_NCA["无形资产"][0]:.2f} | {BS_NCA["无形资产"][1]:.2f} |
| 开发支出 | {BS_NCA["开发支出"][0]:.2f} | {BS_NCA["开发支出"][1]:.2f} |
| 商誉 | {BS_NCA["商誉"][0]:.2f} | {BS_NCA["商誉"][1]:.2f} |
| 递延所得税资产 | {BS_NCA["递延所得税资产"][0]:.2f} | {BS_NCA["递延所得税资产"][1]:.2f} |
| 非流动资产合计 | {NCA:.2f} | {NCA_PREV:.2f} |
| 资产总计 | {TA:.2f} | {TA_PREV:.2f} |
| 短期借款 | {BS_CL["短期借款"][0]:.2f} | {BS_CL["短期借款"][1]:.2f} |
| 应付票据 | {BS_CL["应付票据"][0]:.2f} | {BS_CL["应付票据"][1]:.2f} |
| 应付账款 | {BS_CL["应付账款"][0]:.2f} | {BS_CL["应付账款"][1]:.2f} |
| 合同负债 | {BS_CL["合同负债"][0]:.2f} | {BS_CL["合同负债"][1]:.2f} |
| 应付职工薪酬 | {BS_CL["应付职工薪酬"][0]:.2f} | {BS_CL["应付职工薪酬"][1]:.2f} |
| 应交税费 | {BS_CL["应交税费"][0]:.2f} | {BS_CL["应交税费"][1]:.2f} |
| 其他应付款 | {BS_CL["其他应付款"][0]:.2f} | {BS_CL["其他应付款"][1]:.2f} |
| 一年内到期的非流动负债 | {BS_CL["一年内到期的非流动负债"][0]:.2f} | {BS_CL["一年内到期的非流动负债"][1]:.2f} |
| 流动负债合计 | {CL:.2f} | {CL_PREV:.2f} |
| 长期借款 | {BS_NCL["长期借款"][0]:.2f} | {BS_NCL["长期借款"][1]:.2f} |
| 应付债券 | {BS_NCL["应付债券"][0]:.2f} | {BS_NCL["应付债券"][1]:.2f} |
| 租赁负债 | {BS_NCL["租赁负债"][0]:.2f} | {BS_NCL["租赁负债"][1]:.2f} |
| 长期应付款 | {BS_NCL["长期应付款"][0]:.2f} | {BS_NCL["长期应付款"][1]:.2f} |
| 递延收益 | {BS_NCL["递延收益"][0]:.2f} | {BS_NCL["递延收益"][1]:.2f} |
| 递延所得税负债 | {BS_NCL["递延所得税负债"][0]:.2f} | {BS_NCL["递延所得税负债"][1]:.2f} |
| 非流动负债合计 | {NCL:.2f} | {NCL_PREV:.2f} |
| 负债合计 | {TL:.2f} | {TL_PREV:.2f} |
| 实收资本 | 1000000000.00 | 1000000000.00 |
| 资本公积 | 500000000.00 | 500000000.00 |
| 盈余公积 | {EQUITY*0.1:.2f} | {(TA_PREV-TL_PREV)*0.1:.2f} |
| 未分配利润 | {EQUITY - 1e9 - 5e8 - EQUITY*0.1:.2f} | {(TA_PREV-TL_PREV) - 1e9 - 5e8 - (TA_PREV-TL_PREV)*0.1:.2f} |
| 归属于母公司所有者权益合计 | {EQUITY:.2f} | {TA_PREV - TL_PREV:.2f} |
| 所有者权益合计 | {EQUITY:.2f} | {TA_PREV - TL_PREV:.2f} |

# 现金流量表
| 项目 | 2023年12月31日 | 2022年12月31日 |
|------|-------------|-------------|
| 销售商品、提供劳务收到的现金 | {REVENUE*1.13:.2f} | {REVENUE_PREV*1.13:.2f} |
| 经营活动现金流入小计 | {cash_in_op:.2f} | {cash_in_op_p:.2f} |
| 购买商品、接受劳务支付的现金 | {COST*1.1:.2f} | {COST_PREV*1.1:.2f} |
| 经营活动现金流出小计 | {cash_out_op:.2f} | {cash_out_op_p:.2f} |
| 经营活动产生的现金流量净额 | {CF_OPERATING:.2f} | {CF_OPERATING_PREV:.2f} |
| 投资活动产生的现金流量净额 | {CF_INVESTING:.2f} | {CF_INVESTING_PREV:.2f} |
| 筹资活动产生的现金流量净额 | {CF_FINANCING:.2f} | {CF_FINANCING_PREV:.2f} |
| 现金及现金等价物净增加额 | {CASH_END-CASH_BEGIN:.2f} | 200000000.00 |
| 期初现金及现金等价物余额 | {CASH_BEGIN:.2f} | {CASH_BEGIN_PREV:.2f} |
| 期末现金及现金等价物余额 | {CASH_END:.2f} | {CASH_END_PREV:.2f} |
"""

    # ---- 13 个下游任务 ----
    instances = [
        {
            "task_id": "synth_fact_1",
            "task": f"提取公司合并财务报表中2022和2023的营业收入、营业成本、净利润、经营活动产生的现金流量净额的数据。以一个markdown格式的表格输出，列为项目,2022,2023",
            "ground_truth": f"| 项目 | 2022 | 2023 |\n|----|----|----|\n| 营业收入 | {REVENUE_PREV:.2f} | {REVENUE:.2f} |\n| 营业成本 | {COST_PREV:.2f} | {COST:.2f} |\n| 净利润 | {NET_PROFIT_PREV:.2f} | {NET_PROFIT:.2f} |\n| 经营活动产生的现金流量净额 | {CF_OPERATING_PREV:.2f} | {CF_OPERATING:.2f} |",
            "task_type": "fact", "task_num": 1,
            "company": COMPANY['name'], "company_code": f"{COMPANY['code']}.SH",
        },
        {
            "task_id": "synth_fact_2",
            "task": f"提取公司合并财务报表中2022和2023的资产总计、负债合计、所有者权益合计的数据。以一个markdown格式的表格输出，列为项目,2022,2023",
            "ground_truth": f"| 项目 | 2022 | 2023 |\n|----|----|----|\n| 资产总计 | {TA_PREV:.2f} | {TA:.2f} |\n| 负债合计 | {TL_PREV:.2f} | {TL:.2f} |\n| 所有者权益合计 | {TA_PREV-TL_PREV:.2f} | {EQUITY:.2f} |",
            "task_type": "fact", "task_num": 2,
            "company": COMPANY['name'], "company_code": f"{COMPANY['code']}.SH",
        },
        {
            "task_id": "synth_fact_3",
            "task": f"提取公司合并财务报表中2022和2023的货币资金、应收账款、存货、固定资产、短期借款、应付账款的数据。以一个markdown格式的表格输出，列为项目,2022,2023",
            "ground_truth": f"| 项目 | 2022 | 2023 |\n|----|----|----|\n| 货币资金 | {BS_CA['货币资金'][1]:.2f} | {BS_CA['货币资金'][0]:.2f} |\n| 应收账款 | {BS_CA['应收账款'][1]:.2f} | {BS_CA['应收账款'][0]:.2f} |\n| 存货 | {BS_CA['存货'][1]:.2f} | {BS_CA['存货'][0]:.2f} |\n| 固定资产 | {BS_NCA['固定资产'][1]:.2f} | {BS_NCA['固定资产'][0]:.2f} |\n| 短期借款 | {BS_CL['短期借款'][1]:.2f} | {BS_CL['短期借款'][0]:.2f} |\n| 应付账款 | {BS_CL['应付账款'][1]:.2f} | {BS_CL['应付账款'][0]:.2f} |",
            "task_type": "fact", "task_num": 4,
            "company": COMPANY['name'], "company_code": f"{COMPANY['code']}.SH",
        },
        {
            "task_id": "synth_fact_4",
            "task": f"提取公司合并财务报表中2022和2023的研发费用、销售费用、管理费用、财务费用、投资收益、营业外收入的数据。以一个markdown格式的表格输出，列为项目,2022,2023",
            "ground_truth": f"| 项目 | 2022 | 2023 |\n|----|----|----|\n| 研发费用 | {RD_EXP_PREV:.2f} | {RD_EXP:.2f} |\n| 销售费用 | {SELLING_EXP_PREV:.2f} | {SELLING_EXP:.2f} |\n| 管理费用 | {ADMIN_EXP_PREV:.2f} | {ADMIN_EXP:.2f} |\n| 财务费用 | {FINANCE_EXP_PREV:.2f} | {FINANCE_EXP:.2f} |\n| 投资收益 | {INVEST_INCOME_PREV:.2f} | {INVEST_INCOME:.2f} |\n| 营业外收入 | {NONOP_INCOME_PREV:.2f} | {NONOP_INCOME:.2f} |",
            "task_type": "fact", "task_num": 8,
            "company": COMPANY['name'], "company_code": f"{COMPANY['code']}.SH",
        },
        {
            "task_id": "synth_fact_5",
            "task": f"提取公司合并财务报表中2022和2023的流动资产合计、非流动资产合计、流动负债合计、非流动负债合计的数据。以一个markdown格式的表格输出，列为项目,2022,2023",
            "ground_truth": f"| 项目 | 2022 | 2023 |\n|----|----|----|\n| 流动资产合计 | {CA_PREV:.2f} | {CA:.2f} |\n| 非流动资产合计 | {NCA_PREV:.2f} | {NCA:.2f} |\n| 流动负债合计 | {CL_PREV:.2f} | {CL:.2f} |\n| 非流动负债合计 | {NCL_PREV:.2f} | {NCL:.2f} |",
            "task_type": "fact", "task_num": 16,
            "company": COMPANY['name'], "company_code": f"{COMPANY['code']}.SH",
        },
        {
            "task_id": "synth_fact_6",
            "task": f"提取公司合并财务报表中2022和2023的长期股权投资、在建工程、无形资产、商誉、长期借款、应付债券的数据。以一个markdown格式的表格输出，列为项目,2022,2023",
            "ground_truth": f"| 项目 | 2022 | 2023 |\n|----|----|----|\n| 长期股权投资 | {BS_NCA['长期股权投资'][1]:.2f} | {BS_NCA['长期股权投资'][0]:.2f} |\n| 在建工程 | {BS_NCA['在建工程'][1]:.2f} | {BS_NCA['在建工程'][0]:.2f} |\n| 无形资产 | {BS_NCA['无形资产'][1]:.2f} | {BS_NCA['无形资产'][0]:.2f} |\n| 商誉 | {BS_NCA['商誉'][1]:.2f} | {BS_NCA['商誉'][0]:.2f} |\n| 长期借款 | {BS_NCL['长期借款'][1]:.2f} | {BS_NCL['长期借款'][0]:.2f} |\n| 应付债券 | {BS_NCL['应付债券'][1]:.2f} | {BS_NCL['应付债券'][0]:.2f} |",
            "task_type": "fact", "task_num": 32,
            "company": COMPANY['name'], "company_code": f"{COMPANY['code']}.SH",
        },
        # indicator (6)
        {
            "task_id": "synth_ind_1",
            "task": f"计算公式合并财务报表中2023年度的销售毛利率、净利率、总资产收益率（ROA）、净资产收益率（ROE）的数据。以一个markdown格式的表格输出，列为项目,2023，结果表示为小数并保留4位小数",
            "ground_truth": f"| 项目 | 2023 |\n|----|----|\n| 销售毛利率 | {(REVENUE-COST)/REVENUE:.4f} |\n| 净利率 | {NET_PROFIT/REVENUE:.4f} |\n| 总资产收益率(ROA) | {NET_PROFIT/TA:.4f} |\n| 净资产收益率(ROE) | {NET_PROFIT/EQUITY:.4f} |",
            "task_type": "indicator", "task_num": 1,
            "company": COMPANY['name'], "company_code": f"{COMPANY['code']}.SH",
        },
        {
            "task_id": "synth_ind_2",
            "task": f"计算公式合并财务报表中2023年度的资产负债率、流动比率、速动比率的数据。以一个markdown格式的表格输出，列为项目,2023，结果表示为小数并保留4位小数",
            "ground_truth": f"| 项目 | 2023 |\n|----|----|\n| 资产负债率 | {TL/TA:.4f} |\n| 流动比率 | {CA/CL:.4f} |\n| 速动比率 | {(CA-BS_CA['存货'][0])/CL:.4f} |",
            "task_type": "indicator", "task_num": 2,
            "company": COMPANY['name'], "company_code": f"{COMPANY['code']}.SH",
        },
        {
            "task_id": "synth_ind_3",
            "task": f"计算公式合并财务报表中2023年度的应收账款周转率、存货周转率、总资产周转率的数据。以一个markdown格式的表格输出，列为项目,2023，结果表示为小数并保留4位小数",
            "ground_truth": f"| 项目 | 2023 |\n|----|----|\n| 应收账款周转率 | {REVENUE/((BS_CA['应收账款'][0]+BS_CA['应收账款'][1])/2):.4f} |\n| 存货周转率 | {COST/((BS_CA['存货'][0]+BS_CA['存货'][1])/2):.4f} |\n| 总资产周转率 | {REVENUE/((TA+TA_PREV)/2):.4f} |",
            "task_type": "indicator", "task_num": 4,
            "company": COMPANY['name'], "company_code": f"{COMPANY['code']}.SH",
        },
        {
            "task_id": "synth_ind_4",
            "task": f"计算公式合并财务报表中2023年度的期间费用率（含销售费用、管理费用、研发费用、财务费用占营业收入比例）的数据。以一个markdown格式的表格输出，列为项目,2023，结果表示为小数并保留4位小数",
            "ground_truth": f"| 项目 | 2023 |\n|----|----|\n| 期间费用率 | {(SELLING_EXP+ADMIN_EXP+RD_EXP+FINANCE_EXP)/REVENUE:.4f} |\n| 销售费用率 | {SELLING_EXP/REVENUE:.4f} |\n| 管理费用率 | {ADMIN_EXP/REVENUE:.4f} |\n| 研发费用率 | {RD_EXP/REVENUE:.4f} |",
            "task_type": "indicator", "task_num": 8,
            "company": COMPANY['name'], "company_code": f"{COMPANY['code']}.SH",
        },
        {
            "task_id": "synth_ind_5",
            "task": f"计算公式合并财务报表中2023年度的非流动资产占总资产比例、营业收入增长率、净利润增长率的数据。以一个markdown格式的表格输出，列为项目,2023，结果表示为小数并保留4位小数",
            "ground_truth": f"| 项目 | 2023 |\n|----|----|\n| 非流动资产占总资产比例 | {NCA/TA:.4f} |\n| 营业收入增长率 | {REVENUE/REVENUE_PREV-1:.4f} |\n| 净利润增长率 | {NET_PROFIT/NET_PROFIT_PREV-1:.4f} |",
            "task_type": "indicator", "task_num": 16,
            "company": COMPANY['name'], "company_code": f"{COMPANY['code']}.SH",
        },
        {
            "task_id": "synth_ind_6",
            "task": f"计算公式合并财务报表中2023年度的现金比率、权益乘数、经营活动现金流与净利润比率的数据。以一个markdown格式的表格输出，列为项目,2023，结果表示为小数并保留4位小数",
            "ground_truth": f"| 项目 | 2023 |\n|----|----|\n| 现金比率 | {BS_CA['货币资金'][0]/CL:.4f} |\n| 权益乘数 | {TA/EQUITY:.4f} |\n| 经营活动现金流与净利润比率 | {CF_OPERATING/NET_PROFIT:.4f} |",
            "task_type": "indicator", "task_num": 32,
            "company": COMPANY['name'], "company_code": f"{COMPANY['code']}.SH",
        },
        # reasoning (1)
        {
            "task_id": "synth_reas_1",
            "task": f"根据给定的判断条件和公司的合并财务报表数据，回答问题: 1. 判断公司{COMPANY['year']}年的财务状况是否满足以下条件。以一个markdown格式的表格输出，列为序号,是否满足",
            "ground_truth": "| 序号 | 是否满足 |\n|----|----|\n| 0 | 1 |\n| 1 | 0 |\n| 2 | 1 |\n| 3 | 1 |\n| 4 | 0 |\n| 5 | 1 |\n| 6 | 0 |\n| 7 | 1 |\n| 8 | 0 |\n| 9 | 0 |\n| 10 | 0 |\n| 11 | 1 |",
            "conditions": f"| 序号 | 条件 |\n|----|----|\n| 0 | 营业收入增长率大于10% |\n| 1 | 净利润相比上年下降 |\n| 2 | 资产负债率小于50% |\n| 3 | 流动比率大于1.5 |\n| 4 | 经营活动现金流净额小于净利润 |\n| 5 | ROE大于5% |\n| 6 | 研发费用占营业收入比例大于30% |\n| 7 | 期间费用率小于30% |\n| 8 | 存货周转率小于1 |\n| 9 | 现金比率大于1 |\n| 10 | 应收账款占总资产比例大于40% |\n| 11 | 毛利率大于30% |",
            "task_type": "reasoning", "task_num": 64,
            "company": COMPANY['name'], "company_code": f"{COMPANY['code']}.SH",
        },
    ]

    record = {
        "table": xbrl_table,
        "instances": instances,
        "file_path": "./data/pdf_data/SYNTH_001.pdf",
    }

    xbrl_path = OUT_DIR / "SYNTH_001_xbrl.json"
    xbrl_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"XBRL GT saved: {xbrl_path}")
    print(f"Tasks: {len(instances)} (6 fact + 6 indicator + 1 reasoning)")


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    build_pdf()
    build_xbrl_json()
    print("\nDone — SYNTH_001 长文档 PDF + XBRL GT 已重新生成")
