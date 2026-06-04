"""统一异常处理单元测试。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "skill" / "script"))

from error_handler import (
    ErrorCode,
    OperationResult,
    check_poll_response,
    check_submit_response,
    validate_input,
)


# ---------------------------------------------------------------------------
# 输入校验
# ---------------------------------------------------------------------------

def test_empty_url():
    result = validate_input("")
    assert not result.success
    assert result.errors[0]["code"] == ErrorCode.EMPTY_URL


def test_invalid_url_format():
    result = validate_input("not-a-url")
    assert not result.success
    assert result.errors[0]["code"] == ErrorCode.INVALID_URL_FORMAT


def test_valid_url():
    result = validate_input("https://example.com/report.pdf")
    assert result.success


def test_non_pdf_extension_warning():
    result = validate_input("https://example.com/report.txt")
    assert result.success  # 只警告不阻断
    assert len(result.warnings) >= 1
    assert result.warnings[0]["code"] == ErrorCode.UNSUPPORTED_FORMAT


# ---------------------------------------------------------------------------
# Submit 响应校验
# ---------------------------------------------------------------------------

def test_submit_success():
    response = {"metadata": {"business_code": "0", "task_id": "task-123"}}
    result = check_submit_response(response)
    assert result.success
    assert result.task_id == "task-123"


def test_submit_business_error():
    response = {"metadata": {"business_code": "1001", "error_msg": "invalid PDF"}}
    result = check_submit_response(response)
    assert not result.success


def test_submit_no_task_id():
    response = {"metadata": {"business_code": "0"}}
    result = check_submit_response(response)
    assert not result.success


# ---------------------------------------------------------------------------
# Poll 响应校验
# ---------------------------------------------------------------------------

def test_poll_completed():
    response = {
        "metadata": {"business_code": "0", "task_status": "COMPLETED"},
        "data": {"markdown": "# Report\n\ncontent", "detail": []},
    }
    result = check_poll_response(response)
    assert result.success


def test_poll_no_markdown():
    response = {
        "metadata": {"business_code": "0", "task_status": "COMPLETED"},
        "data": {"markdown": "", "detail": []},
    }
    result = check_poll_response(response)
    assert not result.success
    assert result.errors[0]["code"] == ErrorCode.NO_MARKDOWN_OUTPUT


def test_poll_task_failed():
    response = {"metadata": {"task_status": "FAILED", "error_msg": "parse error"}}
    result = check_poll_response(response)
    assert not result.success
    assert result.errors[0]["code"] == ErrorCode.TASK_FAILED


def test_poll_task_cancelled():
    response = {"metadata": {"task_status": "CANCELLED"}}
    result = check_poll_response(response)
    assert not result.success
    assert result.errors[0]["code"] == ErrorCode.TASK_CANCELLED


def test_poll_partial_pages():
    response = {
        "metadata": {"business_code": "0", "task_status": "COMPLETED"},
        "data": {
            "markdown": "content",
            "detail": [
                {"page_id": 1, "page_md": ""},
                {"page_id": 2, "page_md": "has content"},
            ],
        },
    }
    result = check_poll_response(response)
    assert result.success  # 总体成功
    assert len(result.warnings) >= 1  # 但有部分页面问题


# ---------------------------------------------------------------------------
# OperationResult
# ---------------------------------------------------------------------------

def test_operation_result_json():
    op = OperationResult(success=True)
    op.add_warning(ErrorCode.PARTIAL_PARSE, "page 3 empty")
    op_json = op.to_json()
    assert "warnings" in op_json
    assert "PARTIAL_PARSE" in op_json or "303" in op_json


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

def main() -> int:
    tests = [
        ("empty_url", test_empty_url),
        ("invalid_url_format", test_invalid_url_format),
        ("valid_url", test_valid_url),
        ("non_pdf_extension_warning", test_non_pdf_extension_warning),
        ("submit_success", test_submit_success),
        ("submit_business_error", test_submit_business_error),
        ("submit_no_task_id", test_submit_no_task_id),
        ("poll_completed", test_poll_completed),
        ("poll_no_markdown", test_poll_no_markdown),
        ("poll_task_failed", test_poll_task_failed),
        ("poll_task_cancelled", test_poll_task_cancelled),
        ("poll_partial_pages", test_poll_partial_pages),
        ("operation_result_json", test_operation_result_json),
    ]

    passed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as e:
            print(f"FAIL {name}: {e}")
        except Exception as e:
            print(f"ERROR {name}: {e}")

    print(f"\n{passed}/{len(tests)} tests passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
