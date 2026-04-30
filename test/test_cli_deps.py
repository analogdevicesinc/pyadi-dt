"""Unit tests for the `adidtc deps` CLI wrapper.

The dependency parser itself is exhaustively tested in
``test/utils/parsers``; this file only verifies the Click wrapping layer
(format dispatch, output redirection, depth limiting, missing-dep
visibility, and error handling).
"""

import json
from pathlib import Path

from click.testing import CliRunner

from adidt.cli.main import cli


FIXTURES = Path(__file__).parent / "utils" / "parsers" / "fixtures"


def test_deps_renders_tree_format_by_default():
    runner = CliRunner()
    result = runner.invoke(cli, ["deps", str(FIXTURES / "with_includes.dts")])

    assert result.exit_code == 0, result.output
    assert "with_includes.dts" in result.output
    # The fixture pulls in includes/common.dtsi — tree should reference it
    assert "common.dtsi" in result.output
    # Tree legend appears in render_tree output
    assert "Legend:" in result.output
    assert "Statistics:" in result.output


def test_deps_renders_dot_format():
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["deps", str(FIXTURES / "with_includes.dts"), "--format", "dot"],
    )

    assert result.exit_code == 0, result.output
    assert "digraph" in result.output
    assert "with_includes.dts" in result.output


def test_deps_renders_json_format():
    runner = CliRunner()
    result = runner.invoke(
        cli,
        ["deps", str(FIXTURES / "with_includes.dts"), "--format", "json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "root" in payload
    assert "nodes" in payload
    assert payload["root"].endswith("with_includes.dts")


def test_deps_writes_dot_to_output_file(tmp_path):
    runner = CliRunner()
    out_file = tmp_path / "deps.dot"
    result = runner.invoke(
        cli,
        [
            "deps",
            str(FIXTURES / "with_includes.dts"),
            "--format",
            "dot",
            "--output",
            str(out_file),
        ],
    )

    assert result.exit_code == 0, result.output
    assert out_file.exists()
    assert "digraph" in out_file.read_text()
    assert f"DOT output written to {out_file}" in result.output


def test_deps_writes_json_to_output_file(tmp_path):
    runner = CliRunner()
    out_file = tmp_path / "deps.json"
    result = runner.invoke(
        cli,
        [
            "deps",
            str(FIXTURES / "with_includes.dts"),
            "--format",
            "json",
            "--output",
            str(out_file),
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(out_file.read_text())
    assert payload["root"].endswith("with_includes.dts")


def test_deps_max_depth_truncates_tree():
    runner = CliRunner()
    full = runner.invoke(
        cli,
        ["deps", str(FIXTURES / "nested_includes.dts"), "--format", "tree"],
    )
    truncated = runner.invoke(
        cli,
        [
            "deps",
            str(FIXTURES / "nested_includes.dts"),
            "--format",
            "tree",
            "--max-depth",
            "1",
        ],
    )

    assert full.exit_code == 0, full.output
    assert truncated.exit_code == 0, truncated.output
    # The full render walks deeper into the include graph than --max-depth 1.
    # The line count is a good proxy for depth-limited rendering.
    full_tree_lines = sum(1 for ln in full.output.splitlines() if "──" in ln)
    truncated_tree_lines = sum(
        1 for ln in truncated.output.splitlines() if "──" in ln
    )
    assert truncated_tree_lines < full_tree_lines


def test_deps_hide_missing_omits_unresolved_section():
    runner = CliRunner()
    shown = runner.invoke(cli, ["deps", str(FIXTURES / "with_missing.dts")])
    hidden = runner.invoke(
        cli, ["deps", str(FIXTURES / "with_missing.dts"), "--hide-missing"]
    )

    assert shown.exit_code == 0, shown.output
    assert hidden.exit_code == 0, hidden.output
    assert "Missing Dependencies:" in shown.output
    assert "Missing Dependencies:" not in hidden.output


def test_deps_errors_on_missing_input_file():
    runner = CliRunner()
    result = runner.invoke(cli, ["deps", "/tmp/does_not_exist.dts"])

    # The handler reports the error via click.echo and returns; treat any
    # non-fatal exit (0 with error message printed) as the documented contract.
    assert "Error" in result.output
