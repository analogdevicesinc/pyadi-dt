"""DTC compilation tests for generated device tree overlays.

Compiles golden DTS files and PetalinuxFormatter output with ``dtc``
to catch syntax and structural errors that the built-in linter misses.

Requirements:
    - ``dtc`` on PATH or at a known PetaLinux sysroots location.

Usage:
    nox -s dtc_compile
    pytest -vs test/xsa/test_dtc_compile.py
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from adidt.xsa.merge.petalinux import PetalinuxFormatter

# ---------------------------------------------------------------------------
# dtc discovery
# ---------------------------------------------------------------------------

_DTC_FALLBACK_PATHS = [
    "/tools/Xilinx/2025.1/PetaLinux/sysroots/x86_64-petalinux-linux/usr/bin/dtc",
]


def _find_dtc() -> str | None:
    """Return the path to ``dtc``, or *None* if not found."""
    path = shutil.which("dtc")
    if path:
        return path
    for candidate in _DTC_FALLBACK_PATHS:
        if Path(candidate).is_file():
            return candidate
    return None


DTC = _find_dtc()

if DTC is None:
    pytest.skip(
        "dtc not found on PATH or known locations",
        allow_module_level=True,
    )

# ---------------------------------------------------------------------------
# Golden file discovery
# ---------------------------------------------------------------------------

_BUILDERS_DIR = Path(__file__).parent / "test_builders"
_GOLDEN_FILES = sorted(_BUILDERS_DIR.glob("golden_*.dts"))

if not _GOLDEN_FILES:
    pytest.skip(
        f"No golden_*.dts files found in {_BUILDERS_DIR}",
        allow_module_level=True,
    )

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_OVERLAY_HEADER = "/dts-v1/;\n/plugin/;\n\n"


def _compile_dts(
    content: str, tmp_path: Path, name: str
) -> subprocess.CompletedProcess:
    """Write *content* to a temp ``.dts`` file and compile with dtc."""
    dts_file = tmp_path / f"{name}.dts"
    dts_file.write_text(content)
    return subprocess.run(
        [DTC, "-@", "-I", "dts", "-O", "dtb", "-o", "/dev/null", str(dts_file)],
        capture_output=True,
        text=True,
    )


def _as_overlay(content: str) -> str:
    """Prepend the overlay header if not already present."""
    if content.lstrip().startswith("/dts-v1/"):
        return content
    return _OVERLAY_HEADER + content


def _strip_includes(content: str) -> str:
    """Remove ``#include`` lines that dtc cannot resolve."""
    return "\n".join(
        ln for ln in content.splitlines() if not ln.strip().startswith("#include")
    )


def _replace_macros(content: str) -> str:
    """Replace C preprocessor macro identifiers in DTS cell lists with ``0``.

    Golden files use macros like ``FDDC_I``, ``ADC_CLK`` as phandle
    arguments inside ``< >`` cells.  These are normally resolved by
    ``cpp`` before ``dtc`` sees the file.  We replace them with ``0``
    so ``dtc`` can parse the overlay without a preprocessor step.
    """
    import re

    def _sub_cells(m: re.Match) -> str:
        # Inside a < ... > cell list, replace bare UPPER_CASE identifiers
        return re.sub(r"\b([A-Z][A-Z_]+[A-Z])\b", "0", m.group(0))

    return re.sub(r"<[^>]+>", _sub_cells, content)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "golden_file",
    _GOLDEN_FILES,
    ids=[f.stem for f in _GOLDEN_FILES],
)
class TestDtcCompile:
    """Compile golden DTS overlays and PetalinuxFormatter output with dtc."""

    def test_golden_overlay_compiles(self, golden_file: Path, tmp_path: Path):
        """Raw golden overlay compiles as a DTS overlay."""
        content = _as_overlay(_replace_macros(golden_file.read_text()))
        result = _compile_dts(content, tmp_path, golden_file.stem)
        assert result.returncode == 0, (
            f"dtc failed on {golden_file.name}:\n{result.stderr[-2000:]}"
        )

    def test_petalinux_dtsi_compiles(self, golden_file: Path, tmp_path: Path):
        """PetalinuxFormatter output compiles as a DTS overlay."""
        raw = golden_file.read_text()
        dtsi = PetalinuxFormatter().format_system_user_dtsi(raw)
        content = _as_overlay(_strip_includes(_replace_macros(dtsi)))
        result = _compile_dts(content, tmp_path, f"{golden_file.stem}_dtsi")
        assert result.returncode == 0, (
            f"dtc failed on PetalinuxFormatter output for {golden_file.name}:\n"
            f"{result.stderr[-2000:]}"
        )

    def test_petalinux_zynqmp_dtsi_compiles(self, golden_file: Path, tmp_path: Path):
        """PetalinuxFormatter output with ZynqMP rewrite compiles."""
        raw = golden_file.read_text()
        dtsi = PetalinuxFormatter().format_system_user_dtsi(raw, platform="zcu102")
        content = _as_overlay(_strip_includes(_replace_macros(dtsi)))
        result = _compile_dts(content, tmp_path, f"{golden_file.stem}_zynqmp")
        assert result.returncode == 0, (
            f"dtc failed on ZynqMP PetalinuxFormatter output for {golden_file.name}:\n"
            f"{result.stderr[-2000:]}"
        )
