import pytest
import os

import adidt as dt


def test_adrv9009_profile_writez():

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

    node = d.get_node_by_compatible("adrv9009")
    # for n in node:
    #     print(n)
    # assert len(node) == 1
    node = node[3]

    config = {}
    d.set_dt_node_from_config(node=node, config=config, profile=dprofile)

    # # Checks
    # d.write_out_dts("test.dts")
