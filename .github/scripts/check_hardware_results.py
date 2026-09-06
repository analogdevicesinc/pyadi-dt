#!/usr/bin/env python3
"""Reject hardware jobs that fail or produce no passing test evidence."""

from __future__ import annotations

import argparse
import xml.etree.ElementTree as ET
from pathlib import Path


def check_results(path: Path) -> None:
    """Require at least one passing testcase and no failures or errors."""
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    if any(
        case.find("failure") is not None or case.find("error") is not None
        for case in cases
    ):
        raise ValueError("Hardware test results contain failures or errors")
    if not any(case.find("skipped") is None for case in cases):
        raise ValueError(
            "Hardware validation requires at least one passing test; no tests ran or all skipped"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("junit", type=Path)
    args = parser.parse_args()
    try:
        check_results(args.junit)
    except (OSError, ET.ParseError, ValueError) as exc:
        parser.exit(1, f"Hardware validation failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
