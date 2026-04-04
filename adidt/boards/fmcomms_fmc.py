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

    def __init__(self, platform: str = "zed", kernel_path: str | None = None):
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
        """Build a BoardModel for AD9361/AD9363 SDR.

        The AD9361 device tree node is simple — most configuration
        happens via IIO at runtime.  The DT just needs compatible,
        SPI, clocks, and reset GPIO.
        """
        from ..model.contexts import build_adis16495_ctx  # reuse simple SPI pattern

        spi_bus = self.platform_config["spi_bus"]
        compatible = cfg.get("compatible", "adi,ad9361")
        cs = cfg.get("cs", 0)
        reset_gpio = cfg.get("reset_gpio", None)

        # AD9361 is a simple SPI device at DT level
        config = {
            "label": "ad9361_phy",
            "device": "ad9361-phy",
            "compatible": compatible,
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
                template="adis16495.tmpl",  # reuse simple SPI template
                spi_bus=spi_bus,
                spi_cs=cs,
                config=config,
            ),
        ]

        return BoardModel(
            name=f"fmcomms_{self.platform}",
            platform=self.platform,
            components=components,
        )
