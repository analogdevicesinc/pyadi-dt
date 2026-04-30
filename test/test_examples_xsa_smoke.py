"""Import-smoke each ``examples/xsa/*.py`` script.

The xsa examples are guarded by ``if __name__ == "__main__":`` so
importing them does *not* run their network or pipeline calls; the
import alone validates syntax + that every top-level reference (helper
imports, function signatures) still resolves against the current API.

This is the cheap counterpart to ``test_example_fmcdaq2_zc706.py``,
which exercises an example end-to-end with mocked solver / pipeline.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


XSA_DIR = (Path(__file__).resolve().parent / ".." / "examples" / "xsa").resolve()
XSA_EXAMPLES = sorted(p.name for p in XSA_DIR.glob("*.py"))


@pytest.mark.parametrize("script", XSA_EXAMPLES)
def test_xsa_example_imports(script: str) -> None:
    spec = importlib.util.spec_from_file_location(
        f"_xsa_example_{script[:-3]}", XSA_DIR / script
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
