"""Analyze all measurable scene dimensions from FinAR-Bench data."""
import json, os, re, fitz
from collections import defaultdict

pdf_dir = 'D:/Code/bytedanceCamp/data/FinAR-Bench/extracted/pdf_data'
all_pdfs = sorted([f for f in os.listdir(pdf_dir) if f.endswith('.pdf')])

# ============================================================================
# Dim 1: Page count
# ============================================================================
page_counts = {}
for pdf_name in all_pdfs:
    path = os.path.join(pdf_dir, pdf_name)
    code = pdf_name.replace('.pdf', '')
    try:
        doc = fitz.open(path)
        page_counts[code] = doc.page_count
        doc.close()
    except Exception:
        page_counts[code] = 0

pc = sorted(page_counts.items(), key=lambda x: x[1])
print('=== D1: Page Count ===')
print(f'  Range: {pc[0][1]} ~ {pc[-1][1]} pages, median={pc[len(pc)//2][1]}')
print(f'  Shortest 5: {pc[:5]}')
print(f'  Longest 5:  {pc[-5:]}')
print(f'  >=14 pages: {sum(1 for _,p in pc if p>=14)} companies')
print(f'  >=20 pages: {sum(1 for _,p in pc if p>=20)} companies')

# ============================================================================
# Dim 2+3+4: XBRL table complexity
# ============================================================================
xbxl = defaultdict(lambda: {
    'total_rows': 0, 'max_rows': 0,
    'total_cols': 0, 'max_cols': 0,
    'num_cells': 0, 'tables': 0,
})

for split_file in ['dev.txt', 'test.txt']:
    path = f'D:/Code/bytedanceCamp/data/FinAR-Bench/{split_file}'
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            for inst in data.get('instances', []):
                code = inst.get('company_code', '').replace('.SH', '')
                gt = inst.get('ground_truth', '')
                rows = [l for l in gt.split('\n')
                        if l.strip().startswith('|')
                        and not l.strip().startswith('|--')]
                n_rows = len(rows)
                n_cols = max(
                    (len([c for c in r.split('|') if c.strip()]) for r in rows),
                    default=0,
                )
                num_count = sum(
                    1 for r in rows
                    for c in r.split('|')
                    if re.search(r'\d', c)
                )
                xbxl[code]['total_rows'] += n_rows
                xbxl[code]['max_rows'] = max(xbxl[code]['max_rows'], n_rows)
                xbxl[code]['total_cols'] += n_cols
                xbxl[code]['max_cols'] = max(xbxl[code]['max_cols'], n_cols)
                xbxl[code]['num_cells'] += num_count
                xbxl[code]['tables'] += 1

for code in xbxl:
    t = xbxl[code]['tables']
    if t > 0:
        xbxl[code]['avg_rows'] = xbxl[code]['total_rows'] / t
        xbxl[code]['num_density'] = xbxl[code]['num_cells'] / max(xbxl[code]['total_rows'], 1)

# Print D2: Max rows
rows_s = sorted(
    [(c, xbxl[c]['max_rows']) for c in xbxl],
    key=lambda x: x[1], reverse=True,
)
print('\n=== D2: XBRL Max Table Rows ===')
print(f'  Range: {rows_s[-1][1]} ~ {rows_s[0][1]} rows')
print('  Top 5:')
for c, r in rows_s[:5]:
    print(f'    {c}: max_rows={r}, pages={page_counts.get(c,"?")}')
print('  Bottom 5:')
for c, r in rows_s[-5:]:
    print(f'    {c}: max_rows={r}')

# Print D3: Max columns
cols_s = sorted(
    [(c, xbxl[c]['max_cols']) for c in xbxl],
    key=lambda x: x[1], reverse=True,
)
print('\n=== D3: XBRL Max Table Columns ===')
print(f'  Range: {cols_s[-1][1]} ~ {cols_s[0][1]} cols')
print('  Top 5:')
for c, r in cols_s[:5]:
    print(f'    {c}: max_cols={r}')
print('  Bottom 5:')
for c, r in cols_s[-5:]:
    print(f'    {c}: max_cols={r}')

# Print D4: Numerical density
dens_s = sorted(
    [(c, xbxl[c].get('num_density', 0)) for c in xbxl],
    key=lambda x: x[1], reverse=True,
)
print('\n=== D4: Numerical Density (num_cells / total_rows) ===')
print(f'  Range: {dens_s[-1][1]:.2f} ~ {dens_s[0][1]:.2f}')
print('  Top 5:')
for c, d in dens_s[:5]:
    print(f'    {c}: density={d:.2f}')
print('  Bottom 5:')
for c, d in dens_s[-5:]:
    print(f'    {c}: density={d:.2f}')

# ============================================================================
# Dim 5: PDF text extraction quality (chars per page)
# ============================================================================
pdf_quality = {}
for pdf_name in all_pdfs:
    path = os.path.join(pdf_dir, pdf_name)
    code = pdf_name.replace('.pdf', '')
    try:
        doc = fitz.open(path)
        total_chars = 0
        total_images = 0
        for page in doc:
            text = page.get_text()
            total_chars += len(text.strip())
            total_images += len(page.get_images())
        pdf_quality[code] = {
            'chars_per_page': total_chars / max(doc.page_count, 1),
            'images_per_page': total_images / max(doc.page_count, 1),
        }
        doc.close()
    except Exception:
        pdf_quality[code] = {'chars_per_page': 0, 'images_per_page': 0}

tq_sorted = sorted(
    [(c, pdf_quality[c]['chars_per_page']) for c in pdf_quality],
    key=lambda x: x[1],
)
print('\n=== D5: PDF Text Quality (chars per page) ===')
print(f'  Range: {tq_sorted[0][1]:.0f} ~ {tq_sorted[-1][1]:.0f} chars/page')
print('  Lowest 5 (least text, potentially image-heavy):')
for c, cpp in tq_sorted[:5]:
    print(f'    {c}: {cpp:.0f} ch/p, imgs={pdf_quality[c]["images_per_page"]:.1f}/p')
print('  Highest 5:')
for c, cpp in tq_sorted[-5:]:
    print(f'    {c}: {cpp:.0f} ch/p')
print(f'  <500 ch/p: {sum(1 for _,c in tq_sorted if c<500)} companies')

# ============================================================================
# Dim 6: Parser disagreement (length ratio across reference parsers)
# ============================================================================
txt_base = 'D:/Code/bytedanceCamp/data/FinAR-Bench/extracted/pdf_extractor_result/txt_output'
parser_disagreement = {}

for code in list(page_counts.keys()):
    texts = {}
    for parser in ['mineru', 'pdfplumber', 'pymupdf', 'pdftotext']:
        txt_path = os.path.join(txt_base, parser, f'{code}.txt')
        if os.path.exists(txt_path):
            with open(txt_path, 'r', encoding='utf-8') as f:
                texts[parser] = f.read()

    if len(texts) >= 2:
        lengths = {p: len(t) for p, t in texts.items()}
        max_len = max(lengths.values())
        min_len = min(lengths.values())
        parser_disagreement[code] = max_len / max(min_len, 1)

pd_sorted = sorted(
    [(c, parser_disagreement[c]) for c in parser_disagreement],
    key=lambda x: x[1], reverse=True,
)
print('\n=== D6: Parser Disagreement (max/min text length ratio) ===')
print(f'  Range: {pd_sorted[-1][1]:.2f} ~ {pd_sorted[0][1]:.2f}')
print('  Top 10 (most disagreement = structurally challenging):')
for c, ratio in pd_sorted[:10]:
    print(f'    {c}: ratio={ratio:.2f}, pages={page_counts.get(c,"?")}')
print('  Bottom 5 (most agreement = structurally simple):')
for c, ratio in pd_sorted[-5:]:
    print(f'    {c}: ratio={ratio:.2f}')

# ============================================================================
# Dim 7: Cross-page intensity (max_rows * page_count as proxy)
# ============================================================================
cross_s = sorted(
    [(c, xbxl[c]['max_rows'] * page_counts.get(c, 1), xbxl[c]['max_rows'], page_counts.get(c, 0))
     for c in xbxl if c in page_counts],
    key=lambda x: x[1], reverse=True,
)
print('\n=== D7: Cross-page Intensity (max_rows * page_count) ===')
print('  Top 10 (most cross-page impact):')
for c, score, max_r, pages in cross_s[:10]:
    print(f'    {c}: intensity={score}, max_rows={max_r}, pages={pages}')
print('  Bottom 5:')
for c, score, max_r, pages in cross_s[-5:]:
    print(f'    {c}: intensity={score}')

# ============================================================================
# Save all computed dimensions
# ============================================================================
all_dims = {}
for code in page_counts:
    all_dims[code] = {
        'pages': page_counts.get(code, 0),
        'max_rows': xbxl[code].get('max_rows', 0),
        'avg_rows': round(xbxl[code].get('avg_rows', 0), 1),
        'max_cols': xbxl[code].get('max_cols', 0),
        'num_density': round(xbxl[code].get('num_density', 0), 3),
        'chars_per_page': round(pdf_quality.get(code, {}).get('chars_per_page', 0)),
        'images_per_page': round(pdf_quality.get(code, {}).get('images_per_page', 0), 1),
        'parser_disagreement': round(parser_disagreement.get(code, 1.0), 2),
        'cross_page_intensity': xbxl[code].get('max_rows', 0) * page_counts.get(code, 1),
    }

with open('D:/Code/bytedanceCamp/data/eval_dataset/_finarb_all_dims.json', 'w', encoding='utf-8') as f:
    json.dump(all_dims, f, ensure_ascii=False, indent=2)

print(f'\nAll dimensions saved for {len(all_dims)} companies.')
print('File: data/eval_dataset/_finarb_all_dims.json')
