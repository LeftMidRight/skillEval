"""模块 2：结构组织度（Structure Quality）。

评测 PDF 解析输出的结构质量——噪声残留、章节完整、内容连续性。
"""

from module2.evaluator import Evaluator, Module2Result

__all__ = ["Evaluator", "Module2Result"]
