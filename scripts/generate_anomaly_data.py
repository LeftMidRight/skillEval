"""生成异常兜底评测所需的 5 种测试文件。

输出: data/eval_dataset/anomaly/
"""

import json
import os
from pathlib import Path

import fitz

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_ROOT / "data" / "eval_dataset" / "anomaly"
OUT_DIR.mkdir(parents=True, exist_ok=True)
GT_DIR = PROJECT_ROOT / "data" / "eval_dataset" / "ground_truth"
GT_DIR.mkdir(parents=True, exist_ok=True)


def _write_expected_failure_gt(
    sample_id: str,
    company_code: str,
    category: str,
    description: str,
) -> None:
    path = GT_DIR / f"{sample_id}_gt.json"
    payload = {
        "sample_id": sample_id,
        "company_code": company_code,
        "gt_kind": "expected_parse_failure",
        "expected_parse_status": "failure",
        "expected_error_category": category,
        "description": description,
        "source": "synthetic",
        "generated_by": "scripts/generate_anomaly_data.py",
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

# ============================================================================
# 1. 空 PDF（0 页）— 手动写一个最小化的空 PDF
# ============================================================================
# 构造一个合法的但有 0 页的 PDF（PyMuPDF 不允许 0 页，用二进制方式构造）
empty_pdf = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\n"
    b"xref\n0 3\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n"
    b"trailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n110\n%%EOF"
)
(OUT_DIR / "empty.pdf").write_bytes(empty_pdf)
print(f"1. empty.pdf: {len(empty_pdf)} bytes (0 pages)")

# ============================================================================
# 2. 非 PDF 文件（.txt 改名 .pdf）
# ============================================================================
txt_path = OUT_DIR / "not_a_pdf.pdf"
txt_path.write_text("This is a plain text file, not a PDF.\n这是一段普通文本，不是PDF文件。\n", encoding="utf-8")
print(f"2. not_a_pdf.pdf: {os.path.getsize(txt_path)} bytes (actually a .txt)")

# ============================================================================
# 3. 损坏 PDF（截断的 PDF 文件）
# ============================================================================
# 复制一份正常 PDF，从中间截断
src_pdf = PROJECT_ROOT / "data" / "eval_dataset" / "cross_page_tables" / "603256.pdf"
with open(src_pdf, "rb") as f:
    data = f.read()
truncated = data[:len(data) // 3]
corrupt_path = OUT_DIR / "corrupted.pdf"
corrupt_path.write_bytes(truncated)
print(f"3. corrupted.pdf: {len(truncated)} bytes (original: {len(data)} bytes, truncated to 1/3)")

# ============================================================================
# 4. 加密 PDF（带密码保护）
# ============================================================================
doc = fitz.open()
page = doc.new_page(width=595, height=842)
page.insert_text((72, 300), "This PDF is password protected.", fontname="helv", fontsize=14)
page.insert_text((72, 330), "Password: 123456", fontname="helv", fontsize=12)

enc_path = str(OUT_DIR / "encrypted.pdf")
doc.save(
    enc_path,
    encryption=fitz.PDF_ENCRYPT_AES_256,
    owner_pw="owner_secret",
    user_pw="123456",
    permissions=fitz.PDF_PERM_PRINT,
)
doc.close()
print(f"4. encrypted.pdf: {os.path.getsize(enc_path)} bytes (password: 123456)")

# ============================================================================
# 5. 文件不存在 → 不需要文件，评测时直接给不存在的路径
# 6. 超时 → 不需要文件，评测时配置 5 秒超时
# ============================================================================
print("5. file_not_found: no file needed (use non-existent path in test)")
print("6. timeout: no file needed (configure timeout=5s in test)")

_write_expected_failure_gt(
    "anomaly_corrupted",
    "anomaly_corrupted",
    "corrupted_pdf",
    "The parser should fail gracefully or return a structured error for a corrupted PDF.",
)
_write_expected_failure_gt(
    "anomaly_empty",
    "anomaly_empty",
    "zero_page_pdf",
    "The parser should fail gracefully or return a structured error for a zero-page PDF.",
)
_write_expected_failure_gt(
    "anomaly_encrypted",
    "anomaly_encrypted",
    "encrypted_pdf",
    "The parser should fail gracefully or return a structured error for an encrypted PDF.",
)
_write_expected_failure_gt(
    "anomaly_not_a_pdf",
    "anomaly_not_a_pdf",
    "not_a_pdf",
    "The parser should fail gracefully or return a structured error for a non-PDF payload.",
)

print(f"\nAll anomaly files saved to {OUT_DIR}")
for f in sorted(OUT_DIR.glob("*")):
    print(f"  {f.name} ({os.path.getsize(f)} bytes)")
