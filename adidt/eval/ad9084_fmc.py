"""AD9084-FMCA-EBZ evaluation board composite (simple variant).

Composes an :class:`HMC7044` with an :class:`AD9084` following the
schematic clock-channel assignments used by
``adidt/boards/ad9084_fmc.py``.  The optional ADF4382/ADF4030 support in
the legacy board is not modeled here yet; those will plug in as
additional devices on the composite in a later phase.
"""

from __future__ import annotations

from ..devices.base import ClockOutput
from ..devices.clocks import HMC7044, ClockChannel
from ..devices.converters import AD9084
from .base import EvalBoard


# AD9084-FMCA-EBZ schematic wiring (subset used by the simple flow).
_CLOCK_CHANNEL_MAP: dict[int, dict] = {
    0: {"name": "CORE_CLK_RX", "divider": 8, "driver_mode": 2, "is_sysref": False},
    2: {"name": "DEV_REFCLK", "divider": 4, "driver_mode": 2, "is_sysref": False},
    3: {"name": "DEV_SYSREF", "divider": 1024, "driver_mode": 2, "is_sysref": True},
    6: {"name": "CORE_CLK_TX", "divider": 8, "driver_mode": 2, "is_sysref": False},
    8: {"name": "FPGA_REFCLK1", "divider": 4, "driver_mode": 2, "is_sysref": False},
    12: {"name": "FPGA_REFCLK2", "divider": 4, "driver_mode": 2, "is_sysref": False},
    13: {"name": "FPGA_SYSREF", "divider": 1024, "driver_mode": 2, "is_sysref": True},
}


class ad9084_fmc(EvalBoard):
    """AD9084-FMCA-EBZ composite."""

    def __init__(self, *, reference_frequency: int = 125_000_000) -> None:
        self.reference_frequency = reference_frequency

        channels = {
            cid: ClockChannel(id=cid, **spec)
            for cid, spec in _CLOCK_CHANNEL_MAP.items()
        }
        self.clock = HMC7044(
            label="hmc7044",
            spi_max_hz=1_000_000,
            pll1_clkin_frequencies=[reference_frequency, 10_000_000, 0, 0],
            vcxo_hz=reference_frequency,
            pll2_output_hz=reference_frequency * 20,
            channels=channels,
            pll1_loop_bandwidth_hz=200,
            pll1_ref_prio_ctrl="0xE1",
            pll1_ref_autorevert=True,
            pll1_charge_pump_ua=720,
            pfd1_max_freq_hz=1_000_000,
            sysref_timer_divider=1024,
            pulse_generator_mode=0,
            clkin0_buffer_mode="0x07",
            clkin1_buffer_mode="0x07",
            oscin_buffer_mode="0x15",
            gpi_controls=[0x00, 0x00, 0x00, 0x00],
            gpo_controls=[0x37, 0x33, 0x00, 0x00],
        )

        self.converter = AD9084(
            label="ad9084",
            firmware_name="ad9084.bin",
            subclass=1,
        )

    # Named clock-output aliases -------------------------------------------
    def _named(self, name: str) -> ClockOutput:
        for out in self.clock.clk_out:
            if out.name == name:
                return out
        raise AttributeError(f"no clock output named {name!r} on {type(self).__name__}")

    @property
    def dev_refclk(self) -> ClockOutput:
        """HMC7044 output feeding the AD9084 device reference clock."""
        return self._named("DEV_REFCLK")

    @property
    def dev_sysref(self) -> ClockOutput:
        """AD9084 SYSREF source."""
        return self._named("DEV_SYSREF")

    @property
    def fpga_sysref(self) -> ClockOutput:
        """FPGA-side SYSREF source."""
        return self._named("FPGA_SYSREF")

    @property
    def core_clk_rx(self) -> ClockOutput:
        """RX core-clock feeding the FPGA."""
        return self._named("CORE_CLK_RX")

    @property
    def core_clk_tx(self) -> ClockOutput:
        """TX core-clock feeding the FPGA."""
        return self._named("CORE_CLK_TX")

    @property
    def fpga_refclk_rx(self) -> ClockOutput:
        """RX-side GT reference clock."""
        return self._named("FPGA_REFCLK1")

    @property
    def fpga_refclk_tx(self) -> ClockOutput:
        """TX-side GT reference clock."""
        return self._named("FPGA_REFCLK2")
