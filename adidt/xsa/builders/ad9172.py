"""AD9172 board builder (HMC7044 + AD9172 DAC).

Handles boards with an HMC7044 clock distribution IC and AD9172/AD9162 DAC.
Topology match: converter IP ``axi_ad9162`` or ``ad9172``/``ad9162`` in JESD names,
or ``"ad9172_board"`` key in config.
"""

from __future__ import annotations

from typing import Any

from ..topology import XsaTopology


class AD9172Builder:
    """Board builder for AD9172 DAC designs."""

    def matches(self, topology: XsaTopology, cfg: dict[str, Any]) -> bool:
        if any(c.ip_type == "axi_ad9162" for c in topology.converters):
            return True
        names = " ".join(
            j.name.lower() for j in topology.jesd204_rx + topology.jesd204_tx
        )
        if "ad9172" in names or "ad9162" in names:
            return True
        return "ad9172_board" in cfg

    def build_nodes(
        self,
        node_builder: Any,
        topology: XsaTopology,
        cfg: dict[str, Any],
        ps_clk_label: str,
        ps_clk_index: int | None,
        gpio_label: str,
    ) -> list[str]:
        return node_builder._build_ad9172_nodes(
            topology, cfg, ps_clk_label, ps_clk_index
        )

    def skips_generic_jesd(self) -> bool:
        return True

    def skip_ip_types(self) -> set[str]:
        return {"axi_ad9162"}
