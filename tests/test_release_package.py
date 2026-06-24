from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_release_package import find_release_package_issues


pytestmark = pytest.mark.unit


def test_release_package_check_accepts_clean_tree(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("ok", encoding="utf-8")
    (tmp_path / "python-processor").mkdir()
    (tmp_path / "python-processor" / "main.py").write_text("print('ok')\n", encoding="utf-8")

    assert find_release_package_issues(tmp_path) == []


def test_release_package_check_rejects_env_and_runtime_data(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("SECRET=1\n", encoding="utf-8")
    (tmp_path / "uploads").mkdir()
    (tmp_path / "uploads" / "capture.bin").write_bytes(b"x")

    issues = find_release_package_issues(tmp_path)

    assert "forbidden_env:.env" in issues
    assert "forbidden_path:uploads" in issues or "forbidden_path:uploads/capture.bin" in issues


def test_release_package_check_rejects_secret_like_names(tmp_path: Path) -> None:
    (tmp_path / "api-token.txt").write_text("value\n", encoding="utf-8")
    (tmp_path / "tls.pem").write_text("pem\n", encoding="utf-8")

    issues = find_release_package_issues(tmp_path)

    assert "suspicious_name:api-token.txt" in issues
    assert "forbidden_secret_file:tls.pem" in issues
