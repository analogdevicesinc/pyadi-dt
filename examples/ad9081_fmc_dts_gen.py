import adidt

###############################################################################

cfg = {
    "clock": {
        "n2": 957,
        "out_dividers": [66, 3168, 1584, 20, 10],
        "output_clocks": {
            "AD9081_ref_clk": {"divider": 66, "rate": 45312500.0},
            "adc_fpga_ref_clk": {"divider": 20, "rate": 149531250.0},
            "adc_sysref": {"divider": 3168, "rate": 944010.4166666666},
            "dac_fpga_ref_clk": {"divider": 10, "rate": 299062500.0},
            "dac_sysref": {"divider": 1584, "rate": 1888020.8333333333},
        },
        "r2": 32,
        "vco": 2990625000.0,
        "vcxo": 100000000.0,
        "vcxo_doubler": 1,
    },
    "converter": {
        "clocking_option": "integrated_pll",
        "pll_config": {"d": 2, "m_vco": 8, "n_vco": 32, "r": 1},
    },
    "datapath_adc": {
        "cddc": {
            "decimations": [1, 1, 1, 1],
            "enabled": [True, True, True, True],
            "nco_frequencies": [0, 0, 0, 0],
            "nco_phases": [0, 0, 0, 0],
        },
        "fddc": {
            "decimations": [1, 1, 1, 1, 1, 1, 1, 1],
            "enabled": [False, False, False, False, False, False, False, False],
            "nco_frequencies": [0, 0, 0, 0, 0, 0, 0, 0],
            "nco_phases": [0, 0, 0, 0, 0, 0, 0, 0],
            "source": [1, 1, 2, 2, 3, 3, 4, 4],
        },
    },
    "datapath_dac": {
        "cduc": {
            "enabled": [True, True, True, True],
            "interpolation": 1,
            "nco_frequencies": [0, 0, 0, 0],
            "nco_phases": [0, 0, 0, 0],
            "sources": [[0], [0], [2], [2]],
        },
        "fduc": {
            "enabled": [False, False, False, False, False, False, False, False],
            "interpolation": 1,
            "nco_frequencies": [0, 0, 0, 0, 0, 0, 0, 0],
            "nco_phases": [0, 0, 0, 0, 0, 0, 0, 0],
        },
    },
    "fpga_adc": {
        "band": 0,
        "d": 2,
        "m": 1,
        "n": 80,
        "qty4_full_rate_enabled": 1,
        "type": "qpll",
        "vco": 11962500000.0,
    },
    "fpga_dac": {
        "band": 0,
        "d": 1,
        "m": 1,
        "n": 40,
        "qty4_full_rate_enabled": 1,
        "type": "qpll",
        "vco": 11962500000.0,
    },
    "jesd_adc": {
        "F": 12,
        "HD": 0,
        "K": 64,
        "L": 1,
        "M": 8,
        "Np": 12,
        "S": 1,
        "bit_clock": 5981250000.0,
        "converter_clock": 2900000000.0,
        "jesd_class": "jesd204c",
        "jesd_mode": "1.0",
        "multiframe_clock": 944010.4166666666,
        "sample_clock": 60416666.666666664,
    },
    "jesd_dac": {
        "F": 12,
        "HD": 0,
        "K": 64,
        "L": 1,
        "M": 8,
        "Np": 12,
        "S": 1,
        "bit_clock": 11962500000.0,
        "converter_clock": 5800000000.0,
        "jesd_class": "jesd204c",
        "jesd_mode": "0",
        "multiframe_clock": 1888020.8333333333,
        "sample_clock": 120833333.33333333,
    },
}


###############################################################################

fmc = adidt.ad9081_fmc()

clock, adc, dac = fmc.map_clocks_to_board_layout(cfg)

fmc.gen_dt(clock=clock, adc=adc, dac=dac)
