from .layout import layout
import numpy as np


class ad9081_fmc(layout):
    """AD9081 FMC board layout map for clocks and DSP"""

    clock = "HMC7044"

    adc = "ad9081_rx"
    dac = "ad9081_tx"

    template_filename = "ad9081_fmc_zcu102.tmpl"
    output_filename = "ad9081_fmc_zcu102.dts"

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
                [clk["adc_fpga_ref_clk"]["divider"], clk["dac_sysref"]["divider"]]
            ),
        }

        # RX side
        map["CORE_CLK_RX"] = {
            "source_port": 0,
            "divider": clk["adc_fpga_link_out_clk"]["divider"],
        }
        map["CORE_CLK_RX_ALT"] = {
            "source_port": 10,
            "divider": clk["adc_fpga_link_out_clk"]["divider"] * 1,
        }
        map["FPGA_REFCLK1"] = {
            "source_port": 8,
            "divider": clk["adc_fpga_ref_clk"]["divider"],
        }

        # Tx side
        map["CORE_CLK_TX"] = {
            "source_port": 6,
            "divider": clk["dac_fpga_link_out_clk"]["divider"],
        }
        map["FPGA_REFCLK2"] = {
            "source_port": 12,
            "divider": clk["dac_fpga_ref_clk"]["divider"],
        }

        ccfg = {"map": map, "clock": cfg["clock"]}

        fpga = {}
        fpga['fpga_adc'] = cfg["fpga_adc"]
        fpga['fpga_dac'] = cfg["fpga_dac"]

        # Check all clocks are mapped
        # FIXME

        # Check no source_port is mapped to more than one clock
        # FIXME
        adc, dac = self.map_jesd_structs(cfg)

        # Section disables
        adc["fddc_enabled"] = any(cfg["datapath_adc"]["fddc"]["enabled"])         
        dac["fduc_enabled"] = any(cfg["datapath_dac"]["fduc"]["enabled"])

        # Change QPLL0 to naming in kernel
        if fpga['fpga_dac']['sys_clk_select'] == 'XCVR_QPLL0':
            fpga['fpga_dac']['sys_clk_select'] = 'XCVR_QPLL'
        if fpga['fpga_adc']['sys_clk_select'] == 'XCVR_QPLL0':
            fpga['fpga_adc']['sys_clk_select'] = 'XCVR_QPLL'

        return ccfg, adc, dac, fpga
