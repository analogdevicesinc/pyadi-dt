import pytest
import os

import adidt as dt


def test_hmc7044_add_nodes():
    loc = os.path.dirname(__file__)
    dtb = os.path.join(loc, "ad9081_hmc7044.dtb")

    d = dt.hmc7044_dt(dt_source="fs", local_dt_filepath=dtb)

    clock = {
        "n2": 24,
        "out_dividers": [3, 6, 384],
        "output_clocks": {
            "ADC": {"divider": 3, "rate": 1000000000.0},
            "FPGA": {"divider": 6, "rate": 500000000.0},
            "SYSREF": {"divider": 384, "rate": 7812500.0},
        },
        "r2": 2,
    }
    config = {"vcxo": 125000000, "clock": clock}

    node = d.get_node_by_compatible("adi,hmc7044")
    assert len(node) == 1

    node = node[0]
    d.set_dt_node_from_config(node, config)

    # Check for updated DT
    assert node.get_property("adi,vcxo-frequency").value == config["vcxo"]

    divs = [clock['output_clocks'][oc]['divider']  for oc in clock['output_clocks']]
    for n in node.nodes:
        assert n.get_property("adi,extended-name").value in list(
            clock["output_clocks"].keys()
        )
        assert n.get_property("adi,divider").value in divs
        assert n.get_property("adi,driver-mode").value == 2

    # d.write_out_dts("test.dts")
