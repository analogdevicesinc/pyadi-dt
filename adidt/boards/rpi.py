"""Raspberry Pi board class for ADI device tree overlay generation.

Generates device tree overlays for ADI sensors and converters connected
to Raspberry Pi SPI/I2C buses.  Unlike FPGA board classes, RPi boards
have no JESD204 links or FPGA transceivers — just simple SPI/I2C
devices with optional interrupt GPIOs.

Usage::

    from adidt.boards.rpi import rpi
    from adidt.model import components

    board = rpi(platform="rpi5")
    board.output_filename = "adi-sensors.dts"

    model = board.build_model(
        components=[
            components.adis16495(spi_bus="spi0", cs=0, interrupt_gpio=25),
            components.adxl345(spi_bus="spi0", cs=1, interrupt_gpio=24),
        ],
    )
    board.gen_dt_from_model(model)
"""

from __future__ import annotations

from ..model.board_model import BoardModel, ComponentModel


class rpi:
    """Raspberry Pi board class for ADI sensor overlays.

    Attributes:
        platform: Target RPi model (``"rpi4"``, ``"rpi5"``).
    """

    PLATFORM_CONFIGS = {
        "rpi4": {
            "base_dts_include": "",
            "compatible": "brcm,bcm2711",
            "arch": "arm64",
            "output_dir": "generated_dts",
        },
        "rpi5": {
            "base_dts_include": "",
            "compatible": "brcm,bcm2712",
            "arch": "arm64",
            "output_dir": "generated_dts",
        },
        "rpi3": {
            "base_dts_include": "",
            "compatible": "brcm,bcm2837",
            "arch": "arm64",
            "output_dir": "generated_dts",
        },
    }

    def __init__(self, platform: str = "rpi5"):
        if platform not in self.PLATFORM_CONFIGS:
            supported = ", ".join(self.PLATFORM_CONFIGS.keys())
            raise ValueError(
                f"Platform '{platform}' not supported. Supported: {supported}"
            )
        self.platform = platform
        self.platform_config = self.PLATFORM_CONFIGS[platform]
        self.output_filename = None
        self.use_plugin_mode = True

    def build_model(
        self,
        components: list[ComponentModel],
        name: str | None = None,
    ) -> BoardModel:
        """Build a :class:`BoardModel` from a list of components.

        Unlike FPGA board classes, RPi models have no JESD links or
        FPGA config — just SPI/I2C device components.

        Args:
            components: List of :class:`ComponentModel` instances
                (use ``adidt.model.components`` factories).
            name: Model name. Defaults to ``rpi_<platform>``.

        Returns:
            An editable :class:`BoardModel`.
        """
        if name is None:
            name = f"rpi_{self.platform}"
        return BoardModel(
            name=name,
            platform=self.platform,
            components=list(components),
            metadata={
                "compatible": self.platform_config["compatible"],
            },
        )

    def gen_dt_from_model(
        self,
        model: BoardModel,
        config_source: str = "rpi_overlay",
    ) -> str:
        """Render a :class:`BoardModel` to an RPi device tree overlay file.

        Args:
            model: Board model to render.
            config_source: Source string for metadata header.

        Returns:
            Path to the generated DTS file.
        """
        if not self.output_filename:
            raise ValueError("output_filename must be set before rendering")
        return model.to_dts(self.output_filename, config_source=config_source)
