"""ADRV9364-Z7020 SOM board class for AD9364 SDR transceiver.

The ADRV9364-Z7020 is a System-on-Module pairing an AD9364 (1x1 TRX)
SDR transceiver with a Zynq Z-7020 SoC.  It uses SPI + LVDS (no
JESD204), identical to the ADRV9361-Z7035 but with a single TX/RX path.

Supported carrier:
- **bob** — breakout board (ADRV1CRR-BOB)
"""

from __future__ import annotations

from .adrv9361_z7035 import adrv9361_z7035


class adrv9364_z7020(adrv9361_z7035):
    """ADRV9364-Z7020 SOM board class."""

    AD936X_COMPATIBLE = "adi,ad9364"
    AD936X_LABEL = "ad9364_phy"
    AD936X_DEVICE = "ad9364-phy"
    AD936X_PART = "ad9364"

    PLATFORM_CONFIGS = {
        "bob": {
            "base_dts_include": "zynq-adrv9364-z7020-bob.dts",
            "arch": "arm",
            "spi_bus": "spi0",
            "output_dir": "generated_dts",
        },
    }
