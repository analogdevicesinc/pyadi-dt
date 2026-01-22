from .layout import layout
import numpy as np


class adsy1100_vu11p(layout):
    """ADSY1100 VU11P board layout map for clocks and DSP"""

    clock = "LTC6952"

    adc = "ad9081_rx"
    dac = "ad9081_tx"

    template_filename = "adsy1100_vu11p.tmpl"
    output_filename = "adsy1100_vu11p.dts"

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

    def map_clocks_to_board_layout(self, cfg):
        """Map JIF configuration to board clock connection layout.

        Args:
            cfg (dict): JIF configuration.

        Returns:
            dict: Board clock connection layout.
        """
        # Fix ups
        for key in ["VCO", "vcxo"]:
            cfg["clock"][key] = int(np.ceil(cfg["clock"][key]))

        map = {}
        clk = cfg["clock"]["output_clocks"]

        # Common
        map["sysref_divider"] = {
            "source_port": 3,
            "divider": clk["AD9084_RX_sysref"]["divider"],
        }

        # AD9084 ext PLL
        map["converter_clock_rate"] = np.ceil(cfg["clock_ext_pll_adf4382"]["rf_out_frequency"])
        map["converter_clock_rate"] = int(map["converter_clock_rate"])

        # FPGA side
        map["ref_clk_divider"] = {
            "source_port": 3,
            "divider": clk["adsy1100_AD9084_RX_ref_clk"]["divider"],
        }

        map["core_clk_divider"] = {
            "source_port": 0,
            "divider": clk["adsy1100_AD9084_RX_device_clk"]["divider"],
        }

        ccfg = {"map": map, "clock": cfg["clock"]}

        fpga = {}
        fpga['fpga'] = cfg["fpga_AD9084_RX"]
        if fpga['fpga']['sys_clk_select'] == 'XCVR_QPLL0':
            fpga['fpga']['sys_clk_select'] = 'XCVR_QPLL'
        # fpga['fpga_dac'] = cfg["fpga_dac"]


        return ccfg, fpga
