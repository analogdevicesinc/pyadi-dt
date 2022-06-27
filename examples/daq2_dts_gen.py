import adidt

###############################################################################

cfg = {
    "clock": {
        "m1": 3,
        "n2": 24,
        "out_dividers": [1, 128, 4, 1, 64, 4],
        "output_clocks": {
            "AD9144_fpga_ref_clk": {"divider": 4, "rate": 250000000.0},
            "AD9144_ref_clk": {"divider": 1, "rate": 1000000000.0},
            "AD9144_sysref": {"divider": 64, "rate": 15625000.0},
            "AD9680_fpga_ref_clk": {"divider": 4, "rate": 250000000.0},
            "AD9680_ref_clk": {"divider": 1, "rate": 1000000000.0},
            "AD9680_sysref": {"divider": 128, "rate": 7812500.0},
        },
        "part": "AD9523-1",
        "r2": 1,
        "vco": 1000000000.0,
        "vcxo": 125000000.0,
    },
    "converter": [],
    "converter_AD9144": {"clocking_option": "direct", "interpolation": 1},
    "converter_AD9680": {"clocking_option": "direct", "decimation": 1},
    "fpga_AD9144": {
        "d": 1,
        "m": 1,
        "n1": 4,
        "n2": 5,
        "type": "cpll",
        "vco": 5000000000.0,
    },
    "fpga_AD9680": {
        "d": 1,
        "m": 1,
        "n1": 4,
        "n2": 5,
        "type": "cpll",
        "vco": 5000000000.0,
    },
    "jesd_AD9144": {
        "F": 1,
        "HD": 1,
        "K": 4,
        "L": 4,
        "M": 2,
        "Np": 16,
        "S": 1,
        "bit_clock": 10000000000.0,
        "converter_clock": 1000000000.0,
        "jesd_class": "jesd204b",
        "jesd_mode": "4",
        "multiframe_clock": 250000000.0,
        "sample_clock": 1000000000.0,
    },
    "jesd_AD9680": {
        "F": 1,
        "HD": 1,
        "K": 32,
        "L": 4,
        "M": 2,
        "Np": 16,
        "S": 1,
        "bit_clock": 10000000000.0,
        "converter_clock": 1000000000.0,
        "jesd_class": "jesd204b",
        "jesd_mode": "136",
        "multiframe_clock": 31250000.0,
        "sample_clock": 1000000000.0,
    },
}


###############################################################################

d2 = adidt.daq2()

clock, adc, dac = d2.map_clocks_to_board_layout(cfg)

d2.gen_dt(clock=clock, adc=adc, dac=dac)