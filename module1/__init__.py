"""模块 1：内容还原度（Content Fidelity）评测。

子指标：
  1. 文本准确率（CER vs 6 parsers + Mineru baseline）
  2. 表格还原度（XBRL Item Recall + Mineru TEDS/Cell F1）
  3. 数值提取率（XBRL Recall + Mineru Jaccard）

实际评测逻辑已迁移至 evaluation/module1/。
本模块仅保留共用工具函数（utils.py）和 CER 计算（text_accuracy.py）。
"""

from evaluation.module1.evaluator import evaluate_company as evaluate_module1

__all__ = ["evaluate_module1"]
