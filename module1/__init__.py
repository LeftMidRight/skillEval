"""模块 1：内容还原度（Content Fidelity）评测。

子指标：
  1. 文本准确率（CER）
  2. 表格还原度（Cell F1）
  3. 金融数值匹配率
"""

from module1.evaluator import Evaluator, Module1Result

__all__ = ["Evaluator", "Module1Result"]
