"""Xilinx ZCU102 (Zynq UltraScale+ MPSoC) FPGA board."""

from __future__ import annotations

from typing import ClassVar

from .base import FpgaBoard


class zcu102(FpgaBoard):
    """ZCU102 evaluation platform.

    Constants mirror the entries in the legacy
    ``adidt/boards/*.py:PLATFORM_CONFIGS["zcu102"]`` dicts.
    """

    PLATFORM: ClassVar[str] = "zcu102"
    ADDR_CELLS: ClassVar[int] = 2
    PS_CLK_LABEL: ClassVar[str] = "zynqmp_clk"
    PS_CLK_INDEX: ClassVar[int] = 71
    GPIO_LABEL: ClassVar[str] = "gpio"
    SPI_LABELS: ClassVar[tuple[str, ...]] = ("spi0", "spi1")
    NUM_GT_LANES: ClassVar[int] = 16

    JESD_PHY: ClassVar[str] = "GTH"
    DEFAULT_FPGA_ADC_PLL: ClassVar[str] = "XCVR_QPLL"
    DEFAULT_FPGA_DAC_PLL: ClassVar[str] = "XCVR_QPLL"

    label: str = "zcu102"
