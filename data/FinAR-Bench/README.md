---
license: apache-2.0
---

# FinAR-Bench Dataset

[GitHub Repository](https://github.com/SAIFS-AIHub/FinAR-Bench)

This repository contains the FinAR-Bench dataset, which is designed to assess the capabilities of Large Language Models (LLMs) in performing financial fundamental analysis. The dataset focuses on three key tasks:


1. Information Extraction
2. Indicator Computation
3. Logical Reasoning


## Dataset Components

### 1. Company Tables and PDFs (`pdf_data`)
This directory contains financial statements extracted from 2023 annual reports of 100 companies listed on the Shanghai Stock Exchange (SSE). Each file is named using the company's stock code and contains the financial statement section of their annual report in PDF format.

### 2. Extracted Text (`pdf_extractor_result/txt_output`)
This directory contains text extracted from the PDF documents using six different PDF extraction tools:
- PyMuPDF
- PyPDF
- pdftotext
- PDFMiner
- Mineru
- pdfplumber

Each file is named using the company's stock code and contains the processed text output from these extraction tools.

### 3. Development Set (`dev.txt`)
Contains evaluation tasks for 10 companies, where each company's data includes:
- 6 fact extraction tasks
- 6 financial indicator computation tasks
- 1 logical reasoning task


### 4. Test Set (`test.txt`)
Contains evaluation tasks for 90 companies, following the same structure as the development set:
- 6 fact extraction tasks per company
- 6 financial indicator computation tasks per company
- 1 logical reasoning task per company



## Data Structure

The dataset is organized into several key files and directories:

1. `dev.txt` and `test.txt`: Contains the evaluation data in JSON format, with each entry including:
   - `table`: Financial statements data in markdown table format (derived from XBRL data from Shanghai Stock Exchange), including:
     - Income Statement
     - Balance Sheet
     - Cash Flow Statement
   - `instances`: A list of tasks, where each task contains:
     - `task_id`: Unique identifier for the task
     - `task`: The specific task description
     - `ground_truth`: The expected answer in markdown table format
     - `task_type`: Type of task (fact, indicator, or reasoning)
     - `task_num`: Number of items to extract/calculate
     - `company`: Company name
     - `company_code`: Stock code
     - `conditions`: (for reasoning tasks) List of conditions to evaluate

2. `pdf_extractor_result/txt_output/`: Directory containing the raw extracted text from PDFs using various PDF extraction tools

3. `pdf_data/`: Directory containing the original PDF files of financial statements




Each company's evaluation set contains 13 tasks (6 fact extraction + 6 indicator computation + 1 reasoning task), and the data is provided in three formats:
1. XBRL-derived markdown tables (in dev.txt/test.txt)
2. Extracted text files from PDFs
3. Original PDF files


## Usage

These datasets are hosted on Hugging Face and can be accessed using the Hugging Face datasets library.  
For best results, we recommend using them together with the code and evaluation scripts provided in our [GitHub Repository](https://github.com/SAIFS-AIHub/FinAR-Bench).

Example:
```python
from datasets import load_dataset
dataset = load_dataset("SAIFS-AIHub/FinAR-Bench")
# See https://github.com/SAIFS-AIHub/FinAR-Bench for code examples and evaluation scripts.
```