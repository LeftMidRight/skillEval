"""LAS 默认配置契约测试。"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "skill" / "script"))

from las_pdf_parse import load_config


def test_default_config_matches_las_client_contract():
    config_path = PROJECT_ROOT / "skill" / "script" / "config.yaml"
    config = load_config(str(config_path))
    las = config["las"]

    assert "base_url" in las
    assert "api_key" in las
    assert "operator_id" in las
    assert "operator_version" in las


def main() -> int:
    tests = [
        ("default_config_matches_las_client_contract", test_default_config_matches_las_client_contract),
    ]

    passed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
        except AssertionError as exc:
            print(f"FAIL {name}: {exc}")
        except Exception as exc:
            print(f"ERROR {name}: {exc}")

    print(f"\n{passed}/{len(tests)} tests passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
