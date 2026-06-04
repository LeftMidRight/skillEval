"""生成一份 ~100 页的超长金融年报 PDF，含 XBRL 真值和下游任务。

输出:
- data/eval_dataset/S5_long_documents/SYNTH_001.pdf
- data/eval_dataset/S5_long_documents/SYNTH_001_xbrl.json  (XBRL 真值 + 13 tasks)
"""

import json
import os
import random
from pathlib import Path

import fitz  # PyMuPDF

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_ROOT / "data" / "eval_dataset" / "S5_long_documents"
OUT_DIR.mkdir(parents=True, exist_ok=True)

random.seed(42)

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

# 资产负债表数据
BALANCE_SHEET = {
    "流动资产": {
        "货币资金": (892_456_789.12, 756_234_567.89),
        "交易性金融资产": (345_678_901.23, 298_765_432.10),
        "应收票据": (123_456_789.45, 98_765_432.10),
        "应收账款": (1_567_890_123.45, 1_234_567_890.12),
        "预付款项": (234_567_890.12, 198_765_432.10),
        "其他应收款": (89_012_345.67, 76_543_210.98),
        "存货": (987_654_321.09, 876_543_210.98),
        "合同资产": (45_678_901.23, 34_567_890.12),
        "一年内到期的非流动资产": (12_345_678.90, 10_123_456.78),
        "其他流动资产": (56_789_012.34, 45_678_901.23),
    },
    "非流动资产": {
        "长期股权投资": (345_678_901.23, 298_765_432.10),
        "其他权益工具投资": (89_012_345.67, 76_543_210.98),
        "投资性房地产": (123_456_789.45, 0),
        "固定资产": (2_345_678_901.23, 2_123_456_789.01),
        "在建工程": (567_890_123.45, 456_789_012.34),
        "使用权资产": (89_012_345.67, 76_543_210.98),
        "无形资产": (456_789_012.34, 398_765_432.10),
        "开发支出": (34_567_890.12, 28_765_432.10),
        "商誉": (123_456_789.45, 123_456_789.45),
        "长期待摊费用": (23_456_789.01, 19_876_543.21),
        "递延所得税资产": (45_678_901.23, 38_765_432.10),
        "其他非流动资产": (12_345_678.90, 10_123_456.78),
    },
    "流动负债": {
        "短期借款": (456_789_012.34, 398_765_432.10),
        "应付票据": (234_567_890.12, 198_765_432.10),
        "应付账款": (987_654_321.09, 876_543_210.98),
        "预收款项": (123_456_789.45, 98_765_432.10),
        "合同负债": (89_012_345.67, 76_543_210.98),
        "应付职工薪酬": (145_678_901.23, 134_567_890.12),
        "应交税费": (56_789_012.34, 45_678_901.23),
        "其他应付款": (67_890_123.45, 56_789_012.34),
        "一年内到期的非流动负债": (34_567_890.12, 28_765_432.10),
        "其他流动负债": (23_456_789.01, 19_876_543.21),
    },
    "非流动负债": {
        "长期借款": (567_890_123.45, 498_765_432.10),
        "应付债券": (345_678_901.23, 345_678_901.23),
        "租赁负债": (56_789_012.34, 45_678_901.23),
        "长期应付款": (34_567_890.12, 28_765_432.10),
        "递延收益": (45_678_901.23, 38_765_432.10),
        "递延所得税负债": (23_456_789.01, 19_876_543.21),
    },
}


def _sum_section(section):
    return sum(v[0] for v in section.values())


def _sum_section_prev(section):
    return sum(v[1] for v in section.values())


CA = _sum_section(BALANCE_SHEET["流动资产"])
NCA = _sum_section(BALANCE_SHEET["非流动资产"])
TA = CA + NCA
CL = _sum_section(BALANCE_SHEET["流动负债"])
NCL = _sum_section(BALANCE_SHEET["非流动负债"])
TL = CL + NCL
EQUITY = TA - TL

CA_PREV = _sum_section_prev(BALANCE_SHEET["流动资产"])
NCA_PREV = _sum_section_prev(BALANCE_SHEET["非流动资产"])
TA_PREV = CA_PREV + NCA_PREV
CL_PREV = _sum_section_prev(BALANCE_SHEET["流动负债"])
NCL_PREV = _sum_section_prev(BALANCE_SHEET["非流动负债"])
TL_PREV = CL_PREV + NCL_PREV
EQUITY_PREV = TA_PREV - TL_PREV

# 利润表
REVENUE = 3_456_789_012.34
REVENUE_PREV = 2_987_654_321.09
COST = 2_345_678_901.23
COST_PREV = 2_012_345_678.90
GROSS_PROFIT = REVENUE - COST
GROSS_PROFIT_PREV = REVENUE_PREV - COST_PREV
SELLING_EXP = 234_567_890.12
SELLING_EXP_PREV = 198_765_432.10
ADMIN_EXP = 189_012_345.67
ADMIN_EXP_PREV = 167_890_123.45
RD_EXP = 145_678_901.23
RD_EXP_PREV = 123_456_789.01
FINANCE_EXP = 56_789_012.34
FINANCE_EXP_PREV = 45_678_901.23
OP_PROFIT = GROSS_PROFIT - SELLING_EXP - ADMIN_EXP - RD_EXP - FINANCE_EXP
OP_PROFIT_PREV = GROSS_PROFIT_PREV - SELLING_EXP_PREV - ADMIN_EXP_PREV - RD_EXP_PREV - FINANCE_EXP_PREV
OTHER_INCOME = 12_345_678.90
OTHER_INCOME_PREV = 9_876_543.21
TOTAL_PROFIT = OP_PROFIT + OTHER_INCOME
TOTAL_PROFIT_PREV = OP_PROFIT_PREV + OTHER_INCOME_PREV
TAX = TOTAL_PROFIT * 0.15
TAX_PREV = TOTAL_PROFIT_PREV * 0.15
NET_PROFIT = TOTAL_PROFIT - TAX
NET_PROFIT_PREV = TOTAL_PROFIT_PREV - TAX_PREV

# 现金流量表
CF_OPERATING = 567_890_123.45
CF_OPERATING_PREV = 456_789_012.34
CF_INVESTING = -345_678_901.23
CF_INVESTING_PREV = -298_765_432.10
CF_FINANCING = -123_456_789.01
CF_FINANCING_PREV = -98_765_432.10
CASH_BEGIN = 756_234_567.89
CASH_END = CASH_BEGIN + CF_OPERATING + CF_INVESTING + CF_FINANCING


# ============================================================================
# 2. 生成 PDF
# ============================================================================

def _fmt(val):
    """格式化金额: 1,234,567.89"""
    if val == int(val):
        return f"{int(val):,}"
    return f"{val:,.2f}"


def _write_text(page, y, text, fontsize=10, x=72, bold=False, color=(0, 0, 0)):
    font = "hebo" if bold else "china-s"
    page.insert_text((x, y), text, fontname=font, fontsize=fontsize, color=color)


def _write_table(page, headers, rows, start_y, col_widths, fontsize=9):
    """在页面上绘制无边框表格。"""
    y = start_y
    x_positions = [72]
    for w in col_widths[:-1]:
        x_positions.append(x_positions[-1] + w)

    # 表头
    for ci, h in enumerate(headers):
        if ci < len(x_positions):
            _write_text(page, y, h, fontsize=fontsize, x=x_positions[ci], bold=True)
    y += 18

    # 分隔线
    page.draw_line((72, y - 4), (72 + sum(col_widths), y - 4), color=(0.6, 0.6, 0.6))

    # 数据行
    for row in rows:
        if y > 750:  # 换页
            page = _new_page(page)
            y = 100
        for ci, val in enumerate(row):
            if ci < len(x_positions):
                _write_text(page, y, str(val), fontsize=fontsize, x=x_positions[ci])
        y += 16
    y += 10
    return page, y


def _new_page(page):
    doc = page.parent
    return doc.new_page(width=595, height=842)


def _add_header_footer(page, page_num, total_pages):
    """添加页眉页脚。"""
    _write_text(page, 36, f"{COMPANY['year']} 年年度报告", fontsize=8, x=72, color=(0.4, 0.4, 0.4))
    _write_text(page, 36, f"{page_num} / {total_pages}", fontsize=8, x=500, color=(0.4, 0.4, 0.4))
    if page_num > 3:
        _write_text(page, 810, "公司负责人：张明华    主管会计工作负责人：李建国    会计机构负责人：王芳",
                    fontsize=7, x=72, color=(0.5, 0.5, 0.5))


def build_pdf():
    doc = fitz.open()
    total_pages = 98
    page_num = [0]  # mutable counter

    def next_page():
        page_num[0] += 1
        page = doc.new_page(width=595, height=842)
        _add_header_footer(page, page_num[0], total_pages)
        return page

    # ---- 封面 ----
    page = next_page()
    _write_text(page, 200, COMPANY["name"], fontsize=22, x=72, bold=True)
    _write_text(page, 240, f"{COMPANY['year']} 年年度报告", fontsize=18, x=72)
    _write_text(page, 300, f"股票代码：{COMPANY['code']}", fontsize=12, x=72)
    _write_text(page, 330, f"报告日期：{COMPANY['year']}年4月25日", fontsize=12, x=72)
    _write_text(page, 500, "本报告依据中国企业会计准则编制", fontsize=10, x=72, color=(0.4, 0.4, 0.4))

    # ---- 目录 ----
    page = next_page()
    _write_text(page, 100, "目    录", fontsize=16, x=200, bold=True)
    toc = [
        ("第一节", "重要提示及释义", 3),
        ("第二节", "公司简介和主要财务指标", 5),
        ("第三节", "管理层讨论与分析", 8),
        ("第四节", "公司治理", 15),
        ("第五节", "环境与社会责任", 18),
        ("第六节", "重要事项", 20),
        ("第七节", "股份变动及股东情况", 25),
        ("第八节", "优先股相关情况", 28),
        ("第九节", "债券相关情况", 30),
        ("第十节", "财务报告", 32),
        ("", "    — 审计报告", 32),
        ("", "    — 合并资产负债表", 34),
        ("", "    — 合并利润表", 36),
        ("", "    — 合并现金流量表", 37),
        ("", "    — 财务报表附注", 38),
    ]
    y = 140
    for section, title, p in toc:
        line = f"{section + '  ' if section else '':>8}{title}"
        line += "." * (60 - len(line)) + f" {p}"
        _write_text(page, y, line, fontsize=10, x=72)
        y += 22

    # ---- 第一节：重要提示 ----
    for _ in range(2):
        page = next_page()
        y = 100 + 700 * (page_num[0] % 2)
        _write_text(page, 80, "第一节  重要提示及释义", fontsize=14, bold=True, x=72)
        _write_text(page, 110, "本公司董事会、监事会及董事、监事、高级管理人员保证年度报告内容的真实、准确、完整，",
                    fontsize=10, x=72)
        _write_text(page, 128, "不存在虚假记载、误导性陈述或重大遗漏，并承担个别和连带的法律责任。", fontsize=10, x=72)
        _write_text(page, 160, f"公司{COMPANY['year']}年度财务报告已经中正会计师事务所（特殊普通合伙）审计，"
                    f"并出具了标准无保留意见的审计报告。", fontsize=10, x=72)

    # ---- 第二节：主要财务指标 ----
    page = next_page()
    _write_text(page, 80, "第二节  公司简介和主要财务指标", fontsize=14, bold=True, x=72)
    _write_text(page, 110, "一、主要会计数据和财务指标", fontsize=12, bold=True, x=72)

    headers = ["指标", f"{COMPANY['year']}年", f"{COMPANY['prev_year']}年", "同比增减(%)"]
    col_w = [200, 110, 110, 80]
    rows = [
        ["营业收入（元）", _fmt(REVENUE), _fmt(REVENUE_PREV), f"{(REVENUE/REVENUE_PREV-1)*100:.2f}"],
        ["归属于上市公司股东的净利润（元）", _fmt(NET_PROFIT), _fmt(NET_PROFIT_PREV), f"{(NET_PROFIT/NET_PROFIT_PREV-1)*100:.2f}"],
        ["归属于上市公司股东的扣除非经常性损益的净利润（元）", _fmt(NET_PROFIT * 0.92), _fmt(NET_PROFIT_PREV * 0.91), f"{((NET_PROFIT*0.92)/(NET_PROFIT_PREV*0.91)-1)*100:.2f}"],
        ["经营活动产生的现金流量净额（元）", _fmt(CF_OPERATING), _fmt(CF_OPERATING_PREV), f"{(CF_OPERATING/CF_OPERATING_PREV-1)*100:.2f}"],
        ["基本每股收益（元/股）", f"{NET_PROFIT/1_000_000_000:.2f}", f"{NET_PROFIT_PREV/1_000_000_000:.2f}", f"{(NET_PROFIT/NET_PROFIT_PREV-1)*100:.2f}"],
        ["稀释每股收益（元/股）", f"{NET_PROFIT/1_000_000_000:.2f}", f"{NET_PROFIT_PREV/1_000_000_000:.2f}", f"{(NET_PROFIT/NET_PROFIT_PREV-1)*100:.2f}"],
        ["加权平均净资产收益率(%)", f"{(NET_PROFIT/EQUITY)*100:.2f}", f"{(NET_PROFIT_PREV/EQUITY_PREV)*100:.2f}", f"{((NET_PROFIT/EQUITY)/(NET_PROFIT_PREV/EQUITY_PREV)-1)*100:.2f}"],
        [f"{COMPANY['year']}年末总资产（元）", _fmt(TA), _fmt(TA_PREV), f"{(TA/TA_PREV-1)*100:.2f}"],
        [f"{COMPANY['year']}年末归属于上市公司股东的净资产（元）", _fmt(EQUITY), _fmt(EQUITY_PREV), f"{(EQUITY/EQUITY_PREV-1)*100:.2f}"],
    ]
    page, _ = _write_table(page, headers, rows, 140, col_w)

    # ---- 第十节：财务报告（核心三张表）----
    page = next_page()
    _write_text(page, 80, "第十节  财务报告", fontsize=14, bold=True, x=72)
    _write_text(page, 110, "一、审计报告", fontsize=12, bold=True, x=72)
    _write_text(page, 130, "中正审字[2024]第00128号", fontsize=10, x=72)
    audit_text = [
        f"{COMPANY['name']}全体股东：",
        "",
        f"我们审计了{COMPANY['name']}（以下简称'贵公司'）的财务报表，包括{COMPANY['year']}年12月31日的",
        "合并及母公司资产负债表，2023年度的合并及母公司利润表、合并及母公司现金流量表、",
        "合并及母公司股东权益变动表以及相关财务报表附注。",
        "",
        "我们认为，后附的财务报表在所有重大方面按照企业会计准则的规定编制，公允反映了贵公司",
        f"{COMPANY['year']}年12月31日的合并及母公司财务状况以及{COMPANY['year']}年度的合并及母公司经营成果和现金流量。",
    ]
    y = 155
    for line in audit_text:
        _write_text(page, y, line, fontsize=10, x=72)
        y += 18 if line else 10

    # 合并资产负债表
    page = next_page()
    _write_text(page, 80, "二、合并资产负债表", fontsize=12, bold=True, x=72)
    _write_text(page, 98, f"编制单位：{COMPANY['name']}    单位：元    币种：人民币", fontsize=9, x=72)

    bs_headers = ["项目", "附注", f"{COMPANY['year']}年12月31日", f"{COMPANY['prev_year']}年12月31日"]
    bs_col_w = [180, 40, 120, 120]
    bs_rows = []

    def _add_section(title):
        bs_rows.append([f"    {title}", "", "", ""])

    def _add_item(name, val, prev_val, note=""):
        bs_rows.append([f"    {name}", note, _fmt(val), _fmt(prev_val)])

    _add_section("流动资产：")
    note_num = 1
    for name, (v, pv) in BALANCE_SHEET["流动资产"].items():
        _add_item(name, v, pv, str(note_num))
        note_num += 1
    _add_item("流动资产合计", CA, CA_PREV)

    _add_section("非流动资产：")
    for name, (v, pv) in BALANCE_SHEET["非流动资产"].items():
        _add_item(name, v, pv, str(note_num))
        note_num += 1
    _add_item("非流动资产合计", NCA, NCA_PREV)
    _add_item("资产总计", TA, TA_PREV)

    bs_rows.insert(0, ["", "", "", ""])  # spacer
    page, y_end = _write_table(page, bs_headers, bs_rows, 115, bs_col_w, fontsize=8)

    # 资产负债表续（负债和权益）
    bs_rows2 = []
    _add_section_l2 = lambda t: bs_rows2.append([f"    {t}", "", "", ""])
    _add_section_l2("流动负债：")
    for name, (v, pv) in BALANCE_SHEET["流动负债"].items():
        _add_item(name, v, pv, str(note_num))
        note_num += 1
    _add_item("流动负债合计", CL, CL_PREV)

    _add_section_l2("非流动负债：")
    for name, (v, pv) in BALANCE_SHEET["非流动负债"].items():
        _add_item(name, v, pv, str(note_num))
        note_num += 1
    _add_item("非流动负债合计", NCL, NCL_PREV)
    _add_item("负债合计", TL, TL_PREV)

    _add_section_l2("所有者权益：")
    _add_item("实收资本", 1_000_000_000, 1_000_000_000)
    _add_item("资本公积", 500_000_000, 500_000_000)
    _add_item("盈余公积", EQUITY * 0.1, EQUITY_PREV * 0.1)
    _add_item("未分配利润", EQUITY - 1_000_000_000 - 500_000_000 - EQUITY * 0.1,
              EQUITY_PREV - 1_000_000_000 - 500_000_000 - EQUITY_PREV * 0.1)
    _add_item("归属于母公司所有者权益合计", EQUITY, EQUITY_PREV)
    _add_item("所有者权益合计", EQUITY, EQUITY_PREV)
    _add_item("负债和所有者权益总计", TA, TA_PREV)

    page = next_page()
    _write_text(page, 80, "合并资产负债表（续）", fontsize=12, bold=True, x=72)
    page, _ = _write_table(page, bs_headers, bs_rows2, 110, bs_col_w, fontsize=8)

    # 合并利润表
    page = next_page()
    _write_text(page, 80, "三、合并利润表", fontsize=12, bold=True, x=72)
    _write_text(page, 98, f"编制单位：{COMPANY['name']}    单位：元    币种：人民币", fontsize=9, x=72)

    pl_headers = ["项目", "附注", f"{COMPANY['year']}年度", f"{COMPANY['prev_year']}年度"]
    pl_rows = [
        ["    一、营业收入", "", _fmt(REVENUE), _fmt(REVENUE_PREV)],
        ["    减：营业成本", "", _fmt(COST), _fmt(COST_PREV)],
        ["    税金及附加", "", _fmt(12_345_678.90), _fmt(10_987_654.32)],
        ["    销售费用", "", _fmt(SELLING_EXP), _fmt(SELLING_EXP_PREV)],
        ["    管理费用", "", _fmt(ADMIN_EXP), _fmt(ADMIN_EXP_PREV)],
        ["    研发费用", "", _fmt(RD_EXP), _fmt(RD_EXP_PREV)],
        ["    财务费用", "", _fmt(FINANCE_EXP), _fmt(FINANCE_EXP_PREV)],
        ["    其中：利息费用", "", _fmt(45_678_901.23), _fmt(38_765_432.10)],
        ["    利息收入", "", _fmt(5_678_901.23), _fmt(4_567_890.12)],
        ["    加：其他收益", "", _fmt(8_765_432.10), _fmt(6_543_210.98)],
        ["    投资收益", "", _fmt(3_456_789.01), _fmt(2_345_678.90)],
        ["    信用减值损失", "", _fmt(-2_345_678.90), _fmt(-1_987_654.32)],
        ["    资产减值损失", "", _fmt(-1_234_567.89), _fmt(-987_654.32)],
        ["    二、营业利润", "", _fmt(OP_PROFIT), _fmt(OP_PROFIT_PREV)],
        ["    加：营业外收入", "", _fmt(1_234_567.89), _fmt(987_654.32)],
        ["    减：营业外支出", "", _fmt(345_678.90), _fmt(234_567.89)],
        ["    三、利润总额", "", _fmt(TOTAL_PROFIT), _fmt(TOTAL_PROFIT_PREV)],
        ["    减：所得税费用", "", _fmt(TAX), _fmt(TAX_PREV)],
        ["    四、净利润", "", _fmt(NET_PROFIT), _fmt(NET_PROFIT_PREV)],
        ["    归属于母公司所有者的净利润", "", _fmt(NET_PROFIT), _fmt(NET_PROFIT_PREV)],
        ["    五、每股收益"], ["    基本每股收益", "", f"{NET_PROFIT/1_000_000_000:.2f}", f"{NET_PROFIT_PREV/1_000_000_000:.2f}"],
        ["    稀释每股收益", "", f"{NET_PROFIT/1_000_000_000:.2f}", f"{NET_PROFIT_PREV/1_000_000_000:.2f}"],
    ]
    page, _ = _write_table(page, pl_headers, pl_rows, 115, bs_col_w, fontsize=8)

    # 合并现金流量表
    page = next_page()
    _write_text(page, 80, "四、合并现金流量表", fontsize=12, bold=True, x=72)
    _write_text(page, 98, f"编制单位：{COMPANY['name']}    单位：元    币种：人民币", fontsize=9, x=72)

    cf_headers = ["项目", f"{COMPANY['year']}年度", f"{COMPANY['prev_year']}年度"]
    cf_col_w = [250, 120, 120]
    cf_rows = [
        ["一、经营活动产生的现金流量：", "", ""],
        ["    销售商品、提供劳务收到的现金", _fmt(REVENUE * 1.13), _fmt(REVENUE_PREV * 1.13)],
        ["    收到的税费返还", _fmt(23_456_789.01), _fmt(19_876_543.21)],
        ["    收到其他与经营活动有关的现金", _fmt(34_567_890.12), _fmt(28_765_432.10)],
        ["    经营活动现金流入小计", _fmt(REVENUE * 1.13 + 23_456_789.01 + 34_567_890.12), _fmt(REVENUE_PREV * 1.13 + 19_876_543.21 + 28_765_432.10)],
        ["    购买商品、接受劳务支付的现金", _fmt(COST * 1.1), _fmt(COST_PREV * 1.1)],
        ["    支付给职工以及为职工支付的现金", _fmt(345_678_901.23), _fmt(298_765_432.10)],
        ["    支付的各项税费", _fmt(TAX + 34_567_890.12), _fmt(TAX_PREV + 28_765_432.10)],
        ["    支付其他与经营活动有关的现金", _fmt(67_890_123.45), _fmt(56_789_012.34)],
        ["    经营活动现金流出小计", _fmt(COST * 1.1 + 345_678_901.23 + TAX + 34_567_890.12 + 67_890_123.45), _fmt(COST_PREV * 1.1 + 298_765_432.10 + TAX_PREV + 28_765_432.10 + 56_789_012.34)],
        ["    经营活动产生的现金流量净额", _fmt(CF_OPERATING), _fmt(CF_OPERATING_PREV)],
        ["二、投资活动产生的现金流量：", "", ""],
        ["    收回投资收到的现金", _fmt(234_567_890.12), _fmt(198_765_432.10)],
        ["    取得投资收益收到的现金", _fmt(5_678_901.23), _fmt(4_567_890.12)],
        ["    处置固定资产收回的现金净额", _fmt(2_345_678.90), _fmt(1_234_567.89)],
        ["    投资活动现金流入小计", _fmt(234_567_890.12 + 5_678_901.23 + 2_345_678.90), _fmt(198_765_432.10 + 4_567_890.12 + 1_234_567.89)],
        ["    购建固定资产支付的现金", _fmt(567_890_123.45), _fmt(456_789_012.34)],
        ["    投资支付的现金", _fmt(20_000_000), _fmt(15_000_000)],
        ["    投资活动现金流出小计", _fmt(567_890_123.45 + 20_000_000), _fmt(456_789_012.34 + 15_000_000)],
        ["    投资活动产生的现金流量净额", _fmt(CF_INVESTING), _fmt(CF_INVESTING_PREV)],
        ["三、筹资活动产生的现金流量：", "", ""],
        ["    取得借款收到的现金", _fmt(345_678_901.23), _fmt(298_765_432.10)],
        ["    筹资活动现金流入小计", _fmt(345_678_901.23), _fmt(298_765_432.10)],
        ["    偿还债务支付的现金", _fmt(298_765_432.10), _fmt(234_567_890.12)],
        ["    分配股利、利润或偿付利息支付的现金", _fmt(170_370_258.14), _fmt(162_962_542.08)],
        ["    筹资活动现金流出小计", _fmt(469_135_690.24), _fmt(397_530_432.20)],
        ["    筹资活动产生的现金流量净额", _fmt(CF_FINANCING), _fmt(CF_FINANCING_PREV)],
        ["四、汇率变动对现金的影响", _fmt(0), _fmt(0)],
        ["五、现金及现金等价物净增加额", _fmt(CASH_END - CASH_BEGIN), _fmt(CA_PREV - CASH_BEGIN + CF_OPERATING_PREV + CF_INVESTING_PREV + CF_FINANCING_PREV)],
        ["    加：期初现金及现金等价物余额", _fmt(CASH_BEGIN), _fmt(CASH_BEGIN - 200_000_000)],
        ["六、期末现金及现金等价物余额", _fmt(CASH_END), _fmt(CASH_BEGIN)],
    ]
    page, _ = _write_table(page, cf_headers, cf_rows, 115, cf_col_w, fontsize=8)

    # ---- 财务报表附注（填充到 ~98 页）----
    notes_sections = [
        ("一、公司基本情况", [
            f"{COMPANY['name']}（以下简称'本公司'或'公司'）系经XX省人民政府批准，",
            f"由XX集团有限公司联合其他发起人共同发起设立的股份有限公司。",
            f"公司于2008年5月18日在XX省市场监督管理局登记注册，",
            f"统一社会信用代码：91330000MA28XXXXXX。",
            f"公司注册资本为人民币1,000,000,000.00元。",
            f"公司注册地址：XX省XX市XX区XX路168号。",
            f"公司属于智能制造行业，主要经营范围包括：智能制造装备研发、生产和销售；",
            f"工业机器人及自动化系统集成；智能工厂整体解决方案；",
            f"物联网技术开发与应用；软件开发及技术服务等。",
        ]),
        ("二、财务报表的编制基础", [
            "本公司财务报表以持续经营假设为基础，根据实际发生的交易和事项，",
            "按照中华人民共和国财政部颁布的《企业会计准则——基本准则》和各项具体会计准则、",
            "企业会计准则应用指南、企业会计准则解释及其他相关规定（以下合称'企业会计准则'）",
            "进行确认和计量，在此基础上编制财务报表。",
        ]),
        ("三、重要会计政策及会计估计", [
            "1. 会计期间：本公司会计年度自公历1月1日起至12月31日止。",
            "2. 记账本位币：本公司以人民币为记账本位币。",
            "3. 记账基础和计价原则：本公司会计核算以权责发生制为记账基础。",
            "   本公司对会计要素进行计量时，一般采用历史成本，当所确定的会计要素金额",
            "   符合企业会计准则的要求、能够取得并可靠计量时，可采用重置成本、可变现净值、现值、公允价值计量。",
            "4. 企业合并：同一控制下企业合并采用权益结合法，非同一控制下企业合并采用购买法。",
            "5. 合并报表编制方法：合并财务报表的合并范围以控制为基础予以确定。",
            "6. 现金及现金等价物：现金是指库存现金以及可以随时用于支付的存款。",
            "   现金等价物是指本公司持有的期限短（一般指从购买日起三个月内到期）、",
            "   流动性强、易于转换为已知金额现金、价值变动风险很小的投资。",
            "7. 外币业务：本公司发生外币业务时，按业务发生时的市场汇率的近似汇率将外币金额折算为记账本位币金额。",
            "8. 金融工具：本公司根据管理金融资产的业务模式和金融资产的合同现金流量特征，",
            "   将金融资产分类为以摊余成本计量、以公允价值计量且其变动计入其他综合收益、",
            "   和以公允价值计量且其变动计入当期损益三类。",
            "9. 应收款项坏账准备：本公司采用预期信用损失模型对应收款项计提坏账准备。",
            "   应收账款坏账准备计提比例如下：",
        ]),
        ("四、税项", [
            "1. 主要税种及税率：",
            f"   增值税：按销售收入13%、9%、6%的税率计算销项税额，扣除当期允许抵扣的进项税额后缴纳。",
            f"   企业所得税：本公司适用的企业所得税税率为15%（高新技术企业）。",
            f"   城市维护建设税：按应纳流转税额的7%缴纳。",
            f"   教育费附加：按应纳流转税额的3%缴纳。",
            f"   地方教育附加：按应纳流转税额的2%缴纳。",
            "2. 税收优惠：",
            f"   本公司于{COMPANY['year']-1}年12月取得高新技术企业证书（编号：GR20XXXXXX），",
            f"   有效期三年，{COMPANY['year']}年度适用15%的企业所得税优惠税率。",
            f"   本公司之子公司XX科技有限公司于{COMPANY['year']}年11月取得高新技术企业证书，适用15%税率。",
        ]),
        ("五、合并财务报表项目附注", []),
    ]

    # 生成详细的附注内容（填充到 ~95 页）
    for section_title, paragraphs in notes_sections:
        page = next_page()
        _write_text(page, 80, section_title, fontsize=12, bold=True, x=72)
        y = 110
        for p in paragraphs:
            if y > 760:
                page = next_page()
                y = 80
            _write_text(page, y, p, fontsize=10, x=72)
            y += 18 if len(p) > 60 else 22

    # 应收款项账龄分析表（跨页大表）
    page = next_page()
    _write_text(page, 80, "5.1 应收账款", fontsize=11, bold=True, x=72)
    _write_text(page, 98, "（1）应收账款分类披露", fontsize=10, bold=True, x=72)
    ar_headers = ["类别", "期末余额", "坏账准备", "账面价值", "期初余额"]
    ar_col_w = [180, 90, 90, 90, 90]

    ar_rows = [
        ["单项计提坏账准备的应收账款", _fmt(12_345_678.90), _fmt(12_345_678.90), "0", _fmt(10_987_654.32)],
        ["按组合计提坏账准备的应收账款", _fmt(1_567_890_123.45), _fmt(78_394_506.17), _fmt(1_489_495_617.28), _fmt(1_234_567_890.12)],
        ["    其中：账龄组合", _fmt(1_567_890_123.45), _fmt(78_394_506.17), _fmt(1_489_495_617.28), _fmt(1_234_567_890.12)],
        ["合计", _fmt(1_580_235_802.35), _fmt(90_740_185.07), _fmt(1_489_495_617.28), _fmt(1_245_555_544.44)],
    ]
    page, _ = _write_table(page, ar_headers, ar_rows, 115, ar_col_w, fontsize=8)

    # 账龄分析（跨页）
    _write_text(page, 200, "（2）应收账款账龄分析", fontsize=10, bold=True, x=72)
    aging_headers = ["账龄", "期末余额", "比例(%)", "坏账准备", "期初余额"]
    aging_col_w = [120, 110, 70, 110, 110]
    aging_rows = [
        ["1年以内", _fmt(1_234_567_890.12), "78.12", _fmt(61_728_394.51), _fmt(987_654_321.09)],
        ["1至2年", _fmt(234_567_890.12), "14.84", _fmt(23_456_789.01), _fmt(156_789_012.34)],
        ["2至3年", _fmt(67_890_123.45), "4.30", _fmt(6_789_012.35), _fmt(45_678_901.23)],
        ["3至4年", _fmt(23_456_789.01), "1.48", _fmt(4_691_357.80), _fmt(23_456_789.01)],
        ["4至5年", _fmt(11_728_394.50), "0.74", _fmt(5_864_197.25), _fmt(11_728_394.50)],
        ["5年以上", _fmt(8_024_716.15), "0.51", _fmt(8_024_716.15), _fmt(8_024_716.15)],
        ["合计", _fmt(1_580_235_802.35), "100.00", _fmt(90_740_185.07), _fmt(1_233_332_134.32)],
    ]
    page, _ = _write_table(page, aging_headers, aging_rows, 240, aging_col_w, fontsize=8)

    # 存货明细（跨页大表）
    page = next_page()
    _write_text(page, 80, "5.2 存货", fontsize=11, bold=True, x=72)
    inv_headers = ["项目", "期末余额", "跌价准备", "账面价值", "期初余额"]
    inv_rows = [
        ["原材料", _fmt(234_567_890.12), _fmt(5_678_901.23), _fmt(228_888_988.89), _fmt(198_765_432.10)],
        ["在产品", _fmt(345_678_901.23), _fmt(8_765_432.10), _fmt(336_913_469.13), _fmt(298_765_432.10)],
        ["库存商品", _fmt(345_678_901.23), _fmt(12_345_678.90), _fmt(333_333_222.33), _fmt(312_345_678.90)],
        ["周转材料", _fmt(23_456_789.01), _fmt(1_234_567.89), _fmt(22_222_221.12), _fmt(19_876_543.21)],
        ["委托加工物资", _fmt(12_345_678.90), "0", _fmt(12_345_678.90), _fmt(10_987_654.32)],
        ["发出商品", _fmt(25_951_160.60), "0", _fmt(25_951_160.60), _fmt(35_802_470.25)],
        ["合计", _fmt(987_679_321.09), _fmt(28_024_580.12), _fmt(959_654_740.97), _fmt(876_543_210.98)],
    ]
    page, _ = _write_table(page, inv_headers, inv_rows, 115, [140, 100, 90, 100, 100], fontsize=8)

    # 固定资产明细（跨页大表）
    _write_text(page, 280, "5.3 固定资产", fontsize=11, bold=True, x=72)
    fa_headers = ["类别", "期初余额", "本期增加", "本期减少", "期末余额"]
    fa_rows = [
        ["房屋及建筑物", _fmt(1_234_567_890.12), _fmt(123_456_789.01), _fmt(0), _fmt(1_358_024_679.13)],
        ["机器设备", _fmt(678_901_234.56), _fmt(89_012_345.67), _fmt(5_678_901.23), _fmt(762_234_679.00)],
        ["运输工具", _fmt(45_678_901.23), _fmt(5_678_901.23), _fmt(2_345_678.90), _fmt(49_012_123.56)],
        ["电子设备", _fmt(89_012_345.67), _fmt(12_345_678.90), _fmt(3_456_789.01), _fmt(97_901_235.56)],
        ["办公设备", _fmt(23_456_789.01), _fmt(3_456_789.01), _fmt(1_234_567.89), _fmt(25_679_010.13)],
        ["其他设备", _fmt(12_345_678.90), _fmt(1_234_567.89), _fmt(567_890.12), _fmt(13_012_356.67)],
        ["合计", _fmt(2_083_962_839.49), _fmt(235_185_071.71), _fmt(13_283_827.15), _fmt(2_305_864_084.05)],
    ]
    page, _ = _write_table(page, fa_headers, fa_rows, 310, [120, 90, 90, 90, 90], fontsize=8)

    # ---- 补充多个附注页面来填充到98页 ----
    additional_notes = [
        ("5.4 在建工程", [
            ("项目名称", "预算数", "期初余额", "本期增加", "本期转固", "期末余额", "工程进度"),
            ("智能制造基地一期", _fmt(500_000_000), _fmt(234_567_890.12), _fmt(123_456_789.01), _fmt(0), _fmt(358_024_679.13), "72%"),
            ("研发中心大楼", _fmt(200_000_000), _fmt(89_012_345.67), _fmt(45_678_901.23), _fmt(0), _fmt(134_691_246.90), "67%"),
            ("智慧物流系统", _fmt(80_000_000), _fmt(34_567_890.12), _fmt(12_345_678.90), _fmt(0), _fmt(46_913_569.02), "59%"),
            ("其他零星工程", _fmt(50_000_000), _fmt(15_678_901.23), _fmt(8_765_432.10), _fmt(5_678_901.23), _fmt(18_765_432.10), "38%"),
            ("合  计", _fmt(830_000_000), _fmt(373_827_027.14), _fmt(190_246_801.24), _fmt(5_678_901.23), _fmt(558_394_927.15), "—"),
        ]),
        ("5.5 无形资产", [
            ("类别", "原值", "累计摊销", "减值准备", "账面价值"),
            ("土地使用权", _fmt(234_567_890.12), _fmt(34_567_890.12), "0", _fmt(200_000_000.00)),
            ("专利权", _fmt(89_012_345.67), _fmt(23_456_789.01), "0", _fmt(65_555_556.66)),
            ("软件著作权", _fmt(45_678_901.23), _fmt(12_345_678.90), "0", _fmt(33_333_222.33)),
            ("商标权", _fmt(5_678_901.23), _fmt(1_234_567.89), "0", _fmt(4_444_333.34)),
            ("其他", _fmt(12_345_678.90), _fmt(3_456_789.01), "0", _fmt(8_888_889.89)),
            ("合  计", _fmt(387_283_717.15), _fmt(75_061_714.93), "0", _fmt(312_222_002.22)),
        ]),
        ("5.6 短期借款", [
            ("借款类别", "期末余额", "利率区间", "期初余额"),
            ("信用借款", _fmt(234_567_890.12), "3.20%-3.85%", _fmt(198_765_432.10)),
            ("保证借款", _fmt(123_456_789.01), "3.45%-4.15%", _fmt(98_765_432.10)),
            ("抵押借款", _fmt(56_789_012.34), "3.65%-4.35%", _fmt(56_789_012.34)),
            ("质押借款", _fmt(41_975_320.87), "3.55%-4.05%", _fmt(44_444_555.66)),
            ("合  计", _fmt(456_789_012.34), "—", _fmt(398_765_432.10)),
        ]),
        ("5.7 应付账款", [
            ("账龄", "期末余额", "比例(%)", "期初余额"),
            ("1年以内", _fmt(789_012_345.67), "79.88", _fmt(678_901_234.56)),
            ("1至2年", _fmt(123_456_789.01), "12.50", _fmt(98_765_432.10)),
            ("2至3年", _fmt(45_678_901.23), "4.62", _fmt(56_789_012.34)),
            ("3年以上", _fmt(29_506_285.18), "2.99", _fmt(42_087_531.98)),
            ("合  计", _fmt(987_654_321.09), "100.00", _fmt(876_543_210.98)),
        ]),
        ("5.8 营业收入及成本", [
            ("（1）营业收入、营业成本按产品分类"),
            ("产品类别", "营业收入", "营业成本", "毛利率"),
            ("智能制造装备", _fmt(REVENUE * 0.45), _fmt(COST * 0.42), f"{(REVENUE*0.45-COST*0.42)/(REVENUE*0.45)*100:.2f}%"),
            ("工业机器人系统", _fmt(REVENUE * 0.30), _fmt(COST * 0.32), f"{(REVENUE*0.30-COST*0.32)/(REVENUE*0.30)*100:.2f}%"),
            ("智能工厂解决方案", _fmt(REVENUE * 0.15), _fmt(COST * 0.16), f"{(REVENUE*0.15-COST*0.16)/(REVENUE*0.15)*100:.2f}%"),
            ("软件及技术服务", _fmt(REVENUE * 0.10), _fmt(COST * 0.10), f"{(REVENUE*0.10-COST*0.10)/(REVENUE*0.10)*100:.2f}%"),
            ("合  计", _fmt(REVENUE), _fmt(COST), f"{GROSS_PROFIT/REVENUE*100:.2f}%"),
            ("", "", "", ""),
            ("（2）营业收入按地区分类"),
            ("地区", "营业收入", "占比", ""),
            ("华东地区", _fmt(REVENUE * 0.35), "35%", ""),
            ("华南地区", _fmt(REVENUE * 0.25), "25%", ""),
            ("华北地区", _fmt(REVENUE * 0.18), "18%", ""),
            ("西南地区", _fmt(REVENUE * 0.12), "12%", ""),
            ("境外", _fmt(REVENUE * 0.10), "10%", ""),
            ("合  计", _fmt(REVENUE), "100%", ""),
        ]),
        ("5.9 研发费用", [
            ("项目", "本期发生额", "上期发生额"),
            ("人工费用", _fmt(RD_EXP * 0.55), _fmt(RD_EXP_PREV * 0.55)),
            ("材料费用", _fmt(RD_EXP * 0.20), _fmt(RD_EXP_PREV * 0.20)),
            ("折旧摊销", _fmt(RD_EXP * 0.10), _fmt(RD_EXP_PREV * 0.10)),
            ("试验检验费", _fmt(RD_EXP * 0.08), _fmt(RD_EXP_PREV * 0.08)),
            ("其他费用", _fmt(RD_EXP * 0.07), _fmt(RD_EXP_PREV * 0.07)),
            ("合  计", _fmt(RD_EXP), _fmt(RD_EXP_PREV)),
        ]),
        ("六、关联方及关联交易", [
            "1. 本公司的母公司：XX控股集团有限公司（持股比例42.8%）",
            "2. 本公司的主要子公司：",
        ]),
        ("子公司信息", [
            ("子公司名称", "注册地", "持股比例", "注册资本", "主营业务"),
            ("XX智能制造技术有限公司", "上海", "100%", "200,000,000元", "智能制造装备研发与生产"),
            ("XX机器人科技有限公司", "深圳", "85%", "100,000,000元", "工业机器人系统集成"),
            ("XX物联网技术有限公司", "杭州", "70%", "50,000,000元", "物联网平台开发"),
            ("XX精密机械有限公司", "苏州", "100%", "80,000,000元", "精密零部件加工"),
            ("XX软件技术有限公司", "南京", "90%", "30,000,000元", "工业软件开发"),
            ("XX智能物流有限公司", "武汉", "65%", "40,000,000元", "智能仓储物流"),
        ]),
        ("七、或有事项", [
            "截止本报告期末，本公司不存在应披露的重大未决诉讼、对外担保等或有事项。",
        ]),
        ("八、承诺事项", [
            f"截止{COMPANY['year']}年12月31日，本公司已签约但尚未在财务报表中确认的",
            f"购建长期资产合同金额为人民币{_fmt(234_567_890.12)}元。",
        ]),
        ("九、资产负债表日后事项", [
            f"截止本报告报出日（{COMPANY['year']+1}年4月25日），",
            f"本公司不存在应披露的重大资产负债表日后事项。",
        ]),
        ("十、补充资料", [
            "1. 非经常性损益明细表：",
            ("项目", "金额"),
            ("非流动资产处置损益", _fmt(345_678.90)),
            ("计入当期损益的政府补助", _fmt(5_678_901.23)),
            ("委托他人投资或管理资产的损益", _fmt(3_456_789.01)),
            ("除上述各项之外的其他营业外收入和支出", _fmt(888_888.99)),
            ("减：所得税影响额", _fmt(1_536_788.72)),
            ("合  计", _fmt(8_833_469.41)),
            "",
            "2. 净资产收益率及每股收益：",
            ("报告期利润", "加权平均净资产收益率(%)", "每股收益（基本）", "每股收益（稀释）"),
            ("归属于母公司所有者的净利润", f"{(NET_PROFIT/EQUITY)*100:.2f}", f"{NET_PROFIT/1_000_000_000:.2f}", f"{NET_PROFIT/1_000_000_000:.2f}"),
            ("扣除非经常性损益后净利润", f"{(NET_PROFIT*0.92/EQUITY)*100:.2f}", f"{NET_PROFIT*0.92/1_000_000_000:.2f}", f"{NET_PROFIT*0.92/1_000_000_000:.2f}"),
        ]),
    ]

    for note in additional_notes:
        title = note[0]
        data = list(note[1:])
        page = next_page()
        _write_text(page, 80, title, fontsize=11, bold=True, x=72)
        y = 110

        if data and isinstance(data[0], tuple):
            # 表格格式
            headers = list(data[0])
            rows = [list(r) for r in data[1:] if isinstance(r, tuple)]
            col_w = [max(60, 480 // len(headers))] * len(headers)
            page, y = _write_table(page, headers, rows, y, col_w, fontsize=8)
        else:
            # 文本格式
            for item in data:
                if isinstance(item, str):
                    if y > 760:
                        page = next_page()
                        y = 80
                    _write_text(page, y, item, fontsize=10, x=72)
                    y += 18 if len(item) > 50 else 22
                elif isinstance(item, tuple):
                    if y > 700:
                        page = next_page()
                        y = 80
                    headers = list(item)
                    next_items = [d for d in data[data.index(item)+1:] if isinstance(d, tuple)]
                    rows = [list(r) for r in next_items[:20]]
                    col_w = [max(60, 480 // len(headers))] * len(headers)
                    page, y = _write_table(page, headers, rows, y, col_w, fontsize=8)

    # 继续填充剩余页（大量附注文本，保证达到 ~98 页）
    filler_topics = [
        "公允价值计量", "金融工具风险分析", "资本管理", "股份支付",
        "租赁", "政府补助", "递延所得税", "企业合并", "分部报告",
        "关联方交易详情", "重大合同", "审计费用", "持续经营评估",
    ]
    filler_idx = 0
    while page_num[0] < 95:
        page = next_page()
        topic = filler_topics[filler_idx % len(filler_topics)]
        filler_idx += 1
        _write_text(page, 80, f"附注{filler_idx + 10}：{topic}", fontsize=11, bold=True, x=72)
        y = 110
        for _ in range(35):
            if y > 760:
                break
            text = (
                f"本公司根据企业会计准则的相关规定，对{topic}进行了详细的评估和计量。"
                f"截止{COMPANY['year']}年12月31日，相关项目已按照公允价值/历史成本/可变现净值"
                f"进行确认，不存在重大差异。本公司管理层认为，相关会计估计和方法的选择"
                f"符合企业会计准则的规定，能够公允反映公司的财务状况和经营成果。"
            )
            _write_text(page, y, text, fontsize=10, x=72)
            y += 18

    # 最后一页
    while page_num[0] < total_pages:
        page = next_page()
        _write_text(page, 400, "（此页无正文，为年度报告签署页）", fontsize=11, x=150, color=(0.5, 0.5, 0.5))

    # 保存
    pdf_path = OUT_DIR / "SYNTH_001.pdf"
    doc.save(str(pdf_path))
    doc.close()
    print(f"PDF saved: {pdf_path} ({os.path.getsize(pdf_path)/1024:.0f} KB, {total_pages} pages)")


# ============================================================================
# 3. 生成 XBRL Ground Truth + 下游任务
# ============================================================================

def build_xbrl_and_tasks():
    """生成 FinAR-Bench 格式的 XBRL 真值和 13 个下游任务。"""

    # XBRL 三张表
    xbrl_table = f"""# 利润表
| 项目 | 2023年12月31日 | 2022年12月31日 |
|------|-------------|-------------|
| 营业收入 | {REVENUE:.2f} | {REVENUE_PREV:.2f} |
| 营业成本 | {COST:.2f} | {COST_PREV:.2f} |
| 税金及附加 | 12345678.90 | 10987654.32 |
| 销售费用 | {SELLING_EXP:.2f} | {SELLING_EXP_PREV:.2f} |
| 管理费用 | {ADMIN_EXP:.2f} | {ADMIN_EXP_PREV:.2f} |
| 研发费用 | {RD_EXP:.2f} | {RD_EXP_PREV:.2f} |
| 财务费用 | {FINANCE_EXP:.2f} | {FINANCE_EXP_PREV:.2f} |
| 其他收益 | 8765432.10 | 6543210.98 |
| 投资收益 | 3456789.01 | 2345678.90 |
| 营业利润 | {OP_PROFIT:.2f} | {OP_PROFIT_PREV:.2f} |
| 营业外收入 | 1234567.89 | 987654.32 |
| 营业外支出 | 345678.90 | 234567.89 |
| 利润总额 | {TOTAL_PROFIT:.2f} | {TOTAL_PROFIT_PREV:.2f} |
| 所得税费用 | {TAX:.2f} | {TAX_PREV:.2f} |
| 净利润 | {NET_PROFIT:.2f} | {NET_PROFIT_PREV:.2f} |

# 资产负债表
| 项目 | 2023年12月31日 | 2022年12月31日 |
|------|-------------|-------------|
| 货币资金 | {CASH_END:.2f} | {CASH_BEGIN:.2f} |
| 交易性金融资产 | 345678901.23 | 298765432.10 |
| 应收账款 | 1567890123.45 | 1234567890.12 |
| 预付款项 | 234567890.12 | 198765432.10 |
| 其他应收款 | 89012345.67 | 76543210.98 |
| 存货 | 987654321.09 | 876543210.98 |
| 流动资产合计 | {CA:.2f} | {CA_PREV:.2f} |
| 长期股权投资 | 345678901.23 | 298765432.10 |
| 固定资产 | 2345678901.23 | 2123456789.01 |
| 在建工程 | 567890123.45 | 456789012.34 |
| 无形资产 | 456789012.34 | 398765432.10 |
| 商誉 | 123456789.45 | 123456789.45 |
| 非流动资产合计 | {NCA:.2f} | {NCA_PREV:.2f} |
| 资产总计 | {TA:.2f} | {TA_PREV:.2f} |
| 短期借款 | 456789012.34 | 398765432.10 |
| 应付票据 | 234567890.12 | 198765432.10 |
| 应付账款 | 987654321.09 | 876543210.98 |
| 应付职工薪酬 | 145678901.23 | 134567890.12 |
| 流动负债合计 | {CL:.2f} | {CL_PREV:.2f} |
| 长期借款 | 567890123.45 | 498765432.10 |
| 应付债券 | 345678901.23 | 345678901.23 |
| 非流动负债合计 | {NCL:.2f} | {NCL_PREV:.2f} |
| 负债合计 | {TL:.2f} | {TL_PREV:.2f} |
| 实收资本 | 1000000000.00 | 1000000000.00 |
| 资本公积 | 500000000.00 | 500000000.00 |
| 未分配利润 | {EQUITY - 1500000000 - EQUITY*0.1:.2f} | {EQUITY_PREV - 1500000000 - EQUITY_PREV*0.1:.2f} |
| 所有者权益合计 | {EQUITY:.2f} | {EQUITY_PREV:.2f} |

# 现金流量表
| 项目 | 2023年12月31日 | 2022年12月31日 |
|------|-------------|-------------|
| 销售商品、提供劳务收到的现金 | {REVENUE*1.13:.2f} | {REVENUE_PREV*1.13:.2f} |
| 经营活动现金流入小计 | {REVENUE*1.13 + 23456789.01 + 34567890.12:.2f} | {REVENUE_PREV*1.13 + 19876543.21 + 28765432.10:.2f} |
| 购买商品、接受劳务支付的现金 | {COST*1.1:.2f} | {COST_PREV*1.1:.2f} |
| 经营活动现金流出小计 | {COST*1.1 + 345678901.23 + TAX + 34567890.12 + 67890123.45:.2f} | {COST_PREV*1.1 + 298765432.10 + TAX_PREV + 28765432.10 + 56789012.34:.2f} |
| 经营活动产生的现金流量净额 | {CF_OPERATING:.2f} | {CF_OPERATING_PREV:.2f} |
| 投资活动产生的现金流量净额 | {CF_INVESTING:.2f} | {CF_INVESTING_PREV:.2f} |
| 筹资活动产生的现金流量净额 | {CF_FINANCING:.2f} | {CF_FINANCING_PREV:.2f} |
| 现金及现金等价物净增加额 | {CASH_END - CASH_BEGIN:.2f} | {CASH_BEGIN - (CASH_BEGIN - 200000000):.2f} |
| 期初现金及现金等价物余额 | {CASH_BEGIN:.2f} | {CASH_BEGIN - 200000000:.2f} |
| 期末现金及现金等价物余额 | {CASH_END:.2f} | {CASH_BEGIN:.2f} |
"""

    # 13 个下游任务
    instances = [
        # ---- fact (6) ----
        {
            "task_id": "synth_fact_1",
            "task": f"提取公司合并财务报表中2022和2023的营业收入、营业成本、净利润、经营活动产生的现金流量净额的数据。以一个markdown格式的表格输出，列为项目,2022,2023",
            "ground_truth": f"| 项目 | 2022 | 2023 |\n|----|----|----|\n| 营业收入 | {REVENUE_PREV:.2f} | {REVENUE:.2f} |\n| 营业成本 | {COST_PREV:.2f} | {COST:.2f} |\n| 净利润 | {NET_PROFIT_PREV:.2f} | {NET_PROFIT:.2f} |\n| 经营活动产生的现金流量净额 | {CF_OPERATING_PREV:.2f} | {CF_OPERATING:.2f} |",
            "task_type": "fact",
            "task_num": 1,
            "company": COMPANY['name'],
            "company_code": f"{COMPANY['code']}.SH",
        },
        {
            "task_id": "synth_fact_2",
            "task": f"提取公司合并财务报表中2022和2023的资产总计、负债合计、所有者权益合计的数据。以一个markdown格式的表格输出，列为项目,2022,2023",
            "ground_truth": f"| 项目 | 2022 | 2023 |\n|----|----|----|\n| 资产总计 | {TA_PREV:.2f} | {TA:.2f} |\n| 负债合计 | {TL_PREV:.2f} | {TL:.2f} |\n| 所有者权益合计 | {EQUITY_PREV:.2f} | {EQUITY:.2f} |",
            "task_type": "fact",
            "task_num": 2,
            "company": COMPANY['name'],
            "company_code": f"{COMPANY['code']}.SH",
        },
        {
            "task_id": "synth_fact_3",
            "task": f"提取公司合并财务报表中2022和2023的货币资金、应收账款、存货、固定资产、短期借款、应付账款的数据。以一个markdown格式的表格输出，列为项目,2022,2023",
            "ground_truth": f"| 项目 | 2022 | 2023 |\n|----|----|----|\n| 货币资金 | {CASH_BEGIN:.2f} | {CASH_END:.2f} |\n| 应收账款 | 1234567890.12 | 1567890123.45 |\n| 存货 | 876543210.98 | 987654321.09 |\n| 固定资产 | 2123456789.01 | 2345678901.23 |\n| 短期借款 | 398765432.10 | 456789012.34 |\n| 应付账款 | 876543210.98 | 987654321.09 |",
            "task_type": "fact",
            "task_num": 4,
            "company": COMPANY['name'],
            "company_code": f"{COMPANY['code']}.SH",
        },
        {
            "task_id": "synth_fact_4",
            "task": f"提取公司合并财务报表中2022和2023的研发费用、销售费用、管理费用、财务费用、投资收益、营业外收入的数据。以一个markdown格式的表格输出，列为项目,2022,2023",
            "ground_truth": f"| 项目 | 2022 | 2023 |\n|----|----|----|\n| 研发费用 | {RD_EXP_PREV:.2f} | {RD_EXP:.2f} |\n| 销售费用 | {SELLING_EXP_PREV:.2f} | {SELLING_EXP:.2f} |\n| 管理费用 | {ADMIN_EXP_PREV:.2f} | {ADMIN_EXP:.2f} |\n| 财务费用 | {FINANCE_EXP_PREV:.2f} | {FINANCE_EXP:.2f} |\n| 投资收益 | 2345678.90 | 3456789.01 |\n| 营业外收入 | 987654.32 | 1234567.89 |",
            "task_type": "fact",
            "task_num": 8,
            "company": COMPANY['name'],
            "company_code": f"{COMPANY['code']}.SH",
        },
        {
            "task_id": "synth_fact_5",
            "task": f"提取公司合并财务报表中2022和2023的流动资产合计、非流动资产合计、流动负债合计、非流动负债合计的数据。以一个markdown格式的表格输出，列为项目,2022,2023",
            "ground_truth": f"| 项目 | 2022 | 2023 |\n|----|----|----|\n| 流动资产合计 | {CA_PREV:.2f} | {CA:.2f} |\n| 非流动资产合计 | {NCA_PREV:.2f} | {NCA:.2f} |\n| 流动负债合计 | {CL_PREV:.2f} | {CL:.2f} |\n| 非流动负债合计 | {NCL_PREV:.2f} | {NCL:.2f} |",
            "task_type": "fact",
            "task_num": 16,
            "company": COMPANY['name'],
            "company_code": f"{COMPANY['code']}.SH",
        },
        {
            "task_id": "synth_fact_6",
            "task": f"提取公司合并财务报表中2022和2023的长期股权投资、在建工程、无形资产、商誉、长期借款、应付债券的数据。以一个markdown格式的表格输出，列为项目,2022,2023",
            "ground_truth": f"| 项目 | 2022 | 2023 |\n|----|----|----|\n| 长期股权投资 | 298765432.10 | 345678901.23 |\n| 在建工程 | 456789012.34 | 567890123.45 |\n| 无形资产 | 398765432.10 | 456789012.34 |\n| 商誉 | 123456789.45 | 123456789.45 |\n| 长期借款 | 498765432.10 | 567890123.45 |\n| 应付债券 | 345678901.23 | 345678901.23 |",
            "task_type": "fact",
            "task_num": 32,
            "company": COMPANY['name'],
            "company_code": f"{COMPANY['code']}.SH",
        },
        # ---- indicator (6) ----
        {
            "task_id": "synth_ind_1",
            "task": f"计算公式合并财务报表中2023年度的销售毛利率、净利率、总资产收益率（ROA）、净资产收益率（ROE）的数据。以一个markdown格式的表格输出，列为项目,2023，结果表示为小数并保留4位小数",
            "ground_truth": f"| 项目 | 2023 |\n|----|----|\n| 销售毛利率 | {GROSS_PROFIT/REVENUE:.4f} |\n| 净利率 | {NET_PROFIT/REVENUE:.4f} |\n| 总资产收益率(ROA) | {NET_PROFIT/TA:.4f} |\n| 净资产收益率(ROE) | {NET_PROFIT/EQUITY:.4f} |",
            "task_type": "indicator",
            "task_num": 1,
            "company": COMPANY['name'],
            "company_code": f"{COMPANY['code']}.SH",
        },
        {
            "task_id": "synth_ind_2",
            "task": f"计算公式合并财务报表中2023年度的资产负债率、流动比率、速动比率的数据。以一个markdown格式的表格输出，列为项目,2023，结果表示为小数并保留4位小数",
            "ground_truth": f"| 项目 | 2023 |\n|----|----|\n| 资产负债率 | {TL/TA:.4f} |\n| 流动比率 | {CA/CL:.4f} |\n| 速动比率 | {(CA-987654321.09)/CL:.4f} |",
            "task_type": "indicator",
            "task_num": 2,
            "company": COMPANY['name'],
            "company_code": f"{COMPANY['code']}.SH",
        },
        {
            "task_id": "synth_ind_3",
            "task": f"计算公式合并财务报表中2023年度的应收账款周转率、存货周转率、总资产周转率的数据。以一个markdown格式的表格输出，列为项目,2023，结果表示为小数并保留4位小数",
            "ground_truth": f"| 项目 | 2023 |\n|----|----|\n| 应收账款周转率 | {REVENUE/((1567890123.45+1234567890.12)/2):.4f} |\n| 存货周转率 | {COST/((987654321.09+876543210.98)/2):.4f} |\n| 总资产周转率 | {REVENUE/((TA+TA_PREV)/2):.4f} |",
            "task_type": "indicator",
            "task_num": 4,
            "company": COMPANY['name'],
            "company_code": f"{COMPANY['code']}.SH",
        },
        {
            "task_id": "synth_ind_4",
            "task": f"计算公式合并财务报表中2023年度的期间费用率（含销售费用、管理费用、研发费用、财务费用占营业收入比例）的数据。以一个markdown格式的表格输出，列为项目,2023，结果表示为小数并保留4位小数",
            "ground_truth": f"| 项目 | 2023 |\n|----|----|\n| 期间费用率 | {(SELLING_EXP+ADMIN_EXP+RD_EXP+FINANCE_EXP)/REVENUE:.4f} |\n| 销售费用率 | {SELLING_EXP/REVENUE:.4f} |\n| 管理费用率 | {ADMIN_EXP/REVENUE:.4f} |\n| 研发费用率 | {RD_EXP/REVENUE:.4f} |",
            "task_type": "indicator",
            "task_num": 8,
            "company": COMPANY['name'],
            "company_code": f"{COMPANY['code']}.SH",
        },
        {
            "task_id": "synth_ind_5",
            "task": f"计算公式合并财务报表中2023年度的非流动资产占总资产比例、营业收入增长率、净利润增长率的数据。以一个markdown格式的表格输出，列为项目,2023，结果表示为小数并保留4位小数",
            "ground_truth": f"| 项目 | 2023 |\n|----|----|\n| 非流动资产占总资产比例 | {NCA/TA:.4f} |\n| 营业收入增长率 | {(REVENUE/REVENUE_PREV-1):.4f} |\n| 净利润增长率 | {(NET_PROFIT/NET_PROFIT_PREV-1):.4f} |",
            "task_type": "indicator",
            "task_num": 16,
            "company": COMPANY['name'],
            "company_code": f"{COMPANY['code']}.SH",
        },
        {
            "task_id": "synth_ind_6",
            "task": f"计算公式合并财务报表中2023年度的现金比率（货币资金/流动负债）、权益乘数（总资产/所有者权益）、经营活动现金流与净利润比率的数据。以一个markdown格式的表格输出，列为项目,2023，结果表示为小数并保留4位小数",
            "ground_truth": f"| 项目 | 2023 |\n|----|----|\n| 现金比率 | {CASH_END/CL:.4f} |\n| 权益乘数 | {TA/EQUITY:.4f} |\n| 经营活动现金流与净利润比率 | {CF_OPERATING/NET_PROFIT:.4f} |",
            "task_type": "indicator",
            "task_num": 32,
            "company": COMPANY['name'],
            "company_code": f"{COMPANY['code']}.SH",
        },
        # ---- reasoning (1) ----
        {
            "task_id": "synth_reas_1",
            "task": f"根据给定的判断条件和公司的合并财务报表数据，回答问题: 1. 判断公司{COMPANY['year']}年的财务状况是否满足以下条件。以一个markdown格式的表格输出，列为序号,是否满足",
            "ground_truth": (
                "| 序号 | 是否满足 |\n|----|----|\n"
                "| 0 | 1 |\n"
                "| 1 | 0 |\n"
                "| 2 | 1 |\n"
                "| 3 | 1 |\n"
                "| 4 | 0 |\n"
                "| 5 | 1 |\n"
                "| 6 | 0 |\n"
                "| 7 | 1 |\n"
                "| 8 | 0 |\n"
                "| 9 | 1 |\n"
                "| 10 | 0 |\n"
                "| 11 | 1 |"
            ),
            "conditions": (
                "| 序号 | 条件 |\n|----|----|\n"
                "| 0 | 营业收入增长率大于10% |\n"
                f"| 1 | 净利润相比上年下降 |\n"
                "| 2 | 资产负债率小于50% |\n"
                "| 3 | 流动比率大于1.5 |\n"
                "| 4 | 经营活动现金流净额小于净利润 |\n"
                f"| 5 | ROE（净资产收益率）大于5% |\n"
                "| 6 | 研发费用占营业收入比例大于30% |\n"
                "| 7 | 期间费用率小于30% |\n"
                "| 8 | 存货周转率小于1 |\n"
                "| 9 | 现金比率大于1 |\n"
                "| 10 | 应收账款占总资产比例大于40% |\n"
                "| 11 | 毛利率大于30% |"
            ),
            "task_type": "reasoning",
            "task_num": 64,
            "company": COMPANY['name'],
            "company_code": f"{COMPANY['code']}.SH",
        },
    ]

    # 输出
    record = {
        "table": xbrl_table,
        "instances": instances,
        "file_path": "./data/pdf_data/SYNTH_001.pdf",
    }

    xbrl_path = OUT_DIR / "SYNTH_001_xbrl.json"
    xbrl_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"XBRL saved: {xbrl_path}")

    # 各场景也复制一份
    for scene_dir in ["S3_cross_page", "S4_borderless", "S5_long_documents"]:
        scene_path = PROJECT_ROOT / "data" / "eval_dataset" / scene_dir / "SYNTH_001_xbrl.json"
        scene_path.parent.mkdir(parents=True, exist_ok=True)
        scene_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Tasks: {len(instances)} (6 fact + 6 indicator + 1 reasoning)")


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    build_pdf()
    build_xbrl_and_tasks()
    print("\nDone: 超长年报 PDF + XBRL + 下游任务已生成")
