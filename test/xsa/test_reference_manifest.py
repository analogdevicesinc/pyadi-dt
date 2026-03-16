from pathlib import Path

import pytest

from adidt.xsa.reference import ReferenceManifestExtractor


def test_extract_manifest_resolves_nested_includes_and_maps_roles(tmp_path: Path):
    root = tmp_path / "root.dts"
    common = tmp_path / "common.dtsi"
    jesd = tmp_path / "jesd.dtsi"

    root.write_text('#include "common.dtsi"\n/ { model = "x"; };\n')
    common.write_text(
        '#include "jesd.dtsi"\n'
        "/ {\n"
        '\tclk0: clock@0 { compatible = "adi,hmc7044"; };\n'
        '\tadc0: adc@0 { compatible = "adi,ad9081"; };\n'
        "};\n"
    )
    jesd.write_text(
        "/ {\n"
        '\trx0: jesd-rx@0 { compatible = "adi,axi-jesd204-rx-1.0"; };\n'
        '\ttx0: jesd-tx@0 { compatible = "adi,axi-jesd204-tx-1.0"; };\n'
        "};\n"
    )

    manifest = ReferenceManifestExtractor().extract(root)

    assert set(manifest.included_files) == {root, common, jesd}
    assert sorted(r.role for r in manifest.roles) == [
        "ad9081_core",
        "clock_chip",
        "jesd_rx_link",
        "jesd_tx_link",
    ]


def test_extract_manifest_collects_jesd_required_links(tmp_path: Path):
    root = tmp_path / "root.dts"
    root.write_text(
        "/ {\n"
        "\trx0: jesd-rx@0 {\n"
        '\t\tcompatible = "adi,axi-jesd204-rx-1.0";\n'
        "\t\tjesd204-inputs = <&xcvr0 0 2>;\n"
        "\t};\n"
        "};\n"
    )

    manifest = ReferenceManifestExtractor().extract(root)

    assert len(manifest.links) == 1
    assert manifest.links[0].source_label == "rx0"
    assert manifest.links[0].property_name == "jesd204-inputs"
    assert manifest.links[0].target_label == "xcvr0"


def test_extract_manifest_collects_required_properties(tmp_path: Path):
    root = tmp_path / "root.dts"
    root.write_text(
        "/ {\n"
        "\trx0: jesd-rx@0 {\n"
        '\t\tcompatible = "adi,axi-jesd204-rx-1.0";\n'
        "\t\tadi,octets-per-frame = <4>;\n"
        "\t\tadi,frames-per-multiframe = <32>;\n"
        "\t};\n"
        "};\n"
    )

    manifest = ReferenceManifestExtractor().extract(root)

    names = sorted(p.property_name for p in manifest.properties)
    assert names == ["adi,frames-per-multiframe", "adi,octets-per-frame"]
    values = {p.property_name: p.expected_value for p in manifest.properties}
    assert values["adi,octets-per-frame"] == "<4>"
    assert values["adi,frames-per-multiframe"] == "<32>"


def test_extract_manifest_handles_include_cycles(tmp_path: Path):
    root = tmp_path / "root.dts"
    a = tmp_path / "a.dtsi"
    b = tmp_path / "b.dtsi"

    root.write_text('#include "a.dtsi"\n')
    a.write_text('#include "b.dtsi"\n/ { node@0 { compatible = "adi,hmc7044"; }; };\n')
    b.write_text('#include "a.dtsi"\n')

    manifest = ReferenceManifestExtractor().extract(root)

    assert set(manifest.included_files) == {root, a, b}
    assert [r.role for r in manifest.roles] == ["clock_chip"]


def test_extract_manifest_raises_for_missing_root(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        ReferenceManifestExtractor().extract(tmp_path / "missing.dts")


def test_extract_manifest_deduplicates_duplicate_requirements(tmp_path: Path):
    root = tmp_path / "root.dts"
    a = tmp_path / "a.dtsi"
    b = tmp_path / "b.dtsi"

    root.write_text('#include "a.dtsi"\n#include "b.dtsi"\n')
    node = (
        "/ {\n"
        "\trx0: jesd-rx@0 {\n"
        '\t\tcompatible = "adi,axi-jesd204-rx-1.0";\n'
        "\t\tjesd204-inputs = <&xcvr0 0 2>;\n"
        "\t\tadi,octets-per-frame = <4>;\n"
        "\t};\n"
        "};\n"
    )
    a.write_text(node)
    b.write_text(node)

    manifest = ReferenceManifestExtractor().extract(root)

    assert len(manifest.roles) == 1
    assert len(manifest.links) == 1
    assert len(manifest.properties) == 1
