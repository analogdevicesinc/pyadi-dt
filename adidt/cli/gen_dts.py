"""``adidtc gen-dts`` — compose a DTS from a board-class + platform recipe.

Unlike ``xsa2dt``, this path needs neither Vivado nor an ``.xsa`` archive.
It wires a supported ``(board, platform)`` combination through the
declarative :class:`adidt.System` API and calls
:meth:`System.generate_dts` to produce a DTS overlay.

Each supported combination has a small recipe in :data:`BUILDERS` that
mirrors the example script in ``examples/``.  The optional config JSON
is applied after wiring so values from a pyadi-jif solver can drive
converter parameters (sample rate, JESD mode, decimation /
interpolation).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

import click

import adidt


def _apply_converter_cfg(converter: Any, cfg: dict | None) -> None:
    """Apply converter-level overrides from the config dict."""
    if not cfg:
        return

    mode = cfg.get("jesd204_mode")
    if isinstance(mode, list) and len(mode) == 2:
        converter.set_jesd204_mode(int(mode[0]), str(mode[1]))
    elif isinstance(mode, dict):
        converter.set_jesd204_mode(int(mode["mode"]), str(mode["class"]))

    for key in ("sample_rate", "cddc_decimation", "fddc_decimation"):
        if key in cfg.get("adc", {}):
            setattr(converter.adc, key, int(cfg["adc"][key]))

    for key in ("sample_rate", "cduc_interpolation", "fduc_interpolation"):
        if key in cfg.get("dac", {}):
            setattr(converter.dac, key, int(cfg["dac"][key]))


def _build_ad9081_fmc_zcu102(cfg: dict) -> adidt.System:
    fmc_kwargs: dict = {}
    if "reference_frequency" in cfg:
        fmc_kwargs["reference_frequency"] = int(cfg["reference_frequency"])
    fmc = adidt.eval.ad9081_fmc(**fmc_kwargs)
    _apply_converter_cfg(fmc.converter, cfg.get("converter"))

    fpga = adidt.fpga.zcu102()

    system = adidt.System(name="ad9081_zcu102", components=[fmc, fpga])
    system.connect_spi(
        bus_index=0, primary=fpga.spi[0], secondary=fmc.clock.spi, cs=0
    )
    system.connect_spi(
        bus_index=1, primary=fpga.spi[1], secondary=fmc.converter.spi, cs=0
    )
    system.add_link(
        source=fmc.converter.adc,
        sink=fpga.gt[0],
        sink_reference_clock=fmc.dev_refclk,
        sink_core_clock=fmc.core_clk_rx,
        sink_sysref=fmc.dev_sysref,
    )
    system.add_link(
        source=fpga.gt[1],
        sink=fmc.converter.dac,
        source_reference_clock=fmc.fpga_refclk_tx,
        source_core_clock=fmc.core_clk_tx,
        sink_sysref=fmc.fpga_sysref,
    )
    return system


def _build_ad9084_fmc_vpk180(cfg: dict) -> adidt.System:
    fmc_kwargs: dict = {}
    if "reference_frequency" in cfg:
        fmc_kwargs["reference_frequency"] = int(cfg["reference_frequency"])
    fmc = adidt.eval.ad9084_fmc(**fmc_kwargs)
    _apply_converter_cfg(fmc.converter, cfg.get("converter"))

    fpga = adidt.fpga.vpk180()

    system = adidt.System(name="ad9084_vpk180", components=[fmc, fpga])
    system.connect_spi(
        bus_index=0, primary=fpga.spi[0], secondary=fmc.clock.spi, cs=0
    )
    system.connect_spi(
        bus_index=0, primary=fpga.spi[0], secondary=fmc.converter.spi, cs=1
    )
    system.add_link(
        source=fmc.converter.adc,
        sink=fpga.gt[0],
        sink_reference_clock=fmc.dev_refclk,
        sink_core_clock=fmc.core_clk_rx,
        sink_sysref=fmc.dev_sysref,
    )
    system.add_link(
        source=fpga.gt[1],
        sink=fmc.converter.dac,
        source_reference_clock=fmc.fpga_refclk_tx,
        source_core_clock=fmc.core_clk_tx,
        sink_sysref=fmc.fpga_sysref,
    )
    return system


BUILDERS: dict[tuple[str, str], Callable[[dict], adidt.System]] = {
    ("ad9081_fmc", "zcu102"): _build_ad9081_fmc_zcu102,
    ("ad9084_fmc", "vpk180"): _build_ad9084_fmc_vpk180,
}


def supported_combos_text() -> str:
    return ", ".join(f"{b} + {p}" for b, p in sorted(BUILDERS.keys()))


def run_gen_dts(
    board: str,
    platform: str,
    config_path: Path,
    output: Path | None,
    compile_dtb: bool,
) -> Path:
    """Execute the ``gen-dts`` pipeline; return the DTS output path."""
    key = (board, platform)
    if key not in BUILDERS:
        raise click.UsageError(
            f"No builder for board={board!r} + platform={platform!r}. "
            f"Supported combos: {supported_combos_text()}"
        )

    cfg = json.loads(Path(config_path).read_text())
    system = BUILDERS[key](cfg)
    dts = system.generate_dts()

    out_path = Path(output) if output else Path(f"{system.name}.dts")
    if out_path.parent and not out_path.parent.exists():
        out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(dts)
    click.echo(f"Wrote {out_path}")

    if compile_dtb:
        dtc = shutil.which("dtc")
        if dtc is None:
            click.echo(
                "warning: dtc not found on PATH; skipping compile", err=True
            )
        else:
            dtb_path = out_path.with_suffix(".dtb")
            subprocess.run(
                [dtc, "-I", "dts", "-O", "dtb", "-o", str(dtb_path), str(out_path)],
                check=True,
            )
            click.echo(f"Wrote {dtb_path}")

    return out_path
