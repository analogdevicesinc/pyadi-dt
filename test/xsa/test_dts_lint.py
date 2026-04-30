"""Tests for the DTS structural linter."""

from adidt.xsa.validate.dts_lint import DtsLinter, LintDiagnostic


def _lint(dts: str) -> list[LintDiagnostic]:
    return DtsLinter().lint(dts)


def _rules(diags: list[LintDiagnostic]) -> set[str]:
    return {d.rule for d in diags}


# ---------------------------------------------------------------------------
# phandle-unresolved
# ---------------------------------------------------------------------------


class TestPhandleUnresolved:
    def test_detects_missing_target(self):
        dts = """\
        &spi0 {
            dev@0 {
                clocks = <&nonexistent 0>;
            };
        };
        """
        diags = _lint(dts)
        assert any(
            d.rule == "phandle-unresolved" and "nonexistent" in d.message for d in diags
        )

    def test_passes_when_target_exists(self):
        dts = """\
        clk0: clock {
            #clock-cells = <0>;
        };
        spi0: spi@0 {
            dev@0 {
                clocks = <&clk0>;
            };
        };
        """
        diags = _lint(dts)
        assert not any(d.rule == "phandle-unresolved" for d in diags)

    def test_passes_with_overlay_ref_target(self):
        dts = """\
        &spi0 {
            status = "okay";
            dev@0 {
                clocks = <&spi0>;
            };
        };
        """
        diags = _lint(dts)
        assert not any(
            d.rule == "phandle-unresolved" and d.node == "spi0" for d in diags
        )

    def test_multiple_missing_refs_reported(self):
        dts = """\
        node: dev {
            clocks = <&missing1 0>, <&missing2 1>;
        };
        """
        diags = _lint(dts)
        unresolved = [d for d in diags if d.rule == "phandle-unresolved"]
        assert len(unresolved) == 2
        nodes = {d.node for d in unresolved}
        assert nodes == {"missing1", "missing2"}


# ---------------------------------------------------------------------------
# clock-cells-mismatch
# ---------------------------------------------------------------------------


class TestClockCellsMismatch:
    def test_detects_missing_arg(self):
        dts = """\
        clk: clock {
            #clock-cells = <1>;
        };
        dev: device {
            clocks = <&clk>;
        };
        """
        diags = _lint(dts)
        assert any(d.rule == "clock-cells-mismatch" and "1" in d.message for d in diags)

    def test_passes_with_correct_args(self):
        dts = """\
        clk: clock {
            #clock-cells = <1>;
        };
        dev: device {
            clocks = <&clk 0>;
        };
        """
        diags = _lint(dts)
        assert not any(d.rule == "clock-cells-mismatch" for d in diags)

    def test_passes_with_zero_cells(self):
        dts = """\
        clk: clock {
            #clock-cells = <0>;
        };
        dev: device {
            clocks = <&clk>;
        };
        """
        diags = _lint(dts)
        assert not any(d.rule == "clock-cells-mismatch" for d in diags)

    def test_detects_extra_args(self):
        dts = """\
        clk: clock {
            #clock-cells = <0>;
        };
        dev: device {
            clocks = <&clk 5>;
        };
        """
        diags = _lint(dts)
        assert any(d.rule == "clock-cells-mismatch" for d in diags)


# ---------------------------------------------------------------------------
# spi-cs-duplicate
# ---------------------------------------------------------------------------


class TestSpiCsDuplicate:
    def test_detects_duplicate_cs(self):
        dts = """\
        &spi0 {
            #address-cells = <1>;
            #size-cells = <0>;
            dev_a: dev_a@0 {
                reg = <0>;
                spi-max-frequency = <1000000>;
            };
            dev_b: dev_b@0 {
                reg = <0>;
                spi-max-frequency = <1000000>;
            };
        };
        """
        diags = _lint(dts)
        assert any(
            d.rule == "spi-cs-duplicate" and "2 devices" in d.message for d in diags
        )

    def test_passes_with_unique_cs(self):
        dts = """\
        &spi0 {
            #address-cells = <1>;
            #size-cells = <0>;
            dev_a: dev_a@0 {
                reg = <0>;
                spi-max-frequency = <1000000>;
            };
            dev_b: dev_b@1 {
                reg = <1>;
                spi-max-frequency = <1000000>;
            };
        };
        """
        diags = _lint(dts)
        assert not any(d.rule == "spi-cs-duplicate" for d in diags)


# ---------------------------------------------------------------------------
# compatible-missing
# ---------------------------------------------------------------------------


class TestCompatibleMissing:
    def test_detects_bare_device(self):
        dts = """\
        bare_dev: bare@0 {
            reg = <0>;
            spi-max-frequency = <1000000>;
        };
        """
        diags = _lint(dts)
        assert any(
            d.rule == "compatible-missing" and "bare_dev" in d.message for d in diags
        )

    def test_passes_with_compatible(self):
        dts = """\
        good_dev: good@0 {
            compatible = "adi,ad9680";
            reg = <0>;
            spi-max-frequency = <1000000>;
        };
        """
        diags = _lint(dts)
        assert not any(d.rule == "compatible-missing" for d in diags)

    def test_skips_bus_nodes(self):
        """Bus nodes with reg + #address-cells should not need compatible."""
        dts = """\
        bus: bus@0 {
            reg = <0x0 0x10000>;
            #address-cells = <1>;
            #size-cells = <0>;
        };
        """
        diags = _lint(dts)
        assert not any(d.rule == "compatible-missing" for d in diags)


# ---------------------------------------------------------------------------
# General
# ---------------------------------------------------------------------------


class TestLinterGeneral:
    def test_empty_dts_returns_no_diagnostics(self):
        assert _lint("") == []

    def test_clean_dts_returns_no_diagnostics(self):
        dts = """\
        clk0: clock {
            #clock-cells = <1>;
        };
        hmc7044: hmc7044@0 {
            compatible = "adi,hmc7044";
            reg = <0>;
            #clock-cells = <1>;
            spi-max-frequency = <1000000>;
        };
        dev: device@1 {
            compatible = "adi,ad9084";
            reg = <1>;
            clocks = <&hmc7044 0>;
        };
        """
        diags = _lint(dts)
        errors = [d for d in diags if d.severity == "error"]
        assert not errors

    def test_errors_sorted_first(self):
        dts = """\
        bare: bare@0 {
            reg = <0>;
            spi-max-frequency = <1000000>;
            clocks = <&nonexistent 0>;
        };
        """
        diags = _lint(dts)
        assert len(diags) >= 2
        assert diags[0].severity == "error"

    def test_lint_file(self, tmp_path):
        dts_file = tmp_path / "test.dts"
        dts_file.write_text('good: dev { compatible = "test"; };')
        diags = DtsLinter().lint_file(dts_file)
        assert isinstance(diags, list)

    def test_str_representation(self):
        d = LintDiagnostic(
            severity="error",
            rule="phandle-unresolved",
            node="missing",
            message="phandle reference <&missing> has no matching node",
        )
        assert "[error]" in str(d)
        assert "phandle-unresolved" in str(d)
