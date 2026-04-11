"""Utility helpers and FPGA infrastructure context builders.

Contains frequency formatting, integer coercion, GPI/GPO formatting,
and context builders for ADXCVR, JESD204 overlay, and TPL core nodes.
"""

from __future__ import annotations

from typing import Any


def fmt_hz(hz: int) -> str:
    """Format *hz* as a human-readable frequency string (e.g. '245.76 MHz')."""
    if hz >= 1_000_000_000:
        s = f"{hz / 1_000_000_000:.6f}".rstrip("0").rstrip(".")
        return f"{s} GHz"
    if hz >= 1_000_000:
        s = f"{hz / 1_000_000:.6f}".rstrip("0").rstrip(".")
        return f"{s} MHz"
    if hz >= 1_000:
        s = f"{hz / 1_000:.3f}".rstrip("0").rstrip(".")
        return f"{s} kHz"
    return f"{hz} Hz"


def coerce_board_int(value: Any, key_path: str) -> int:
    """Convert *value* to int; raise ValueError with *key_path* context on failure."""
    if isinstance(value, bool):
        raise ValueError(f"{key_path} must be an integer, got {value!r}")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key_path} must be an integer, got {value!r}") from exc


def fmt_gpi_gpo(controls: list) -> str:
    """Format a list of int/hex values as a space-separated hex string for DTS."""
    return " ".join(f"0x{int(v):02x}" for v in controls)


def build_adxcvr_ctx(
    *,
    label: str,
    sys_clk_select: int,
    out_clk_select: int,
    clk_ref: str | None = None,
    use_div40: bool = True,
    div40_clk_ref: str | None = None,
    clock_output_names_str: str,
    use_lpm_enable: bool = True,
    jesd_l: int | None = None,
    jesd_m: int | None = None,
    jesd_s: int | None = None,
    jesd204_inputs: str | None = None,
    is_rx: bool = True,
) -> dict:
    """Build context dict for ``adxcvr.tmpl``."""
    return {
        "label": label,
        "sys_clk_select": sys_clk_select,
        "out_clk_select": out_clk_select,
        "clk_ref": clk_ref,
        "use_div40": use_div40,
        "div40_clk_ref": div40_clk_ref or clk_ref,
        "clock_output_names_str": clock_output_names_str,
        "use_lpm_enable": use_lpm_enable,
        "jesd_l": jesd_l,
        "jesd_m": jesd_m,
        "jesd_s": jesd_s,
        "jesd204_inputs": jesd204_inputs,
        "is_rx": is_rx,
    }


def build_jesd204_overlay_ctx(
    *,
    label: str,
    direction: str,
    clocks_str: str,
    clock_names_str: str,
    clock_output_name: str | None = None,
    f: int,
    k: int,
    jesd204_inputs: str,
    converter_resolution: int | None = None,
    converters_per_device: int | None = None,
    bits_per_sample: int | None = None,
    control_bits_per_sample: int | None = None,
) -> dict:
    """Build context dict for ``jesd204_overlay.tmpl``."""
    return {
        "label": label,
        "direction": direction,
        "clocks_str": clocks_str,
        "clock_names_str": clock_names_str,
        "clock_output_name": clock_output_name,
        "f": f,
        "k": k,
        "jesd204_inputs": jesd204_inputs,
        "converter_resolution": converter_resolution,
        "converters_per_device": converters_per_device,
        "bits_per_sample": bits_per_sample,
        "control_bits_per_sample": control_bits_per_sample,
    }


def build_tpl_core_ctx(
    *,
    label: str,
    compatible: str,
    direction: str,
    dma_label: str | None,
    spibus_label: str | None = None,
    jesd_label: str | None = None,
    jesd_link_offset: int,
    link_id: int,
    pl_fifo_enable: bool = False,
    sampl_clk_ref: str | None = None,
    sampl_clk_name: str | None = None,
) -> dict:
    """Build context dict for ``tpl_core.tmpl``."""
    return {
        "label": label,
        "compatible": compatible,
        "direction": direction,
        "dma_label": dma_label,
        "spibus_label": spibus_label,
        "jesd_label": jesd_label,
        "jesd_link_offset": jesd_link_offset,
        "link_id": link_id,
        "pl_fifo_enable": pl_fifo_enable,
        "sampl_clk_ref": sampl_clk_ref,
        "sampl_clk_name": sampl_clk_name,
    }
