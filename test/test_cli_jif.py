"""Smoke tests for ``adidtc jif clock``."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import fdt
from click.testing import CliRunner

from adidt.cli.main import cli


def _make_fake_dt_with_hmc7044():
    """Build an in-memory fdt tree exposing an HMC7044 with 3 channels."""
    root = fdt.Node("/")
    hmc = fdt.Node("hmc7044@0")
    hmc.append(fdt.PropStrings("compatible", "adi,hmc7044"))
    for idx, divider in [(0, 12), (2, 4), (3, 1536)]:
        ch = fdt.Node(f"channel@{idx}")
        ch.append(fdt.PropWords("reg", idx))
        ch.append(fdt.PropWords("adi,divider", divider))
        hmc.append(ch)
    root.append(hmc)
    tree = fdt.FDT()
    tree.add_item(hmc)

    fake = MagicMock()
    fake.get_node_by_compatible.side_effect = (
        lambda compatible: [hmc] if compatible == "adi,hmc7044" else []
    )
    fake.update_current_dt = MagicMock()
    fake._dt = tree
    fake._hmc_node = hmc  # exposed for test assertions
    return fake


def test_jif_clock_rejects_remote_sysfs(tmp_path: Path):
    runner = CliRunner()
    solver = tmp_path / "clk.json"
    solver.write_text(json.dumps({"out_dividers": [1, 2]}))

    result = runner.invoke(
        cli,
        ["-c", "remote_sysfs", "-i", "192.168.2.1", "jif", "clock", "-f", str(solver)],
    )
    assert result.exit_code != 0
    assert "remote_sysfs" in result.output.lower()


def test_jif_clock_rejects_empty_solver_json(tmp_path: Path):
    runner = CliRunner()
    solver = tmp_path / "empty.json"
    solver.write_text("{}")

    fake = _make_fake_dt_with_hmc7044()
    with patch("adidt.cli.jif.adidt.dt", return_value=fake):
        result = runner.invoke(
            cli,
            [
                "-c",
                "local_file",
                "-f",
                "devicetree.dtb",
                "-a",
                "arm64",
                "jif",
                "clock",
                "-f",
                str(solver),
            ],
        )
    assert result.exit_code != 0
    assert "out_dividers" in result.output or "channels" in result.output


def test_jif_clock_applies_out_dividers_and_writes(tmp_path: Path):
    runner = CliRunner()
    solver = tmp_path / "clk.json"
    solver.write_text(json.dumps({"out_dividers": [42, 99, 7, 123]}))

    fake = _make_fake_dt_with_hmc7044()
    with patch("adidt.cli.jif.adidt.dt", return_value=fake):
        result = runner.invoke(
            cli,
            [
                "-c",
                "local_file",
                "-f",
                "devicetree.dtb",
                "-a",
                "arm64",
                "jif",
                "clock",
                "-f",
                str(solver),
            ],
        )
    assert result.exit_code == 0, result.output

    # Channel 0, 2, 3 existed; channel 1 did not — expect a warning.
    channels = {int(c.get_property("reg").value): c for c in fake._hmc_node.nodes}
    assert channels[0].get_property("adi,divider").value == 42
    assert channels[2].get_property("adi,divider").value == 7
    assert channels[3].get_property("adi,divider").value == 123
    assert "no channel subnodes for indices [1]" in result.output
    fake.update_current_dt.assert_called_once_with(reboot=False)


def test_jif_clock_dry_run_does_not_write(tmp_path: Path):
    runner = CliRunner()
    solver = tmp_path / "clk.json"
    solver.write_text(json.dumps({"channels": {"2": {"divider": 77}}}))

    fake = _make_fake_dt_with_hmc7044()
    with patch("adidt.cli.jif.adidt.dt", return_value=fake):
        result = runner.invoke(
            cli,
            [
                "-c",
                "local_file",
                "-f",
                "devicetree.dtb",
                "-a",
                "arm64",
                "jif",
                "clock",
                "-f",
                str(solver),
                "--dry-run",
            ],
        )
    assert result.exit_code == 0, result.output
    assert "dry-run: no changes written." in result.output
    # Divider must not have been mutated.
    channels = {int(c.get_property("reg").value): c for c in fake._hmc_node.nodes}
    assert channels[2].get_property("adi,divider").value == 4
    fake.update_current_dt.assert_not_called()


def test_jif_clock_accepts_nested_clock_block(tmp_path: Path):
    runner = CliRunner()
    solver = tmp_path / "clk.json"
    solver.write_text(
        json.dumps({"clock": {"out_dividers": [1, 2, 3, 4]}, "jesd": {}})
    )

    fake = _make_fake_dt_with_hmc7044()
    with patch("adidt.cli.jif.adidt.dt", return_value=fake):
        result = runner.invoke(
            cli,
            [
                "-c",
                "local_file",
                "-f",
                "devicetree.dtb",
                "-a",
                "arm64",
                "jif",
                "clock",
                "-f",
                str(solver),
            ],
        )
    assert result.exit_code == 0, result.output
    channels = {int(c.get_property("reg").value): c for c in fake._hmc_node.nodes}
    assert channels[0].get_property("adi,divider").value == 1
    assert channels[2].get_property("adi,divider").value == 3
    assert channels[3].get_property("adi,divider").value == 4
    fake.update_current_dt.assert_called_once()
