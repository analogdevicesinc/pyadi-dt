"""IIO names distinguish the two AD9371 ADC frontends."""

from adidt.xsa.build.board_fixups import apply_board_fixups


def test_primary_and_observation_names_are_distinct(tmp_path):
    pl = tmp_path / "pl.dtsi"
    pl.write_text(
        "rx: ad_ip_jesd204_tpl_adc@44a00000 {};\n"
        "obs: ad_ip_jesd204_tpl_adc@44a08000 {};\n"
        "tx: ad_ip_jesd204_tpl_dac@44a04000 {};\n"
    )
    apply_board_fixups("adrv937x_zc706", tmp_path)
    assert "rx: axi-ad9371-rx-hpc@44a00000" in pl.read_text()
    assert "obs: axi-ad9371-rx-obs-hpc@44a08000" in pl.read_text()
    assert "tx: axi-ad9371-tx-hpc@44a04000" in pl.read_text()
