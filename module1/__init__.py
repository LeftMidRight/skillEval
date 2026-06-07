"""模块 1：内容还原度（Content Fidelity）评测。

子指标：
  1. 文本准确率（CER vs 6 parsers + Mineru baseline）
  2. 表格还原度（XBRL Item Recall + Mineru TEDS/Cell F1）
  3. 数值提取率（XBRL Recall + Mineru Jaccard）
  4. 跨页表格连续性（合并成功率 + 表头保留率）

实际评测逻辑已迁移至 evaluation/module1/。
本模块仅保留共用工具函数（utils.py）和 CER 计算（text_accuracy.py）。
"""


def __getattr__(name):
    if name == "evaluate_module1":
        from evaluation.module1.evaluator import evaluate_company
        return evaluate_company
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["evaluate_module1"]
