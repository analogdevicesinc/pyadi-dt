import json
from unittest.mock import patch

from click.testing import CliRunner

from adidt.cli.main import cli
from adidt.xsa.exceptions import ParityError


def test_xsa2dt_passes_profile_to_pipeline(tmp_path):
    runner = CliRunner()
    xsa = tmp_path / "design.xsa"
    cfg = tmp_path / "cfg.json"
    out = tmp_path / "out"
    xsa.write_bytes(b"PK\x03\x04")
    cfg.write_text(json.dumps({"jesd": {"rx": {"F": 4, "K": 32}, "tx": {"F": 4, "K": 32}}}))

    with patch("adidt.xsa.pipeline.XsaPipeline") as MockPipeline:
        MockPipeline.return_value.run.return_value = {
            "overlay": out / "a.dtso",
            "merged": out / "a.dts",
            "report": out / "a.html",
            "base_dir": out / "base",
        }
        result = runner.invoke(
            cli,
            [
                "xsa2dt",
                "-x",
                str(xsa),
                "-c",
                str(cfg),
                "-o",
                str(out),
                "--profile",
                "ad9081_zcu102",
            ],
        )

    assert result.exit_code == 0, result.output
    call = MockPipeline.return_value.run.call_args
    assert call is not None
    assert call.kwargs["profile"] == "ad9081_zcu102"


def test_xsa_profiles_lists_builtin_profiles():
    runner = CliRunner()
    result = runner.invoke(cli, ["xsa-profiles"])
    assert result.exit_code == 0, result.output
    assert "ad9081_zcu102" in result.output
    assert "adrv9009_zcu102" in result.output


def test_xsa_profile_show_prints_profile_defaults():
    runner = CliRunner()
    result = runner.invoke(cli, ["xsa-profile-show", "ad9081_zcu102"])
    assert result.exit_code == 0, result.output
    assert '"name": "ad9081_zcu102"' in result.output
    assert '"ad9081_board"' in result.output


def test_xsa_profile_show_handles_unknown_profile():
    runner = CliRunner()
    result = runner.invoke(cli, ["xsa-profile-show", "does_not_exist"])
    assert result.exit_code == 0, result.output
    assert "Error: profile not found: does_not_exist" in result.output


def test_xsa2dt_passes_reference_dts_to_pipeline(tmp_path):
    runner = CliRunner()
    xsa = tmp_path / "design.xsa"
    cfg = tmp_path / "cfg.json"
    ref = tmp_path / "ref.dts"
    out = tmp_path / "out"
    xsa.write_bytes(b"PK\x03\x04")
    cfg.write_text(json.dumps({"jesd": {"rx": {"F": 4, "K": 32}, "tx": {"F": 4, "K": 32}}}))
    ref.write_text('/ { n@0 { compatible = "adi,hmc7044"; }; };\n')

    with patch("adidt.xsa.pipeline.XsaPipeline") as MockPipeline:
        (out / "a.map.json").parent.mkdir(parents=True, exist_ok=True)
        (out / "a.map.json").write_text(
            json.dumps(
                {
                    "coverage": {
                        "roles_pct": 75.0,
                        "links_pct": 40.0,
                        "properties_pct": 100.0,
                        "overall_pct": 66.7,
                        "overall_matched": 8,
                        "overall_total": 12,
                    },
                    "missing_roles": ["clock_chip:clk0"],
                    "missing_links": ["rx0.jesd204-inputs->xcvr0", "rx1.jesd204-inputs->xcvr1"],
                    "missing_properties": [],
                    "mismatched_properties": ["rx0.adi,octets-per-frame: expected <4>, got <8>"],
                }
            )
        )
        MockPipeline.return_value.run.return_value = {
            "overlay": out / "a.dtso",
            "merged": out / "a.dts",
            "report": out / "a.html",
            "map": out / "a.map.json",
            "coverage": out / "a.coverage.md",
            "base_dir": out / "base",
        }
        result = runner.invoke(
            cli,
            [
                "xsa2dt",
                "-x",
                str(xsa),
                "-c",
                str(cfg),
                "-o",
                str(out),
                "--reference-dts",
                str(ref),
            ],
        )

    assert result.exit_code == 0, result.output
    call = MockPipeline.return_value.run.call_args
    assert call is not None
    assert call.kwargs["reference_dts"] == ref
    assert "Map:" in result.output
    assert "Coverage:" in result.output
    assert "Coverage % (roles/links/properties/overall): 75.0/40.0/100.0/66.7" in result.output
    assert "Overall matched items: 8/12" in result.output
    assert "Missing gaps (roles/links/properties/mismatched): 1/2/0/1" in result.output


def test_xsa2dt_passes_strict_parity_to_pipeline(tmp_path):
    runner = CliRunner()
    xsa = tmp_path / "design.xsa"
    cfg = tmp_path / "cfg.json"
    ref = tmp_path / "ref.dts"
    out = tmp_path / "out"
    xsa.write_bytes(b"PK\x03\x04")
    cfg.write_text(json.dumps({"jesd": {"rx": {"F": 4, "K": 32}, "tx": {"F": 4, "K": 32}}}))
    ref.write_text('/ { n@0 { compatible = "adi,hmc7044"; }; };\n')

    with patch("adidt.xsa.pipeline.XsaPipeline") as MockPipeline:
        MockPipeline.return_value.run.return_value = {
            "overlay": out / "a.dtso",
            "merged": out / "a.dts",
            "report": out / "a.html",
            "base_dir": out / "base",
        }
        result = runner.invoke(
            cli,
            [
                "xsa2dt",
                "-x",
                str(xsa),
                "-c",
                str(cfg),
                "-o",
                str(out),
                "--reference-dts",
                str(ref),
                "--strict-parity",
            ],
        )

    assert result.exit_code == 0, result.output
    call = MockPipeline.return_value.run.call_args
    assert call is not None
    assert call.kwargs["strict_parity"] is True


def test_xsa2dt_warns_when_map_json_is_invalid(tmp_path):
    runner = CliRunner()
    xsa = tmp_path / "design.xsa"
    cfg = tmp_path / "cfg.json"
    ref = tmp_path / "ref.dts"
    out = tmp_path / "out"
    xsa.write_bytes(b"PK\x03\x04")
    cfg.write_text(json.dumps({"jesd": {"rx": {"F": 4, "K": 32}, "tx": {"F": 4, "K": 32}}}))
    ref.write_text('/ { n@0 { compatible = "adi,hmc7044"; }; };\n')

    with patch("adidt.xsa.pipeline.XsaPipeline") as MockPipeline:
        (out / "bad.map.json").parent.mkdir(parents=True, exist_ok=True)
        (out / "bad.map.json").write_text("{")
        MockPipeline.return_value.run.return_value = {
            "overlay": out / "a.dtso",
            "merged": out / "a.dts",
            "report": out / "a.html",
            "map": out / "bad.map.json",
            "coverage": out / "a.coverage.md",
            "base_dir": out / "base",
        }
        result = runner.invoke(
            cli,
            [
                "xsa2dt",
                "-x",
                str(xsa),
                "-c",
                str(cfg),
                "-o",
                str(out),
                "--reference-dts",
                str(ref),
            ],
        )

    assert result.exit_code == 0, result.output
    assert "Warning: unable to parse parity map JSON" in result.output


def test_xsa2dt_prints_error_when_strict_parity_fails(tmp_path):
    runner = CliRunner()
    xsa = tmp_path / "design.xsa"
    cfg = tmp_path / "cfg.json"
    ref = tmp_path / "ref.dts"
    out = tmp_path / "out"
    xsa.write_bytes(b"PK\x03\x04")
    cfg.write_text(json.dumps({"jesd": {"rx": {"F": 4, "K": 32}, "tx": {"F": 4, "K": 32}}}))
    ref.write_text('/ { n@0 { compatible = "adi,hmc7044"; }; };\n')

    with patch("adidt.xsa.pipeline.XsaPipeline") as MockPipeline:
        MockPipeline.return_value.run.side_effect = ParityError(
            "missing required roles: clock_chip"
        )
        result = runner.invoke(
            cli,
            [
                "xsa2dt",
                "-x",
                str(xsa),
                "-c",
                str(cfg),
                "-o",
                str(out),
                "--reference-dts",
                str(ref),
                "--strict-parity",
            ],
        )

    assert result.exit_code != 0, result.output
    assert "missing required roles: clock_chip" in result.output
