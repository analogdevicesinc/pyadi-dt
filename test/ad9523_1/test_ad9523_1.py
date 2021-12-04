import pytest
import os

import adidt as dt


def test_ad9523_1_add_nodes():
    loc = os.path.dirname(__file__)
    dtb = os.path.join(loc, "daq2_ad9523_1_zcu102.dtb")

    d = dt.clock(dt_source="local_file", local_dt_filepath=dtb, arch="arm64")

    config = {
        "n2": 24,
        "out_dividers": [3, 6, 384],
        "output_clocks": {
            "ADC_CLK": {"divider": 3, "rate": 1000000000.0},
            "FPGA": {"divider": 6, "rate": 500000000.0},
            "SYSREF": {"divider": 384, "rate": 7812500.0},
        },
        "r2": 2,
        "vcxo": 125000000,
    }

    config2 = {
        "clock": {
            "m1": 4,
            "n2": 24,
            "out_dividers": [1, 900, 4],
            "output_clocks": {
                "AD9680_fpga_ref_clk": {"divider": 4, "rate": 187500000.0},
                "AD9680_ref_clk": {"divider": 1, "rate": 750000000.0},
                "AD9680_sysref": {"divider": 900, "rate": 833333.3333333334},
            },
            "part": "AD9523-1",
            "r2": 1,
            "vco": 750000000.0,
            "vcxo": 125000000.0,
        },
        "converter": {"clocking_option": "direct"},
        "fpga_AD9680": {
            "d": 1,
            "m": 1,
            "n1": 5,
            "n2": 4,
            "type": "cpll",
            "vco": 3750000000.0,
        },
    }

    d.set(config2['clock']['part'], config2['clock'])

    config = config2['clock']

    # Checks
    node = d.get_node_by_compatible("adi,ad9523-1")
    assert len(node) == 1

    node = node[0]

    # Check for updated DT
    assert node.get_property("adi,vcxo-frequency").value == config["vcxo"]

    d.write_out_dts("test_out.dts")

    divs = [config["output_clocks"][oc]["divider"] for oc in config["output_clocks"]]
    k = 0
    for n in node.nodes:
        if n.get_property("adi,extended-name").value in list(
            config["output_clocks"].keys()
        ):
            print(n.get_property("adi,extended-name").value)
            assert n.get_property("adi,channel-divider").value in divs
            assert n.get_property("adi,driver-mode").value == 2
            k += 1
    assert k == 3

    d.write_out_dts("test.dts")
