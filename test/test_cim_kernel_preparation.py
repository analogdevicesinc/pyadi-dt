"""Preparation must not build unselected platforms or bypass existing overrides."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test.test_kernel_artifacts import isolated_environment, manifest  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "prepare_cim_kernel", ROOT / ".github/scripts/prepare_cim_kernel.py"
)
prep = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prep)


def options(tmp_path, **kw):
    return SimpleNamespace(
        **(
            dict(
                platform="zynq",
                release=None,
                source="https://github.com/tfcollins/cim.git",
                version="a" * 40,
                workspace=tmp_path / "workspace",
                cim="/opt/cim/bin/cim",
                jobs=2,
            )
            | kw
        )
    )


@pytest.mark.parametrize("mode", ["image", "artifacts", "disabled"])
def test_prepared_or_disabled_never_calls_cim(tmp_path, monkeypatch, capsys, mode):
    path, image, _ = manifest(tmp_path)
    if mode == "disabled":
        monkeypatch.setenv("ADI_XSA_BUILD_KERNEL", "0")
    else:
        variable = (
            "ADIDT_KERNEL_IMAGE_ZYNQ"
            if mode == "image"
            else "ADIDT_KERNEL_ARTIFACTS_ZYNQ"
        )
        monkeypatch.setenv(variable, str(image if mode == "image" else path))
    run = Mock(side_effect=AssertionError("must not build"))
    monkeypatch.setattr(prep.subprocess, "run", run)
    prep.prepare(options(tmp_path, source=None, version=None))
    run.assert_not_called()
    out = capsys.readouterr().out
    assert ("export ADIDT_KERNEL_" in out) == (mode != "disabled")


@pytest.mark.parametrize("version", [None, "main", "2023_R2", "abcd", "z" * 40])
def test_requires_immutable_manifest_version(tmp_path, version):
    with pytest.raises(ValueError, match="full Git commit"):
        prep.prepare(options(tmp_path, version=version))


def test_existing_workspace_never_overwritten(tmp_path):
    with pytest.raises(ValueError, match="Refusing to overwrite"):
        prep.prepare(options(tmp_path, workspace=tmp_path))


@pytest.mark.parametrize("release", [None, "2023_R2", "2026-R1"])
@pytest.mark.parametrize("platform", ["zynq", "zynqmp"])
def test_exact_cim_contract_and_validated_handoff(
    tmp_path, monkeypatch, capsys, release, platform
):
    args = options(tmp_path, release=release, platform=platform)
    release = release or "2023_R2"
    output = args.workspace / "artifacts"
    if release != "2023_R2":
        output /= prep.CIM_RELEASES[release]["builder_release"]
    output /= platform
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs.get("cwd")))
        if command[0] == "make":
            output.mkdir(parents=True)
            manifest(output, platform, release)

    monkeypatch.setattr(prep.subprocess, "run", run)
    prep.prepare(args)
    assert calls == [
        (
            [
                args.cim,
                "init",
                "--target",
                "adi-linux",
                "--source",
                args.source,
                "--version",
                args.version,
                "--workspace",
                str(args.workspace),
                "--yes",
            ],
            None,
        ),
        ([args.cim, "makefile"], args.workspace),
        (
            [
                "make",
                "sdk-build",
                f"KERNEL_RELEASE={prep.CIM_RELEASES[release]['builder_release']}",
                f"KERNEL_PLATFORM={platform}",
                f"KERNEL_OUTPUT={output}",
                "KERNEL_JOBS=2",
            ],
            args.workspace,
        ),
        (
            [
                prep.sys.executable,
                str(args.workspace / "scripts/build-kernel.py"),
                "--platform",
                platform,
                "--release",
                prep.CIM_RELEASES[release]["builder_release"],
                "--output",
                str(output),
                "--verify",
            ],
            None,
        ),
    ]
    assert (
        f"export ADIDT_KERNEL_ARTIFACTS_{platform.upper()}={output}/artifacts.json"
        in capsys.readouterr().out
    )


def test_bad_existing_artifact_does_not_trigger_rebuild(tmp_path, monkeypatch):
    monkeypatch.setenv("ADIDT_KERNEL_ARTIFACTS_ZYNQ", str(tmp_path / "missing.json"))
    run = Mock(side_effect=AssertionError("must not build"))
    monkeypatch.setattr(prep.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="not a file"):
        prep.prepare(options(tmp_path))
    run.assert_not_called()
