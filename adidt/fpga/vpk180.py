"""Xilinx VPK180 (Versal Premium) FPGA board."""

from __future__ import annotations

from typing import ClassVar

from .base import FpgaBoard


class vpk180(FpgaBoard):
    """VPK180 evaluation platform.

    Constants mirror the legacy
    ``adidt/boards/ad9084_fmc.py:PLATFORM_CONFIGS["vpk180"]`` entries.
    """

    PLATFORM: ClassVar[str] = "vpk180"
    ADDR_CELLS: ClassVar[int] = 2
    PS_CLK_LABEL: ClassVar[str] = "versal_clk"
    PS_CLK_INDEX: ClassVar[int | None] = None
    GPIO_LABEL: ClassVar[str] = "gpio0"
    SPI_LABELS: ClassVar[tuple[str, ...]] = ("spi0",)
    NUM_GT_LANES: ClassVar[int] = 24

    JESD_PHY: ClassVar[str] = "GTY"
    DEFAULT_FPGA_ADC_PLL: ClassVar[str] = "XCVR_QPLL0"
    DEFAULT_FPGA_DAC_PLL: ClassVar[str] = "XCVR_QPLL0"

    label: str = "vpk180"
