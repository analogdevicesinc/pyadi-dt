"""ADRV9003 (Navassa) transceiver device model."""

from typing import ClassVar

from .adrv9009 import ADRV9009


class ADRV9003(ADRV9009):
    """ADRV9003 two-RX/one-TX Navassa transceiver.

    ADRV9003 uses the ADRV9002 Linux driver and AXI IP family, but its
    device-tree compatible and clock names differ from the Talise ADRV9009.
    The common SPI/JESD rendering remains useful for applications that supply
    the Navassa profile properties separately.
    """

    part: ClassVar[str] = "adrv9003"
    compatible: ClassVar[str] = "adi,adrv9003"
    label: str = "adc0_adrv9002"
    node_name_base: str = "adrv9002-phy"
    compatible_strings: list[str] = ["adi,adrv9003", "adrv9003"]
    dt_header: ClassVar[dict[str, object]] = {
        "#clock-cells": 1,
        "clock-output-names": [
            "rx1_sampl_clk",
            "tx1_sampl_clk",
            "tdd1_intf_clk",
            "rx2_sampl_clk",
        ],
        "#jesd204-cells": 2,
        "jesd204-top-device": 0,
    }
