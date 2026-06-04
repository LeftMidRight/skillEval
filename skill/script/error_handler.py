"""统一异常处理。

为 skill 提供输入校验、错误分类、友好报错。
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# 错误码定义
# ---------------------------------------------------------------------------

class ErrorCode:
    # 输入错误 (1xx)
    EMPTY_URL = 101
    INVALID_URL_FORMAT = 102
    URL_NOT_ACCESSIBLE = 103
    FILE_NOT_FOUND = 104
    UNSUPPORTED_FORMAT = 105
    EMPTY_FILE = 106
    FILE_TOO_LARGE = 107

    # API 错误 (2xx)
    API_SUBMIT_FAILED = 201
    API_POLL_FAILED = 202
    API_TIMEOUT = 203
    API_BUSINESS_ERROR = 204
    TASK_FAILED = 205
    TASK_CANCELLED = 206

    # 解析错误 (3xx)
    NO_MARKDOWN_OUTPUT = 301
    NO_TABLES_FOUND = 302
    PARTIAL_PARSE = 303


ERROR_MESSAGES = {
    ErrorCode.EMPTY_URL: "PDF URL 为空",
    ErrorCode.INVALID_URL_FORMAT: "URL 格式无效",
    ErrorCode.URL_NOT_ACCESSIBLE: "URL 无法访问",
    ErrorCode.FILE_NOT_FOUND: "文件不存在",
    ErrorCode.UNSUPPORTED_FORMAT: "不支持的文件格式（需要 PDF）",
    ErrorCode.EMPTY_FILE: "文件为空（0 字节或 0 页）",
    ErrorCode.FILE_TOO_LARGE: "文件过大",
    ErrorCode.API_SUBMIT_FAILED: "LAS 提交失败",
    ErrorCode.API_POLL_FAILED: "LAS 轮询失败",
    ErrorCode.API_TIMEOUT: "LAS 请求超时",
    ErrorCode.API_BUSINESS_ERROR: "LAS 业务错误",
    ErrorCode.TASK_FAILED: "LAS 任务执行失败",
    ErrorCode.TASK_CANCELLED: "LAS 任务已取消",
    ErrorCode.NO_MARKDOWN_OUTPUT: "解析结果为空（无 markdown 输出）",
    ErrorCode.NO_TABLES_FOUND: "解析结果中未检测到表格",
    ErrorCode.PARTIAL_PARSE: "部分页面解析失败",
}


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class SkillError:
    code: int
    message: str
    detail: str = ""
    recoverable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "detail": self.detail,
            "recoverable": self.recoverable,
        }


@dataclass
class OperationResult:
    success: bool
    task_id: str = ""
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)

    def add_error(self, code: int, detail: str = "") -> None:
        self.errors.append(SkillError(
            code=code,
            message=ERROR_MESSAGES.get(code, "未知错误"),
            detail=detail,
        ).to_dict())
        self.success = False

    def add_warning(self, code: int, detail: str = "") -> None:
        self.warnings.append(SkillError(
            code=code,
            message=ERROR_MESSAGES.get(code, "未知警告"),
            detail=detail,
            recoverable=True,
        ).to_dict())

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "task_id": self.task_id,
            "errors": self.errors,
            "warnings": self.warnings,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# 输入校验
# ---------------------------------------------------------------------------

_URL_PATTERN = re.compile(r"^https?://")

# 常见非 PDF 扩展名
_NON_PDF_EXTENSIONS = {".txt", ".doc", ".docx", ".xls", ".xlsx", ".png", ".jpg", ".jpeg"}


def validate_input(pdf_url: str) -> OperationResult:
    """校验输入参数。

    Args:
        pdf_url: PDF 文件的 URL。

    Returns:
        OperationResult，含校验结果。
    """
    result = OperationResult(success=True)

    if not pdf_url or not pdf_url.strip():
        result.add_error(ErrorCode.EMPTY_URL, "未提供 PDF URL")
        return result

    url = pdf_url.strip()

    # URL 格式
    if not _URL_PATTERN.match(url):
        result.add_error(ErrorCode.INVALID_URL_FORMAT, f"URL 必须以 http:// 或 https:// 开头: {url[:80]}")
        return result

    # 文件扩展名检查（仅警告，不阻断——URL 可能不含扩展名）
    lower_url = url.lower().split("?")[0]  # 去掉 query string
    for ext in _NON_PDF_EXTENSIONS:
        if lower_url.endswith(ext):
            result.add_warning(ErrorCode.UNSUPPORTED_FORMAT, f"URL 扩展名为 {ext}，可能不是 PDF 文件")
            break

    return result


# ---------------------------------------------------------------------------
# LAS 响应校验
# ---------------------------------------------------------------------------

def check_submit_response(response: dict[str, Any]) -> OperationResult:
    """校验 LAS submit 响应。"""
    result = OperationResult(success=True)

    metadata = response.get("metadata", {})
    business_code = str(metadata.get("business_code", ""))

    if business_code not in ("", "0"):
        error_msg = metadata.get("error_msg", "未知错误")
        result.add_error(ErrorCode.API_SUBMIT_FAILED, f"business_code={business_code}: {error_msg}")
        return result

    task_id = metadata.get("task_id") or response.get("task_id")
    if not task_id:
        result.add_error(ErrorCode.API_SUBMIT_FAILED, "响应中缺少 task_id")
        return result

    result.task_id = task_id
    return result


def check_poll_response(response: dict[str, Any]) -> OperationResult:
    """校验 LAS poll 响应。"""
    result = OperationResult(success=True)

    metadata = response.get("metadata", {})
    business_code = str(metadata.get("business_code", ""))

    if business_code not in ("", "0"):
        result.add_error(ErrorCode.API_BUSINESS_ERROR,
                         f"business_code={business_code}: {metadata.get('error_msg', '')}")
        return result

    status = str(metadata.get("task_status", "")).upper()

    if status == "FAILED":
        result.add_error(ErrorCode.TASK_FAILED, metadata.get("error_msg", "任务执行失败"))
        return result

    if status in ("CANCELED", "CANCELLED"):
        result.add_error(ErrorCode.TASK_CANCELLED, "任务已被取消")
        return result

    if status != "COMPLETED":
        result.add_warning(ErrorCode.API_TIMEOUT, f"任务状态: {status}（可能仍在处理中）")
        return result

    data = response.get("data", {})
    markdown = data.get("markdown", "")
    if not markdown:
        result.add_error(ErrorCode.NO_MARKDOWN_OUTPUT, "LAS 返回数据中无 markdown 内容")
        return result

    # 检查详细结果
    detail = data.get("detail", [])
    if detail:
        failed_pages = [
            d.get("page_id", i + 1)
            for i, d in enumerate(detail)
            if not d.get("page_md", "").strip()
        ]
        if failed_pages:
            result.add_warning(ErrorCode.PARTIAL_PARSE, f"部分页面解析为空: {failed_pages[:5]}")

    return result
