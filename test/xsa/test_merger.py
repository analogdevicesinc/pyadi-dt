# test/xsa/test_merger.py
import warnings
from adidt.xsa.merger import DtsMerger

BASE_DTS = """\
/dts-v1/;
/ {
\tmodel = "Zynq UltraScale+ ZCU102 Rev1.0";
\t#address-cells = <2>;
\t#size-cells = <2>;
\tamba: axi {
\t\t#address-cells = <2>;
\t\t#size-cells = <2>;
\t\tcompatible = "simple-bus";
\t\tranges;
\t};
};"""

ADI_NODES = {
    "jesd204_rx": [
        '\taxi_jesd204_rx_0: axi-jesd204-rx@44a90000 {\n\t\tcompatible = "adi,axi-jesd204-rx-1.0";\n\t};'
    ],
    "jesd204_tx": [
        '\taxi_jesd204_tx_0: axi-jesd204-tx@44b90000 {\n\t\tcompatible = "adi,axi-jesd204-tx-1.0";\n\t};'
    ],
    "converters": [],
}


def test_overlay_references_amba_label(tmp_path):
    overlay, _ = DtsMerger().merge(BASE_DTS, ADI_NODES, tmp_path, "test")
    assert "&amba" in overlay


def test_overlay_contains_adi_nodes(tmp_path):
    overlay, _ = DtsMerger().merge(BASE_DTS, ADI_NODES, tmp_path, "test")
    assert "adi,axi-jesd204-rx-1.0" in overlay
    assert "adi,axi-jesd204-tx-1.0" in overlay


def test_overlay_has_dts_v1_and_plugin_header(tmp_path):
    overlay, _ = DtsMerger().merge(BASE_DTS, ADI_NODES, tmp_path, "test")
    assert "/dts-v1/;" in overlay
    assert "/plugin/;" in overlay


def test_merged_contains_adi_nodes(tmp_path):
    _, merged = DtsMerger().merge(BASE_DTS, ADI_NODES, tmp_path, "test")
    assert "adi,axi-jesd204-rx-1.0" in merged
    assert "adi,axi-jesd204-tx-1.0" in merged


def test_merged_retains_base_content(tmp_path):
    _, merged = DtsMerger().merge(BASE_DTS, ADI_NODES, tmp_path, "test")
    assert "Zynq UltraScale+" in merged


def test_overlay_file_written(tmp_path):
    DtsMerger().merge(BASE_DTS, ADI_NODES, tmp_path, "myboard")
    assert (tmp_path / "myboard.dtso").exists()


def test_merged_file_written(tmp_path):
    DtsMerger().merge(BASE_DTS, ADI_NODES, tmp_path, "myboard")
    assert (tmp_path / "myboard.dts").exists()


def test_conflict_replaces_existing_node_and_warns(tmp_path):
    base_with_conflict = BASE_DTS.replace(
        "\t\tranges;\n\t};",
        '\t\tranges;\n\n\t\taxi-jesd204-rx@44a90000 {\n\t\t\tcompatible = "stub";\n\t\t};\n\t};',
    )
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        _, merged = DtsMerger().merge(
            base_with_conflict, ADI_NODES, tmp_path, "conflict"
        )
    assert any("replaced" in str(warning.message).lower() for warning in w)
    assert '"stub"' not in merged
    assert "adi,axi-jesd204-rx-1.0" in merged


def test_fallback_to_root_when_no_amba_label(tmp_path):
    no_amba = "/dts-v1/;\n/ {\n\t#address-cells = <1>;\n};\n"
    with warnings.catch_warnings(record=True):
        warnings.simplefilter("always")
        _, merged = DtsMerger().merge(no_amba, ADI_NODES, tmp_path, "noamba")
    assert "adi,axi-jesd204-rx-1.0" in merged
    # Ensure fallback insertion stays inside root node, not after top-level close.
    assert "\n};\n\n\taxi_jesd204_rx_0:" not in merged


def test_conflict_replaces_existing_node_with_same_label(tmp_path):
    base_with_same_label = BASE_DTS.replace(
        "\t\tranges;\n\t};",
        '\t\tranges;\n\n\t\taxi_jesd204_rx_0: old-node@1000 {\n\t\t\tcompatible = "stub";\n\t\t};\n\t};',
    )
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        _, merged = DtsMerger().merge(
            base_with_same_label, ADI_NODES, tmp_path, "labelconflict"
        )
    assert any("duplicate label" in str(warning.message).lower() for warning in w)
    assert "old-node@1000" not in merged
    assert "adi,axi-jesd204-rx-1.0" in merged


def test_overlay_references_amba_pl_label(tmp_path):
    base = "/dts-v1/;\n/ {\n\tamba_pl: amba_pl {\n\t\t#address-cells = <2>;\n\t};\n};\n"
    overlay, _ = DtsMerger().merge(base, ADI_NODES, tmp_path, "ambapl")
    assert "&amba_pl" in overlay


def test_replace_nodes_with_duplicate_labels_from_included_dtsi(tmp_path):
    (tmp_path / "pl.dtsi").write_text(
        '/ {\n\taxi_jesd204_rx_0: axi-jesd204-rx@44a90000 { compatible = "xlnx,axi-jesd204-rx-1.0"; };\n};\n'
    )
    base_with_include = (
        '/dts-v1/;\n#include "pl.dtsi"\n/ {\n\tamba_pl: amba_pl {\n\t};\n};\n'
    )
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        _, merged = DtsMerger().merge(base_with_include, ADI_NODES, tmp_path, "incl")
    assert any("duplicate label" in str(warn.message).lower() for warn in w)
    assert "xlnx,axi-jesd204-rx-1.0" not in merged
    assert "adi,axi-jesd204-rx-1.0" in merged
    assert "axi_jesd204_tx_0:" in merged


def test_replacement_preserves_interrupts_from_included_dtsi(tmp_path):
    (tmp_path / "pl.dtsi").write_text(
        "/ {\n\taxi_jesd204_rx_0: axi-jesd204-rx@44a90000 {\n"
        '\t\tcompatible = "xlnx,axi-jesd204-rx-1.0";\n'
        "\t\tinterrupt-parent = <&gic>;\n"
        "\t\tinterrupts = <0 106 4>;\n\t};\n};\n"
    )
    base_with_include = (
        '/dts-v1/;\n#include "pl.dtsi"\n/ {\n\tamba_pl: amba_pl {\n\t};\n};\n'
    )
    _, merged = DtsMerger().merge(base_with_include, ADI_NODES, tmp_path, "incl-irq")
    assert "interrupt-parent = <&gic>;" in merged
    assert "interrupts = <0 106 4>;" in merged


def test_merge_uses_include_bus_label_reference_block(tmp_path):
    (tmp_path / "pl.dtsi").write_text(
        "/ {\n\tamba_pl: amba_pl {\n\t\t#address-cells = <2>;\n\t};\n};\n"
    )
    base_with_include = '/dts-v1/;\n#include "pl.dtsi"\n/ {\n\tmodel = "test";\n};\n'
    _, merged = DtsMerger().merge(base_with_include, ADI_NODES, tmp_path, "incl-bus")
    assert "&amba_pl {" in merged
    assert "adi,axi-jesd204-rx-1.0" in merged


def test_include_bus_insertion_happens_after_delete_directives(tmp_path):
    (tmp_path / "pl.dtsi").write_text(
        "/ {\n\tamba_pl: amba_pl {\n\t\taxi_jesd204_rx_0: axi-jesd204-rx@44a90000 {"
        ' compatible = "stub"; };\n\t};\n};\n'
    )
    base_with_include = '/dts-v1/;\n#include "pl.dtsi"\n/ {\n\tmodel = "test";\n};\n'
    _, merged = DtsMerger().merge(
        base_with_include, ADI_NODES, tmp_path, "incl-bus-del"
    )
    delete_idx = merged.index("/delete-node/ &axi_jesd204_rx_0;")
    block_idx = merged.index("&amba_pl {")
    assert delete_idx < block_idx
