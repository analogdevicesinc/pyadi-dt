import pytest
import os

import adidt as dt


def test_import_profile():

    # Map to DT
    loc = os.path.dirname(__file__)
    dtb = os.path.join(loc, "adrv9009_ad9528.dtb")

    d = dt.adrv9009_dt(dt_source="local_file", local_dt_filepath=dtb, arch="arm64")

    loc = os.path.dirname(__file__)
    profile = os.path.join(
        loc, "Tx_BW200_IR245p76_Rx_BW200_OR245p76_ORx_BW200_OR245p76_DC245p76.txt"
    )
    dprofile = d.parse_profile(profile)

    import pprint
    dprofile = dict(dprofile)
    pprint.pprint(dprofile)
    pprint.pprint(dprofile['profile']['rx']['filter']['@gain_dB'])


    # Generate DT fragment
    som = dt.adrv9009_zu11eg(dt_source="local_file", local_dt_filepath=dtb, arch="arm64")
    # clock, adc, dac, fpga = som.map_clocks_to_board_layout(cfg)
    dts_filename = som.gen_dt(profile=dprofile)
    print(f"Generated DTS file: {dts_filename}")
