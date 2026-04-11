"""FMComms2/3/4/5 board class for AD9361/AD9363 SDR transceivers.

The FMComms family uses AD9361 or AD9363 SDR transceivers connected
via SPI with clock and GPIO lines.  These are the most common ADI
SDR evaluation boards, supported on Zedboard, ZC702, ZC706, and ZCU102.

This is a simplified board class — the AD9361 has extensive
configuration via IIO at runtime, so the device tree node is
relatively simple (compatible, SPI, clocks, GPIOs).
"""

from __future__ import annotations

from .layout import layout
from ..model.board_model import BoardModel, ComponentModel, FpgaConfig


class fmcomms_fmc(layout):
    """FMComms2/3/4/5 SDR board class."""

    # AD936x device identity — override in subclasses for AD9364 variants
    AD936X_COMPATIBLE = "adi,ad9361"
    AD936X_LABEL = "ad9361_phy"
    AD936X_DEVICE = "ad9361-phy"
    AD936X_PART = "ad9361"

    PLATFORM_CONFIGS = {
        "zed": {
            "base_dts_include": "zynq-zed-adv7511.dtsi",
            "arch": "arm",
            "spi_bus": "spi0",
            "output_dir": "generated_dts",
        },
        "zc702": {
            "base_dts_include": "zynq-zc702.dts",
            "arch": "arm",
            "spi_bus": "spi0",
            "output_dir": "generated_dts",
        },
        "zc706": {
            "base_dts_include": "zynq-zc706.dts",
            "arch": "arm",
            "spi_bus": "spi0",
            "output_dir": "generated_dts",
        },
        "zcu102": {
            "base_dts_include": "zynqmp-zcu102-rev1.0.dts",
            "arch": "arm64",
            "spi_bus": "spi1",
            "output_dir": "generated_dts",
        },
    }

    def __init__(self, platform: str = "zed", kernel_path: str | None = None) -> None:
        if platform not in self.PLATFORM_CONFIGS:
            supported = ", ".join(self.PLATFORM_CONFIGS.keys())
            raise ValueError(
                f"Platform '{platform}' not supported. Supported: {supported}"
            )
        self.platform = platform
        self.platform_config = self.PLATFORM_CONFIGS[platform]
        self.output_filename = None
        self.use_plugin_mode = False

    def to_board_model(self, cfg: dict) -> BoardModel:
        """Build a BoardModel for an AD936x SDR transceiver.

        The AD936x device tree node is simple — most configuration
        happens via IIO at runtime.  The DT just needs compatible,
        SPI, clocks, and reset GPIO.

        Subclasses override AD936X_* class attributes to select the
        correct compatible string, label, device name, and part.
        """
        spi_bus = self.platform_config["spi_bus"]
        cs = cfg.get("cs", 0)

        config = {
            "label": self.AD936X_LABEL,
            "device": self.AD936X_DEVICE,
            "compatible": cfg.get("compatible", self.AD936X_COMPATIBLE),
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
                part=self.AD936X_PART,
                template="adis16495.tmpl",
                spi_bus=spi_bus,
                spi_cs=cs,
                config=config,
            ),
        ]

        board_name = type(self).__name__
        return BoardModel(
            name=f"{board_name}_{self.platform}",
            platform=self.platform,
            components=components,
        )
