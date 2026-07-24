"""Opt-in real SDTGen integration test for the Tcl driver POC."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from adidt.sdt import stage_sdt_repository
from adidt.xsa.parse.sdtgen import SdtgenRunner

UPSTREAM = os.environ.get("ADIDT_SDT_UPSTREAM")
XSA = os.environ.get("ADIDT_SDT_XSA")
DRIVERS = Path(__file__).resolve().parents[2] / "adidt/sdt/drivers"
RX_LABELS = (
    "axi_adrv9009_rx_jesd_rx_axi",
    "axi_adrv9009_rx_os_jesd_rx_axi",
)

requires_sdtgen_fixture = pytest.mark.skipif(
    not (UPSTREAM and XSA),
    reason="set ADIDT_SDT_UPSTREAM and ADIDT_SDT_XSA for real SDTGen integration",
)


def _node_block(text: str, label: str) -> str:
    match = re.search(rf"\b{re.escape(label)}\s*:.*?\n\s*\}};", text, re.DOTALL)
    assert match is not None, f"SDTGen did not emit {label}"
    return match.group()


@requires_sdtgen_fixture
def test_adrv9009_zc706_rx_driver_with_real_sdtgen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Stage the driver, run HSI on the real XSA, and compile its SDT."""
    assert UPSTREAM is not None
    assert XSA is not None
    staged = tmp_path / "system-device-tree-xlnx"
    output = tmp_path / "output"
    output.mkdir()
    manifest = stage_sdt_repository(UPSTREAM, staged, DRIVERS)
    monkeypatch.setenv("CUSTOM_SDT_REPO", str(staged))

    system_top = SdtgenRunner().run(Path(XSA), output, timeout=300)

    assert manifest.is_file()
    pl_text = (output / "pl.dtsi").read_text()
    for label in RX_LABELS:
        block = _node_block(pl_text, label)
        assert 'compatible = "adi,axi-jesd204-rx-1.0";' in block
        assert "xlnx,axi-jesd204-rx-1.0" not in block

    if shutil.which("cpp") and shutil.which("dtc"):
        preprocessed = output / "system-top.pp.dts"
        dtb = output / "system-top.dtb"
        with preprocessed.open("w") as stream:
            cpp = subprocess.run(
                [
                    "cpp",
                    "-nostdinc",
                    "-undef",
                    "-x",
                    "assembler-with-cpp",
                    "-I",
                    str(output),
                    str(system_top),
                ],
                stdout=stream,
                text=True,
                timeout=60,
                check=False,
            )
        assert cpp.returncode == 0
        dtc = subprocess.run(
            ["dtc", "-I", "dts", "-O", "dtb", "-o", str(dtb), str(preprocessed)],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert dtc.returncode == 0, dtc.stderr
        assert dtb.stat().st_size > 0
