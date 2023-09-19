from .layout import layout
from ..parts import ad9528, adrv9009
import numpy as np
from pathlib import Path


class adrv9009_pcbz(layout):
    """ADRV9009-PCBZ FMC board layout map for clocks and DSP"""

    template_filename = "adi-adrv9009.dtsi"
    output_filename = "adi-adrv9009.dtsi"

    profile = None

    def __init__(self):
        self.jesd204 = {
            "framerA": {
                "bankId": 1,
                "deviceId": 0,
                "lane0Id": 0,
                "M": 4,
                "K": 32,
                "F": 4,
                "Np": 16,
                "scramble": 1,
                "externalSysref": 1,
                "serializerLanesEnabled": 0x03,
                "serializerLaneCrossbar": 0xE4,
                "lmfcOffset": 31,
                "newSysrefOnRelink": 0,
                "syncbInSelect": 0,
                "overSample": 0,
                "syncbInLvdsMode": 1,
                "syncbInLvdsPnInvert": 0,
                "enableManualLaneXbar": 0,
            },
            "framerB": {
                "bankId": 0,
                "deviceId": 0,
                "lane0Id": 0,
                "M": 4,
                "K": 32,
                "F": 4,
                "Np": 16,
                "scramble": 1,
                "externalSysref": 1,
                "serializerLanesEnabled": 0x0C,
                "serializerLaneCrossbar": 0xE4,
                "lmfcOffset": 31,
                "newSysrefOnRelink": 0,
                "syncbInSelect": 1,
                "overSample": 0,
                "syncbInLvdsMode": 1,
                "syncbInLvdsPnInvert": 0,
                "enableManualLaneXbar": 0,
            },
            "deframerA": {
                "bankId": 0,
                "deviceId": 0,
                "lane0Id": 0,
                "M": 4,
                "K": 32,
                "scramble": 1,
                "externalSysref": 1,
                "deserializerLanesEnabled": 0x0F,
                "deserializerLaneCrossbar": 0xE4,
                "lmfcOffset": 17,
                "newSysrefOnRelink": 0,
                "syncbOutSelect": 0,
                "Np": 16,
                "syncbOutLvdsMode": 1,
                "syncbOutLvdsPnInvert": 0,
                "syncbOutCmosSlewRate": 0,
                "syncbOutCmosDriveLevel": 0,
                "enableManualLaneXbar": 0,
            },
            "serAmplitude": 15,
            "serPreEmphasis": 1,
            "serInvertLanePolarity": 0,
            "desInvertLanePolarity": 0,
            "desEqSetting": 1,
            "sysrefLvdsMode": 1,
            "sysrefLvdsPnInvert": 0,
        }

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
            "jesd204": self.jesd204,
        }
