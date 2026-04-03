from pathlib import Path
import json

from adidt.xsa.parity import (
    ParityReport,
    check_manifest_against_dts,
    write_parity_reports,
)
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


def test_check_manifest_against_dts_counts_role_multiplicity(tmp_path: Path):
    manifest = DriverManifest(
        roles=[
            RoleRequirement(
                role="jesd_rx_link",
                compatible="adi,axi-jesd204-rx-1.0",
                label="rx0",
                source_file=tmp_path / "ref.dts",
            ),
            RoleRequirement(
                role="jesd_rx_link",
                compatible="adi,axi-jesd204-rx-1.0",
                label="rx1",
                source_file=tmp_path / "ref.dts",
            ),
        ]
    )
    merged_dts = '/ { rx0: jesd@0 { compatible = "adi,axi-jesd204-rx-1.0"; }; };\n'

    report = check_manifest_against_dts(manifest, merged_dts)

    assert report.total_roles == 2
    assert report.matched_roles == 1
    assert report.missing_roles == ["jesd_rx_link:rx1"]


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
    merged_dts = "/ { rx0: jesd@0 { jesd204-inputs = <&xcvr1 0 2>; }; };\n"

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
    merged_dts = "/ { rx0: jesd@0 { adi,frames-per-multiframe = <32>; }; };\n"

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
        "/ {\n"
        "  rx0: jesd@0 { jesd204-inputs = <&wrong 0 1>; };\n"
        "  other: jesd@1 { jesd204-inputs = <&xcvr0 0 1>; };\n"
        "};\n"
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
        "/ {\n"
        '  rx0: jesd@0 { compatible = "stub,wrong"; };\n'
        '  other: jesd@1 { compatible = "adi,axi-jesd204-rx-1.0"; };\n'
        "};\n"
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
        "/ {\n"
        "  rx0: jesd@0 { adi,frames-per-multiframe = <32>; };\n"
        "  other: jesd@1 { adi,octets-per-frame = <4>; };\n"
        "};\n"
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
    merged_dts = "/ { rx0: jesd@0 { adi,octets-per-frame = <8>; }; };\n"

    report = check_manifest_against_dts(manifest, merged_dts)

    assert report.total_properties == 1
    assert report.matched_properties == 0
    assert report.missing_properties == []
    assert report.mismatched_properties == [
        "rx0.adi,octets-per-frame: expected <4>, got <8>"
    ]


def test_check_manifest_against_dts_normalizes_property_value_whitespace(
    tmp_path: Path,
):
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
    merged_dts = "/ { rx0: jesd@0 { adi,octets-per-frame = < 4 >; }; };\n"

    report = check_manifest_against_dts(manifest, merged_dts)

    assert report.matched_properties == 1
    assert report.missing_properties == []


def test_check_manifest_against_dts_sorts_gap_lists(tmp_path: Path):
    manifest = DriverManifest(
        roles=[
            RoleRequirement(
                role="clock_chip",
                compatible="adi,hmc7044",
                label="clk1",
                source_file=tmp_path / "ref.dts",
            ),
            RoleRequirement(
                role="clock_chip",
                compatible="adi,hmc7044",
                label="clk0",
                source_file=tmp_path / "ref.dts",
            ),
        ],
        links=[
            LinkRequirement(
                source_label="rx1",
                property_name="jesd204-inputs",
                target_label="xcvr1",
                source_file=tmp_path / "ref.dts",
            ),
            LinkRequirement(
                source_label="rx0",
                property_name="jesd204-inputs",
                target_label="xcvr0",
                source_file=tmp_path / "ref.dts",
            ),
        ],
        properties=[
            PropertyRequirement(
                source_label="rx1",
                property_name="adi,octets-per-frame",
                expected_value="<8>",
                source_file=tmp_path / "ref.dts",
            ),
            PropertyRequirement(
                source_label="rx0",
                property_name="adi,octets-per-frame",
                expected_value="<4>",
                source_file=tmp_path / "ref.dts",
            ),
        ],
    )
    merged_dts = "/ { rx1: jesd@1 { adi,octets-per-frame = <4>; }; };\n"

    report = check_manifest_against_dts(manifest, merged_dts)

    assert report.missing_roles == ["clock_chip:clk0", "clock_chip:clk1"]
    assert report.missing_links == [
        "rx0.jesd204-inputs->xcvr0",
        "rx1.jesd204-inputs->xcvr1",
    ]
    assert report.missing_properties == ["rx0.adi,octets-per-frame=<4>"]
    assert report.mismatched_properties == [
        "rx1.adi,octets-per-frame: expected <8>, got <4>"
    ]


def test_check_manifest_against_dts_deduplicates_gap_lists(tmp_path: Path):
    manifest = DriverManifest(
        roles=[
            RoleRequirement(
                role="clock_chip",
                compatible="adi,hmc7044",
                label="clk0",
                source_file=tmp_path / "ref.dts",
            ),
            RoleRequirement(
                role="clock_chip",
                compatible="adi,hmc7044",
                label="clk0",
                source_file=tmp_path / "ref.dts",
            ),
        ],
        links=[
            LinkRequirement(
                source_label="rx0",
                property_name="jesd204-inputs",
                target_label="xcvr0",
                source_file=tmp_path / "ref.dts",
            ),
            LinkRequirement(
                source_label="rx0",
                property_name="jesd204-inputs",
                target_label="xcvr0",
                source_file=tmp_path / "ref.dts",
            ),
        ],
        properties=[
            PropertyRequirement(
                source_label="rx0",
                property_name="adi,octets-per-frame",
                expected_value="<8>",
                source_file=tmp_path / "ref.dts",
            ),
            PropertyRequirement(
                source_label="rx0",
                property_name="adi,octets-per-frame",
                expected_value="<8>",
                source_file=tmp_path / "ref.dts",
            ),
        ],
    )
    merged_dts = "/ { rx0: jesd@0 { adi,octets-per-frame = <4>; }; };\n"

    report = check_manifest_against_dts(manifest, merged_dts)

    assert report.missing_roles == ["clock_chip:clk0"]
    assert report.missing_links == ["rx0.jesd204-inputs->xcvr0"]
    assert report.mismatched_properties == [
        "rx0.adi,octets-per-frame: expected <8>, got <4>"
    ]


def test_write_parity_reports_emits_stable_schema_keys(tmp_path: Path):
    report = ParityReport(
        total_roles=1,
        matched_roles=0,
        total_links=1,
        matched_links=0,
        total_properties=1,
        matched_properties=0,
        missing_roles=["clock_chip:clk0"],
        missing_links=["rx0.jesd204-inputs->xcvr0"],
        missing_properties=["rx0.adi,octets-per-frame=<4>"],
        mismatched_properties=["rx1.adi,octets-per-frame: expected <8>, got <4>"],
    )

    map_path, _ = write_parity_reports(report, tmp_path, "demo")
    data = json.loads(map_path.read_text())

    expected_keys = {
        "coverage",
        "total_roles",
        "matched_roles",
        "total_links",
        "matched_links",
        "total_properties",
        "matched_properties",
        "missing_roles",
        "missing_links",
        "missing_properties",
        "mismatched_properties",
        "items",
        "link_items",
        "property_items",
    }
    assert set(data.keys()) == expected_keys


def test_write_parity_reports_serializes_sorted_gap_lists(tmp_path: Path):
    report = ParityReport(
        total_roles=0,
        matched_roles=0,
        total_links=0,
        matched_links=0,
        total_properties=0,
        matched_properties=0,
        missing_roles=["b", "a"],
        missing_links=["b", "a"],
        missing_properties=["b", "a"],
        mismatched_properties=["b", "a"],
    )

    map_path, _ = write_parity_reports(report, tmp_path, "demo")
    data = json.loads(map_path.read_text())

    assert data["missing_roles"] == ["a", "b"]
    assert data["missing_links"] == ["a", "b"]
    assert data["missing_properties"] == ["a", "b"]
    assert data["mismatched_properties"] == ["a", "b"]


def test_write_parity_reports_emits_coverage_percentages(tmp_path: Path):
    report = ParityReport(
        total_roles=4,
        matched_roles=3,
        total_links=5,
        matched_links=2,
        total_properties=3,
        matched_properties=3,
    )

    map_path, coverage_path = write_parity_reports(report, tmp_path, "demo")
    data = json.loads(map_path.read_text())
    md = coverage_path.read_text()

    assert data["coverage"]["roles_pct"] == 75.0
    assert data["coverage"]["links_pct"] == 40.0
    assert data["coverage"]["properties_pct"] == 100.0
    assert data["coverage"]["overall_pct"] == 66.7
    assert data["coverage"]["overall_matched"] == 8
    assert data["coverage"]["overall_total"] == 12
    assert "Role coverage: 75.0%" in md
    assert "Link coverage: 40.0%" in md
    assert "Property coverage: 100.0%" in md
    assert "Overall coverage: 66.7%" in md
    assert "Overall matched items: 8/12" in md
