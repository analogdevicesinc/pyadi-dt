"""Shared conventions for JESD204 IP label naming and FPGA PLL-select maps.

These helpers were duplicated across ``adidt/boards/ad9081_fmc.py``,
``adidt/boards/ad9084_fmc.py``, and ``adidt/boards/adrv9009_fmc.py``.
Factoring them here lets both the legacy board builders and the new
``adidt.system.System`` converge on a single set of label conventions.
"""

from __future__ import annotations


def jesd_labels(prefix: str, direction: str) -> dict[str, str]:
    """Return the set of IP labels for one JESD204 link.

    The *prefix* usually identifies the converter family as it appears in
    the FPGA project (e.g. ``"mxfe_rx"``, ``"mxfe_tx"``, ``"ad9680"``,
    ``"ad9144"``).  *direction* must be ``"rx"`` or ``"tx"``.

    Returned keys:

    - ``jesd_label``  — AXI JESD204 link label, e.g. ``axi_mxfe_rx_jesd_rx_axi``
    - ``xcvr_label``  — ADXCVR label, e.g. ``axi_mxfe_rx_xcvr``
    - ``dma_label``   — AXI DMA label, e.g. ``axi_mxfe_rx_dma``
    - ``core_label``  — TPL core label, e.g. ``rx_mxfe_tpl_core_adc_tpl_core``

    The TPL-core label is the only one that does not follow a strict
    ``axi_<prefix>_*`` pattern; it is constructed from *direction* +
    *prefix* + ``_tpl_core_{adc|dac}_tpl_core``.
    """
    if direction not in ("rx", "tx"):
        raise ValueError(f"direction must be 'rx' or 'tx', got {direction!r}")
    side = "adc" if direction == "rx" else "dac"
    return {
        "jesd_label": f"axi_{prefix}_jesd_{direction}_axi",
        "xcvr_label": f"axi_{prefix}_xcvr",
        "dma_label": f"axi_{prefix}_dma",
        "core_label": f"{direction}_{prefix.split('_', 1)[0]}_tpl_core_{side}_tpl_core",
    }


# FPGA PLL-select translation from the string values emitted by pyadi-jif /
# the solver output to the numeric selectors understood by the ADXCVR IP.
# Keys are case-insensitive; look up with ``.upper()``.
SYS_CLK_SELECT_MAP: dict[str, int] = {
    "XCVR_CPLL": 0,
    "XCVR_QPLL1": 2,
    "XCVR_QPLL": 3,
    "XCVR_QPLL0": 3,
}

OUT_CLK_SELECT_MAP: dict[str, int] = {
    "XCVR_REFCLK": 4,
    "XCVR_REFCLK_DIV2": 4,
}


def sys_clk_select(name: str | int) -> int:
    """Resolve a ``sys_clk_select`` name or numeric passthrough to its int value."""
    if isinstance(name, int):
        return name
    return SYS_CLK_SELECT_MAP.get(str(name).upper(), 3)


def out_clk_select(name: str | int) -> int:
    """Resolve an ``out_clk_select`` name or numeric passthrough."""
    if isinstance(name, int):
        return name
    return OUT_CLK_SELECT_MAP.get(str(name).upper(), 4)
