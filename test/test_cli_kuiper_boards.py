"""Unit tests for the `adidtc kuiper-boards` CLI."""

import json

from click.testing import CliRunner

from adidt.cli.main import cli


def test_kuiper_boards_lists_default_view():
    runner = CliRunner()
    result = runner.invoke(cli, ["kuiper-boards"])

    assert result.exit_code == 0, result.output
    assert "Kuiper" in result.output
    assert "boards" in result.output
    # The bundled manifest carries entries from every status — at minimum a
    # "FULL" row and an "UNSUPPORTED" row should both be visible by default.
    assert "FULL" in result.output
    assert "UNSUPPORTED" in result.output


def test_kuiper_boards_filter_status_full():
    runner = CliRunner()
    result = runner.invoke(cli, ["kuiper-boards", "--status", "full"])

    assert result.exit_code == 0, result.output
    assert "FULL" in result.output
    # When filtering to 'full', no rows of other statuses should be rendered.
    assert "UNSUPPORTED" not in result.output
    assert "PROFILE_ONLY" not in result.output


def test_kuiper_boards_filter_status_profile_only():
    runner = CliRunner()
    result = runner.invoke(cli, ["kuiper-boards", "--status", "profile_only"])

    assert result.exit_code == 0, result.output
    assert "PROFILE_ONLY" in result.output
    assert "FULL" not in result.output
    assert "UNSUPPORTED" not in result.output


def test_kuiper_boards_filter_status_unsupported():
    runner = CliRunner()
    result = runner.invoke(cli, ["kuiper-boards", "--status", "unsupported"])

    assert result.exit_code == 0, result.output
    assert "UNSUPPORTED" in result.output
    assert "FULL" not in result.output


def test_kuiper_boards_json_output_is_valid_json():
    runner = CliRunner()
    result = runner.invoke(cli, ["kuiper-boards", "--json-output"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert isinstance(payload, dict)
    assert payload, "expected at least one board entry in JSON output"
    sample_board = next(iter(payload.values()))
    # Each manifest entry exposes status + platform + converter in the bundled JSON.
    for required_key in ("status", "platform", "converter"):
        assert required_key in sample_board


def test_kuiper_boards_json_output_respects_status_filter():
    runner = CliRunner()
    result = runner.invoke(
        cli, ["kuiper-boards", "--status", "full", "--json-output"]
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload, "expected at least one full-support board"
    assert all(info.get("status") == "full" for info in payload.values())


def test_kuiper_boards_rejects_unknown_status():
    runner = CliRunner()
    result = runner.invoke(cli, ["kuiper-boards", "--status", "bogus"])

    assert result.exit_code != 0
    # Click reports invalid Choice values via stderr / usage error
    combined = (result.output or "") + (result.stderr or "" if hasattr(result, "stderr") else "")
    assert "bogus" in combined or "invalid choice" in combined.lower()
