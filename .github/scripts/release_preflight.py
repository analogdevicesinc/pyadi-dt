#!/usr/bin/env python3
"""Release preflight validation script for adidt.

Validates release tag format, matches version numbers across pyproject.toml and
adidt/__init__.py, and extracts release notes from CHANGELOG.md.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - exercised on Python 3.10 CI
    tomllib = None

TAG_REGEX = re.compile(
    r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[-+][0-9A-Za-z.-]+)?$"
)


def validate_tag_format(tag: str) -> str:
    """Validate v-prefixed tag format and return the bare version string."""
    if not TAG_REGEX.fullmatch(tag):
        raise ValueError(f"invalid release tag format: {tag!r}")
    return tag.removeprefix("v")


def get_pyproject_version(repo_dir: Path) -> str:
    """Extract project version from pyproject.toml."""
    pyproject_path = repo_dir / "pyproject.toml"
    if not pyproject_path.exists():
        raise FileNotFoundError(f"pyproject.toml not found at {pyproject_path}")
    content = pyproject_path.read_text(encoding="utf-8")
    if tomllib is not None:
        return tomllib.loads(content)["project"]["version"]

    project_match = re.search(
        r"^\[project\]\s*$\n(?P<body>.*?)(?=^\[|\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    )
    if not project_match:
        raise ValueError("pyproject.toml has no [project] table")
    version_match = re.search(
        r'^version\s*=\s*["\'](?P<version>[^"\']+)["\']\s*$',
        project_match.group("body"),
        re.MULTILINE,
    )
    if not version_match:
        raise ValueError("pyproject.toml [project] table has no static version")
    return version_match.group("version")


def get_init_version(repo_dir: Path) -> str:
    """Extract __version__ from adidt/__init__.py using AST parsing."""
    init_path = repo_dir / "adidt" / "__init__.py"
    if not init_path.exists():
        raise FileNotFoundError(f"adidt/__init__.py not found at {init_path}")
    tree = ast.parse(init_path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__version__":
                    return ast.literal_eval(node.value)
    raise ValueError("adidt/__init__.py does not define __version__")


def extract_changelog_notes(repo_dir: Path, version: str) -> str:
    """Extract release notes for version from CHANGELOG.md."""
    changelog_path = repo_dir / "CHANGELOG.md"
    if not changelog_path.exists():
        raise FileNotFoundError(f"CHANGELOG.md not found at {changelog_path}")
    content = changelog_path.read_text(encoding="utf-8")
    escaped_ver = re.escape(version)
    pattern = rf"^## \[{escaped_ver}\].*?\n(?P<body>.*?)(?=^## \[|^\[Unreleased\]:|\Z)"
    match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
    if not match:
        raise ValueError(f"CHANGELOG.md has no section for version {version!r}")
    body = match.group("body").strip()
    if not body:
        raise ValueError(f"CHANGELOG.md section for version {version!r} is empty")
    return body + "\n"


def run_preflight(tag: str, repo_dir: Path) -> tuple[str, str, str]:
    """Run full preflight validation.

    Returns:
        (tag, version, release_notes)
    """
    version = validate_tag_format(tag)
    pyproject_ver = get_pyproject_version(repo_dir)
    init_ver = get_init_version(repo_dir)

    if len({version, pyproject_ver, init_ver}) != 1:
        raise ValueError(
            f"version mismatch: tag={version!r}, pyproject.toml={pyproject_ver!r}, "
            f"adidt.__version__={init_ver!r}"
        )

    notes = extract_changelog_notes(repo_dir, version)
    return tag, version, notes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Release preflight validation")
    parser.add_argument("--tag", required=True, help="Release tag (e.g. v0.1.0)")
    parser.add_argument(
        "--repo-dir",
        type=Path,
        default=Path("."),
        help="Path to repository root (default: current directory)",
    )
    parser.add_argument(
        "--github-output",
        type=Path,
        help="Path to write GITHUB_OUTPUT key-value pairs",
    )
    parser.add_argument(
        "--notes-output",
        type=Path,
        help="Path to write extracted release notes markdown file",
    )

    args = parser.parse_args(argv)
    repo_dir = args.repo_dir.resolve()

    try:
        tag, version, notes = run_preflight(args.tag, repo_dir)
    except Exception as exc:
        print(f"ERROR: release preflight failed: {exc}", file=sys.stderr)
        return 1

    print(f"Preflight validation SUCCESS: tag={tag}, version={version}")

    if args.github_output:
        with args.github_output.open("a", encoding="utf-8") as f:
            f.write(f"tag={tag}\n")
            f.write(f"version={version}\n")

    if args.notes_output:
        args.notes_output.write_text(notes, encoding="utf-8")
        print(f"Wrote release notes to {args.notes_output}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
