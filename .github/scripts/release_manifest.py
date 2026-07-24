#!/usr/bin/env python3
"""Release artifact manifest and upsert helper for adidt.

Provides deterministic SHA-256 manifest generation, verification, and idempotent
GitHub Release asset upsert across Python and Debian workflows.
"""

from __future__ import annotations

import argparse
import hashlib
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MANIFEST_NAME = "SHA256SUMS"


def compute_sha256(file_path: Path) -> str:
    """Compute SHA-256 hex digest for a given file."""
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def generate_manifest(
    files_or_dir: Path | list[Path],
    output_file: Path | None = None,
    exclude_names: set[str] | None = None,
) -> str:
    """Generate deterministic SHA-256 manifest string.

    Format per line: `<sha256>  <filename>` sorted alphabetically by filename.
    """
    if exclude_names is None:
        exclude_names = {MANIFEST_NAME, "release-notes.md"}
    else:
        exclude_names = set(exclude_names) | {MANIFEST_NAME}

    target_files: list[Path] = []
    if isinstance(files_or_dir, Path) and files_or_dir.is_dir():
        for item in files_or_dir.iterdir():
            if item.is_file() and item.name not in exclude_names:
                target_files.append(item)
    elif isinstance(files_or_dir, list):
        for item in files_or_dir:
            p = Path(item)
            if p.is_file() and p.name not in exclude_names:
                target_files.append(p)
    elif isinstance(files_or_dir, Path) and files_or_dir.is_file():
        if files_or_dir.name not in exclude_names:
            target_files.append(files_or_dir)

    target_files.sort(key=lambda p: p.name)

    lines = []
    for file_path in target_files:
        digest = compute_sha256(file_path)
        lines.append(f"{digest}  {file_path.name}")

    manifest_text = "\n".join(lines) + ("\n" if lines else "")

    if output_file is not None:
        output_file.write_text(manifest_text, encoding="utf-8")

    return manifest_text


def verify_manifest(manifest_path: Path, directory: Path) -> tuple[bool, list[str]]:
    """Verify files in directory against a SHA256SUMS manifest file."""
    if not manifest_path.exists():
        return False, [f"Manifest file not found: {manifest_path}"]

    errors: list[str] = []
    lines = manifest_path.read_text(encoding="utf-8").splitlines()

    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            errors.append(f"Line {line_num}: invalid manifest format: {line!r}")
            continue
        expected_hash, filename = parts[0], parts[1].lstrip(" *")
        file_path = directory / filename
        if not file_path.exists():
            errors.append(f"Missing file: {filename}")
            continue
        actual_hash = compute_sha256(file_path)
        if actual_hash.lower() != expected_hash.lower():
            errors.append(
                f"Checksum mismatch for {filename}: expected {expected_hash}, got {actual_hash}"
            )

    return len(errors) == 0, errors


def run_cmd(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run shell command with string output."""
    return subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=check,
    )


def upsert_github_release(
    tag: str,
    files_to_upload: list[Path],
    notes_file: Path | None = None,
    title: str | None = None,
    runner_func=run_cmd,
) -> None:
    """Robustly create/update GitHub Release, upload files, and update SHA256SUMS."""
    rel_title = title or tag

    view_proc = runner_func(["gh", "release", "view", tag], check=False)
    release_exists = view_proc.returncode == 0

    if not release_exists:
        create_cmd = ["gh", "release", "create", tag, "--verify-tag", "--title", rel_title]
        if notes_file and notes_file.exists():
            create_cmd.extend(["--notes-file", str(notes_file)])
        else:
            create_cmd.extend(["--notes", f"Release {tag}"])

        create_proc = runner_func(create_cmd, check=False)
        if create_proc.returncode != 0:
            view_proc2 = runner_func(["gh", "release", "view", tag], check=False)
            if view_proc2.returncode != 0:
                sys.stderr.write(f"Failed to create release {tag}: {create_proc.stderr}\n")
                sys.exit(create_proc.returncode)

    if release_exists and notes_file and notes_file.exists():
        edit_cmd = [
            "gh",
            "release",
            "edit",
            tag,
            "--title",
            rel_title,
            "--notes-file",
            str(notes_file),
        ]
        edit_proc = runner_func(edit_cmd, check=False)
        if edit_proc.returncode != 0:
            sys.stderr.write(f"Warning: Failed to edit release notes: {edit_proc.stderr}\n")

    valid_files = [p for p in files_to_upload if p.exists()]
    if valid_files:
        upload_cmd = ["gh", "release", "upload", tag] + [str(p) for p in valid_files] + ["--clobber"]
        runner_func(upload_cmd, check=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        dl_proc = runner_func(
            ["gh", "release", "download", tag, "-D", str(tmp_path), "--clobber"],
            check=False,
        )
        if dl_proc.returncode == 0:
            manifest_file = tmp_path / MANIFEST_NAME
            generate_manifest(tmp_path, output_file=manifest_file)
            runner_func(
                ["gh", "release", "upload", tag, str(manifest_file), "--clobber"],
                check=True,
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Release artifact manifest helper")
    subparsers = parser.add_subparsers(dest="subcommand", required=True)

    # generate
    gen_parser = subparsers.add_parser("generate", help="Generate SHA256SUMS manifest")
    gen_parser.add_argument("--dir", type=Path, help="Directory containing files")
    gen_parser.add_argument("--files", type=Path, nargs="*", help="List of files")
    gen_parser.add_argument("--output", type=Path, help="Output manifest file path")

    # verify
    ver_parser = subparsers.add_parser("verify", help="Verify files against manifest")
    ver_parser.add_argument("--manifest", type=Path, required=True, help="Manifest file path")
    ver_parser.add_argument("--dir", type=Path, required=True, help="Directory with files")

    # upsert-release
    upsert_parser = subparsers.add_parser("upsert-release", help="Upsert GitHub release & manifest")
    upsert_parser.add_argument("--tag", required=True, help="Release tag (e.g. v0.1.0)")
    upsert_parser.add_argument("--files", type=Path, nargs="*", default=[], help="Files to upload")
    upsert_parser.add_argument("--notes-file", type=Path, help="Path to release notes file")
    upsert_parser.add_argument("--title", help="Release title")

    args = parser.parse_args(argv)

    if args.subcommand == "generate":
        if args.dir:
            target = args.dir.resolve()
        elif args.files:
            target = [f.resolve() for f in args.files]
        else:
            print("ERROR: Must provide --dir or --files", file=sys.stderr)
            return 1

        manifest = generate_manifest(target, output_file=args.output)
        if not args.output:
            sys.stdout.write(manifest)
        return 0

    if args.subcommand == "verify":
        ok, errors = verify_manifest(args.manifest.resolve(), args.dir.resolve())
        if not ok:
            print("ERROR: Manifest verification failed:", file=sys.stderr)
            for err in errors:
                print(f"  - {err}", file=sys.stderr)
            return 1
        print(f"Manifest verification SUCCESS for {args.manifest}")
        return 0

    if args.subcommand == "upsert-release":
        files = [f.resolve() for f in args.files]
        notes_file = args.notes_file.resolve() if args.notes_file else None
        upsert_github_release(args.tag, files, notes_file=notes_file, title=args.title)
        print(f"Release {args.tag} upserted successfully.")
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
