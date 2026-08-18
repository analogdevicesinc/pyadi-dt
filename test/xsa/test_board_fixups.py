from pathlib import Path

from adidt.xsa.build.board_fixups import apply_board_fixups


def test_zu11eg_fixup_adds_production_sd1_pinmux(tmp_path: Path):
    pl_dtsi = tmp_path / "pl.dtsi"
    pcw_dtsi = tmp_path / "pcw.dtsi"
    pl_dtsi.write_text("/ { };\n")
    pcw_dtsi.write_text(
        "&sdhci1 {\n\t\txlnx,bus-width = <8>;\n};\n"
        "&gem3 {\n\t\txlnx,bus-width = <2>;\n};\n"
    )

    apply_board_fixups("adrv9009_zu11eg", tmp_path)
    fixed = pl_dtsi.read_text()

    assert 'status = "disabled";' in fixed
    assert "num-cs = <8>;" in fixed
    assert "is-decoded-cs;" in fixed
    assert "pinctrl_sdhci1_default: sdhci1-default" in fixed
    assert 'groups = "sdio1_0_grp";' in fixed
    assert "pinctrl-0 = <&pinctrl_sdhci1_default>;" in fixed
    assert "no-1-8-v;" in fixed
    assert "disable-wp;" in fixed
    assert "xlnx,mio_bank = <1>;" in fixed
    assert "xlnx,bus-width = <8>;" not in pcw_dtsi.read_text()
    assert "xlnx,bus-width = <2>;" in pcw_dtsi.read_text()

    apply_board_fixups("adrv9009_zu11eg", tmp_path)
    assert pl_dtsi.read_text() == fixed


def test_unrelated_profile_does_not_receive_zu11eg_fixup(tmp_path: Path):
    pl_dtsi = tmp_path / "pl.dtsi"
    original = "/ { };\n"
    pl_dtsi.write_text(original)

    apply_board_fixups("adrv9009_zcu102", tmp_path)

    assert pl_dtsi.read_text() == original
