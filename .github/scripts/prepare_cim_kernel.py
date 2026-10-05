#!/usr/bin/env python3
"""Prepare one kernel before reserving hardware; emit a shell export on stdout."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

# Run from any cwd with the checkout's consumer, without importing pyadi-dt.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from test.hw.kernel_artifacts import (  # noqa: E402
    CIM_RELEASES,
    cim_release,
    resolve_kernel_image,
)


def prepare(args):
    """Reuse explicit images/manifests; only invoke CIM when a build is required."""
    release = cim_release(args.release)
    os.environ["ADIDT_CIM_RELEASE"] = release
    platform = args.platform
    image_var = f"ADIDT_KERNEL_IMAGE_{platform.upper()}"
    artifact_var = f"ADIDT_KERNEL_ARTIFACTS_{platform.upper()}"
    disabled = os.environ.get("ADI_XSA_BUILD_KERNEL", "1").lower() in {
        "0",
        "false",
        "no",
    }
    if os.environ.get(image_var) or os.environ.get(artifact_var) or disabled:
        image = resolve_kernel_image(platform)
        if image is not None:
            variable = image_var if os.environ.get(image_var) else artifact_var
            print(f"export {variable}={shlex.quote(os.environ[variable])}")
        print(f"export ADIDT_CIM_RELEASE={shlex.quote(release)}")
        return
    if (
        not args.source
        or not args.version
        or not re.fullmatch(r"[0-9a-fA-F]{40}", args.version)
    ):
        raise ValueError(
            "Building requires --source and --version with an explicit full Git commit SHA"
        )
    if args.workspace is None:
        raise ValueError("Building requires --workspace (a new persistent directory)")
    workspace = args.workspace.resolve()
    if workspace.exists():
        raise ValueError(
            f"Refusing to overwrite existing workspace: {workspace}; reuse its artifacts.json instead"
        )
    spec = CIM_RELEASES[release]
    target = "adi-linux"
    output = workspace / "artifacts"
    if release != "2023_R2":
        output /= spec["builder_release"]
    output /= platform
    commands = [
        (
            [
                args.cim,
                "init",
                "--target",
                target,
                "--source",
                args.source,
                "--version",
                args.version,
                "--workspace",
                str(workspace),
                "--yes",
            ],
            None,
        ),
        ([args.cim, "makefile"], workspace),
        (
            [
                "make",
                "sdk-build",
                f"KERNEL_RELEASE={spec['builder_release']}",
                f"KERNEL_PLATFORM={platform}",
                f"KERNEL_OUTPUT={output}",
                f"KERNEL_JOBS={args.jobs}",
            ],
            workspace,
        ),
    ]
    for command, cwd in commands:
        print("+ " + shlex.join(command), file=sys.stderr)
        subprocess.run(
            command, cwd=cwd, check=True, stdout=sys.stderr, stdin=subprocess.DEVNULL
        )
    subprocess.run(
        [
            sys.executable,
            str(workspace / "scripts/build-kernel.py"),
            "--platform",
            platform,
            "--release",
            spec["builder_release"],
            "--output",
            str(output),
            "--verify",
        ],
        check=True,
        stdout=sys.stderr,
        stdin=subprocess.DEVNULL,
    )
    manifest = output / "artifacts.json"
    os.environ[artifact_var] = str(manifest)
    resolve_kernel_image(platform)
    print(f"export {artifact_var}={shlex.quote(str(manifest))}")
    print(f"export ADIDT_CIM_RELEASE={shlex.quote(release)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", required=True, choices=("zynq", "zynqmp"))
    parser.add_argument(
        "--cim",
        default="cim",
        help="Installed CIM executable (not installed by this script)",
    )
    parser.add_argument(
        "--source", help="Explicit CIM manifest Git URL or local repository"
    )
    parser.add_argument(
        "--version", help="Full pinned manifest Git commit SHA; no mutable branch/tag"
    )
    parser.add_argument(
        "--workspace", type=Path, help="New persistent CIM workspace; never removed"
    )
    parser.add_argument(
        "--release",
        choices=tuple(CIM_RELEASES),
        help="CIM kernel release (default: ADIDT_CIM_RELEASE or 2023_R2)",
    )
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    try:
        prepare(args)
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Kernel preparation failed: {exc}\n")


if __name__ == "__main__":
    main()
