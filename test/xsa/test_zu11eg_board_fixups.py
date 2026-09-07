"""Compile SoM carrier fixups to check the resulting Linux IO configuration."""

import shutil
import subprocess

import pytest

from adidt.xsa.build.board_fixups import apply_board_fixups


@pytest.mark.skipif(not shutil.which("dtc"), reason="dtc required")
def test_carrier_fixup_disables_unconfigured_smmu_and_supplies_ethernet_phy(tmp_path):
    pl = tmp_path / "pl.dtsi"
    pl.write_text("rx: ad_ip_jesd204_tpl_adc@84a00000 {};\n")
    pcw = tmp_path / "pcw.dtsi"
    pcw.write_text('&smmu { status = "okay"; };\n')
    apply_board_fixups("adrv9009_zu11eg", tmp_path)
    once = pcw.read_text()
    apply_board_fixups("adrv9009_zu11eg", tmp_path)
    assert pcw.read_text() == once
    assert "axi-adrv9009-rx-hpc@84a00000" in pl.read_text()
    source = tmp_path / "board.dts"
    source.write_text("""/dts-v1/;
/ {
 gic_r5: rpu-interrupt-controller { status = "okay"; };
 smmu: iommu { status = "okay"; };
 sdhci1: mmc {};
 psgtr: phy { #phy-cells = <4>; };
 gpio: gpio { #gpio-cells = <2>; gpio-controller; };
 gem0: ethernet0 {};
 gem3: ethernet3 { #address-cells = <1>; #size-cells = <0>; };
};
/include/ "pcw.dtsi"
""")
    dtb = tmp_path / "board.dtb"
    subprocess.run(
        ["dtc", "-I", "dts", "-O", "dtb", "-o", str(dtb), str(source)],
        check=True,
        capture_output=True,
    )

    def get(node, prop):
        return subprocess.check_output(
            ["fdtget", str(dtb), node, prop], text=True
        ).strip()

    assert get("/iommu", "status") == "disabled"
    assert get("/rpu-interrupt-controller", "status") == "disabled"
    assert get("/mmc", "bus-width") == "4"
    assert get("/ethernet3/ethernet-phy@1", "reg") == "1"
    assert get("/adidt-gtr-ref1", "clock-frequency") == "125000000"
