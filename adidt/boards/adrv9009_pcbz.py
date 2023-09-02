from .layout import layout
from ..parts import ad9528, adrv9009
import numpy as np
from pathlib import Path


class adrv9009_pcbz(layout):
    """ADRV9009-PCBZ FMC board layout map for clocks and DSP"""

    template_filename = "adi-adrv9009.dtsi"
    output_filename = "adi-adrv9009.dtsi"

    profile = None

    def parse_profile(self, filename: Path):
        """Parse a profile file.

        Args:
            filename: Profile file name.

        Returns:
            dict: Profile configuration.
        """
        if not filename.exists():
            raise Exception(f"Profile file not found: {filename}")

        self.xcvr_profile = adrv9009.parse_profile(filename)

        ad9528_file = filename.parent / (filename.stem + '_AD9528.txt')
        if not ad9528_file.exists():
            raise Exception(f"AD9528 Profile file not found: {ad9528_file}")

        self.clock_profile = ad9528.parse_profile(ad9528_file)

    def gen_dt_preprocess(self):
        return {
            "pll1": self.clock_profile["pll1"],
            "pll2": self.clock_profile["pll2"],
            "sysref": self.clock_profile["sysref"],
            "out": self.clock_profile["out"],

            "rx": self.xcvr_profile["rx"],
            "tx": self.xcvr_profile["tx"],
            "orx": self.xcvr_profile["orx"],
            "lpbk": self.xcvr_profile["lpbk"],
            "clocks": self.xcvr_profile["clocks"],
        }
