"""ADRV937x-FMC evaluation board composite.

Pre-wires an :class:`AD9528_1` clock distributor to an :class:`ADRV9009`
transceiver (with AD9371 compatible string) following the ADRV937x-FMC
schematic.  The channel-id map mirrors the adrv937x_zc706 XSA profile.
"""

from __future__ import annotations

from ..devices.base import ClockOutput
from ..devices.clocks import AD9528_1, AD9528_1Channel
from ..devices.transceivers import ADRV9009
from .base import EvalBoard


_CLOCK_CHANNEL_MAP: dict[int, dict] = {
    1: {"name": "XCVR_REFCLK", "divider": 1, "is_sysref": False},
    3: {"name": "SYSREF_FMC", "divider": 1, "is_sysref": True},
    12: {"name": "SYSREF_DEV", "divider": 1, "is_sysref": True},
    13: {"name": "DEV_CLK", "divider": 1, "is_sysref": False},
}


class adrv937x_fmc(EvalBoard):
    """ADRV937x-FMC composite (AD9371 + AD9528 clock)."""

    def __init__(self, *, reference_frequency: int = 122_880_000) -> None:
        self.reference_frequency = reference_frequency

        channels = {
            cid: AD9528_1Channel(id=cid, **spec)
            for cid, spec in _CLOCK_CHANNEL_MAP.items()
        }
        self.clock = AD9528_1(
            label="clk0_ad9528",
            spi_max_hz=10_000_000,
            vcxo_hz=reference_frequency,
            channels=channels,
        )

        self.converter = ADRV9009(
            label="trx0_ad9371",
            node_name_base="ad9371-phy",
            compatible_strings=["adi,ad9371"],
            reset_gpio=130,
            sysref_req_gpio=136,
        )

    def _named(self, name: str) -> ClockOutput:
        for out in self.clock.clk_out:
            if out.name == name:
                return out
        raise AttributeError(f"no clock output named {name!r} on {type(self).__name__}")

    @property
    def dev_clk(self) -> ClockOutput:
        """AD9528 output feeding the transceiver device clock."""
        return self._named("DEV_CLK")

    @property
    def sysref_dev(self) -> ClockOutput:
        """Device-side SYSREF source."""
        return self._named("SYSREF_DEV")

    @property
    def sysref_fmc(self) -> ClockOutput:
        """FPGA-side SYSREF source."""
        return self._named("SYSREF_FMC")

    @property
    def xcvr_refclk(self) -> ClockOutput:
        """GT transceiver reference clock."""
        return self._named("XCVR_REFCLK")
