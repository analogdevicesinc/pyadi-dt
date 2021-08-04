import pytest
import os

import adidt as dt


def test_ad9081_tx():
    loc = os.path.dirname(__file__)
    dtb = os.path.join(loc, "ad9081_hmc7044.dtb")

    d = dt.ad9081_dt(dt_source="local_file", local_dt_filepath=dtb)

    cfg = {
        "clock": {
            "n2": 3125,
            "out_dividers": [30, 1536, 12],
            "output_clocks": {
                "AD9081_fpga_ref_clk": {"divider": 12, "rate": 250000000.0},
                "AD9081_ref_clk": {"divider": 30, "rate": 100000000.0},
                "AD9081_sysref": {"divider": 1536, "rate": 1953125.0},
            },
            "r2": 256,
        },
        "converter": {"clocking_option": "integrated_pll"},
        "fpga_AD9081": {
            "d": 1,
            "m": 1,
            "n1": 4,
            "n2": 5,
            "type": "cpll",
            "vco": 5000000000.0,
        },
    }
    config = {"vcxo": 125000000, "clock": cfg}

    node = d.get_node_by_compatible("adi,ad9081")
    assert len(node) == 1

    node = node[0]
    d.update_dt_node_from_config(node, config, d._dt)

    d.write_out_dts("test_1.dts")
