import pytest
import os

import adidt as dt


def test_hmc7044_add_nodes():
    loc = os.path.dirname(__file__)
    dtb = os.path.join(loc, "ad9081_hmc7044.dtb")

    d = dt.hmc7044_dt(dt_source="local_file", local_dt_filepath=dtb)

    clock = {
        "reference_frequencies" : [38400000, 38400000, 38400000, 38400000],
        "reference_selection_order" : [0, 3, 2, 1],
        "n2": 24,
        "out_dividers": [3, 6, 384],
        "output_clocks": {
            "ADC": {"divider": 3, "rate": 1000000000.0, "driver-mode": "CML",
                "high-performance-mode-disable": True,
                "startup-mode-dynamic-enable": True,
                "dynamic-driver-enable": True,
                "force-mute-enable": True,
                "output-mux-mode": "CH_DIV",
                "driver_impedances": "100_OHM"},
            "FPGA": {"divider": 6, "rate": 500000000.0, "driver-mode": "CML",
                "fine-delay": 16, "coarse-delay": 5},
            "SYSREF": {"divider": 384, "rate": 7812500.0, "driver-mode": "CMOS",
                "CMOS": {"P" : 0, "N" : 1}},
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

    # Check input reference priorities
    if ("reference_selection_order" in clock):
        ref_order = []
        priority = 0
        ref_order_prop_val = node.get_property("adi,pll1-ref-prio-ctrl").value

        # MSB (Fourth priority input [1:0]) .... (First priority input [1:0]) LSB
        for ref_nr in clock["reference_selection_order"]:
            if (ref_nr > 4):
                raise Exception("Refernce number:" + str(ref_nr) + " invalid.")
            ref_order.append((ref_order_prop_val >> (priority * 2)) & 0x3)
            priority += 1

        assert ref_order == clock["reference_selection_order"]

    # Check input referece frequencies
    if "reference_frequencies" in clock:
        ref_freqs_prop_name = "adi,pll1-clkin-frequencies"
        ref_freqs_prop = node.get_property(ref_freqs_prop_name)
        if ref_freqs_prop is None:
            raise Exception(ref_freqs_prop_name + " property not in DT.")

        assert list(ref_freqs_prop) == clock["reference_frequencies"]

        # Check if same frequencies are set to dummy input clocks
        used_clocks = d.get_used_clocks(node)
        i = 0
        for used_clock in used_clocks:
            compat_prop = used_clock.get_property("compatible")
            if compat_prop.value != "fixed-clock":
                i += 1
                continue

            clock_freq = used_clock.get_property("clock-frequency")
            assert clock["reference_frequencies"][i] == clock_freq.value
            i += 1

    divs = [clock['output_clocks'][oc]['divider']  for oc in clock['output_clocks']]
    for n in node.nodes:
        assert n.get_property("adi,extended-name").value in list(
            clock["output_clocks"].keys()
        )
        assert n.get_property("adi,divider").value in divs

    # Test if all output clock nodes properties from config have been set in DT
    for i in range(0, len(node.nodes)):
        output_node = node.nodes[i]
        output_node_name = output_node.get_property("adi,extended-name").value
        assert output_node_name in clock["output_clocks"]

        output_dict = clock["output_clocks"][output_node_name]

        assert output_node.get_property("adi,divider").value == output_dict["divider"]

        if "driver-mode" in output_dict:
            driver_mode = d.driver_modes[output_dict["driver-mode"]]
            prop = output_node.get_property("adi,driver-mode")
            assert prop.value == driver_mode

        if "high-performance-mode-disable" in output_dict:
            prop = output_node.get_property("adi,high-performance-mode-disable")
            assert prop != None

        if "startup-mode-dynamic-enable" in output_dict:
            prop = output_node.get_property("adi,startup-mode-dynamic-enable")
            assert prop != None

            if "dynamic-driver-enable" in output_dict:
                prop = output_node.get_property("adi,dynamic-driver-enable")
                assert prop != None

            if "force-mute-enable" in output_dict:
                prop = output_node.get_property("adi,force-mute-enable")
                assert prop != None

        if ("output-mux-mode" in output_dict):
            mux_mode = d.output_mux_modes[output_dict["output-mux-mode"]]
            prop = output_node.get_property("adi,output-mux-mode")
            assert prop.value == mux_mode

        if ("driver-impedance-mode" in output_dict):
            impedance_mode = self.driver_impedances[output_dict["driver-impedance-mode"]]
            prop = output_node.get_property("adi,driver-impedance-mode")
            assert prop.value == impedance_mode

        if "fine-delay" in output_dict:
            fine_delay = output_node.get_property("adi,fine-analog-delay").value
            assert fine_delay == output_dict["fine-delay"]

        if "coarse-delay" in output_dict:
            fine_delay = output_node.get_property("adi,coarse-digital-delay").value
            assert fine_delay == output_dict["coarse-delay"]

        if "CMOS" in output_dict:
            impedance_prop_val = output_node.get_property("adi,driver-impedance-mode").value
            impedance_prop_dict = output_dict["CMOS"]["P"] + (output_dict["CMOS"]["N"] << 1)
            assert impedance_prop_val == impedance_prop_dict

    # d.write_out_dts("test.dts")
