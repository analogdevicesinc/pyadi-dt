from __future__ import annotations

import json
from pathlib import Path

import pytest

from adidt.profiles import parse_ad9371_profile
from adidt.xsa.build.node_builder import NodeBuilder
from adidt.xsa.config.board_configs import ADRV9009BoardConfig
from adidt.xsa.parse.topology import ConverterInstance, Jesd204Instance, XsaTopology

ROOT = Path(__file__).parents[2]
PROFILES = ROOT / "examples" / "xsa" / "profiles" / "ad9371_5"
PROFILE_NAMES = [
    "profile_TxBW100_ORxBW100_RxBW100.txt",
    "profile_TxBW100_ORxBW100_RxBW20.txt",
    "profile_TxBW100_ORxBW100_RxBW50.txt",
    "profile_TxBW200_ORxBW200_RxBW100.txt",
    "profile_TxBW50_ORxBW50_RxBW25.txt",
    "profile_TxBW50_ORxBW50_RxBW50.txt",
]


@pytest.mark.parametrize("filename", PROFILE_NAMES)
def test_parse_all_canonical_ad9371_profiles(filename):
    profile = parse_ad9371_profile(PROFILES / filename)
    assert profile.name
    assert profile.sections["clocks"]["scalars"]["deviceClock_kHz"] == 122_880
    props = profile.to_dt_properties()
    assert len(props) == 51
    assert any(prop.startswith("adi,rx-profile-rx-fir-coefs") for prop in props)
    assert any(prop.startswith("adi,obs-profile-custom-adc-profile") for prop in props)
    assert any(prop.startswith("adi,tx-profile-tx-fir-coefs") for prop in props)


def test_profile_translation_matches_hardware_reference_properties():
    profile = parse_ad9371_profile(PROFILES / "profile_TxBW200_ORxBW200_RxBW100.txt")
    reference = json.loads(
        (ROOT / "adidt/xsa/config/profiles/adrv937x_zc706.json").read_text()
    )["defaults"]["adrv9009_board"]["trx_profile_props"]
    assert profile.to_dt_properties() == reference


def _topology() -> XsaTopology:
    return XsaTopology(
        jesd204_rx=[
            Jesd204Instance(
                name="axi_ad9371_rx_jesd_rx_axi",
                base_addr=0x44AA0000,
                num_lanes=4,
                irq=106,
                link_clk="axi_rx_clkgen_clk",
                direction="rx",
            ),
            Jesd204Instance(
                name="axi_ad9371_rx_os_jesd_rx_axi",
                base_addr=0x44AB0000,
                num_lanes=2,
                irq=104,
                link_clk="axi_rx_os_clkgen_clk",
                direction="rx",
            ),
        ],
        jesd204_tx=[
            Jesd204Instance(
                name="axi_ad9371_tx_jesd_tx_axi",
                base_addr=0x44A90000,
                num_lanes=4,
                irq=105,
                link_clk="axi_tx_clkgen_clk",
                direction="tx",
            )
        ],
        converters=[
            ConverterInstance(
                name="axi_ad9371_0",
                ip_type="axi_ad9371",
                base_addr=0x44A00000,
                spi_bus=None,
                spi_cs=None,
            )
        ],
    )


def test_node_builder_loads_ad9371_profile_path():
    profile_path = PROFILES / "profile_TxBW50_ORxBW50_RxBW25.txt"
    cfg = {
        "jesd": {
            "rx": {"F": 4, "K": 32},
            "tx": {"F": 2, "K": 32},
        },
        "adrv9009_board": {"ad9371_profile_path": str(profile_path)},
    }
    nodes = NodeBuilder().build(_topology(), cfg)
    merged = "\n".join(nodes["converters"])
    assert "adi,rx-profile-iq-rate_khz = <0x7800>;" in merged
    assert "adi,tx-profile-iq-rate_khz = <0xf000>;" in merged
    assert "adi,rx-profile-rx-fir-num-fir-coefs = <0x48>;" in merged


def test_profile_path_overrides_merged_board_profile_properties():
    cfg = {
        "jesd": {"rx": {"F": 4, "K": 32}, "tx": {"F": 2, "K": 32}},
        "adrv9009_board": {
            "ad9371_profile_path": str(PROFILES / PROFILE_NAMES[0]),
            "trx_profile_props": ["adi,test = <1>;"],
        },
    }
    nodes = NodeBuilder().build(_topology(), cfg)
    merged = "\n".join(nodes["converters"])
    assert "adi,test = <1>;" not in merged
    assert "adi,rx-profile-iq-rate_khz = <0x1e000>;" in merged


def test_ad9371_builder_prefers_three_link_jif_framing():
    cfg = {
        "jesd": {
            "rx": {"F": 4, "K": 32},
            "obs": {"F": 6, "K": 16},
            "tx": {"F": 5, "K": 24, "M": 4},
        },
        "adrv9009_board": {
            "tx_octets_per_frame": 7,
            "rx_os_octets_per_frame": 8,
        },
    }
    merged = "\n".join(NodeBuilder().build(_topology(), cfg)["converters"])

    obs_start = merged.index("&axi_ad9371_rx_os_jesd_rx_axi {")
    obs_end = merged.index("\n\t};", obs_start)
    obs = merged[obs_start:obs_end]
    assert "adi,octets-per-frame = <6>;" in obs
    assert "adi,frames-per-multiframe = <16>;" in obs

    tx_start = merged.index("&axi_ad9371_tx_jesd_tx_axi {")
    tx_end = merged.index("\n\t};", tx_start)
    tx = merged[tx_start:tx_end]
    assert "adi,octets-per-frame = <5>;" in tx
    assert "adi,frames-per-multiframe = <24>;" in tx


def test_board_config_rejects_empty_ad9371_profile_path():
    with pytest.raises(ValueError, match="ad9371_profile_path"):
        ADRV9009BoardConfig(ad9371_profile_path="")


def test_rejects_non_integral_scalar(tmp_path):
    source = PROFILES / "profile_TxBW200_ORxBW200_RxBW100.txt"
    malformed = tmp_path / "non_integral.txt"
    malformed.write_text(source.read_text().replace("<adcDiv=1>", "<adcDiv=1.5>", 1))
    with pytest.raises(ValueError, match="adcDiv must be an integer"):
        parse_ad9371_profile(malformed).to_dt_properties()


def test_rejects_out_of_range_coefficient(tmp_path):
    source = PROFILES / "profile_TxBW200_ORxBW200_RxBW100.txt"
    malformed = tmp_path / "coefficient.txt"
    malformed.write_text(source.read_text().replace("-5\n", "40000\n", 1))
    with pytest.raises(ValueError, match="outside signed 16-bit range"):
        parse_ad9371_profile(malformed).to_dt_properties()


def test_rejects_unsupported_profile_version(tmp_path):
    source = PROFILES / "profile_TxBW200_ORxBW200_RxBW100.txt"
    malformed = tmp_path / "version.txt"
    malformed.write_text(source.read_text().replace("version=0", "version=1", 1))
    with pytest.raises(ValueError, match="Unsupported AD9371 profile version"):
        parse_ad9371_profile(malformed)


def test_rejects_duplicate_section(tmp_path):
    source = PROFILES / "profile_TxBW200_ORxBW200_RxBW100.txt"
    text = source.read_text()
    clocks = text[text.index("<clocks>") : text.index("</clocks>") + len("</clocks>")]
    malformed = tmp_path / "duplicate.txt"
    malformed.write_text(text.replace("</clocks>", f"</clocks>\n{clocks}", 1))
    with pytest.raises(ValueError, match="duplicate clocks section"):
        parse_ad9371_profile(malformed)
