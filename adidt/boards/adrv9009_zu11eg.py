from .layout import layout
from ..parts.adrv9009 import parse_profile
import numpy as np
import os

def coefs_to_long_string(coefs):
    """Convert coefficient array to string.

    Args:
        coefs (list): Coefficients.

    Returns:
        str: Coefficients as a string.
    """
    result = ""
    for coef in coefs.split("\n"):
        coef = coef.replace(" ", "")
        result += f"({coef}) "
    return result[:-1]


class adrv9009_zu11eg(layout):
    """ADRV9009-ZU11EG SOM board layout map for clocks and DSP"""

    clock = "HMC7044"

    adc = "adrv9009_rx"
    dac = "adrv9009_tx"

    template_filename = "adrv9009_zu11eg.dts"
    output_filename = "adrv9009_zu11eg_out.dts"

    profile = None

    def gen_dt_preprocess(self):
        """Preprocess profile for transceiver.

        Args:
            profile (dict): Profile.

        Returns:
            dict: Preprocessed profile.
        """
        if self.profile is None:
            raise Exception("Profile not loaded")
        rx = self.profile['rx']
        tx = self.profile['tx']
        orx = self.profile['obsRx']
        lpbk = self.profile['lpbk']
        clocks = self.profile['clocks']

        rx["rxAdcProfile"]["coefs"] = coefs_to_long_string(rx["rxAdcProfile"]["#text"])
        rx["filter"]["coefs"] = coefs_to_long_string(rx["filter"]["#text"])

        orx["filter"]["coefs"] = coefs_to_long_string(orx["filter"]["#text"])
        orx["orxBandPassAdcProfile"]["coefs"] = coefs_to_long_string(
            orx["orxBandPassAdcProfile"]["#text"]
        )
        orx["orxLowPassAdcProfile"]["coefs"] = coefs_to_long_string(
            orx["orxLowPassAdcProfile"]["#text"]
        )

        tx["filter"]["coefs"] = coefs_to_long_string(tx["filter"]["#text"])
        lpbk["lpbkAdcProfile"]["coefs"] = coefs_to_long_string(
            lpbk["lpbkAdcProfile"]["#text"]
        )

        return {"rx": rx, "tx": tx, "orx": orx, "lpbk": lpbk, "clocks": clocks}

    def make_ints(self, cfg, keys):
        """Convert keys in a dict to integers.

        Args:
            cfg (dict): Configuration.
            keys (list): Keys to convert.

        Returns:
            dict: Configuration with keys converted to integers.
        """
        for key in keys:
            if isinstance(cfg[key], float) and cfg[key].is_integer():
                cfg[key] = int(cfg[key])
        return cfg

    def map_jesd_structs(self, cfg):
        """Map JIF configuration to integer structs.

        Args:
            cfg (dict): JIF configuration.

        Returns:
            dict: ADC JESD structs.
            dict: DAC JESD structs.
        """
        adc = cfg["converter"]
        adc["jesd"] = cfg["jesd_adc"]
        adc["jesd"]["jesd_class_int"] = self.map_jesd_subclass(
            adc["jesd"]["jesd_class"]
        )
        dac = cfg["converter"].copy()
        dac["jesd"] = cfg["jesd_dac"]
        dac["jesd"]["jesd_class_int"] = self.map_jesd_subclass(
            dac["jesd"]["jesd_class"]
        )

        adc["jesd"] = self.make_ints(adc["jesd"], ["converter_clock", "sample_clock"])
        dac["jesd"] = self.make_ints(dac["jesd"], ["converter_clock", "sample_clock"])

        adc["datapath"] = cfg["datapath_adc"]
        dac["datapath"] = cfg["datapath_dac"]

        return adc, dac

    def map_clocks_to_board_layout(self, cfg):
        """Map JIF configuration to board clock connection layout.

        Args:
            cfg (dict): JIF configuration.

        Returns:
            dict: Board clock connection layout.
        """
        # Fix ups
        for key in ["vco", "vcxo"]:
            if isinstance(cfg["clock"][key], float) and cfg["clock"][key].is_integer():
                cfg["clock"][key] = int(cfg["clock"][key])

        map = {}
        clk = cfg["clock"]["output_clocks"]

        # Common
        map["DEV_REFCLK"] = {
            "source_port": 2,
            "divider": clk["AD9081_ref_clk"]["divider"],
        }
        map["DEV_SYSREF"] = {
            "source_port": 3,
            "divider": np.max(
                [clk["adc_sysref"]["divider"], clk["dac_sysref"]["divider"]]
            ),
        }
        map["FPGA_SYSREF"] = {
            "source_port": 13,
            "divider": np.max(
                [clk["adc_fpga_ref_clk"]["divider"], clk["dac_fpga_ref_clk"]["divider"]]
            ),
        }

        # RX side
        map["CORE_CLK_RX"] = {
            "source_port": 0,
            "divider": clk["adc_fpga_ref_clk"]["divider"],
        }
        map["CORE_CLK_RX_ALT"] = {
            "source_port": 10,
            "divider": clk["adc_fpga_ref_clk"]["divider"] * 2,
        }
        map["FPGA_REFCLK1"] = {
            "source_port": 8,
            "divider": clk["adc_fpga_ref_clk"]["divider"],
        }

        # Tx side
        map["CORE_CLK_TX"] = {
            "source_port": 6,
            "divider": clk["dac_fpga_ref_clk"]["divider"],
        }
        map["FPGA_REFCLK2"] = {
            "source_port": 12,
            "divider": clk["dac_fpga_ref_clk"]["divider"],
        }

        ccfg = {"map": map, "clock": cfg["clock"]}

        fpga = {}
        fpga["fpga_adc"] = cfg["fpga_adc"]
        fpga["fpga_dac"] = cfg["fpga_dac"]

        # Check all clocks are mapped
        # FIXME

        # Check no source_port is mapped to more than one clock
        # FIXME
        adc, dac = self.map_jesd_structs(cfg)

        return ccfg, adc, dac, fpga

    def parse_profile(self, filename):
        """Parse a profile file.

        Args:
            filename (str): Profile file name.

        Returns:
            dict: Profile configuration.
        """
        if not os.path.exists(filename):
            raise Exception(f"Profile file not found: {filename}")
        self.profile = parse_profile(filename)
