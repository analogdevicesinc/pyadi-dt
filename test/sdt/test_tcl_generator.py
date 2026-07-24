"""Behavior tests for the AXI JESD204 RX Tcl generator."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

DRIVER = (
    Path(__file__).resolve().parents[2]
    / "adidt/sdt/drivers/axi_jesd204_rx/data/axi_jesd204_rx.tcl"
)

HARNESS = r"""
set driver_file [lindex $argv 0]
set requested_ip [lindex $argv 1]
set node_result [lindex $argv 2]
set operations {}
proc hsi {subcommand args} {
    global requested_ip
    if {$subcommand eq "get_property" && [lindex $args 0] eq "IP_NAME"} {
        return $requested_ip
    }
    error "unexpected hsi invocation: $subcommand $args"
}
proc get_node {drv_handle} {
    global node_result
    return $node_result
}
proc pldt {subcommand node property value} {
    global operations
    lappend operations [list $subcommand $node $property $value]
}
source $driver_file
axi_jesd204_rx_generate axi_rx_0
foreach operation $operations {
    puts [join $operation "\t"]
}
"""


def _run(
    ip_name: str = "axi_jesd204_rx", node: str = "node0"
) -> subprocess.CompletedProcess[str]:
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".tcl", encoding="utf-8"
    ) as harness:
        harness.write(HARNESS)
        harness.flush()
        return subprocess.run(
            ["tclsh", harness.name, str(DRIVER), ip_name, node],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )


def test_generator_replaces_only_compatible_property() -> None:
    result = _run()

    assert result.returncode == 0, result.stderr
    fields = result.stdout.strip().split("\t")
    assert fields[:3] == ["set", "node0", "compatible"]
    assert fields[3] == '"adi,axi-jesd204-rx-1.0"'


def test_generator_rejects_wrong_ip() -> None:
    result = _run(ip_name="axi_jesd204_tx")

    assert result.returncode != 0
    assert "unsupported IP 'axi_jesd204_tx'" in result.stderr


def test_generator_rejects_missing_node() -> None:
    result = _run(node="0")

    assert result.returncode != 0
    assert "no SDT node exists" in result.stderr
