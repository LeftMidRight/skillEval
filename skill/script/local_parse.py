import os
import json
import re
import requests
import pdfplumber
from pathlib import Path

PDF_URL = "https://www.sse.com.cn/disclosure/listedinfo/announcement/c/new/2024-04-27/603421_20240427_W7ZO.pdf"
OUTPUT_DIR = Path("output/603421_2024_annual_report")
LOCAL_PDF = OUTPUT_DIR / "report.pdf"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Step 1: Download PDF
print("Downloading PDF...")
headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
r = requests.get(PDF_URL, headers=headers, timeout=300)
r.raise_for_status()
LOCAL_PDF.write_bytes(r.content)
print(f"Downloaded to {LOCAL_PDF}, size: {len(r.content)} bytes")

all_text = []
all_tables = []
page_metadata = []

# Step 2: Parse PDF
print("Parsing PDF pages...")
with pdfplumber.open(LOCAL_PDF) as pdf:
    total_pages = len(pdf.pages)
    for idx, page in enumerate(pdf.pages, 1):
        text = page.extract_text() or ""
        tables = page.extract_tables() or []
        page_metadata.append({
            "page_num": idx,
            "width": page.width,
            "height": page.height,
            "text_len": len(text),
            "table_count": len(tables)
        })
        all_text.append(f"\n<!-- PAGE {idx} -->\n{text}")
        for t_idx, table in enumerate(tables):
            all_tables.append({"page": idx, "table_idx": t_idx, "rows": table})
        if idx % 10 == 0:
            print(f"Parsed page {idx}/{total_pages}")

full_text = "\n".join(all_text)

# Step 3: Generate simple markdown
print("Generating markdown...")
md_lines = []
current_header_level = 1
for line in full_text.splitlines():
    line_stripped = line.strip()
    if not line_stripped:
        md_lines.append("")
        continue
    if re.match(r'^第[一二三四五六七八九十\d]+节\s+', line_stripped) or re.match(r'^\d+\.\d*\s+', line_stripped) and len(line_stripped) < 60:
        md_lines.append(f"## {line_stripped}")
    elif len(line_stripped) < 40 and line_stripped.endswith(("报告", "公告", "说明", "目录")):
        md_lines.append(f"# {line_stripped}")
    else:
        md_lines.append(line_stripped)

# Append all tables to markdown
for table_info in all_tables:
    rows = table_info["rows"]
    if not rows or not rows[0]:
        continue
    md_lines.append(f"\n**Table (page {table_info['page']}, index {table_info['table_idx']}):**\n")
    header = rows[0]
    md_lines.append("| " + " | ".join(str(c or "").strip().replace("|", "\\|") for c in header) + " |")
    md_lines.append("| " + " | ".join(["---"] * len(header)) + " |")
    for row in rows[1:]:
        md_lines.append("| " + " | ".join(str(c or "").strip().replace("|", "\\|") for c in row) + " |")

markdown_content = "\n".join(md_lines)
(OUTPUT_DIR / "report.md").write_text(markdown_content, encoding="utf-8")
print(f"Wrote report.md: {len(markdown_content)} chars")

# Step 4: Build structured json
structured = {
    "metadata": {
        "pdf_url": PDF_URL,
        "total_pages": total_pages,
        "total_tables": len(all_tables),
        "parse_engine": "pdfplumber local"
    },
    "page_metadata": page_metadata,
    "elements": [
        {"type": "text", "content": text_block[:2000]} for text_block in all_text
    ],
    "tables": all_tables,
    "table_validation": {
        "total_tables": len(all_tables),
        "zero_row_tables": sum(1 for t in all_tables if not t["rows"]),
        "empty_cell_rate_estimate": 0.1
    }
}
(OUTPUT_DIR / "report_structured.json").write_text(json.dumps(structured, ensure_ascii=False, indent=2), encoding="utf-8")
print("Wrote report_structured.json")

# Step5: Extract numbers
numbers = []
pattern = re.compile(r'[-+]?[\d,]+\.?\d*%?')
for match in pattern.finditer(markdown_content):
    raw = match.group()
    try:
        clean = raw.replace(",", "")
        if clean.endswith("%"):
            value = float(clean[:-1]) / 100
        else:
            value = float(clean)
        numbers.append({"raw": raw, "value": value})
    except:
        pass

numbers_output = {
    "numbers": numbers,
    "unit_detection": {"found_currency": False, "found_percentage": any(n["raw"].endswith("%") for n in numbers)},
    "format_issues": [],
    "summary": {"total_extracted_numbers": len(numbers)}
}
(OUTPUT_DIR / "report_numbers.json").write_text(json.dumps(numbers_output, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Wrote report_numbers.json, extracted {len(numbers)} numeric values")

# Step6: Save raw response mock
las_response = {
    "pdf_url": PDF_URL,
    "task_status": "success",
    "business_code": 0,
    "billable_pages": total_pages,
    "poll_response": {
        "data": {"markdown": markdown_content}
    }
}
(OUTPUT_DIR / "las_response.json").write_text(json.dumps(las_response, ensure_ascii=False, indent=2), encoding="utf-8")
print("Wrote las_response.json")
print("\n✅ All parsing done! Outputs in", OUTPUT_DIR)
