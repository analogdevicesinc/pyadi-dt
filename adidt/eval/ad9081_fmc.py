"""AD9081-FMC-EBZ evaluation board composite.

Pre-wires an :class:`HMC7044` clock distributor to an :class:`AD9081`
MxFE transceiver following the AD9081-FMC-EBZ schematic, and exposes
named clock-output aliases so users can write
``system.add_link(sink_reference_clock=fmc.clock.dev_refclk)`` instead
of threading integer channel indices through board-specific knowledge.

The channel-id → name map mirrors
``adidt/boards/ad9081_fmc.py:map_clocks_to_board_layout``.
"""

from __future__ import annotations

from ..devices.base import ClockOutput
from ..devices.clocks import HMC7044, ClockChannel
from ..devices.converters import AD9081
from .base import EvalBoard


# AD9081-FMC-EBZ schematic wiring of the HMC7044 14 outputs.
_CLOCK_CHANNEL_MAP: dict[int, dict] = {
    0: {"name": "CORE_CLK_RX", "divider": 8, "driver_mode": 2, "is_sysref": False},
    2: {"name": "DEV_REFCLK", "divider": 4, "driver_mode": 2, "is_sysref": False},
    3: {"name": "DEV_SYSREF", "divider": 1024, "driver_mode": 2, "is_sysref": True},
    6: {"name": "CORE_CLK_TX", "divider": 8, "driver_mode": 2, "is_sysref": False},
    8: {"name": "FPGA_REFCLK1", "divider": 4, "driver_mode": 2, "is_sysref": False},
    10: {"name": "CORE_CLK_RX_ALT", "divider": 8, "driver_mode": 2, "is_sysref": False},
    12: {"name": "FPGA_REFCLK2", "divider": 4, "driver_mode": 2, "is_sysref": False},
    13: {"name": "FPGA_SYSREF", "divider": 1024, "driver_mode": 2, "is_sysref": True},
}


class ad9081_fmc(EvalBoard):
    """AD9081-FMC-EBZ composite.

    Attributes:
        clock: The HMC7044 clock distributor.
        converter: The AD9081 MxFE transceiver.
    """

    def __init__(self, *, reference_frequency: int = 122_880_000) -> None:
        self.reference_frequency = reference_frequency

        channels = {
            cid: ClockChannel(id=cid, **spec)
            for cid, spec in _CLOCK_CHANNEL_MAP.items()
        }
        # HMC7044 PLL2 at 3000 MHz with 122.88 MHz VCXO: the high band
        # (2.95–3.55 GHz) covers this and the fractional divider locks
        # reliably.  3000 MHz is required downstream because DEV_REFCLK
        # (channel 2, divider 4) drives the AD9081 dev_clk at
        # 3000/4 = 750 MHz — and the AD9081 internal PLL needs an
        # integer multiplier from dev_clk up to the 12 GHz DAC clock
        # (12000/750 = 16).  3072 MHz (N=25) gives 768 MHz dev_clk and
        # 12000/768 = 15.625, which isn't achievable so the AD9081
        # driver prints "Cannot find any settings to lock device PLL."
        self.clock = HMC7044(
            label="hmc7044",
            spi_max_hz=1_000_000,
            pll1_clkin_frequencies=[reference_frequency, 30_720_000, 0, 0],
            vcxo_hz=reference_frequency,
            pll2_output_hz=3_000_000_000,
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

        # Board-specific GPIO wiring for the AD9081 (from
        # adidt/boards/ad9081_fmc.py:to_board_model).
        self.converter = AD9081(
            label="trx0_ad9081",
            reset_gpio=133,
            sysref_req_gpio=121,
            rx1_enable_gpio=134,
            rx2_enable_gpio=135,
            tx1_enable_gpio=136,
            tx2_enable_gpio=137,
        )

    # Named clock-output aliases -------------------------------------------
    def _named(self, name: str) -> ClockOutput:
        for out in self.clock.clk_out:
            if out.name == name:
                return out
        raise AttributeError(f"no clock output named {name!r} on {type(self).__name__}")

    @property
    def dev_refclk(self) -> ClockOutput:
        """HMC7044 output feeding the AD9081 device reference clock."""
        return self._named("DEV_REFCLK")

    @property
    def dev_sysref(self) -> ClockOutput:
        """AD9081 SYSREF source."""
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
