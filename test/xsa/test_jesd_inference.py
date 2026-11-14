"""Tests for reading JESD204 framing from the XSA's transport-layer cores."""

import io
import zipfile

import pytest

from adidt.xsa.build.builders.ad9081 import _resolve_link_mode
from adidt.xsa.exceptions import ConfigError
from adidt.xsa.parse.topology import (
    Jesd204Instance,
    TplCoreInstance,
    XsaParser,
    XsaTopology,
)
from adidt.xsa.pipeline import XsaPipeline


def _tpl(direction, m, lanes, np_, s=1, n=None):
    return TplCoreInstance(
        name=f"{direction}_tpl",
        direction=direction,
        num_channels=m,
        num_lanes=lanes,
        samples_per_frame=s,
        converter_resolution=n or np_,
        bits_per_sample=np_,
    )


def _link(direction, encoder="8b10b"):
    return Jesd204Instance(
        name=f"axi_{direction}_jesd",
        base_addr=0x84A90000,
        num_lanes=4,
        irq=None,
        link_clk="clk",
        direction=direction,
        encoder=encoder,
    )


@pytest.mark.parametrize(
    "m, lanes, np_, s, encoder, expected_f, expected_k",
    [
        # Framing/K pairs below are the ones the kernel reference DTS use.
        (8, 4, 16, 1, "8b10b", 4, 32),
        (4, 8, 16, 1, "8b10b", 1, 32),
        (8, 2, 16, 1, "8b10b", 8, 32),
        (8, 1, 12, 1, "64b66b", 12, 64),
        (8, 8, 12, 2, "64b66b", 3, 256),
        (2, 2, 12, 4, "64b66b", 6, 128),
    ],
)
def test_framing_follows_from_tpl_parameters(
    m, lanes, np_, s, encoder, expected_f, expected_k
):
    topology = XsaTopology(
        jesd204_rx=[_link("rx", encoder)], tpl_cores=[_tpl("rx", m, lanes, np_, s)]
    )
    framing = topology.jesd_framing("rx")
    assert framing == {
        "M": m,
        "L": lanes,
        "S": s,
        "N": np_,
        "Np": np_,
        "F": expected_f,
        "K": expected_k,
    }


def test_framing_is_not_guessed_when_ambiguous_or_absent():
    topology = XsaTopology(
        tpl_cores=[_tpl("rx", 4, 2, 16), _tpl("rx", 2, 2, 16), _tpl("tx", 3, 4, 16)]
    )
    # Two RX transport cores (e.g. RX + observation): caller must choose.
    assert topology.jesd_framing("rx") is None
    # 3 converters x 16 bits over 4 lanes is not a whole number of octets.
    assert topology.jesd_framing("tx") is None
    assert XsaTopology().jesd_framing("rx") is None


def test_xsa_defaults_fill_only_missing_keys_and_leave_input_alone():
    topology = XsaTopology(
        jesd204_rx=[_link("rx")],
        jesd204_tx=[_link("tx")],
        tpl_cores=[_tpl("rx", 4, 8, 16), _tpl("tx", 4, 8, 16)],
    )
    cfg = {"jesd": {"rx": {"K": 64, "L": 2}}, "clock": {"x": 1}}

    merged = XsaPipeline._apply_xsa_jesd_defaults(cfg, topology)

    # Explicit values survive even where the XSA disagrees.
    assert merged["jesd"]["rx"] == {
        "K": 64,
        "L": 2,
        "M": 4,
        "S": 1,
        "N": 16,
        "Np": 16,
        "F": 1,
    }
    assert merged["jesd"]["tx"]["L"] == 8
    assert merged["clock"] == {"x": 1}
    assert cfg == {"jesd": {"rx": {"K": 64, "L": 2}}, "clock": {"x": 1}}


def test_xsa_defaults_are_a_no_op_without_tpl_cores():
    cfg = {"jesd": {"rx": {"F": 4}}}
    assert XsaPipeline._apply_xsa_jesd_defaults(cfg, XsaTopology()) is cfg


@pytest.mark.parametrize(
    "direction, link, expected",
    [
        ("rx", {"M": 8, "L": 4}, 10),
        ("tx", {"M": 8, "L": 4}, 9),
        ("rx", {"M": 4, "L": 8, "Np": 16, "S": 1}, 18),
        ("tx", {"M": 4, "L": 8, "Np": 16, "S": 1}, 17),
        # M=4, L=8 exists at both Np=16 and Np=12: Np decides.
        ("rx", {"M": 4, "L": 8, "Np": 12, "S": 4}, 27),
        ("tx", {"M": 8, "L": 8, "Np": 12, "S": 2}, 24),
    ],
)
def test_ad9081_link_mode_follows_reference_device_trees(direction, link, expected):
    assert _resolve_link_mode({}, {direction: link}, direction) == expected


def test_ad9081_link_mode_explicit_values_win():
    jesd = {"rx": {"M": 8, "L": 4, "mode": 3}}
    assert _resolve_link_mode({"rx_link_mode": 7}, jesd, "rx") == 7
    assert _resolve_link_mode({}, jesd, "rx") == 3


@pytest.mark.parametrize(
    "link",
    [
        {},  # nothing known
        {"M": 4, "L": 8},  # two reference modes share this M/L
        {"M": 6, "L": 3},  # not a reference framing
    ],
)
def test_ad9081_link_mode_refuses_to_guess(link):
    with pytest.raises(ConfigError):
        _resolve_link_mode({}, {"rx": link}, "rx")


def test_parser_reads_tpl_framing_and_link_encoding(tmp_path):
    def params(**kw):
        return "".join(f'<PARAMETER NAME="{k}" VALUE="{v}"/>' for k, v in kw.items())

    hwh = f"""<?xml version="1.0" encoding="UTF-8"?>
<EDKSYSTEM>
  <SYSTEMINFO DEVICE="xczu9eg" PACKAGE="ffvb1156" SPEEDGRADE="-2" NAME="system"/>
  <MODULES>
    <MODULE INSTANCE="axi_mxfe_rx_jesd_rx_axi" MODTYPE="axi_jesd204_rx">
      <PARAMETERS>{params(NUM_LANES=1, LINK_MODE=2)}</PARAMETERS>
      <MEMRANGE BASEVALUE="0x84A90000" />
    </MODULE>
    <MODULE INSTANCE="rx_mxfe_tpl_core_adc_tpl_core" MODTYPE="ad_ip_jesd204_tpl_adc">
      <PARAMETERS>{
        params(
            NUM_CHANNELS=8,
            NUM_LANES=1,
            SAMPLES_PER_FRAME=1,
            CONVERTER_RESOLUTION=12,
            BITS_PER_SAMPLE=12,
        )
    }</PARAMETERS>
      <MEMRANGE BASEVALUE="0x84A10000" />
    </MODULE>
    <MODULE INSTANCE="tx_mxfe_tpl_core_dac_tpl_core" MODTYPE="ad_ip_jesd204_tpl_dac">
      <PARAMETERS>{
        params(
            NUM_CHANNELS=8,
            NUM_LANES=4,
            SAMPLES_PER_FRAME=1,
            CONVERTER_RESOLUTION=16,
            BITS_PER_SAMPLE=16,
        )
    }</PARAMETERS>
      <MEMRANGE BASEVALUE="0x84B10000" />
    </MODULE>
  </MODULES>
</EDKSYSTEM>
"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("system.hwh", hwh)
    xsa = tmp_path / "system_top.xsa"
    xsa.write_bytes(buf.getvalue())

    topology = XsaParser().parse(xsa)

    assert topology.jesd204_rx[0].encoder == "64b66b"
    assert {c.direction: (c.num_channels, c.num_lanes) for c in topology.tpl_cores} == {
        "rx": (8, 1),
        "tx": (8, 4),
    }
    assert topology.jesd_framing("rx")["F"] == 12
    assert topology.jesd_framing("rx")["K"] == 64
    # No TX link IP in this fixture: encoding falls back to 8b10b.
    assert topology.jesd_framing("tx") == {
        "M": 8,
        "L": 4,
        "S": 1,
        "N": 16,
        "Np": 16,
        "F": 4,
        "K": 32,
    }
