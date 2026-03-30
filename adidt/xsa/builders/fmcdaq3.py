"""FMCDAQ3 board builder (AD9528 + AD9680 + AD9152).

Handles boards with an AD9528 clock generator, AD9680 ADC, and AD9152 DAC
on a shared SPI bus.  Topology match: ``has_converter_types("axi_ad9680", "axi_ad9152")``.
"""

from __future__ import annotations

from typing import Any

from ..topology import XsaTopology


class FMCDAQ3Builder:
    """Board builder for FMCDAQ3 designs."""

    def matches(self, topology: XsaTopology, cfg: dict[str, Any]) -> bool:
        return topology.is_fmcdaq3_design()

    def build_nodes(
        self,
        node_builder: Any,
        topology: XsaTopology,
        cfg: dict[str, Any],
        ps_clk_label: str,
        ps_clk_index: int | None,
        gpio_label: str,
    ) -> list[str]:
        return node_builder._build_fmcdaq3_nodes(
            topology, cfg, ps_clk_label, ps_clk_index
        )

    def skips_generic_jesd(self) -> bool:
        return True

    def skip_ip_types(self) -> set[str]:
        return {"axi_ad9680", "axi_ad9152"}
