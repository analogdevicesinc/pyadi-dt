"""Tests for isolated SDT repository staging and registry generation."""

import json
from pathlib import Path

import pytest

from adidt.sdt.staging import stage_sdt_repository

DRIVERS = Path(__file__).resolve().parents[2] / "adidt/sdt/drivers"


def _upstream(tmp_path: Path) -> Path:
    upstream = tmp_path / "upstream"
    registry = upstream / "device_tree/data/xillib_sw.tcl"
    registry.parent.mkdir(parents=True)
    registry.write_text(
        "proc get_drivers_sw args {\n"
        "\tset driverlist [dict create]\n"
        "\tdict set driverlist axi_dma driver axi_dma\n"
        "\treturn $driverlist\n"
        "}\n"
    )
    common_registry = upstream / "device_tree/data/common_proc.tcl"
    common_registry.write_text(
        "proc get_drivers args {\n"
        "\tset driverlist [dict create]\n"
        "\tdict set driverlist axi_dma driver axi_dma\n"
        "\treturn $driverlist\n"
        "}\n"
    )
    dispatcher = upstream / "device_tree/data/device_tree.tcl"
    dispatcher.write_text(
        "proc init_proclist {} {\n"
        '\tdict set ::sdtgen::namespacelist "axi_dma" "axi_dma"\n'
        "}\n"
    )
    (upstream / "cpu/data").mkdir(parents=True)
    (upstream / "cpu/data/cpu.tcl").write_text("# complete-tree sentinel\n")
    return upstream


def test_stage_installs_driver_and_registry_mapping(tmp_path: Path) -> None:
    upstream = _upstream(tmp_path)
    output = tmp_path / "staged"

    manifest_path = stage_sdt_repository(upstream, output, DRIVERS)

    driver = output / "axi_jesd204_rx/data/axi_jesd204_rx.tcl"
    assert driver.is_file()
    registry = (output / "device_tree/data/xillib_sw.tcl").read_text()
    assert "dict set driverlist axi_jesd204_rx driver axi_jesd204_rx" in registry
    common_registry = (output / "device_tree/data/common_proc.tcl").read_text()
    assert "dict set driverlist axi_jesd204_rx driver axi_jesd204_rx" in common_registry
    dispatcher = (output / "device_tree/data/device_tree.tcl").read_text()
    assert (
        'dict set ::sdtgen::namespacelist "axi_jesd204_rx" "axi_jesd204_rx"'
        in dispatcher
    )
    manifest = json.loads(manifest_path.read_text())
    assert manifest["mappings"] == {"axi_jesd204_rx": "axi_jesd204_rx"}
    assert manifest["files"][0]["sha256"]
    assert len(manifest["registries"]) == 3
    assert not (output / ".git").exists()


def test_stage_does_not_overwrite_existing_output(tmp_path: Path) -> None:
    output = tmp_path / "staged"
    output.mkdir()

    with pytest.raises(FileExistsError):
        stage_sdt_repository(_upstream(tmp_path), output, DRIVERS)


def test_stage_requires_complete_registry(tmp_path: Path) -> None:
    upstream = tmp_path / "incomplete"
    upstream.mkdir()

    with pytest.raises(ValueError, match="not a complete"):
        stage_sdt_repository(upstream, tmp_path / "out", DRIVERS)
