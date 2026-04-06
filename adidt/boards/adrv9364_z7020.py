"""ADRV9364-Z7020 SOM board class for AD9364 SDR transceiver.

The ADRV9364-Z7020 is a System-on-Module pairing an AD9364 (1x1 TRX)
SDR transceiver with a Zynq Z-7020 SoC.  It uses SPI + LVDS (no
JESD204), identical to the ADRV9361-Z7035 but with a single TX/RX path.

Supported carrier:
- **bob** — breakout board (ADRV1CRR-BOB)
"""

from __future__ import annotations

from .adrv9361_z7035 import adrv9361_z7035
from ..model.board_model import BoardModel, ComponentModel


class adrv9364_z7020(adrv9361_z7035):
    """ADRV9364-Z7020 SOM board class."""

    PLATFORM_CONFIGS = {
        "bob": {
            "base_dts_include": "zynq-adrv9364-z7020-bob.dts",
            "arch": "arm",
            "spi_bus": "spi0",
            "output_dir": "generated_dts",
        },
    }

    def to_board_model(self, cfg: dict) -> BoardModel:
        """Build a BoardModel for the ADRV9364-Z7020 SOM."""
        spi_bus = self.platform_config["spi_bus"]
        cs = cfg.get("cs", 0)

        config = {
            "label": "ad9364_phy",
            "device": "ad9364-phy",
            "compatible": cfg.get("compatible", "adi,ad9364"),
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
                part="ad9364",
                template="adis16495.tmpl",
                spi_bus=spi_bus,
                spi_cs=cs,
                config=config,
            ),
        ]

        return BoardModel(
            name=f"adrv9364_z7020_{self.platform}",
            platform=self.platform,
            components=components,
        )
