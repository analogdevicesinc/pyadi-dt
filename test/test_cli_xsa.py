import json
from unittest.mock import patch

from click.testing import CliRunner

from adidt.cli.main import cli
from adidt.xsa.exceptions import (
    ConfigError,
    ParityError,
    SdtgenError,
    SdtgenNotFoundError,
    XsaParseError,
)


class _InvalidPathLike:
    def __fspath__(self):
        raise ValueError("invalid path value")


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
    assert "Warning: unable to parse parity map JSON at" in result.output
    assert "bad.map.json" in result.output
    assert "Coverage % (roles/links/properties/overall): n/a/n/a/n/a/n/a" in result.output
    assert "Missing gaps (roles/links/properties/mismatched): n/a/n/a/n/a/n/a" in result.output


def test_xsa2dt_warns_when_map_json_root_is_not_object(tmp_path):
    runner = CliRunner()
    xsa = tmp_path / "design.xsa"
    cfg = tmp_path / "cfg.json"
    ref = tmp_path / "ref.dts"
    out = tmp_path / "out"
    xsa.write_bytes(b"PK\x03\x04")
    cfg.write_text(json.dumps({"jesd": {"rx": {"F": 4, "K": 32}, "tx": {"F": 4, "K": 32}}}))
    ref.write_text('/ { n@0 { compatible = "adi,hmc7044"; }; };\n')

    with patch("adidt.xsa.pipeline.XsaPipeline") as MockPipeline:
        (out / "bad-root.map.json").parent.mkdir(parents=True, exist_ok=True)
        (out / "bad-root.map.json").write_text("[]")
        MockPipeline.return_value.run.return_value = {
            "overlay": out / "a.dtso",
            "merged": out / "a.dts",
            "report": out / "a.html",
            "map": out / "bad-root.map.json",
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
    assert "Warning: parity map JSON root is not an object" in result.output
    assert "bad-root.map.json" in result.output
    assert "Coverage % (roles/links/properties/overall): n/a/n/a/n/a/n/a" in result.output
    assert "Missing gaps (roles/links/properties/mismatched): n/a/n/a/n/a/n/a" in result.output


def test_xsa2dt_handles_map_without_coverage_block(tmp_path):
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
                    "missing_roles": ["clock_chip:clk0"],
                    "missing_links": [],
                    "missing_properties": [],
                    "mismatched_properties": [],
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
    assert "Coverage % (roles/links/properties/overall): n/a/n/a/n/a/n/a" in result.output
    assert "Missing gaps (roles/links/properties/mismatched): 1/0/0/0" in result.output


def test_xsa2dt_normalizes_non_list_gap_fields(tmp_path):
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
                    },
                    "missing_roles": None,
                    "missing_links": "oops",
                    "missing_properties": 10,
                    "mismatched_properties": {"bad": "type"},
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
    assert "Missing gaps (roles/links/properties/mismatched): 0/0/0/0" in result.output
    assert "Warning: unable to parse parity map JSON" not in result.output


def test_xsa2dt_normalizes_non_dict_coverage_field(tmp_path):
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
                    "coverage": "bad-type",
                    "missing_roles": ["clock_chip:clk0"],
                    "missing_links": [],
                    "missing_properties": [],
                    "mismatched_properties": [],
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
    assert "Coverage % (roles/links/properties/overall): n/a/n/a/n/a/n/a" in result.output
    assert "Missing gaps (roles/links/properties/mismatched): 1/0/0/0" in result.output
    assert "Warning: unable to parse parity map JSON" not in result.output


def test_xsa2dt_warns_when_parity_artifacts_missing(tmp_path):
    runner = CliRunner()
    xsa = tmp_path / "design.xsa"
    cfg = tmp_path / "cfg.json"
    ref = tmp_path / "ref.dts"
    out = tmp_path / "out"
    xsa.write_bytes(b"PK\x03\x04")
    cfg.write_text(json.dumps({"jesd": {"rx": {"F": 4, "K": 32}, "tx": {"F": 4, "K": 32}}}))
    ref.write_text('/ { n@0 { compatible = "adi,hmc7044"; }; };\n')

    with patch("adidt.xsa.pipeline.XsaPipeline") as MockPipeline:
        missing_map = out / "missing.map.json"
        missing_cov = out / "missing.coverage.md"
        MockPipeline.return_value.run.return_value = {
            "overlay": out / "a.dtso",
            "merged": out / "a.dts",
            "report": out / "a.html",
            "map": missing_map,
            "coverage": missing_cov,
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
    assert "Warning: parity map not found" in result.output
    assert "Warning: parity coverage report not found" in result.output
    assert "Coverage % (roles/links/properties/overall): n/a/n/a/n/a/n/a" in result.output
    assert "Missing gaps (roles/links/properties/mismatched): n/a/n/a/n/a/n/a" in result.output


def test_xsa2dt_warns_when_parity_map_key_is_missing(tmp_path):
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
    assert "Warning: parity map not provided by pipeline result" in result.output
    assert "Coverage % (roles/links/properties/overall): n/a/n/a/n/a/n/a" in result.output
    assert "Missing gaps (roles/links/properties/mismatched): n/a/n/a/n/a/n/a" in result.output


def test_xsa2dt_warns_when_parity_coverage_key_is_missing(tmp_path):
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
                    "missing_links": [],
                    "missing_properties": [],
                    "mismatched_properties": [],
                }
            )
        )
        MockPipeline.return_value.run.return_value = {
            "overlay": out / "a.dtso",
            "merged": out / "a.dts",
            "report": out / "a.html",
            "map": out / "a.map.json",
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
    assert "Warning: parity coverage report not provided by pipeline result" in result.output


def test_xsa2dt_warns_missing_coverage_key_in_strict_mode(tmp_path):
    runner = CliRunner()
    xsa = tmp_path / "design.xsa"
    cfg = tmp_path / "cfg.json"
    out = tmp_path / "out"
    xsa.write_bytes(b"PK\x03\x04")
    cfg.write_text(json.dumps({"jesd": {"rx": {"F": 4, "K": 32}, "tx": {"F": 4, "K": 32}}}))

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
                    },
                    "missing_roles": [],
                    "missing_links": [],
                    "missing_properties": [],
                    "mismatched_properties": [],
                }
            )
        )
        MockPipeline.return_value.run.return_value = {
            "overlay": out / "a.dtso",
            "merged": out / "a.dts",
            "report": out / "a.html",
            "map": out / "a.map.json",
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
                "--strict-parity",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "Warning: parity coverage report not provided by pipeline result" in result.output


def test_xsa2dt_does_not_warn_missing_coverage_without_reference_dts(tmp_path):
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
            ],
        )

    assert result.exit_code == 0, result.output
    assert "Warning: parity map not provided by pipeline result" not in result.output
    assert "Warning: parity coverage report not provided by pipeline result" not in result.output


def test_xsa2dt_warns_missing_parity_artifacts_in_strict_mode(tmp_path):
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
                "--strict-parity",
            ],
        )

    assert result.exit_code == 0, result.output
    assert "Warning: parity map not provided by pipeline result" in result.output
    assert "Warning: parity coverage report not provided by pipeline result" in result.output
    assert "Coverage % (roles/links/properties/overall): n/a/n/a/n/a/n/a" in result.output
    assert "Missing gaps (roles/links/properties/mismatched): n/a/n/a/n/a/n/a" in result.output


def test_xsa2dt_does_not_process_parity_artifacts_without_parity_mode(tmp_path):
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
            "map": out / "missing.map.json",
            "coverage": out / "missing.coverage.md",
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
            ],
        )

    assert result.exit_code == 0, result.output
    assert "Warning: parity map not found" not in result.output
    assert "Warning: parity coverage report not found" not in result.output
    assert "Coverage % (roles/links/properties/overall): n/a/n/a/n/a/n/a" not in result.output


def test_xsa2dt_does_not_parse_map_json_without_parity_mode(tmp_path):
    runner = CliRunner()
    xsa = tmp_path / "design.xsa"
    cfg = tmp_path / "cfg.json"
    out = tmp_path / "out"
    xsa.write_bytes(b"PK\x03\x04")
    cfg.write_text(json.dumps({"jesd": {"rx": {"F": 4, "K": 32}, "tx": {"F": 4, "K": 32}}}))

    with patch("adidt.xsa.pipeline.XsaPipeline") as MockPipeline:
        bad_map = out / "bad.map.json"
        bad_map.parent.mkdir(parents=True, exist_ok=True)
        bad_map.write_text("{")
        MockPipeline.return_value.run.return_value = {
            "overlay": out / "a.dtso",
            "merged": out / "a.dts",
            "report": out / "a.html",
            "map": bad_map,
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
            ],
        )

    assert result.exit_code == 0, result.output
    assert "Warning: unable to parse parity map JSON" not in result.output
    assert "Coverage % (roles/links/properties/overall): n/a/n/a/n/a/n/a" not in result.output


def test_xsa2dt_does_not_validate_parity_paths_without_parity_mode(tmp_path):
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
            "map": _InvalidPathLike(),
            "coverage": _InvalidPathLike(),
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
            ],
        )

    assert result.exit_code == 0, result.output
    assert "Warning: parity map path is not path-like" not in result.output
    assert "Warning: parity coverage report path is not path-like" not in result.output
    assert "Warning: parity map path is invalid" not in result.output
    assert "Warning: parity coverage report path is invalid" not in result.output


def test_xsa2dt_non_parity_mode_still_prints_artifact_paths(tmp_path):
    runner = CliRunner()
    xsa = tmp_path / "design.xsa"
    cfg = tmp_path / "cfg.json"
    out = tmp_path / "out"
    xsa.write_bytes(b"PK\x03\x04")
    cfg.write_text(json.dumps({"jesd": {"rx": {"F": 4, "K": 32}, "tx": {"F": 4, "K": 32}}}))

    with patch("adidt.xsa.pipeline.XsaPipeline") as MockPipeline:
        map_path = out / "missing.map.json"
        cov_path = out / "missing.coverage.md"
        MockPipeline.return_value.run.return_value = {
            "overlay": out / "a.dtso",
            "merged": out / "a.dts",
            "report": out / "a.html",
            "map": map_path,
            "coverage": cov_path,
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
            ],
        )

    assert result.exit_code == 0, result.output
    assert f"Map:      {map_path}" in result.output
    assert f"Coverage: {cov_path}" in result.output
    assert "Warning: parity map not found" not in result.output
    assert "Warning: parity coverage report not found" not in result.output


def test_xsa2dt_does_not_check_map_root_type_without_parity_mode(tmp_path):
    runner = CliRunner()
    xsa = tmp_path / "design.xsa"
    cfg = tmp_path / "cfg.json"
    out = tmp_path / "out"
    xsa.write_bytes(b"PK\x03\x04")
    cfg.write_text(json.dumps({"jesd": {"rx": {"F": 4, "K": 32}, "tx": {"F": 4, "K": 32}}}))

    with patch("adidt.xsa.pipeline.XsaPipeline") as MockPipeline:
        bad_root_map = out / "bad-root.map.json"
        bad_root_map.parent.mkdir(parents=True, exist_ok=True)
        bad_root_map.write_text("[]")
        MockPipeline.return_value.run.return_value = {
            "overlay": out / "a.dtso",
            "merged": out / "a.dts",
            "report": out / "a.html",
            "map": bad_root_map,
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
            ],
        )

    assert result.exit_code == 0, result.output
    assert "Warning: parity map JSON root is not an object" not in result.output
    assert "Coverage % (roles/links/properties/overall): n/a/n/a/n/a/n/a" not in result.output


def test_xsa2dt_does_not_warn_missing_map_when_non_parity_and_coverage_exists(tmp_path):
    runner = CliRunner()
    xsa = tmp_path / "design.xsa"
    cfg = tmp_path / "cfg.json"
    out = tmp_path / "out"
    xsa.write_bytes(b"PK\x03\x04")
    cfg.write_text(json.dumps({"jesd": {"rx": {"F": 4, "K": 32}, "tx": {"F": 4, "K": 32}}}))

    with patch("adidt.xsa.pipeline.XsaPipeline") as MockPipeline:
        cov_path = out / "coverage.md"
        MockPipeline.return_value.run.return_value = {
            "overlay": out / "a.dtso",
            "merged": out / "a.dts",
            "report": out / "a.html",
            "coverage": cov_path,
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
            ],
        )

    assert result.exit_code == 0, result.output
    assert f"Coverage: {cov_path}" in result.output
    assert "Warning: parity map not provided by pipeline result" not in result.output
    assert "Coverage % (roles/links/properties/overall): n/a/n/a/n/a/n/a" not in result.output


def test_xsa2dt_warns_when_optional_parity_artifacts_not_pathlike(tmp_path):
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
            "map": 100,
            "coverage": 200,
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
    assert "Warning: parity map path is not path-like" in result.output
    assert "Warning: parity coverage report path is not path-like" in result.output
    assert "Unexpected error:" not in result.output


def test_xsa2dt_warns_when_optional_parity_artifact_paths_are_empty(tmp_path):
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
            "map": "   ",
            "coverage": "",
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
    assert "Warning: parity map path is empty" in result.output
    assert "Warning: parity coverage report path is empty" in result.output
    assert "Unexpected error:" not in result.output


def test_xsa2dt_warns_when_optional_parity_artifact_paths_are_null(tmp_path):
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
            "map": None,
            "coverage": None,
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
    assert "Warning: parity map path is null" in result.output
    assert "Warning: parity coverage report path is null" in result.output
    assert "Warning: parity map path is not path-like" not in result.output
    assert "Warning: parity coverage report path is not path-like" not in result.output
    assert "Unexpected error:" not in result.output


def test_xsa2dt_warns_when_optional_parity_artifact_path_is_invalid(tmp_path):
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
            "map": _InvalidPathLike(),
            "coverage": _InvalidPathLike(),
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
    assert "Warning: parity map path is invalid" in result.output
    assert "Warning: parity coverage report path is invalid" in result.output
    assert "Unexpected error:" not in result.output


def test_xsa2dt_fails_when_pipeline_result_missing_required_artifacts(tmp_path):
    runner = CliRunner()
    xsa = tmp_path / "design.xsa"
    cfg = tmp_path / "cfg.json"
    out = tmp_path / "out"
    xsa.write_bytes(b"PK\x03\x04")
    cfg.write_text(json.dumps({"jesd": {"rx": {"F": 4, "K": 32}, "tx": {"F": 4, "K": 32}}}))

    with patch("adidt.xsa.pipeline.XsaPipeline") as MockPipeline:
        MockPipeline.return_value.run.return_value = {"base_dir": out / "base"}
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
            ],
        )

    assert result.exit_code != 0, result.output
    assert "pipeline result missing required artifacts" in result.output
    assert "overlay, merged, report" in result.output


def test_xsa2dt_fails_when_pipeline_result_is_not_a_dict(tmp_path):
    runner = CliRunner()
    xsa = tmp_path / "design.xsa"
    cfg = tmp_path / "cfg.json"
    out = tmp_path / "out"
    xsa.write_bytes(b"PK\x03\x04")
    cfg.write_text(json.dumps({"jesd": {"rx": {"F": 4, "K": 32}, "tx": {"F": 4, "K": 32}}}))

    with patch("adidt.xsa.pipeline.XsaPipeline") as MockPipeline:
        MockPipeline.return_value.run.return_value = ["overlay", "merged", "report"]
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
            ],
        )

    assert result.exit_code != 0, result.output
    assert "pipeline returned invalid result type: list" in result.output


def test_xsa2dt_fails_when_required_artifact_value_is_empty(tmp_path):
    runner = CliRunner()
    xsa = tmp_path / "design.xsa"
    cfg = tmp_path / "cfg.json"
    out = tmp_path / "out"
    xsa.write_bytes(b"PK\x03\x04")
    cfg.write_text(json.dumps({"jesd": {"rx": {"F": 4, "K": 32}, "tx": {"F": 4, "K": 32}}}))

    with patch("adidt.xsa.pipeline.XsaPipeline") as MockPipeline:
        MockPipeline.return_value.run.return_value = {
            "overlay": " ",
            "merged": "",
            "report": "   ",
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
            ],
        )

    assert result.exit_code != 0, result.output
    assert "pipeline result has empty required artifacts" in result.output
    assert "overlay, merged, report" in result.output


def test_xsa2dt_fails_when_required_artifact_value_is_not_pathlike(tmp_path):
    runner = CliRunner()
    xsa = tmp_path / "design.xsa"
    cfg = tmp_path / "cfg.json"
    out = tmp_path / "out"
    xsa.write_bytes(b"PK\x03\x04")
    cfg.write_text(json.dumps({"jesd": {"rx": {"F": 4, "K": 32}, "tx": {"F": 4, "K": 32}}}))

    with patch("adidt.xsa.pipeline.XsaPipeline") as MockPipeline:
        MockPipeline.return_value.run.return_value = {
            "overlay": 1,
            "merged": 2,
            "report": 1234,
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
            ],
        )

    assert result.exit_code != 0, result.output
    assert "pipeline result has non-path required artifacts" in result.output
    assert "overlay, merged, report" in result.output


def test_xsa2dt_fails_when_required_artifact_value_is_invalid_pathlike(tmp_path):
    runner = CliRunner()
    xsa = tmp_path / "design.xsa"
    cfg = tmp_path / "cfg.json"
    out = tmp_path / "out"
    xsa.write_bytes(b"PK\x03\x04")
    cfg.write_text(json.dumps({"jesd": {"rx": {"F": 4, "K": 32}, "tx": {"F": 4, "K": 32}}}))

    with patch("adidt.xsa.pipeline.XsaPipeline") as MockPipeline:
        MockPipeline.return_value.run.return_value = {
            "overlay": _InvalidPathLike(),
            "merged": _InvalidPathLike(),
            "report": _InvalidPathLike(),
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
            ],
        )

    assert result.exit_code != 0, result.output
    assert "pipeline result has non-path required artifacts" in result.output
    assert "overlay, merged, report" in result.output
    assert "Unexpected error:" not in result.output


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


def test_xsa2dt_fails_when_config_json_is_invalid(tmp_path):
    runner = CliRunner()
    xsa = tmp_path / "design.xsa"
    cfg = tmp_path / "cfg.json"
    out = tmp_path / "out"
    xsa.write_bytes(b"PK\x03\x04")
    cfg.write_text("{")

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
        ],
    )

    assert result.exit_code != 0, result.output
    assert "invalid JSON in config file" in result.output


def test_xsa2dt_fails_when_pipeline_raises_config_error(tmp_path):
    runner = CliRunner()
    xsa = tmp_path / "design.xsa"
    cfg = tmp_path / "cfg.json"
    out = tmp_path / "out"
    xsa.write_bytes(b"PK\x03\x04")
    cfg.write_text(json.dumps({"jesd": {"rx": {"F": 4, "K": 32}, "tx": {"F": 4, "K": 32}}}))

    with patch("adidt.xsa.pipeline.XsaPipeline") as MockPipeline:
        MockPipeline.return_value.run.side_effect = ConfigError("invalid JESD config")
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
            ],
        )

    assert result.exit_code != 0, result.output
    assert "invalid JESD config" in result.output


def test_xsa2dt_fails_when_pipeline_raises_parse_error(tmp_path):
    runner = CliRunner()
    xsa = tmp_path / "design.xsa"
    cfg = tmp_path / "cfg.json"
    out = tmp_path / "out"
    xsa.write_bytes(b"PK\x03\x04")
    cfg.write_text(json.dumps({"jesd": {"rx": {"F": 4, "K": 32}, "tx": {"F": 4, "K": 32}}}))

    with patch("adidt.xsa.pipeline.XsaPipeline") as MockPipeline:
        MockPipeline.return_value.run.side_effect = XsaParseError("missing HWH in XSA")
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
            ],
        )

    assert result.exit_code != 0, result.output
    assert "missing HWH in XSA" in result.output


def test_xsa2dt_fails_when_pipeline_raises_sdtgen_not_found(tmp_path):
    runner = CliRunner()
    xsa = tmp_path / "design.xsa"
    cfg = tmp_path / "cfg.json"
    out = tmp_path / "out"
    xsa.write_bytes(b"PK\x03\x04")
    cfg.write_text(json.dumps({"jesd": {"rx": {"F": 4, "K": 32}, "tx": {"F": 4, "K": 32}}}))

    with patch("adidt.xsa.pipeline.XsaPipeline") as MockPipeline:
        MockPipeline.return_value.run.side_effect = SdtgenNotFoundError(
            "sdtgen executable was not found on PATH"
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
            ],
        )

    assert result.exit_code != 0, result.output
    assert "sdtgen executable was not found on PATH" in result.output


def test_xsa2dt_fails_when_pipeline_raises_sdtgen_error(tmp_path):
    runner = CliRunner()
    xsa = tmp_path / "design.xsa"
    cfg = tmp_path / "cfg.json"
    out = tmp_path / "out"
    xsa.write_bytes(b"PK\x03\x04")
    cfg.write_text(json.dumps({"jesd": {"rx": {"F": 4, "K": 32}, "tx": {"F": 4, "K": 32}}}))

    with patch("adidt.xsa.pipeline.XsaPipeline") as MockPipeline:
        MockPipeline.return_value.run.side_effect = SdtgenError(
            "lopper failed",
            stderr="stderr details",
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
            ],
        )

    assert result.exit_code != 0, result.output
    assert "sdtgen failed: lopper failed" in result.output
    assert "stderr details" in result.output


def test_xsa2dt_fails_when_pipeline_raises_unexpected_exception(tmp_path):
    runner = CliRunner()
    xsa = tmp_path / "design.xsa"
    cfg = tmp_path / "cfg.json"
    out = tmp_path / "out"
    xsa.write_bytes(b"PK\x03\x04")
    cfg.write_text(json.dumps({"jesd": {"rx": {"F": 4, "K": 32}, "tx": {"F": 4, "K": 32}}}))

    with patch("adidt.xsa.pipeline.XsaPipeline") as MockPipeline:
        MockPipeline.return_value.run.side_effect = RuntimeError("boom")
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
            ],
        )

    assert result.exit_code != 0, result.output
    assert "Unexpected error: boom" in result.output
