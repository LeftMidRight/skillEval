# Synthetic Multicolumn Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `data/eval_dataset/synthetic_multicolumn/` as realistic annual-report two-column topic pages with XBRL-compatible GT and explicit `layout_gt`.

**Architecture:** Keep the existing single generator `sandbox/gen_synthetic_scenes.py`, but replace the synthetic multicolumn generation path with a page-aware annual-report topic generator. The generator writes PDF content and records layout metadata in the same pass, then `save_gt` persists both XBRL GT and layout GT.

**Tech Stack:** Python 3, `fpdf.FPDF`, existing FinAR XBRL loader, `pdftoppm` for visual render verification, PowerShell for local checks.

---

## File Structure

- Modify `sandbox/gen_synthetic_scenes.py`
  - Keep borderless generation behavior intact.
  - Refactor `MultiColumnPDF` to support realistic annual-report topic pages and layout metadata.
  - Add company-specific section data for the two-column topic pages.
  - Extend `save_gt` to accept `layout_gt`.
  - Update `generate_multicolumn` to create PDF and return layout metadata.
- Create `test/test_synthetic_multicolumn_gt.py`
  - Validate that generated `_multi_gt.json` files include `layout_gt`.
  - Validate `selection.json` remains aligned with `_multi.pdf` files.
- Modify generated data files:
  - `data/eval_dataset/synthetic_multicolumn/600569_multi.pdf`
  - `data/eval_dataset/synthetic_multicolumn/600569_multi_gt.json`
  - `data/eval_dataset/synthetic_multicolumn/603421_multi.pdf`
  - `data/eval_dataset/synthetic_multicolumn/603421_multi_gt.json`
  - `data/eval_dataset/synthetic_multicolumn/603707_multi.pdf`
  - `data/eval_dataset/synthetic_multicolumn/603707_multi_gt.json`
  - `data/eval_dataset/synthetic_multicolumn/selection.json`

---

### Task 1: Add GT Contract Test

**Files:**
- Create: `test/test_synthetic_multicolumn_gt.py`

- [ ] **Step 1: Write the failing GT contract test**

Create `test/test_synthetic_multicolumn_gt.py`:

```python
"""synthetic_multicolumn GT 契约测试。"""

from __future__ import annotations

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCENE_DIR = PROJECT_ROOT / "data" / "eval_dataset" / "synthetic_multicolumn"


def _load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_multicolumn_gt_contains_layout_gt():
    for gt_path in sorted(SCENE_DIR.glob("*_multi_gt.json")):
        data = _load_json(gt_path)
        assert data["company_code"]
        assert data["company_name"]
        assert data["xbrl_table"]
        assert isinstance(data["instances"], list)

        layout_gt = data["layout_gt"]
        assert layout_gt["layout_type"] == "synthetic_multicolumn_annual_report_topic"
        assert layout_gt["reading_order"] == "left_column_then_right_column"
        assert len(layout_gt["pages"]) >= 4

        multicol_pages = [p for p in layout_gt["pages"] if p["is_multicolumn"]]
        assert len(multicol_pages) >= 3
        for page in multicol_pages[:3]:
            assert page["columns"] == ["left", "right"]
            assert page["sections"]
            for section in page["sections"]:
                assert section["id"]
                assert section["title"]
                assert section["column_sequence"] == ["left", "right"]
                assert section["paragraph_ids"]


def test_multicolumn_selection_matches_files():
    selection = _load_json(SCENE_DIR / "selection.json")
    assert len(selection) == 3

    for entry in selection:
        code = entry["code"]
        file_name = entry["file"]
        assert code in {"600569", "603421", "603707"}
        assert file_name == f"{code}_multi.pdf"
        assert (SCENE_DIR / file_name).exists()
        assert (SCENE_DIR / f"{code}_multi_gt.json").exists()


def main() -> int:
    tests = [
        ("multicolumn_gt_contains_layout_gt", test_multicolumn_gt_contains_layout_gt),
        ("multicolumn_selection_matches_files", test_multicolumn_selection_matches_files),
    ]
    passed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as exc:
            print(f"FAIL {name}: {exc}")
        except Exception as exc:
            print(f"ERROR {name}: {exc}")

    print(f"\n{passed}/{len(tests)} tests passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```powershell
C:\Users\24865\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe .\test\test_synthetic_multicolumn_gt.py
```

Expected: first test fails because existing `_multi_gt.json` files do not contain `layout_gt`.

---

### Task 2: Implement Realistic Two-Column Topic Generator

**Files:**
- Modify: `sandbox/gen_synthetic_scenes.py`

- [ ] **Step 1: Add section data model**

Add near the current multicolumn body constants:

```python
MULTICOLUMN_TOPIC_SECTIONS = {
    "600569": [
        {
            "id": "overview",
            "title": "一、公司概况与经营回顾",
            "paragraphs": [
                ("overview_p1", "安阳钢铁股份有限公司是河南省大型钢铁联合企业，拥有焦化、烧结、炼铁、炼钢、轧钢等完整长流程制造能力。报告期内，公司围绕稳产顺行、降本增效和产品结构升级开展经营工作，在行业周期下行阶段保持主要产线连续稳定运行。"),
                ("overview_p2", "2023年度，国内钢材需求恢复不及预期，原燃料价格高位波动，钢铁企业盈利能力普遍承压。公司实现营业收入约421.5亿元，经营结果仍受行业价差收窄影响，但四季度现金流和订单结构出现改善迹象。"),
                ("overview_p3", "公司坚持以高附加值品种钢为突破口，汽车用钢、桥梁钢、容器板和高强结构板等重点产品销量占比继续提升。围绕重点工程和战略客户，公司强化研发、生产、销售协同，提升产品交付稳定性和客户响应效率。"),
            ],
        },
        {
            "id": "operation",
            "title": "二、产品结构与绿色转型",
            "paragraphs": [
                ("operation_p1", "报告期内，公司推进普转特、特转优策略，高附加值品种钢占比达到38%，较上年提升5个百分点。汽车用钢完成多个认证品种，桥梁钢在重大工程中保持供货，优势品种市场影响力进一步提升。"),
                ("operation_p2", "绿色低碳改造是公司年度重点工作。公司累计投入环保改造资金超过25亿元，2号高炉超低排放改造项目通过验收，吨钢综合能耗同比下降，自发电比例和余热余能回收利用率持续提高。"),
                ("operation_p3", "智能制造方面，炼钢智能集控中心投入使用，冷轧智慧物流系统上线运行，厂区物流周转效率提升。公司通过生产组织优化和设备状态监测，降低非计划停机时间，提升产线协同效率。"),
            ],
        },
        {
            "id": "risk_outlook",
            "title": "三、风险因素与经营展望",
            "paragraphs": [
                ("risk_p1", "公司面临的主要风险包括钢材价格波动、铁矿石和焦煤价格变化、环保政策持续趋严以及下游行业需求不确定性。公司将通过长协采购、库存动态管理和产品结构调整降低周期波动影响。"),
                ("risk_p2", "下一年度，公司将继续推进降本增效和绿色制造，优先保障优势品种和重点客户订单，提升现金流质量。管理层将把有限资金投入环保改造、节能降碳和产品升级项目，为行业恢复阶段积累竞争基础。"),
            ],
        },
    ],
}
```

For `603421`, create the same three section IDs (`overview`, `operation`, `risk_outlook`) using these topics: 电力物联网通信业务与 HPLC/双模通信产品、国网统标与海外 AMI 项目、研发投入/芯片量产/利润分配。 Each section must contain 3, 3, and 2 paragraph tuples respectively.

For `603707`, create the same three section IDs (`overview`, `operation`, `risk_outlook`) using these topics: 肝素原料药和低分子肝素制剂业务、美国 FDA/欧洲市场/制剂出口增长、研发管线/质量合规/利润分配。 Each section must contain 3, 3, and 2 paragraph tuples respectively.

- [ ] **Step 2: Replace `MultiColumnPDF` flow helpers**

Add methods to `MultiColumnPDF`:

```python
def start_topic_document(self, title: str, subtitle: str) -> None:
    self._new_page()
    self.full_title(title)
    self.full_subtitle(subtitle)


def current_page_number(self) -> int:
    return self._page_num


def current_column(self) -> str:
    return self._cur_col


def ensure_multicolumn_page(self) -> None:
    if self._page_num == 0:
        self._new_page()
    if self._cur_col == "right" and self._cur_y > self.page_h - self.bottom_margin - 35:
        self._draw_divider()
        self._draw_page_number()
        self._new_page()


def note_box(self, title: str, lines: list[str]) -> None:
    col_x = self.left_x if self._cur_col == "left" else self.right_x
    box_h = 8 + len(lines) * 5
    if self._cur_y + box_h > self.page_h - self.bottom_margin:
        if self._cur_col == "left":
            self._switch_to_right_col()
        else:
            self._draw_divider()
            self._draw_page_number()
            self._new_page()
        col_x = self.left_x if self._cur_col == "left" else self.right_x
    self.set_xy(col_x, self._cur_y)
    self.set_draw_color(150, 150, 150)
    self.set_fill_color(245, 245, 245)
    self.rect(col_x, self._cur_y, self.col_w, box_h, style="DF")
    self.set_xy(col_x + 3, self._cur_y + 2)
    self.set_font("CN", "", 8.5)
    self.cell(self.col_w - 6, 4, title)
    self._cur_y += 7
    self.set_font("CN", "", 7.5)
    for line in lines:
        self.set_xy(col_x + 3, self._cur_y)
        self.cell(self.col_w - 6, 4, line)
        self._cur_y += 5
    self._cur_y += 4
```

- [ ] **Step 3: Add layout metadata builder**

Add helper:

```python
def _new_layout_gt(code: str, company_name: str) -> dict[str, Any]:
    return {
        "layout_type": "synthetic_multicolumn_annual_report_topic",
        "company_code": code,
        "company_name": company_name,
        "reading_order": "left_column_then_right_column",
        "pages": [],
    }
```

Add helper:

```python
def _append_layout_section(
    layout_gt: dict[str, Any],
    page: int,
    section_id: str,
    title: str,
    paragraph_ids: list[str],
) -> None:
    pages = layout_gt["pages"]
    page_entry = next((p for p in pages if p["page"] == page), None)
    if page_entry is None:
        page_entry = {
            "page": page,
            "is_multicolumn": True,
            "columns": ["left", "right"],
            "sections": [],
        }
        pages.append(page_entry)
    page_entry["sections"].append({
        "id": section_id,
        "title": title,
        "column_sequence": ["left", "right"],
        "paragraph_ids": paragraph_ids,
    })
```

- [ ] **Step 4: Rewrite `generate_multicolumn`**

Make `generate_multicolumn` return `layout_gt`:

```python
def generate_multicolumn(code: str, xbrl: dict) -> dict[str, Any]:
    name = COMPANY_NAMES.get(code, code)
    sections = parse_xbrl_sections(xbrl["table"])
    topic_sections = MULTICOLUMN_TOPIC_SECTIONS[code]
    pdf = MultiColumnPDF(name, code)
    layout_gt = _new_layout_gt(code, name)

    pdf.start_topic_document(
        f"{name} 2023 年度报告专题节选",
        f"管理层讨论与分析  |  证券代码：{code}.SH  |  合成双栏排版样本",
    )

    for section in topic_sections:
        page_before = pdf.current_page_number()
        pdf.flow_heading(section["title"], level=1)
        paragraph_ids = []
        for paragraph_id, text in section["paragraphs"]:
            paragraph_ids.append(paragraph_id)
            pdf.flow_paragraph(text)
        _append_layout_section(layout_gt, page_before, section["id"], section["title"], paragraph_ids)

        if section["id"] == "operation":
            pdf.note_box("年度经营摘要", _build_metric_box_lines(code, sections))

    _add_financial_summary_page(pdf, sections, layout_gt)
    pdf.finalize()

    out_path = MULTICOLUMN_DIR / f"{code}_multi.pdf"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out_path))
    print(f"  MultiColumn PDF → {out_path}")
    return layout_gt
```

Add `_build_metric_box_lines` in the same file. It must extract 营业收入、净利润、资产总计 from parsed XBRL sections and return three short display lines such as `营业收入：42,150,904,679.37` so the note box stays narrow.

Add `_add_financial_summary_page` in the same file. It must call `pdf.full_section_break("财务摘要")`, render one compact `full_span_table("关键财务摘要", rows, max_rows=12)`, and append this page entry to `layout_gt["pages"]`:

```python
{
    "page": pdf.current_page_number(),
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
}
```

- [ ] **Step 5: Extend `save_gt`**

Change signature:

```python
def save_gt(code: str, xbrl: dict, scene_dir: Path, suffix: str = "", layout_gt: dict[str, Any] | None = None):
```

Before writing JSON:

```python
if layout_gt is not None:
    gt["layout_gt"] = layout_gt
```

- [ ] **Step 6: Wire `main`**

Change multicolumn call:

```python
layout_gt = generate_multicolumn(code, xbrl)
save_gt(code, xbrl, MULTICOLUMN_DIR, suffix="_multi", layout_gt=layout_gt)
```

---

### Task 3: Regenerate Data

**Files:**
- Modify generated PDFs and GT files under `data/eval_dataset/synthetic_multicolumn/`

- [ ] **Step 1: Run generator**

Run:

```powershell
python sandbox/gen_synthetic_scenes.py
```

Expected:

- 3 multicolumn PDFs regenerated.
- 3 multicolumn GT JSON files regenerated with `layout_gt`.
- `synthetic_multicolumn/selection.json` remains 3 entries.

- [ ] **Step 2: Run GT contract test**

Run:

```powershell
C:\Users\24865\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe .\test\test_synthetic_multicolumn_gt.py
```

Expected: `2/2 tests passed`.

---

### Task 4: Visual Verification

**Files:**
- Create temporary preview files under `sandbox/multi_preview/`

- [ ] **Step 1: Render first three pages**

Run:

```powershell
pdftoppm -png -f 1 -l 3 .\data\eval_dataset\synthetic_multicolumn\600569_multi.pdf .\sandbox\multi_preview\600569_multi_new
pdftoppm -png -f 1 -l 3 .\data\eval_dataset\synthetic_multicolumn\603421_multi.pdf .\sandbox\multi_preview\603421_multi_new
pdftoppm -png -f 1 -l 3 .\data\eval_dataset\synthetic_multicolumn\603707_multi.pdf .\sandbox\multi_preview\603707_multi_new
```

Expected: preview PNGs show realistic annual-report two-column topic pages with both columns populated.

- [ ] **Step 2: Inspect previews**

Use image viewer on representative first pages:

- `sandbox/multi_preview/600569_multi_new-1.png`
- `sandbox/multi_preview/603421_multi_new-1.png`
- `sandbox/multi_preview/603707_multi_new-1.png`

Expected:

- Header is full-width.
- Body text is two-column.
- Right column is not mostly blank.
- Financial tables do not dominate the first pages.

---

### Task 5: Final Verification and Commit

**Files:**
- Modified implementation, tests, generated data.

- [ ] **Step 1: Run relevant tests**

Run:

```powershell
C:\Users\24865\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe .\test\test_synthetic_multicolumn_gt.py
C:\Users\24865\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe .\test\test_las_config.py
```

Expected:

- `2/2 tests passed`
- `1/1 tests passed`

- [ ] **Step 2: Inspect diff**

Run:

```powershell
git diff --stat
git status --short --untracked-files=all
```

Expected: tracked changes are limited to generator, generated multicolumn data, test file, and plan/spec docs. Unrelated untracked local files remain unstaged.

- [ ] **Step 3: Commit**

Run:

```powershell
git add sandbox/gen_synthetic_scenes.py test/test_synthetic_multicolumn_gt.py data/eval_dataset/synthetic_multicolumn docs/superpowers/plans/2026-06-08-synthetic-multicolumn.md
git commit -m "重构多栏合成数据集"
```

Expected: commit succeeds.
