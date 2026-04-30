"""Smoke-run each top-level ``examples/*.py`` script.

Catches the failure mode that masked the legacy ``*_dts_gen.py`` drift:
example scripts referencing removed APIs (``adidt.ad9081_fmc()``,
``.map_clocks_to_board_layout()``, ``.gen_dt()``) sat broken in the tree
because nothing imported or executed them in CI.

Each script runs as a subprocess and is expected to emit a DTS overlay
on stdout. New top-level examples that do not print a DTS should be
added to ``NON_DTS_EXAMPLES``; new examples that need extra setup
should be skip-listed explicitly with rationale.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


EXAMPLES_DIR = Path(__file__).resolve().parents[2] / "examples"
TOP_LEVEL_EXAMPLES = sorted(p.name for p in EXAMPLES_DIR.glob("*.py"))

# Examples that intentionally do not print a DTS to stdout.
NON_DTS_EXAMPLES: set[str] = set()


@pytest.mark.parametrize("script", TOP_LEVEL_EXAMPLES)
def test_top_level_example_runs(script: str) -> None:
    result = subprocess.run(
        [sys.executable, str(EXAMPLES_DIR / script)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"{script} exited {result.returncode}\nstderr:\n{result.stderr}"
    )
    if script in NON_DTS_EXAMPLES:
        return
    assert "/dts-v1/;" in result.stdout, f"{script} did not emit a DTS header"
    assert "/plugin/;" in result.stdout, (
        f"{script} did not emit an overlay header"
    )
