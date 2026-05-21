from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable


TEXT_SUFFIXES = {
    ".bat",
    ".cfg",
    ".css",
    ".html",
    ".ini",
    ".iss",
    ".js",
    ".json",
    ".md",
    ".py",
    ".qss",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

SKIP_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".pytest-codex-tmp",
    ".ruff_cache",
    ".test-tmp",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
    ".venv",
}


def iter_text_files(root: Path) -> Iterable[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative_parts = path.relative_to(root).parts
        if any(part in SKIP_DIRS for part in relative_parts):
            continue
        if path.suffix.lower() in TEXT_SUFFIXES:
            yield path


def find_non_utf8_files(root: Path) -> list[Path]:
    failures: list[Path] = []
    for path in iter_text_files(root):
        try:
            path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            failures.append(path)
        except OSError:
            continue
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check repository text files are readable as UTF-8."
    )
    parser.add_argument(
        "root",
        nargs="?",
        default=".",
        help="Repository root to scan.",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    failures = find_non_utf8_files(root)
    if failures:
        for path in failures:
            print(path.relative_to(root), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
