from pathlib import Path

from adidt.xsa.build.board_fixups import apply_board_fixups


def test_zu11eg_fixup_adds_production_board_wiring(tmp_path: Path):
    pl_dtsi = tmp_path / "pl.dtsi"
    pcw_dtsi = tmp_path / "pcw.dtsi"
    pl_dtsi.write_text("/ { };\n")
    pcw_dtsi.write_text(
        '&smmu {\n\t\tstatus = "okay";\n};\n'
        "&spi0 {\n\t\tnum-cs = <3>;\n};\n"
        "&sdhci1 {\n\t\txlnx,bus-width = <8>;\n};\n"
        "&gem3 {\n\t\txlnx,bus-width = <2>;\n};\n"
    )

    apply_board_fixups("adrv9009_zu11eg", tmp_path)
    fixed = pl_dtsi.read_text()

    fixed_pcw = pcw_dtsi.read_text()
    assert '&smmu {\n\t\tstatus = "disabled";' in fixed_pcw
    assert "num-cs = <8>;" in fixed_pcw
    assert "is-decoded-cs;" in fixed_pcw
    assert "ad9542_out0_c: ad9542-out0-c" in fixed
    assert "clock-frequency = <125000000>;" in fixed
    assert "clock-frequency = <27000000>;" in fixed
    assert "clock-frequency = <26000000>;" in fixed
    assert "clocks = <&ad9542_out0_c>, <&ad9542_out1_a>, <&ad9542_out1_b>;" in fixed
    assert 'clock-names = "ref1", "ref2", "ref3";' in fixed
    assert "pinctrl_gem3_default: gem3-default" in fixed
    assert 'groups = "ethernet3_0_grp";' in fixed
    assert "phy-handle = <&phy1>;" in fixed
    assert "phys = <&psgtr 0 8 0 1>;" in fixed
    assert "mdiobus-connected = <&gem3>;" in fixed
    assert "phy0: phy@0" in fixed
    assert "phy1: phy@1" in fixed
    assert "reset-gpios = <&gpio 25 1>;" in fixed
    assert "reset-gpios = <&gpio 31 1>;" in fixed
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
    assert pcw_dtsi.read_text() == fixed_pcw


def test_unrelated_profile_does_not_receive_zu11eg_fixup(tmp_path: Path):
    pl_dtsi = tmp_path / "pl.dtsi"
    original = "/ { };\n"
    pl_dtsi.write_text(original)

    apply_board_fixups("adrv9009_zcu102", tmp_path)

    assert pl_dtsi.read_text() == original
