from pathlib import Path

from adidt.xsa.parity import check_manifest_against_dts
from adidt.xsa.reference import (
    DriverManifest,
    LinkRequirement,
    PropertyRequirement,
    RoleRequirement,
)


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
    assert report.missing_roles == ["clock_chip:clk0"]


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


def test_check_manifest_against_dts_marks_missing_properties(tmp_path: Path):
    manifest = DriverManifest(
        properties=[
            PropertyRequirement(
                source_label="rx0",
                property_name="adi,octets-per-frame",
                expected_value="<4>",
                source_file=tmp_path / "ref.dts",
            )
        ]
    )
    merged_dts = '/ { rx0: jesd@0 { adi,frames-per-multiframe = <32>; }; };\n'

    report = check_manifest_against_dts(manifest, merged_dts)

    assert report.total_properties == 1
    assert report.matched_properties == 0
    assert report.missing_properties == ["rx0.adi,octets-per-frame=<4>"]


def test_check_manifest_against_dts_scopes_link_to_source_node(tmp_path: Path):
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
    merged_dts = (
        '/ {\n'
        '  rx0: jesd@0 { jesd204-inputs = <&wrong 0 1>; };\n'
        '  other: jesd@1 { jesd204-inputs = <&xcvr0 0 1>; };\n'
        '};\n'
    )

    report = check_manifest_against_dts(manifest, merged_dts)

    assert report.matched_links == 0
    assert report.missing_links == ["rx0.jesd204-inputs->xcvr0"]


def test_check_manifest_against_dts_scopes_role_to_source_label(tmp_path: Path):
    manifest = DriverManifest(
        roles=[
            RoleRequirement(
                role="jesd_rx_link",
                compatible="adi,axi-jesd204-rx-1.0",
                label="rx0",
                source_file=tmp_path / "ref.dts",
            )
        ]
    )
    merged_dts = (
        '/ {\n'
        '  rx0: jesd@0 { compatible = "stub,wrong"; };\n'
        '  other: jesd@1 { compatible = "adi,axi-jesd204-rx-1.0"; };\n'
        '};\n'
    )

    report = check_manifest_against_dts(manifest, merged_dts)

    assert report.matched_roles == 0
    assert report.missing_roles == ["jesd_rx_link:rx0"]


def test_check_manifest_against_dts_scopes_property_to_source_node(tmp_path: Path):
    manifest = DriverManifest(
        properties=[
            PropertyRequirement(
                source_label="rx0",
                property_name="adi,octets-per-frame",
                expected_value="<4>",
                source_file=tmp_path / "ref.dts",
            )
        ]
    )
    merged_dts = (
        '/ {\n'
        '  rx0: jesd@0 { adi,frames-per-multiframe = <32>; };\n'
        '  other: jesd@1 { adi,octets-per-frame = <4>; };\n'
        '};\n'
    )

    report = check_manifest_against_dts(manifest, merged_dts)

    assert report.matched_properties == 0
    assert report.missing_properties == ["rx0.adi,octets-per-frame=<4>"]


def test_check_manifest_against_dts_marks_mismatched_property_values(tmp_path: Path):
    manifest = DriverManifest(
        properties=[
            PropertyRequirement(
                source_label="rx0",
                property_name="adi,octets-per-frame",
                expected_value="<4>",
                source_file=tmp_path / "ref.dts",
            )
        ]
    )
    merged_dts = '/ { rx0: jesd@0 { adi,octets-per-frame = <8>; }; };\n'

    report = check_manifest_against_dts(manifest, merged_dts)

    assert report.total_properties == 1
    assert report.matched_properties == 0
    assert report.missing_properties == []
    assert report.mismatched_properties == ["rx0.adi,octets-per-frame: expected <4>, got <8>"]


def test_check_manifest_against_dts_normalizes_property_value_whitespace(tmp_path: Path):
    manifest = DriverManifest(
        properties=[
            PropertyRequirement(
                source_label="rx0",
                property_name="adi,octets-per-frame",
                expected_value="<4>",
                source_file=tmp_path / "ref.dts",
            )
        ]
    )
    merged_dts = '/ { rx0: jesd@0 { adi,octets-per-frame = < 4 >; }; };\n'

    report = check_manifest_against_dts(manifest, merged_dts)

    assert report.matched_properties == 1
    assert report.missing_properties == []
