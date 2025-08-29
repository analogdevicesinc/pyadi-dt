import os

def test_ad9081_nv_sb_s10():
    import adidt

    ###############################################################################
    cfg = {
        "clock": {
            "n2": 29,
            "out_dividers": [5, 1536, 768, 8, 16, 8, 8],
            "output_clocks": {
                "AD9081_ref_clk": {"divider": 5, "rate": 580000000.0},
                "adc_sysref": {"divider": 1536, "rate": 1888020.8333333333},
                "dac_sysref": {"divider": 768, "rate": 3776041.6666666665},
                "nvsbs10_adc_device_clk": {"divider": 16, "rate": 181250000.0},
                "nvsbs10_adc_ref_clk": {"divider": 8, "rate": 362500000.0},
                "nvsbs10_dac_device_clk": {"divider": 8, "rate": 362500000.0},
                "nvsbs10_dac_ref_clk": {"divider": 8, "rate": 362500000.0},
            },
            "r2": 1,
            "vco": 2900000000.0,
            "vcxo": 100000000.0,
            "vcxo_doubler": 1,
        },
        "converter": {
            "clocking_option": "integrated_pll",
            "pll_config": {"d": 2, "m_vco": 5, "n_vco": 4, "r": 1, "serdes_pll_div": 2},
        },
        "datapath_adc": {
            "cddc": {
                "decimations": [6, 6, 6, 6],
                "enabled": [True, True, True, True],
                "nco_frequencies": [0, 0, 0, 0],
                "nco_phases": [0, 0, 0, 0],
            },
            "fddc": {
                "decimations": [4, 4, 4, 4, 4, 4, 4, 4],
                "enabled": [True, True, True, True, True, True, True, True],
                "nco_frequencies": [0, 0, 0, 0, 0, 0, 0, 0],
                "nco_phases": [0, 0, 0, 0, 0, 0, 0, 0],
                "source": [1, 1, 2, 2, 3, 3, 4, 4],
            },
        },
        "datapath_dac": {
            "cduc": {
                "enabled": [True, True, True, True],
                "interpolation": 6,
                "nco_frequencies": [0, 0, 0, 0],
                "nco_phases": [0, 0, 0, 0],
                "sources": [[1], [1], [3], [3]],
            },
            "fduc": {
                "enabled": [True, True, True, True, True, True, True, True],
                "interpolation": 4,
                "nco_frequencies": [0, 0, 0, 0, 0, 0, 0, 0],
                "nco_phases": [0, 0, 0, 0, 0, 0, 0, 0],
            },
        },
        "fpga_adc": {
            "clkout_rate": 1,
            "d": 2,
            "device_clock_source": "external",
            "m": 1,
            "n": 33,
            "n_dot_frac": 33,
            "out_clk_select": "XCVR_PROGDIV_CLK",
            "progdiv": 66,
            "sys_clk_select": "XCVR_QPLL1",
            "transport_samples_per_clock": 0.6666666666666666,
            "type": "qpll1",
            "vco": 11962500000,
        },
        "fpga_dac": {
            "clkout_rate": 1,
            "d": 1,
            "device_clock_source": "external",
            "m": 1,
            "n": 33,
            "n_dot_frac": 33,
            "out_clk_select": "XCVR_PROGDIV_CLK",
            "progdiv": 66,
            "sys_clk_select": "XCVR_QPLL1",
            "transport_samples_per_clock": 0.6666666666666666,
            "type": "qpll1",
            "vco": 11962500000,
        },
        "jesd_adc": {
            "CS": 0,
            "F": 12,
            "HD": 0,
            "K": 64,
            "L": 1,
            "M": 8,
            "Np": 12,
            "S": 1,
            "bit_clock": 11962500000.0,
            "converter_clock": 2900000000.0,
            "jesd_class": "jesd204c",
            "jesd_mode": "1.0",
            "multiframe_clock": 1888020.8333333333,
            "sample_clock": 120833333.33333333,
        },
        "jesd_dac": {
            "CS": 0,
            "F": 12,
            "HD": 0,
            "K": 64,
            "L": 1,
            "M": 8,
            "Np": 12,
            "S": 1,
            "bit_clock": 23925000000.0,
            "converter_clock": 5800000000.0,
            "jesd_class": "jesd204c",
            "jesd_mode": "0",
            "multiframe_clock": 3776041.6666666665,
            "sample_clock": 241666666.66666666,
        },
    }

    ###############################################################################

    sb = adidt.ad9081_nv_sb_s10()

    clock, adc, dac, fpga = sb.map_clocks_to_board_layout(cfg)

    filename = sb.gen_dt(clock=clock, adc=adc, dac=dac, fpga=fpga)

    print(f"Generated device tree source file: {filename}")
    assert os.path.isfile(filename)

    with open(filename, "r") as f:
        dts_content = f.read()
        print(f"----- Device tree source file content: ----- \n{dts_content}")
        print("----- End of device tree source file content -----")
