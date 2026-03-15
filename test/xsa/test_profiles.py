import pytest

from adidt.xsa.exceptions import ProfileError
from adidt.xsa.profiles import ProfileManager, merge_profile_defaults


def test_profile_manager_lists_builtin_profiles():
    names = ProfileManager().list_profiles()
    assert "ad9081_zcu102" in names
    assert "adrv9009_zcu102" in names
    assert "fmcdaq2_zc706" in names
    assert "fmcdaq2_zcu102" in names


def test_profile_manager_loads_ad9081_profile():
    profile = ProfileManager().load("ad9081_zcu102")
    assert profile["name"] == "ad9081_zcu102"
    assert profile["defaults"]["clock"]["hmc7044_rx_channel"] == 10
    assert profile["defaults"]["clock"]["hmc7044_tx_channel"] == 6
    assert profile["defaults"]["ad9081_board"]["clock_spi"] == "spi1"
    assert profile["defaults"]["ad9081_board"]["clock_cs"] == 0
    assert profile["defaults"]["ad9081_board"]["adc_spi"] == "spi0"
    assert profile["defaults"]["ad9081_board"]["adc_cs"] == 0


def test_profile_manager_loads_adrv9009_profile():
    profile = ProfileManager().load("adrv9009_zcu102")
    assert profile["name"] == "adrv9009_zcu102"
    assert profile["defaults"]["adrv9009_board"]["spi_bus"] == "spi0"
    assert profile["defaults"]["adrv9009_board"]["clk_cs"] == 0
    assert profile["defaults"]["adrv9009_board"]["trx_cs"] == 1
    assert profile["defaults"]["adrv9009_board"]["rx_link_id"] == 1
    assert profile["defaults"]["adrv9009_board"]["rx_os_link_id"] == 2
    assert profile["defaults"]["adrv9009_board"]["tx_link_id"] == 0
    assert profile["defaults"]["adrv9009_board"]["tx_octets_per_frame"] == 2
    assert profile["defaults"]["adrv9009_board"]["rx_os_octets_per_frame"] == 2


def test_profile_manager_loads_fmcdaq2_zcu102_profile():
    profile = ProfileManager().load("fmcdaq2_zcu102")
    assert profile["name"] == "fmcdaq2_zcu102"
    assert profile["defaults"]["fmcdaq2_board"]["spi_bus"] == "spi0"
    assert profile["defaults"]["fmcdaq2_board"]["adc_jesd_link_id"] == 0
    assert profile["defaults"]["fmcdaq2_board"]["clock_cs"] == 0
    assert profile["defaults"]["fmcdaq2_board"]["adc_cs"] == 2
    assert profile["defaults"]["fmcdaq2_board"]["dac_cs"] == 1


def test_profile_manager_rejects_unknown_board_override_key(tmp_path):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "bad.json").write_text(
        """
        {
          "name": "bad",
          "defaults": {
            "adrv9009_board": {
              "spi_bus": "spi0",
              "typo_key": 123
            }
          }
        }
        """
    )

    with pytest.raises(ProfileError, match="unknown key"):
        ProfileManager(profile_dir=profile_dir).load("bad")


def test_profile_manager_rejects_invalid_list_override_type(tmp_path):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "bad_type.json").write_text(
        """
        {
          "name": "bad_type",
          "defaults": {
            "adrv9009_board": {
              "ad9528_channel_blocks": "not-a-list"
            }
          }
        }
        """
    )

    with pytest.raises(ProfileError, match="must be a list"):
        ProfileManager(profile_dir=profile_dir).load("bad_type")


def test_profile_manager_accepts_extended_fmcdaq2_board_keys(tmp_path):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "ok_fmcdaq2.json").write_text(
        """
        {
          "name": "ok_fmcdaq2",
          "defaults": {
            "fmcdaq2_board": {
              "spi_bus": "spi0",
              "clock_cs": 0,
              "adc_cs": 2,
              "dac_cs": 1,
              "adc_dma_label": "axi_ad9680_dma",
              "dac_dma_label": "axi_ad9144_dma",
              "adc_device_clk_idx": 13,
              "adc_sysref_clk_idx": 5,
              "adc_xcvr_ref_clk_idx": 4,
              "dac_device_clk_idx": 1,
              "dac_xcvr_ref_clk_idx": 9,
              "adc_sampling_frequency_hz": 1000000000
            }
          }
        }
        """
    )

    loaded = ProfileManager(profile_dir=profile_dir).load("ok_fmcdaq2")
    board = loaded["defaults"]["fmcdaq2_board"]
    assert board["adc_dma_label"] == "axi_ad9680_dma"
    assert board["adc_sampling_frequency_hz"] == 1000000000


def test_profile_manager_rejects_invalid_fmcdaq2_board_int_type(tmp_path):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "bad_fmcdaq2_type.json").write_text(
        """
        {
          "name": "bad_fmcdaq2_type",
          "defaults": {
            "fmcdaq2_board": {
              "spi_bus": "spi0",
              "adc_cs": "2"
            }
          }
        }
        """
    )

    with pytest.raises(ProfileError, match="expected integer"):
        ProfileManager(profile_dir=profile_dir).load("bad_fmcdaq2_type")


def test_profile_manager_rejects_invalid_fmcdaq2_board_negative_int(tmp_path):
    profile_dir = tmp_path / "profiles"
    profile_dir.mkdir()
    (profile_dir / "bad_fmcdaq2_range.json").write_text(
        """
        {
          "name": "bad_fmcdaq2_range",
          "defaults": {
            "fmcdaq2_board": {
              "spi_bus": "spi0",
              "dac_cs": -1
            }
          }
        }
        """
    )

    with pytest.raises(ProfileError, match="must be >= 0"):
        ProfileManager(profile_dir=profile_dir).load("bad_fmcdaq2_range")


def test_merge_profile_defaults_does_not_alias_mutable_values():
    profile = {
        "defaults": {
            "adrv9009_board": {
                "trx_profile_props": ["adi,a;"],
            }
        }
    }

    merged = merge_profile_defaults({}, profile)
    merged["adrv9009_board"]["trx_profile_props"].append("adi,b;")

    assert profile["defaults"]["adrv9009_board"]["trx_profile_props"] == ["adi,a;"]
