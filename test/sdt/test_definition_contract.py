"""Contract tests for MDD-style SDT Tcl driver definitions."""

from pathlib import Path

import pytest

from adidt.sdt.definitions import load_tcl_definition

DRIVER = (
    Path(__file__).resolve().parents[2]
    / "adidt/sdt/drivers/axi_jesd204_rx/data/axi_jesd204_rx.tcl"
)


def test_axi_jesd204_rx_definition_loads_with_stock_tclsh() -> None:
    definition = load_tcl_definition(DRIVER)

    assert definition.name == "axi_jesd204_rx"
    assert definition.supported_ip_names == ("axi_jesd204_rx",)
    assert "analog.com:user:axi_jesd204_rx:*" in definition.supported_vlnv_globs
    assert definition.generator_proc == "axi_jesd204_rx_generate"
    assert definition.output_files == ("pl.dtsi",)
    assert definition.emitted_properties == {"compatible": "stringlist"}
    assert definition.binding_format == "legacy-text"


def test_definition_is_deterministic() -> None:
    assert load_tcl_definition(DRIVER) == load_tcl_definition(DRIVER)


def test_definition_rejects_missing_generator(tmp_path: Path) -> None:
    broken = tmp_path / "broken.tcl"
    broken.write_text(
        "namespace eval ::adidt::sdt::broken {\n"
        " variable d [dict create schema_version 1 name broken "
        "supported_ip_names x supported_vlnv_globs x generator_proc absent "
        "output_files pl.dtsi architectures zynq required_hsi_properties {} "
        "required_interfaces {} compatibles x binding x binding_format legacy-text "
        "emitted_properties [dict create compatible stringlist]]\n"
        " proc definition {} { variable d; return $d }\n}\n"
    )

    with pytest.raises(ValueError, match="generator proc not found"):
        load_tcl_definition(broken)
