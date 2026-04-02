"""Dataclass definitions for the unified board model."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ComponentModel:
    """One physical device on the board (clock chip, converter, etc.).

    Attributes:
        role: Logical role on the board — ``"clock"``, ``"adc"``, ``"dac"``,
            or ``"transceiver"``.
        part: Part number string, e.g. ``"ad9523_1"``, ``"ad9680"``.
        template: Jinja2 template filename used to render this component,
            e.g. ``"ad9523_1.tmpl"``.
        spi_bus: SPI bus label, e.g. ``"spi0"``, ``"spi1"``.
        spi_cs: SPI chip-select index.
        config: Template context dict — the same dicts that
            :mod:`adidt.model.contexts` functions produce.
    """

    role: str
    part: str
    template: str
    spi_bus: str
    spi_cs: int
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class JesdLinkModel:
    """One JESD204 link (RX or TX) with its associated FPGA IP labels and config.

    Attributes:
        direction: ``"rx"`` or ``"tx"``.
        jesd_label: AXI JESD204 IP label, e.g. ``"axi_ad9680_jesd204_rx"``.
        xcvr_label: ADXCVR IP label, e.g. ``"axi_ad9680_adxcvr"``.
        core_label: TPL core IP label, e.g. ``"axi_ad9680_tpl_adc_tpl_core"``.
        dma_label: AXI DMA IP label, e.g. ``"axi_ad9680_dma"``.
        link_params: JESD framing parameters — keys ``F``, ``K``, ``M``,
            ``L``, ``Np``, ``S``.
        xcvr_config: ADXCVR template context dict (for ``adxcvr.tmpl``).
        jesd_overlay_config: JESD overlay template context dict
            (for ``jesd204_overlay.tmpl``).
        tpl_core_config: TPL core template context dict
            (for ``tpl_core.tmpl``).
    """

    direction: str
    jesd_label: str
    xcvr_label: str
    core_label: str
    dma_label: str
    link_params: dict[str, int] = field(default_factory=dict)
    xcvr_config: dict[str, Any] = field(default_factory=dict)
    jesd_overlay_config: dict[str, Any] = field(default_factory=dict)
    tpl_core_config: dict[str, Any] = field(default_factory=dict)


@dataclass
class FpgaConfig:
    """Platform-level FPGA configuration.

    Attributes:
        platform: Target platform string, e.g. ``"zcu102"``, ``"vcu118"``.
        addr_cells: Number of address cells — ``1`` for vcu118/zc706,
            ``2`` for zcu102/vpk180.
        ps_clk_label: Processing-system clock label,
            e.g. ``"zynqmp_clk"``, ``"clkc"``.
        ps_clk_index: PS clock index (e.g. ``71``), or ``None`` when
            the platform has no PS clock index.
        gpio_label: GPIO controller label, e.g. ``"gpio"``, ``"gpio0"``.
    """

    platform: str
    addr_cells: int
    ps_clk_label: str
    ps_clk_index: int | None
    gpio_label: str


@dataclass
class BoardModel:
    """Unified board model that both the manual and XSA workflows produce.

    A ``BoardModel`` is an editable snapshot of the complete hardware
    composition.  After construction (from either workflow), callers may
    inspect and modify components, JESD links, and metadata before
    passing the model to :class:`~adidt.model.renderer.BoardModelRenderer`
    for DTS rendering.

    Attributes:
        name: Board/design name, e.g. ``"fmcdaq2_zcu102"``.
        platform: Target platform, e.g. ``"zcu102"``.
        components: Physical devices (clock chips, converters, etc.).
        jesd_links: JESD204 link definitions (RX and TX).
        fpga_config: Platform-level FPGA configuration.
        metadata: Free-form dict for rendering metadata — ``date``,
            ``config_source``, ``base_dts_include``, etc.
    """

    name: str
    platform: str
    components: list[ComponentModel] = field(default_factory=list)
    jesd_links: list[JesdLinkModel] = field(default_factory=list)
    fpga_config: FpgaConfig | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_component(self, role: str) -> ComponentModel | None:
        """Return the first component matching *role*, or ``None``."""
        for c in self.components:
            if c.role == role:
                return c
        return None

    def get_components(self, role: str) -> list[ComponentModel]:
        """Return all components matching *role*."""
        return [c for c in self.components if c.role == role]

    def get_jesd_link(self, direction: str) -> JesdLinkModel | None:
        """Return the first JESD link matching *direction*, or ``None``."""
        for link in self.jesd_links:
            if link.direction == direction:
                return link
        return None

    def get_jesd_links(self, direction: str) -> list[JesdLinkModel]:
        """Return all JESD links matching *direction*."""
        return [link for link in self.jesd_links if link.direction == direction]
