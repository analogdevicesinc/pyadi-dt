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
from ..model.board_model import BoardModel, ComponentModel


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

    def __init__(self, platform: str = "bob", kernel_path: str | None = None):
        super().__init__(platform=platform, kernel_path=kernel_path)

    def to_board_model(self, cfg: dict) -> BoardModel:
        """Build a BoardModel for the ADRV9361-Z7035 SOM.

        Reuses the AD9361 SPI device pattern from fmcomms_fmc with
        board-specific compatible string.
        """
        spi_bus = self.platform_config["spi_bus"]
        cs = cfg.get("cs", 0)

        config = {
            "label": "ad9361_phy",
            "device": "ad9361-phy",
            "compatible": cfg.get("compatible", "adi,ad9361"),
            "cs": cs,
            "spi_max_hz": cfg.get("spi_max_hz", 10_000_000),
            "spi_cpol": False,
            "spi_cpha": False,
            "gpio_label": "gpio",
            "interrupt_gpio": cfg.get("interrupt_gpio", None),
            "irq_type": "IRQ_TYPE_EDGE_FALLING",
        }

        components = [
            ComponentModel(
                role="transceiver",
                part="ad9361",
                template="adis16495.tmpl",
                spi_bus=spi_bus,
                spi_cs=cs,
                config=config,
            ),
        ]

        return BoardModel(
            name=f"adrv9361_z7035_{self.platform}",
            platform=self.platform,
            components=components,
        )
