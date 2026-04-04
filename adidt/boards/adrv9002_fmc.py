"""ADRV9002 FMC board class — narrowband transceiver.

The ADRV9002 is architecturally different from the ADRV9009 family:
narrowband, no JESD204 (uses LVDS/CMOS interface), and requires
its own profile-driven configuration.

This is a stub — ``to_board_model()`` is not yet implemented.
The XSA pipeline with a profile is the recommended path for now.
"""

from .layout import layout


class adrv9002_fmc(layout):
    """ADRV9002 FMC board — stub, use XSA pipeline with profile."""

    PLATFORM_CONFIGS = {
        "zc706": {
            "base_dts_include": "zynq-zc706.dts",
            "arch": "arm",
            "spi_bus": "spi0",
            "output_dir": "generated_dts",
        },
    }

    def __init__(self, platform: str = "zc706"):
        if platform not in self.PLATFORM_CONFIGS:
            supported = ", ".join(self.PLATFORM_CONFIGS.keys())
            raise ValueError(
                f"Platform '{platform}' not supported. Supported: {supported}"
            )
        self.platform = platform
        self.platform_config = self.PLATFORM_CONFIGS[platform]
        self.use_plugin_mode = False
