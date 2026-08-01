"""Xilinx ADRV9009-ZU11EG (Zynq UltraScale+ MPSoC SoM) FPGA board."""

from __future__ import annotations

from typing import ClassVar

from .base import FpgaBoard


class zu11eg(FpgaBoard):
    """ADRV9009-ZU11EG System-on-Module (xczu11eg MPSoC).

    The ZU11EG SoM integrates the ADRV9009 transceiver directly on an
    xczu11eg MPSoC (as opposed to an FMC eval card on a ZCU102).  It is
    a Zynq UltraScale+ platform, so it shares the ZCU102's PS-side
    constants (2 address cells, ``zynqmp_clk`` at index 71, two PS SPI
    controllers) but exposes more GT lanes on the larger device.
    """

    PLATFORM: ClassVar[str] = "zu11eg"
    ADDR_CELLS: ClassVar[int] = 2
    PS_CLK_LABEL: ClassVar[str] = "zynqmp_clk"
    PS_CLK_INDEX: ClassVar[int] = 71
    GPIO_LABEL: ClassVar[str] = "gpio"
    SPI_LABELS: ClassVar[tuple[str, ...]] = ("spi0", "spi1")
    NUM_GT_LANES: ClassVar[int] = 16

    JESD_PHY: ClassVar[str] = "GTH"
    DEFAULT_FPGA_ADC_PLL: ClassVar[str] = "XCVR_QPLL"
    DEFAULT_FPGA_DAC_PLL: ClassVar[str] = "XCVR_QPLL"

    label: str = "zu11eg"
