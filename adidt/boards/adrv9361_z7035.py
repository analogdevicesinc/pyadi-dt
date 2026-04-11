"""ADRV9361-Z7035 SOM board class for AD9361 SDR transceiver.

The ADRV9361-Z7035 is a System-on-Module pairing an AD9361 wideband
SDR transceiver with a Zynq Z-7035 SoC.  Like the FMComms boards it
uses SPI + LVDS (no JESD204), so the device tree node is simple.

Two carrier variants are supported:
- **bob** — breakout board (ADRV1CRR-BOB)
- **fmc** — FMC carrier (ADRV1CRR-FMC)
"""

from __future__ import annotations

from .fmcomms_fmc import fmcomms_fmc


class adrv9361_z7035(fmcomms_fmc):
    """ADRV9361-Z7035 SOM board class."""

    PLATFORM_CONFIGS = {
        "bob": {
            "base_dts_include": "zynq-adrv9361-z7035-bob.dts",
            "arch": "arm",
            "spi_bus": "spi0",
            "output_dir": "generated_dts",
        },
        "fmc": {
            "base_dts_include": "zynq-adrv9361-z7035-fmc.dts",
            "arch": "arm",
            "spi_bus": "spi0",
            "output_dir": "generated_dts",
        },
    }

    def __init__(self, platform: str = "bob", kernel_path: str | None = None) -> None:
        super().__init__(platform=platform, kernel_path=kernel_path)
