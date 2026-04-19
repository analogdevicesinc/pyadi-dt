"""FPGA-side JESD204 IP block overlay models.

Each class renders as ``&<label> { /delete-property/ ...; ...; };`` — the
DT-overlay form used to customize AXI IP nodes that a base DTS already
declares (ADXCVR, AXI JESD204 RX/TX, TPL core).

This module also exposes a small set of legacy-compatible factory
functions (``build_adxcvr_ctx``, ``build_jesd204_overlay_ctx``,
``build_tpl_core_ctx``) that construct the corresponding device and
return the rendered DTS string.  They exist purely so XSA builders can
keep their existing call shapes while the declarative devices are the
single source of truth.
"""

from .adxcvr import Adxcvr
from .jesd_overlay import Jesd204Overlay
from .tpl_core import TplCore

__all__ = [
    "Adxcvr",
    "Jesd204Overlay",
    "TplCore",
    "build_adxcvr_ctx",
    "build_jesd204_overlay_ctx",
    "build_tpl_core_ctx",
]


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
) -> str:
    """Render an :class:`Adxcvr` overlay; kwargs match the historical helper."""
    return Adxcvr(
        label=label,
        sys_clk_select=int(sys_clk_select),
        out_clk_select=int(out_clk_select),
        use_lpm_enable=bool(use_lpm_enable),
        clk_ref=clk_ref or "",
        use_div40=bool(use_div40),
        div40_clk_ref=div40_clk_ref,
        clock_output_names_str=clock_output_names_str,
        jesd_l=jesd_l,
        jesd_m=jesd_m,
        jesd_s=jesd_s,
        jesd204_inputs=jesd204_inputs,
    ).render()


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
) -> str:
    """Render a :class:`Jesd204Overlay` overlay node."""
    return Jesd204Overlay(
        label=label,
        compatible_str=f"adi,axi-jesd204-{direction}-1.0",
        f=int(f),
        k=int(k),
        converter_resolution=converter_resolution,
        bits_per_sample=bits_per_sample,
        converters_per_device=converters_per_device,
        control_bits_per_sample=control_bits_per_sample,
        direction=direction,
        clocks_str=clocks_str,
        clock_names_str=clock_names_str,
        clock_output_name=clock_output_name,
        jesd204_inputs=jesd204_inputs,
    ).render()


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
) -> str:
    """Render a :class:`TplCore` overlay node."""
    return TplCore(
        label=label,
        compatible_str=compatible,
        pl_fifo_enable=bool(pl_fifo_enable),
        direction=direction,
        dma_label=dma_label,
        spibus_label=spibus_label or "",
        jesd_label=jesd_label or "",
        jesd_link_offset=int(jesd_link_offset),
        link_id=int(link_id),
        sampl_clk_ref=sampl_clk_ref,
        sampl_clk_name=sampl_clk_name,
    ).render()
