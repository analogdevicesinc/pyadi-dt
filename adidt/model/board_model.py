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
        spi_bus: SPI bus label, e.g. ``"spi0"``, ``"spi1"``.
        spi_cs: SPI chip-select index.
        rendered: Pre-rendered DT node string emitted by the device's
            :meth:`render_dt` method.  The renderer inserts this
            verbatim into the SPI-bus group for *spi_bus*.
        template, config: Legacy fields (Jinja2 template name + context
            dict) kept for backwards compatibility with code that still
            constructs ``ComponentModel`` by hand.  The current
            renderer ignores them when ``rendered`` is set.
    """

    role: str
    part: str
    spi_bus: str
    spi_cs: int
    rendered: str | None = None
    template: str = ""
    config: dict[str, Any] = field(default_factory=dict)


@dataclass
class JesdLinkModel:
    """One JESD204 link (RX or TX) with its FPGA-side IP labels and rendered overlays.

    Attributes:
        direction: ``"rx"`` or ``"tx"``.
        jesd_label: AXI JESD204 IP label, e.g. ``"axi_ad9680_jesd204_rx"``.
        xcvr_label: ADXCVR IP label, e.g. ``"axi_ad9680_adxcvr"``.
        core_label: TPL core IP label, e.g. ``"axi_ad9680_tpl_adc_tpl_core"``.
        dma_label: AXI DMA IP label, e.g. ``"axi_ad9680_dma"``.
        link_params: JESD framing parameters — keys ``F``, ``K``, ``M``,
            ``L``, ``Np``, ``S``.
        dma_clocks_str: Optional ``clocks`` cells-string for the DMA
            overlay (inserted verbatim into the emitted overlay).
        xcvr_rendered, jesd_overlay_rendered, tpl_core_rendered:
            Pre-rendered DTS strings for the three FPGA-side IP
            overlays.  Produced by :mod:`adidt.devices.fpga_ip`.
    """

    direction: str
    jesd_label: str
    xcvr_label: str
    core_label: str
    dma_label: str | None
    link_params: dict[str, int] = field(default_factory=dict)
    dma_clocks_str: str | None = None
    xcvr_rendered: str | None = None
    jesd_overlay_rendered: str | None = None
    tpl_core_rendered: str | None = None


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
    extra_nodes: list[str] = field(default_factory=list)

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

    def to_dts(self, output_path: str, config_source: str = "board_model") -> str:
        """Render this model to a standalone DTS file.

        Convenience method that renders via :class:`BoardModelRenderer`
        and writes the output with SPDX header and metadata.

        Args:
            output_path: Path to write the DTS file.
            config_source: Config source string for the metadata header.

        Returns:
            The *output_path* string.
        """
        from datetime import datetime

        from .renderer import BoardModelRenderer

        nodes = BoardModelRenderer().render(self)
        all_nodes = []
        for key in ("clkgens", "jesd204_rx", "jesd204_tx", "converters"):
            all_nodes.extend(nodes.get(key, []))

        lines = [
            "// SPDX-License-Identifier: GPL-2.0",
            f"// AUTOGENERATED BY PYADI-DT {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "/*",
            f" * Platform: {self.platform}",
            f" * Generated from: {config_source}",
            f" * Board model: {self.name}",
            " */",
            "",
            "/dts-v1/;",
            "/plugin/;",
            "",
            "\n\n".join(all_nodes),
            "",
        ]

        with open(output_path, "w") as f:
            f.write("\n".join(lines))

        return output_path

    def to_dict(self) -> dict[str, Any]:
        """Serialize the model to a plain dict (JSON-compatible).

        Useful for debugging, logging, and sharing configurations.
        """
        from dataclasses import asdict

        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BoardModel":
        """Deserialize a ``BoardModel`` from a dict (as produced by :meth:`to_dict`).

        Args:
            data: Dict with keys matching ``BoardModel`` fields.

        Returns:
            A new ``BoardModel`` instance.
        """
        fpga = data.get("fpga_config")
        if fpga and isinstance(fpga, dict):
            fpga = FpgaConfig(**fpga)

        components = [
            ComponentModel(**c) if isinstance(c, dict) else c
            for c in data.get("components", [])
        ]
        jesd_links = [
            JesdLinkModel(**j) if isinstance(j, dict) else j
            for j in data.get("jesd_links", [])
        ]
        return cls(
            name=data["name"],
            platform=data["platform"],
            components=components,
            jesd_links=jesd_links,
            fpga_config=fpga,
            metadata=data.get("metadata", {}),
            extra_nodes=data.get("extra_nodes", []),
        )
