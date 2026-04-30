"""Integration tests for the DTS linter wired into the pipeline."""

import json

import pytest

from adidt.xsa.validate.dts_lint import DtsLinter, LintDiagnostic
from adidt.xsa.exceptions import DtsLintError


class TestDtsLinterPipelineIntegration:
    """Test the linter against realistic DTS output from NodeBuilder."""

    def test_lint_ad9081_golden_fixture(self):
        """The AD9081 golden DTS fixture should be lint-clean (no errors)."""
        from pathlib import Path

        golden = (
            Path(__file__).parent / "fixtures" / "ad9081_pipeline_merged_golden.dts"
        )
        if not golden.exists():
            pytest.skip("golden DTS fixture not found")
        diagnostics = DtsLinter().lint_file(golden)
        errors = [d for d in diagnostics if d.severity == "error"]
        # Golden fixture may have unresolved phandles to base DTS nodes
        # (e.g., &zynqmp_clk, &gpio) that aren't in the overlay-only golden.
        # Filter those out — they'd be resolved in the full merged DTS.
        real_errors = [e for e in errors if e.rule != "phandle-unresolved"]
        assert not real_errors, f"Golden DTS has lint errors: {real_errors}"


class TestDtsLintError:
    def test_exception_carries_diagnostics(self):
        diags = [
            LintDiagnostic("error", "phandle-unresolved", "foo", "missing foo"),
        ]
        err = DtsLintError("1 lint error(s)", diags)
        assert len(err.diagnostics) == 1
        assert "1 lint error" in str(err)

    def test_empty_diagnostics(self):
        err = DtsLintError("no issues")
        assert err.diagnostics == []


class TestLinterOnGeneratedOutput:
    """Run the linter on NodeBuilder output for known topologies."""

    def test_ad9084_vcu118_output_lint(self):
        """Build AD9084 VCU118 nodes and lint them."""
        from adidt.xsa.parse.topology import (
            ClkgenInstance,
            ConverterInstance,
            Jesd204Instance,
            XsaTopology,
        )
        from adidt.xsa.build.node_builder import NodeBuilder
        from adidt.xsa.config.profiles import ProfileManager, merge_profile_defaults

        topo = XsaTopology(
            jesd204_rx=[
                Jesd204Instance(
                    "axi_apollo_rx_jesd_rx_axi", 0x44A10000, 8, 54, "clk", "rx"
                ),
                Jesd204Instance(
                    "axi_apollo_rx_b_jesd_rx_axi", 0x44A20000, 8, 55, "clk", "rx"
                ),
            ],
            jesd204_tx=[
                Jesd204Instance(
                    "axi_apollo_tx_jesd_tx_axi", 0x44B10000, 8, 56, "clk", "tx"
                ),
                Jesd204Instance(
                    "axi_apollo_tx_b_jesd_tx_axi", 0x44B20000, 8, 57, "clk", "tx"
                ),
            ],
            clkgens=[ClkgenInstance("axi_hsci_clkgen", 0x43C00000, ["hsci_clk"])],
            converters=[
                ConverterInstance("axi_ad9084_0", "axi_ad9084", 0x44A00000, None, None)
            ],
            fpga_part="xcvu9p-flga2104-2l-e",
        )
        cfg = merge_profile_defaults(
            {"jesd": {"rx": {"F": 6, "K": 32}, "tx": {"F": 6, "K": 32}}},
            ProfileManager().load("ad9084_vcu118"),
        )
        nodes = NodeBuilder().build(topo, cfg)
        merged = "\n".join(
            nodes.get("clkgens", [])
            + nodes.get("jesd204_rx", [])
            + nodes.get("jesd204_tx", [])
            + nodes.get("converters", [])
        )
        diagnostics = DtsLinter().lint(merged)
        # Expect no SPI CS duplicates or missing compatibles in generated output
        cs_dupes = [d for d in diagnostics if d.rule == "spi-cs-duplicate"]
        compat_missing = [d for d in diagnostics if d.rule == "compatible-missing"]
        assert not cs_dupes, f"SPI CS duplicates: {cs_dupes}"
        assert not compat_missing, f"Missing compatible: {compat_missing}"


class TestDiagnosticsJson:
    """Test that the diagnostics JSON output format is correct."""

    def test_diagnostics_json_structure(self, tmp_path):
        dts = """\
        clk0: clock { #clock-cells = <1>; };
        dev: device { compatible = "test"; clocks = <&clk0 0>; };
        orphan: orphan_dev { compatible = "test2"; clocks = <&missing 0>; };
        """
        diagnostics = DtsLinter().lint(dts)
        # Simulate what pipeline.py writes
        diag_data = {
            "diagnostics": [
                {
                    "severity": d.severity,
                    "rule": d.rule,
                    "node": d.node,
                    "message": d.message,
                }
                for d in diagnostics
            ],
            "summary": {
                "errors": sum(1 for d in diagnostics if d.severity == "error"),
                "warnings": sum(1 for d in diagnostics if d.severity == "warning"),
                "info": sum(1 for d in diagnostics if d.severity == "info"),
                "total": len(diagnostics),
            },
        }
        diag_path = tmp_path / "diag.json"
        diag_path.write_text(json.dumps(diag_data, indent=2))

        loaded = json.loads(diag_path.read_text())
        assert "diagnostics" in loaded
        assert "summary" in loaded
        assert loaded["summary"]["total"] == len(diagnostics)
        assert loaded["summary"]["errors"] >= 1  # At least the unresolved phandle
