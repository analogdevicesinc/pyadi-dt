from pathlib import Path

from adidt.xsa.parity import check_manifest_against_dts
from adidt.xsa.reference import DriverManifest, LinkRequirement, RoleRequirement


def test_check_manifest_against_dts_marks_missing_roles(tmp_path: Path):
    manifest = DriverManifest(
        roles=[
            RoleRequirement(
                role="jesd_rx_link",
                compatible="adi,axi-jesd204-rx-1.0",
                label="rx0",
                source_file=tmp_path / "ref.dts",
            ),
            RoleRequirement(
                role="clock_chip",
                compatible="adi,hmc7044",
                label="clk0",
                source_file=tmp_path / "ref.dts",
            ),
        ]
    )
    merged_dts = '/ { rx0: jesd@0 { compatible = "adi,axi-jesd204-rx-1.0"; }; };\n'

    report = check_manifest_against_dts(manifest, merged_dts)

    assert report.total_roles == 2
    assert report.matched_roles == 1
    assert report.missing_roles == ["clock_chip"]


def test_check_manifest_against_dts_marks_missing_links(tmp_path: Path):
    manifest = DriverManifest(
        links=[
            LinkRequirement(
                source_label="rx0",
                property_name="jesd204-inputs",
                target_label="xcvr0",
                source_file=tmp_path / "ref.dts",
            )
        ]
    )
    merged_dts = '/ { rx0: jesd@0 { jesd204-inputs = <&xcvr1 0 2>; }; };\n'

    report = check_manifest_against_dts(manifest, merged_dts)

    assert report.total_links == 1
    assert report.matched_links == 0
    assert report.missing_links == ["rx0.jesd204-inputs->xcvr0"]
