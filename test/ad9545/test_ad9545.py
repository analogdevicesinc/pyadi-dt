import os
import adidt as dt


def test_ad9545_add_nodes():
    loc = os.path.dirname(__file__)
    dtb = os.path.join(loc, "rpi-ad9545-hmc7044.dtbo")

    d = dt.ad9545_dt(dt_source="local_file", local_dt_filepath=dtb, arch="arm")

    config = {
            'PLL0': {
                        'hitless': {
                            'fb_source': 0,
                            'fb_source_rate': 10000000
                        },
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
                raise Exception(
                    "AD9545: missing node: ref-input-clk@" + str(i)
                )
            dt_r_div = ref_node.get_property("adi,r-divider-ratio").value
            assert int(dt_r_div) == int(r_div)

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

        if "rate_hz" not in pll_dict:
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
                continue

            adi_pll_source_nr = list(
                pll_profile_node.get_property("adi,pll-source")
            )[0]

            priority_attr = "priority_source_" + str(adi_pll_source_nr)
            if (priority_attr) in config[pll_name]:
                priority = config[pll_name][priority_attr]
                read_priority = list(
                    pll_profile_node.get_property("adi,profile-priority")
                )[0]

                assert priority == int(read_priority)

    # check PLL hitless modes
    for i in range(0, 2):
        pll_name = "PLL" + str(i)
        if pll_name not in config:
            continue

        pll_node = node.get_subnode("pll-clk@" + str(i))
        if pll_node is None:
            continue

        dt_fb_source_nr_str = "adi,pll-internal-zero-delay-feedback"
        dt_fb_source_rate_str = "adi,pll-internal-zero-delay-feedback-hz"
        dt_slew_rate_str = "adi,pll-slew-rate-limit-ps"

        if "hitless" in config[pll_name]:
            hitless_dict = config[pll_name]["hitless"]
            fb_source_nr = hitless_dict["fb_source"]
            fb_source_rate = hitless_dict["fb_source_rate"]

            dt_fb_source_nr = list(
                pll_node.get_property(dt_fb_source_nr_str)
            )[0]

            dt_fb_source_rate = list(
                pll_node.get_property(dt_fb_source_rate_str)
            )[0]

            dt_slew_rate = list(
                pll_node.get_property(dt_slew_rate_str)
            )[0]

            assert int(fb_source_nr) == int(dt_fb_source_nr)
            assert int(fb_source_rate) == int(dt_fb_source_rate)
            assert 4000000000 == int(dt_slew_rate)

        else:
            # check if hitless mode properties are removed:
            if pll_node.exist_property(dt_fb_source_nr_str):
                raise Exception("AD9545: invalid mode: pll-clk@" + str(i))

            if pll_node.exist_property(dt_fb_source_rate_str):
                raise Exception("AD9545: invalid mode: pll-clk@" + str(i))

            # slew rate should be returned to default value
            dt_slew_rate = list(
                pll_node.get_property(dt_slew_rate_str)
            )[0]

            assert 100000000 == int(dt_slew_rate)

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
                out_rate = int(PLL_rate / config["q" + str(i)])
                assert assigned_clock_rates[clock_pos] == out_rate
                output_clock_found = True
                break

        assert output_clock_found

    # d.write_out_dts("test.dts")
