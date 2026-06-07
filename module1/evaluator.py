"""模块 1 评测主协调器。

用法：
    evaluator = Evaluator(
        xbrl_path="data/FinAR-Bench/dev.txt",
        reference_dir="data/FinAR-Bench/extracted/pdf_extractor_result/txt_output/",
    )
    result = evaluator.evaluate("output/company_603421/las_response.json")
    print(f"Module 1 Score: {result.module1_score}")
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from module1.number_matcher import evaluate_number_accuracy
from module1.scorer import evaluate_and_score
from module1.table_fidelity import evaluate_table_fidelity
from module1.text_accuracy import evaluate_text_accuracy
from module1.utils import get_xbrl_for_company, load_xbrl_dataset


@dataclass
class SubMetricResult:
    """单个子指标的结果。"""
    score: int
    raw_metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class Module1Result:
    """模块 1 完整评测结果。"""
    company_code: str
    company_name: str
    task_id: str = ""

    # 子指标
    text_accuracy: SubMetricResult = field(default_factory=lambda: SubMetricResult(score=0))
    table_fidelity: SubMetricResult = field(default_factory=lambda: SubMetricResult(score=0))
    number_accuracy: SubMetricResult = field(default_factory=lambda: SubMetricResult(score=0))

    # 汇总
    module1_score: float = 0.0

    # 诊断
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        table_raw = self.table_fidelity.raw_metrics
        return {
            "company_code": self.company_code,
            "company_name": self.company_name,
            "task_id": self.task_id,
            "text_accuracy": {
                "score": self.text_accuracy.score,
                **self.text_accuracy.raw_metrics,
            },
            "table_fidelity": {
                "score": self.table_fidelity.score,
                "cell_f1": table_raw.get("overall", {}).get("f1", 0),
                "teds": table_raw.get("teds", {}).get("overall", 0),
                "by_statement": table_raw.get("by_statement", {}),
                "teds_by_statement": table_raw.get("teds", {}).get("by_statement", {}),
            },
            "number_accuracy": {
                "score": self.number_accuracy.score,
                **self.number_accuracy.raw_metrics,
            },
            "module1_score": self.module1_score,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class Evaluator:
    """模块 1 评测器。"""

    def __init__(
        self,
        xbrl_path: str | Path,
        xbrl_paths: list[str | Path] | None = None,
        reference_dir: str | Path | None = None,
    ):
        """
        Args:
            xbrl_path: FinAR-Bench dev.txt 或 test.txt 路径
            xbrl_paths: 多个 XBRL 数据集的路径列表（如果提供则合并）
            reference_dir: 其他解析器 txt 输出目录（用于 CER 参照）
        """
        self.xbrl_path = Path(xbrl_path)
        self.xbrl_paths = [Path(p) for p in xbrl_paths] if xbrl_paths else [self.xbrl_path]
        self.reference_dir = Path(reference_dir) if reference_dir else None
        self._xbrl_records: list[dict[str, Any]] | None = None

    @property
    def xbrl_records(self) -> list[dict[str, Any]]:
        if self._xbrl_records is None:
            self._xbrl_records = []
            for p in self.xbrl_paths:
                if p.exists():
                    self._xbrl_records.extend(load_xbrl_dataset(p))
        return self._xbrl_records

    def evaluate(
        self,
        las_output_path: str | Path,
        company_code: str | None = None,
    ) -> Module1Result:
        """评测单份 LAS 输出。

        Args:
            las_output_path: LAS 输出的 JSON 文件路径（包含 poll_response.data.markdown）
            company_code: 股票代码（如 "603421"），如未提供则从 las_output_path 文件名推断

        Returns:
            Module1Result
        """
        output_path = Path(las_output_path)

        # 推断公司代码
        if company_code is None:
            company_code = self._infer_company_code(output_path)

        # 构建结果对象
        result = Module1Result(
            company_code=company_code,
            company_name="",
        )

        # 加载 LAS 输出
        las_data = self._load_las_output(output_path)
        if las_data is None:
            result.errors.append(f"Cannot load LAS output from {output_path}")
            return result

        las_markdown = self._extract_markdown(las_data, output_path)
        if not las_markdown:
            result.errors.append("LAS output contains no markdown")
            return result

        result.task_id = las_data.get("task_id", "")

        # 查找对应公司的 XBRL 记录
        xbrl_rec = get_xbrl_for_company(self.xbrl_records, company_code)
        if xbrl_rec is None:
            result.warnings.append(
                f"Company {company_code} not found in XBRL dataset {self.xbrl_path}"
            )
            # 仍可做 CER 评测
        else:
            result.company_name = xbrl_rec.get("company", "")
            if not result.company_name:
                instances = xbrl_rec.get("instances", [])
                if instances:
                    result.company_name = instances[0].get("company", "")

        # ---- 子指标 1：文本准确率 ----
        if self.reference_dir and self.reference_dir.exists():
            text_result = evaluate_text_accuracy(
                las_markdown, self.reference_dir, company_code
            )
        else:
            text_result = {"cers": {}, "median_cer": float("nan"), "mineru_cer": None, "reference_count": 0}
            result.warnings.append("No reference parser directory provided; skipping text CER")

        from module1.scorer import text_cer_to_score
        text_cer = text_result.get("mineru_cer") or text_result.get("median_cer")
        if text_cer is None or (isinstance(text_cer, float) and text_cer != text_cer):  # NaN check
            text_cer = 1.0
        result.text_accuracy = SubMetricResult(
            score=text_cer_to_score(text_cer),
            raw_metrics=text_result,
        )

        # ---- 子指标 2：表格还原度（TEDS + Cell F1） ----
        if xbrl_rec:
            table_result = evaluate_table_fidelity(las_markdown, xbrl_rec)
        else:
            table_result = {
                "overall": {"precision": 0, "recall": 0, "f1": 0, "tp": 0, "fp": 0, "fn": 0},
                "by_statement": {},
                "teds": {"overall": 0.0, "by_statement": {}},
            }

        from module1.scorer import table_composite_score, teds_to_score, cell_f1_to_score
        teds_val = table_result.get("teds", {}).get("overall", 0.0)
        cell_f1_val = table_result["overall"]["f1"]
        table_comp = table_composite_score(teds_val, cell_f1_val)
        result.table_fidelity = SubMetricResult(
            score=int(round(table_comp)),
            raw_metrics=table_result,
        )

        # ---- 子指标 3：数值匹配率 ----
        if xbrl_rec:
            number_result = evaluate_number_accuracy(las_markdown, xbrl_rec)
        else:
            number_result = {"precision": 0, "recall": 0, "f1": 0, "tp": 0, "fp": 0, "fn": 0}

        from module1.scorer import number_f1_to_score
        result.number_accuracy = SubMetricResult(
            score=number_f1_to_score(number_result["f1"]),
            raw_metrics=number_result,
        )

        # ---- 汇总 ----
        from module1.scorer import compute_module1_score
        result.module1_score = compute_module1_score(
            result.text_accuracy.score,
            result.table_fidelity.score,
            result.number_accuracy.score,
        )

        return result

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _infer_company_code(path: Path) -> str:
        """从文件路径推断股票代码。"""
        # 尝试从路径各部分中提取 6 位数字
        import re
        for part in path.parts:
            m = re.search(r"(\d{6})", part)
            if m:
                return m.group(1)
        return path.stem

    @staticmethod
    def _load_las_output(path: Path) -> dict | None:
        """加载 LAS 输出 JSON。"""
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, FileNotFoundError) as e:
            return None

    @staticmethod
    def _extract_markdown(las_data: dict, json_path: Path = None) -> str:
        """从 LAS 响应中提取 markdown。

        尝试顺序：
        1. poll_response.data.markdown → data.markdown → markdown
        2. 同目录下的 report.md
        """
        poll = las_data.get("poll_response", {})
        if isinstance(poll, dict):
            data = poll.get("data", {})
            if isinstance(data, dict):
                md = data.get("markdown", "")
                if md:
                    return md

        data = las_data.get("data", {})
        if isinstance(data, dict):
            md = data.get("markdown", "")
            if md:
                return md

        md = las_data.get("markdown", "")
        if isinstance(md, str) and md:
            return md

        # Fallback: 同目录下的 report.md
        if json_path is not None:
            report_path = json_path.parent / "report.md"
            if report_path.exists():
                return report_path.read_text(encoding="utf-8", errors="replace")

        return ""
