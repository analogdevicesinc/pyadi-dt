"""AD9081 MxFE board builder (HMC7044 + AD9081/AD9082/AD9083).

Handles boards with an HMC7044 clock distribution IC and AD9081 MxFE converter.
Topology match: converter IP ``axi_ad9081`` AND ``mxfe`` in JESD instance names.
"""

from __future__ import annotations

from typing import Any

from ..topology import XsaTopology


class AD9081Builder:
    """Board builder for AD9081/AD9082/AD9083 MxFE designs."""

    def matches(self, topology: XsaTopology, cfg: dict[str, Any]) -> bool:
        has_ad9081 = any(c.ip_type == "axi_ad9081" for c in topology.converters)
        has_mxfe = any(
            "mxfe" in j.name.lower() for j in topology.jesd204_rx + topology.jesd204_tx
        )
        return has_ad9081 and has_mxfe

    def build_nodes(
        self,
        node_builder: Any,
        topology: XsaTopology,
        cfg: dict[str, Any],
        ps_clk_label: str,
        ps_clk_index: int | None,
        gpio_label: str,
    ) -> list[str]:
        return node_builder._build_ad9081_nodes(
            topology, cfg, ps_clk_label, ps_clk_index, gpio_label
        )

    def skips_generic_jesd(self) -> bool:
        return True

    def skip_ip_types(self) -> set[str]:
        return {"axi_ad9081"}
