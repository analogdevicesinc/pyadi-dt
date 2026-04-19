"""Standalone DTS-comparison CLI.

Usage:

    python3 -m adidt.tools.dts_compare_cli REFERENCE.dts CANDIDATE.dts

Prints a diff of the kernel-critical properties between ``REFERENCE``
and ``CANDIDATE`` — handy for iterating on the System API DT emission
when you have a known-good DTS (e.g. pulled from a passing CI run's
``hw-coord-<place>-output`` artifact) and want to see at a glance
what the declarative path is doing differently.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .dts_inspect import KERNEL_CRITICAL_KEYS, compare_properties, extract_props


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Diff kernel-critical DT properties between two DTS files "
            "(e.g. XSA-pipeline output vs System-API output)."
        )
    )
    parser.add_argument("reference", type=Path, help="Reference DTS (known-good)")
    parser.add_argument("candidate", type=Path, help="Candidate DTS (under test)")
    parser.add_argument(
        "--keys",
        nargs="+",
        default=KERNEL_CRITICAL_KEYS,
        help="Subset of property keys to compare (default: every kernel-critical key).",
    )
    args = parser.parse_args(argv)

    ref = extract_props(args.reference.read_text())
    cand = extract_props(args.candidate.read_text())
    diffs = compare_properties(ref, cand, keys=args.keys)
    if not diffs:
        print("OK — no diff on kernel-critical keys.")
        return 0
    print(f"Diff on {len(diffs)} key(s):")
    for line in diffs:
        print(f"  {line}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
