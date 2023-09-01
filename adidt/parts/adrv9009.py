import xmltodict
from typing import Dict
from adidt.dt import dt
from adidt.utils import profilewiz
import fdt
import math


def handle_ints(val):
    val = int(val)
    # Handles negative numbers
    return int(hex((val + (1 << 32)) % (1 << 32)), 16)


def parse_profile(filename):
    nsxml = profilewiz.profile_to_xml(filename)
    profile = xmltodict.parse(nsxml)["profile"]

    rx = profile['rx']
    tx = profile['tx']
    orx = profile['obsRx']
    lpbk = profile['lpbk']
    clocks = profile['clocks']

    # Custom translations
    # Clock Divide Ratio; 0=2.0, 1=2.5, 2=3.0, 3=4.0, 4=5.0
    HsDiv = {
        "2.0": 0,
        "2.5": 1,
        "3.0": 2,
        "4.0": 3,
        "5.0": 4,
    }
    try:
        clocks["clkPllHsDiv"] = HsDiv[clocks["clkPllHsDiv"]]
    except KeyError:
        raise ValueError(f"Unknown clock divider value {clocks['clkPllHsDiv']}")


    channel_enable = {
        'TAL_RXOFF': 0,
        'TAL_RX1': 1,
        'TAL_RX2': 2,
        'TAL_RX1RX2': 3,
        'TAL_ORXOFF': 0,
        'TAL_ORX1': 1,
        'TAL_ORX2': 2,
        'TAL_ORX1ORX2': 3,
        'TAL_TXOFF': 0,
        'TAL_TX1': 1,
        'TAL_TX2': 2,
        'TAL_TX1TX2': 3,
    }
    try:
        rx["rxChannels"] = channel_enable[rx["rxChannels"]]
    except KeyError:
        raise ValueError(f"Unknown rxChannels value {rx['rxChannels']}")

    try:
        orx["obsRxChannelsEnable"] = channel_enable[orx["obsRxChannelsEnable"]]
    except KeyError:
        val = orx["obsRxChannelsEnable"]
        raise ValueError(f"Unknown obsRxChannelsEnable value {val}")

    try:
        tx["txChannels"] = channel_enable[tx["txChannels"]]
    except KeyError:
        val = tx["txChannels"]
        raise ValueError(f"Unknown txChannels value {val}")

    # Gains can be negative so must be wrapped
    if int(rx["filter"]["@gain_dB"]) < 0:
        rx["filter"]["@gain_dB"] = f"({rx['filter']['@gain_dB']})"
    if int(orx["filter"]["@gain_dB"]) < 0:
        orx["filter"]["@gain_dB"] = f"({orx['filter']['@gain_dB']})"
    if int(tx["filter"]["@gain_dB"]) < 0:

        tx["filter"]["@gain_dB"] = f"({tx['filter']['@gain_dB']})"

    rx["rxAdcProfile"]["coefs"] = profilewiz.coefs_to_long_string(rx["rxAdcProfile"]["#text"])
    del(rx["rxAdcProfile"]["#text"])
    rx["filter"]["coefs"] = profilewiz.coefs_to_long_string(rx["filter"]["#text"])
    del(rx["filter"]["#text"])

    orx["filter"]["coefs"] = profilewiz.coefs_to_long_string(orx["filter"]["#text"])
    del(orx["filter"]["#text"])
    orx["orxBandPassAdcProfile"]["coefs"] = profilewiz.coefs_to_long_string(orx["orxBandPassAdcProfile"]["#text"])
    del(orx["orxBandPassAdcProfile"]["#text"])
    orx["orxLowPassAdcProfile"]["coefs"] = profilewiz.coefs_to_long_string(orx["orxLowPassAdcProfile"]["#text"])
    del(orx["orxLowPassAdcProfile"]["#text"])

    tx["filter"]["coefs"] = profilewiz.coefs_to_long_string(tx["filter"]["#text"])
    del(tx["filter"]["#text"])

    lpbk["lpbkAdcProfile"]["coefs"] = profilewiz.coefs_to_long_string(lpbk["lpbkAdcProfile"]["#text"])
    del(lpbk["lpbkAdcProfile"]["#text"])

    return {"rx": rx, "tx": tx, "orx": orx, "lpbk": lpbk, "clocks": clocks}


class adrv9009_dt(dt):
    def _add_tx_profile_fields(self, node, dprofile: Dict):
        """Add TX profile fields to device tree"""
        ...

    def _add_obs_profile_fields(self, node, dprofile: Dict):
        """Add OBS profile fields to device tree"""
        ...

    def _add_rx_profile_fields(self, node, dprofile: Dict):
        """Add RX profile fields to device tree"""
        rx = dprofile["profile"]["rx"]
        print(node.get_property("adi,rx-profile-rx-fir-gain_db"))
        node.set_property(
            "adi,rx-profile-rx-fir-gain_db", handle_ints(rx["filter"]["@gain_dB"])
        )
        node.set_property(
            "adi,rx-profile-rx-fir-num-fir-coefs", int(rx["filter"]["@numFirCoefs"])
        )
        rxtaps = rx["filter"]["#text"]
        rxtaps = rxtaps.split("\n")
        rxtaps = [handle_ints(tap.strip()) for tap in rxtaps]
        node.set_property("adi,rx-profile-rx-fir-coefs", rxtaps)

        node.set_property(
            "adi,rx-profile-rx-fir-decimation", int(rx["rxFirDecimation"])
        )
        node.set_property(
            "adi,rx-profile-rx-dec5-decimation", int(rx["rxDec5Decimation"])
        )
        node.set_property("adi,rx-profile-rhb1-decimation", int(rx["rhb1Decimation"]))

        node.set_property(
            "adi,rx-profile-rx-output-rate_khz", int(rx["rxOutputRate_kHz"])
        )
        node.set_property("adi,rx-profile-rf-bandwidth_hz", int(rx["rfBandwidth_Hz"]))
        node.set_property(
            "adi,rx-profile-rx-bbf3d-bcorner_khz", int(rx["rxBbf3dBCorner_kHz"])
        )

        adcp = rx["rxAdcProfile"]["#text"]
        adcp = adcp.split("\n")
        adcp = [handle_ints(tap.strip()) for tap in adcp]
        node.set_property("adi,rx-profile-rx-adc-profile", adcp)
        node.set_property("adi,rx-profile-rx-ddc-mode", int(rx["rxDdcMode"]))

        nco = rx["rxNcoShifterCfg"]
        node.set_property(
            "adi,rx-nco-shifter-band-a-input-band-width_khz",
            nco["bandAInputBandWidth_kHz"],
        )
        node.set_property(
            "adi,rx-nco-shifter-band-a-input-center-freq_khz",
            nco["bandAInputCenterFreq_kHz"],
        )
        node.set_property(
            "adi,rx-nco-shifter-band-a-nco1-freq_khz", nco["bandANco1Freq_kHz"]
        )
        node.set_property(
            "adi,rx-nco-shifter-band-a-nco2-freq_khz", nco["bandANco2Freq_kHz"]
        )

        node.set_property(
            "adi,rx-nco-shifter-band-binput-band-width_khz",
            nco["bandBInputBandWidth_kHz"],
        )
        node.set_property(
            "adi,rx-nco-shifter-band-binput-center-freq_khz",
            nco["bandBInputCenterFreq_kHz"],
        )
        node.set_property(
            "adi,rx-nco-shifter-band-bnco1-freq_khz", nco["bandBNco1Freq_kHz"]
        )
        node.set_property(
            "adi,rx-nco-shifter-band-bnco2-freq_khz", nco["bandBNco2Freq_kHz"]
        )

        # node.set_property("adi,rx-settings-framer-sel = <0>;
        # node.set_property("adi,rx-settings-rx-channels = <3>;

    def set_dt_node_from_config(
        self, node: fdt.Node, config: Dict, profile: Dict, append=False
    ):
        """Set ADRV9009 node from JIF configuration

        Args:
            node (fdt.Node): Device tree parent node of adrv9009
            config (Dict): Configuration struct generated from JIF
            append (boolean): Enable appending to subnode, if false the existing are removed
        """

        # Add profile fields
        self._add_rx_profile_fields(node, profile)
