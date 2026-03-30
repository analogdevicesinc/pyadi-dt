"""AD9084 board builder (HMC7044 + ADF4382 + dual-link AD9084).

Handles the AD9084 "apollo" dual-link design with HMC7044 clock distribution,
optional ADF4382 PLL, HSCI, and per-link JESD204 device clocks.
Topology match: converter IP ``axi_ad9084``.
"""

from __future__ import annotations

from typing import Any

from ..topology import XsaTopology


class AD9084Builder:
    """Board builder for AD9084 dual-link designs."""

    def matches(self, topology: XsaTopology, cfg: dict[str, Any]) -> bool:
        return any(c.ip_type == "axi_ad9084" for c in topology.converters)

    def build_nodes(
        self,
        node_builder: Any,
        topology: XsaTopology,
        cfg: dict[str, Any],
        ps_clk_label: str,
        ps_clk_index: int | None,
        gpio_label: str,
    ) -> list[str]:
        return node_builder._build_ad9084_nodes(
            topology, cfg, ps_clk_label, ps_clk_index, gpio_label
        )

    def skips_generic_jesd(self) -> bool:
        return True

    def skip_ip_types(self) -> set[str]:
        return {"axi_ad9084"}
