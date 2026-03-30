"""FMCDAQ2 board builder (AD9523-1 + AD9680 + AD9144).

Handles boards with an AD9523-1 clock generator, AD9680 ADC, and AD9144 DAC
on a shared SPI bus.  Topology match: ``has_converter_types("axi_ad9680", "axi_ad9144")``.
"""

from __future__ import annotations

from typing import Any

from ..topology import XsaTopology


class FMCDAQ2Builder:
    """Board builder for FMCDAQ2 designs."""

    def matches(self, topology: XsaTopology, cfg: dict[str, Any]) -> bool:
        return topology.is_fmcdaq2_design()

    def build_nodes(
        self,
        node_builder: Any,
        topology: XsaTopology,
        cfg: dict[str, Any],
        ps_clk_label: str,
        ps_clk_index: int | None,
        gpio_label: str,
    ) -> list[str]:
        return node_builder._build_fmcdaq2_nodes(
            topology, cfg, ps_clk_label, ps_clk_index
        )

    def skips_generic_jesd(self) -> bool:
        return True

    def skip_ip_types(self) -> set[str]:
        return {"axi_ad9680", "axi_ad9144"}
