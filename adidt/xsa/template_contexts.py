"""Typed context dataclasses for Jinja2 DTS node templates.

Each dataclass corresponds to a ``.tmpl`` template in ``adidt/templates/xsa/``
and defines the exact fields that the template expects.  Using typed contexts
instead of raw dicts ensures that all call sites for a shared template produce
the same shape, catching mismatches at construction time.

Usage::

    ctx = AdxcvrContext(label="axi_ad9680_adxcvr", sys_clk_select=0, ...)
    rendered = node_builder._render("adxcvr.tmpl", ctx.as_dict())
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class AdxcvrContext:
    """Context for ``adxcvr.tmpl`` (Xilinx transceiver overlay node).

    Used by FMCDAQ2, FMCDAQ3, AD9084, AD9172, and ADRV9009 builders.
    """

    label: str
    sys_clk_select: int
    out_clk_select: int
    clk_ref: str
    use_div40: bool
    div40_clk_ref: Optional[str]
    clock_output_names_str: str
    use_lpm_enable: bool
    jesd_l: Optional[int]
    jesd_m: Optional[int]
    jesd_s: Optional[int]
    jesd204_inputs: Optional[str]
    is_rx: bool

    def as_dict(self) -> dict[str, Any]:
        """Convert to a template context dict."""
        return dataclasses.asdict(self)


@dataclass
class Jesd204OverlayContext:
    """Context for ``jesd204_overlay.tmpl`` (JESD204 link-layer overlay node).

    Used by FMCDAQ2, FMCDAQ3, AD9084, AD9172, and ADRV9009 builders.
    """

    label: str
    direction: str  # "rx" or "tx"
    clocks_str: str
    clock_names_str: str
    clock_output_name: Optional[str]
    f: int
    k: int
    jesd204_inputs: str
    converter_resolution: Optional[int]
    converters_per_device: Optional[int]
    bits_per_sample: Optional[int]
    control_bits_per_sample: Optional[int]

    def as_dict(self) -> dict[str, Any]:
        """Convert to a template context dict."""
        return dataclasses.asdict(self)


@dataclass
class TplCoreContext:
    """Context for ``tpl_core.tmpl`` (JESD204 transport-protocol-layer core).

    Used by FMCDAQ2, FMCDAQ3, AD9084, AD9081, and AD9172 builders.
    """

    label: str
    compatible: str
    direction: str  # "rx" or "tx"
    dma_label: str
    spibus_label: str
    jesd_label: str
    jesd_link_offset: int
    link_id: int
    pl_fifo_enable: bool
    sampl_clk_ref: Optional[str]
    sampl_clk_name: Optional[str]

    def as_dict(self) -> dict[str, Any]:
        """Convert to a template context dict."""
        return dataclasses.asdict(self)


@dataclass
class Hmc7044ChannelContext:
    """Context for one HMC7044 channel child node."""

    id: int
    name: str
    divider: int
    freq_str: str
    driver_mode: int = 2
    coarse_digital_delay: Optional[int] = None
    startup_mode_dynamic: bool = False
    high_perf_mode_disable: bool = False
    is_sysref: bool = False

    def as_dict(self) -> dict[str, Any]:
        """Convert to a template context dict."""
        return dataclasses.asdict(self)


@dataclass
class Hmc7044Context:
    """Context for ``hmc7044.tmpl`` (HMC7044 clock distribution IC).

    Used by AD9084, AD9081, AD9172, and ADRV9009 (FMComms8) builders.
    """

    label: str
    cs: int
    spi_max_hz: int
    pll1_clkin_frequencies: list[int]
    vcxo_hz: int
    pll2_output_hz: int
    clock_output_names_str: str
    jesd204_sysref_provider: bool = True
    jesd204_max_sysref_hz: int = 2_000_000
    pll1_loop_bandwidth_hz: Optional[int] = None
    pll1_ref_prio_ctrl: Optional[str] = None
    pll1_ref_autorevert: bool = False
    pll1_charge_pump_ua: Optional[int] = None
    pfd1_max_freq_hz: Optional[int] = None
    sysref_timer_divider: Optional[int] = None
    pulse_generator_mode: Optional[int] = None
    clkin0_buffer_mode: Optional[str] = None
    clkin1_buffer_mode: Optional[str] = None
    clkin2_buffer_mode: Optional[str] = None
    clkin3_buffer_mode: Optional[str] = None
    oscin_buffer_mode: Optional[str] = None
    gpi_controls_str: str = ""
    gpo_controls_str: str = ""
    sync_pin_mode: Optional[int] = None
    high_perf_mode_dist_enable: bool = False
    clkin0_ref: Optional[str] = None
    channels: Optional[list[dict[str, Any]]] = None
    raw_channels: Optional[str] = None

    def as_dict(self) -> dict[str, Any]:
        """Convert to a template context dict."""
        return dataclasses.asdict(self)


@dataclass
class ClkgenContext:
    """Context for ``clkgen.tmpl`` (AXI clock generator overlay node)."""

    instance: Any  # ClkgenInstance (uses .name and .base_addr)
    ps_clk_label: str
    ps_clk_index: Optional[int]

    def as_dict(self) -> dict[str, Any]:
        """Convert to a template context dict."""
        return dataclasses.asdict(self)


@dataclass
class Ad9523Context:
    """Context for ``ad9523_1.tmpl`` (AD9523-1 clock generator)."""

    label: str
    cs: int
    spi_max_hz: int
    vcxo_hz: int
    gpio_lines: list[dict[str, Any]]
    channels: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        """Convert to a template context dict."""
        return dataclasses.asdict(self)


@dataclass
class Ad9528Context:
    """Context for ``ad9528.tmpl`` and ``ad9528_1.tmpl`` (AD9528 clock generator)."""

    label: str
    cs: int
    spi_max_hz: int
    vcxo_hz: int
    gpio_lines: list[dict[str, Any]]
    channels: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        """Convert to a template context dict."""
        return dataclasses.asdict(self)


@dataclass
class Ad9680Context:
    """Context for ``ad9680.tmpl`` (AD9680 ADC)."""

    label: str
    cs: int
    spi_max_hz: int
    use_spi_3wire: bool
    clks_str: str
    clk_names_str: str
    sampling_frequency_hz: int
    m: int
    l: int
    f: int
    k: int
    np: int
    jesd204_top_device: int
    jesd204_link_ids: list[int]
    jesd204_inputs: str
    gpio_lines: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        """Convert to a template context dict."""
        return dataclasses.asdict(self)


@dataclass
class Ad9144Context:
    """Context for ``ad9144.tmpl`` (AD9144 DAC)."""

    label: str
    cs: int
    spi_max_hz: int
    clk_ref: str
    jesd204_top_device: int
    jesd204_link_ids: list[int]
    jesd204_inputs: str
    gpio_lines: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        """Convert to a template context dict."""
        return dataclasses.asdict(self)


@dataclass
class Ad9152Context:
    """Context for ``ad9152.tmpl`` (AD9152 DAC)."""

    label: str
    cs: int
    spi_max_hz: int
    clk_ref: str
    jesd_link_mode: int
    jesd204_top_device: int
    jesd204_link_ids: list[int]
    jesd204_inputs: str
    gpio_lines: list[dict[str, Any]]

    def as_dict(self) -> dict[str, Any]:
        """Convert to a template context dict."""
        return dataclasses.asdict(self)


@dataclass
class Ad9172DeviceContext:
    """Context for ``ad9172.tmpl`` (AD9172 DAC device node)."""

    label: str
    cs: int
    spi_max_hz: int
    clk_ref: str
    dac_rate_khz: int
    jesd_link_mode: int
    dac_interpolation: int
    channel_interpolation: int
    clock_output_divider: int
    jesd_link_ids: list[int]
    jesd204_inputs: str

    def as_dict(self) -> dict[str, Any]:
        """Convert to a template context dict."""
        return dataclasses.asdict(self)
