#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

FORBIDDEN_DIR_NAMES = {
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "htmlcov",
    "recordings",
    "uploads",
    "backups",
}
FORBIDDEN_SUFFIXES = {".pem", ".key"}
SUSPICIOUS_NAME_PARTS = {"secret", "token", "credential", "passwd", "password"}


def _relative_items(root: Path) -> list[Path]:
    items = [path.relative_to(root) for path in root.rglob("*")]
    items.sort()
    return items


def find_release_package_issues(root: Path) -> list[str]:
    issues: list[str] = []
    for relative_path in _relative_items(root):
        parts = set(relative_path.parts)
        name = relative_path.name
        lowered_name = name.casefold()

        if parts & FORBIDDEN_DIR_NAMES:
            issues.append(f"forbidden_path:{relative_path.as_posix()}")
            continue

        if lowered_name == ".env" or (
            lowered_name.startswith(".env.") and lowered_name != ".env.example"
        ):
            issues.append(f"forbidden_env:{relative_path.as_posix()}")
            continue

        if relative_path.suffix.casefold() in FORBIDDEN_SUFFIXES:
            issues.append(f"forbidden_secret_file:{relative_path.as_posix()}")
            continue

        stem_words = {
            word
            for token in lowered_name.replace(".", "-").replace("_", "-").split("-")
            for word in [token]
            if word
        }
        if stem_words & SUSPICIOUS_NAME_PARTS:
            issues.append(f"suspicious_name:{relative_path.as_posix()}")

    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate that a staged release package does not contain local or secret material."
        )
    )
    parser.add_argument(
        "package_root",
        nargs="?",
        default=".",
        help="Path to the staged release package root",
    )
    args = parser.parse_args(argv)

    root = Path(args.package_root).resolve()
    if not root.is_dir():
        print(f"Package root is not a directory: {root}", file=sys.stderr)
        return 2

    issues = find_release_package_issues(root)
    if not issues:
        print(f"Release package OK: {root}")
        return 0

    print(f"Release package check failed for: {root}", file=sys.stderr)
    for issue in issues:
        print(issue, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
