from .layout import layout
from ..parts.adrv9009 import parse_profile
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
        self.profile = parse_profile(filename)

    def gen_dt_preprocess(self):
        return {
            "rx": self.profile["rx"],
            "tx": self.profile["tx"],
            "orx": self.profile["orx"],
            "lpbk": self.profile["lpbk"],
            "clocks": self.profile["clocks"],
        }
