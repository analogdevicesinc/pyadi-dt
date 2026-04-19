"""Xilinx ZC706 (Zynq-7000) FPGA board."""

from __future__ import annotations

from typing import ClassVar

from .base import FpgaBoard


class zc706(FpgaBoard):
    """ZC706 evaluation platform (Zynq-7000, 32-bit ARM)."""

    PLATFORM: ClassVar[str] = "zc706"
    ADDR_CELLS: ClassVar[int] = 1
    PS_CLK_LABEL: ClassVar[str] = "clkc"
    PS_CLK_INDEX: ClassVar[int] = 15
    GPIO_LABEL: ClassVar[str] = "gpio0"
    SPI_LABELS: ClassVar[tuple[str, ...]] = ("spi0", "spi1")
    NUM_GT_LANES: ClassVar[int] = 8

    JESD_PHY: ClassVar[str] = "GTX"
    DEFAULT_FPGA_ADC_PLL: ClassVar[str] = "XCVR_CPLL"
    DEFAULT_FPGA_DAC_PLL: ClassVar[str] = "XCVR_QPLL"

    label: str = "zc706"
