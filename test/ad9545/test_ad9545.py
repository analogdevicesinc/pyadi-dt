import pytest
import os

import adidt as dt

def test_ad9545_add_nodes():
    loc = os.path.dirname(__file__)
    dtb = os.path.join(loc, "rpi-ad9545-hmc7044.dtbo")

    d = dt.ad9545_dt(dt_source="local_file", local_dt_filepath=dtb, arch="arm")

    config = {
            'PLL0': {
                    'n0_profile_0': 1228800000.0,
                    'n0_profile_2': 6144.0,
                    'rate_hz': 1228800000.0,
					'priority_source_0': 5,
					'priority_source_2': 15,
					'priority_source_4': 25,

                },
                'q0': 40.0,
                'r0': 1.0,
                'r2': 50.0,
    }

    node = d.get_node_by_compatible("adi,ad9545")
    assert len(node) == 1

    node = node[0]
    d.set_dt_node_from_config(node, config)

    # Check for updated DT

    # Check input dividers
    for i in range(0, 4):
        if "r" + str(i) not in config:
            continue

        r_div = int(config["r" + str(i)])

        if r_div != 0:
            ref_node = node.get_subnode("ref-input-clk@" + str(i))
            if ref_node is None:
                raise Exception("AD9545: missing node: ref-input-clk@" + str(i))

            assert ref_node.get_property("adi,r-divider-ratio").value == int(r_div)

    assigned_clock_rates_prop = node.get_property("assigned-clock-rates")
    assigned_clock_rates = list(assigned_clock_rates_prop)
    assigned_clocks_prop = node.get_property("assigned-clocks")
    assigned_clocks = []

    for i in range(0, int(len(assigned_clocks_prop) / 3)):
        clock_type = assigned_clocks_prop[3 * i + 1]
        clock_address = assigned_clocks_prop[3 * i + 2]

        assigned_clocks.append((i, clock_type, clock_address))

    # Check PLL rates
    for i in range(0, 2):
        if "PLL" + str(i) not in config:
            continue

        pll_dict = config["PLL" + str(i)]

        if "rate_hz" not in  pll_dict:
            continue

        PLL_clock_found = False
        for (clock_pos, clock_type, clock_address) in assigned_clocks:
            if clock_type == d.pll_clock_id and clock_address == i:
                assert assigned_clock_rates[clock_pos] == pll_dict["rate_hz"]
                PLL_clock_found = True
                break

        assert PLL_clock_found

    # check PLL reference priorities
    for i in range(0, 2):
        pll_name = "PLL" + str(i)
        if pll_name not in config:
            continue

        pll_node = node.get_subnode("pll-clk@" + str(i))
        if pll_node is None:
            continue

        for j in range(0, 6):
            pll_profile_node = pll_node.get_subnode("profile@" + str(j))
            if pll_profile_node is None:
                continue;

            adi_pll_source_nr = list(pll_profile_node.get_property("adi,pll-source"))[0]

            if ("priority_source_" + str(adi_pll_source_nr)) in config[pll_name]:
                priority = config[pll_name]["priority_source_" + str(adi_pll_source_nr)]
                read_priority = list(pll_profile_node.get_property("adi,profile-priority"))[0]
                assert priority == read_priority

    # Check output rates
    for i in range(0, 10):
        if "q" + str(i) not in config:
            continue

        if config["q" + str(i)] == 0:
            continue

        if i > 5:
            PLL_rate = config["PLL1"]["rate_hz"]
        else:
            PLL_rate = config["PLL0"]["rate_hz"]

        output_clock_found = False
        for (clock_pos, clock_type, clock_address) in assigned_clocks:
            if clock_type == d.out_clock_id and clock_address == i:
                assert assigned_clock_rates[clock_pos] == int(PLL_rate / config["q" + str(i)])
                output_clock_found = True
                break

        assert output_clock_found

    #d.write_out_dts("test.dts")
