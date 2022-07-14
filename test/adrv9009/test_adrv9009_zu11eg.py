import os
from pprint import pprint

import adidt as dt
import pytest


def test_import_profile(kernel_build_config):

    # Map to DT
    # loc = os.path.dirname(__file__)
    # dtb = os.path.join(loc, "adrv9009_ad9528.dtb")

    # d = dt.adrv9009_dt(dt_source="local_file", local_dt_filepath=dtb, arch="arm64")

    loc = os.path.dirname(__file__)
    profile = os.path.join(
        loc, "Tx_BW200_IR245p76_Rx_BW200_OR245p76_ORx_BW200_OR245p76_DC245p76.txt"
    )
    # dprofile = d.parse_profile(profile)

    # Generate DT fragment
    som = dt.adrv9009_zu11eg()
    som.parse_profile(profile)
    # clock, adc, dac, fpga = som.map_clocks_to_board_layout(cfg)
    dts_filename = som.gen_dt()
    print(f"Generated DTS file: {dts_filename}")

    kernel_build_config["devicetree_to_test"] = os.path.join(os.getcwd(), dts_filename)


def test_kernel_build(kernel_build_config):
    kernel_build_config["branch"] = "master"
    loc = os.path.dirname(__file__)
    dts = os.path.join(loc, "adrv9009_zu11eg_out.dts")
    kernel_build_config["devicetree_to_test"] = dts
