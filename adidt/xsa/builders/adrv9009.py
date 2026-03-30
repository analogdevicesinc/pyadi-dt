"""ADRV9009/9025/9026 board builder.

Handles ADRV9009, ADRV9025, and ADRV9026 transceiver designs, including both
standard single-chip and dual-chip FMComms8 layouts.
Topology match: converter IP or JESD instance names containing ``adrv9009``,
``adrv9025``, or ``adrv9026``.
"""

from __future__ import annotations

from typing import Any

from ..topology import XsaTopology

_ADRV90XX_KEYWORDS = ("adrv9009", "adrv9025", "adrv9026")


def _is_adrv90xx_name(value: str) -> bool:
    """Return True if *value* contains an ADRV9009/9025/9026 keyword."""
    lower = value.lower()
    return any(key in lower for key in _ADRV90XX_KEYWORDS)


class ADRV9009Builder:
    """Board builder for ADRV9009/9025/9026 transceiver designs."""

    def matches(self, topology: XsaTopology, cfg: dict[str, Any]) -> bool:
        if any(
            c.ip_type in {"axi_adrv9009", "axi_adrv9025", "axi_adrv9026"}
            or _is_adrv90xx_name(c.name)
            for c in topology.converters
        ):
            return True
        return any(
            _is_adrv90xx_name(j.name)
            for j in topology.jesd204_rx + topology.jesd204_tx
        )

    def build_nodes(
        self,
        node_builder: Any,
        topology: XsaTopology,
        cfg: dict[str, Any],
        ps_clk_label: str,
        ps_clk_index: int | None,
        gpio_label: str,
    ) -> list[str]:
        return node_builder._build_adrv9009_nodes(topology, cfg)

    def skips_generic_jesd(self) -> bool:
        return True

    def skip_ip_types(self) -> set[str]:
        return {"axi_adrv9009", "axi_adrv9025", "axi_adrv9026"}
