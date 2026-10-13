"""Release selection is opt-in, fail-closed, and independent of overlay kernels."""

import json
from unittest.mock import Mock

import pytest

from test.hw.kernel_artifacts import read_kernel_artifacts, resolve_kernel_image
from test.test_cim_kernel_preparation import options, prep
from test.test_hardware_kernel_preflight import run_preflight
from test.test_kernel_artifacts import isolated_environment, manifest  # noqa: F401


@pytest.mark.parametrize("release", ["2023_R2", "2026-R1"])
@pytest.mark.parametrize("platform", ["zynq", "zynqmp"])
def test_release_handoff_rejects_cross_release(
    tmp_path, monkeypatch, release, platform
):
    path, image, data = manifest(tmp_path, platform, release)
    # CIM uses underscore-form internal release keys in provenance/output paths.
    data["provenance"]["release"] = "2026_R1" if release == "2026-R1" else release
    path.write_text(json.dumps(data))
    monkeypatch.setenv(f"ADIDT_KERNEL_ARTIFACTS_{platform.upper()}", str(path))
    monkeypatch.setenv("ADIDT_CIM_RELEASE", release)
    assert resolve_kernel_image(platform) == image
    other = "2026-R1" if release == "2023_R2" else "2023_R2"
    monkeypatch.setenv("ADIDT_CIM_RELEASE", other)
    with pytest.raises(RuntimeError, match="source ref/commit"):
        resolve_kernel_image(platform)
    monkeypatch.setenv(f"ADIDT_KERNEL_IMAGE_{platform.upper()}", str(image))
    assert resolve_kernel_image(platform) == image


@pytest.mark.parametrize(
    "provenance",
    [
        None,
        {},
        [],
        {"source": {}},
        {"source": {"ref": "xlnx_2026.1.0", "commit": "0" * 40}},
    ],
)
def test_missing_or_wrong_source_rejected(tmp_path, provenance):
    path, _, data = manifest(tmp_path, release="2026-R1")
    data["provenance"] = provenance
    path.write_text(json.dumps(data))
    with pytest.raises(RuntimeError, match="source ref/commit"):
        read_kernel_artifacts(str(path), "zynq", release="2026-R1")


@pytest.mark.parametrize("release", ["2023_R2", "2026-R1"])
@pytest.mark.parametrize("platform", ["zynq", "zynqmp"])
def test_wrong_release_field_rejected_with_correct_source(tmp_path, release, platform):
    path, _, data = manifest(tmp_path, platform, release)
    data["provenance"]["release"] = "2026_R1" if release == "2023_R2" else "2023_R2"
    path.write_text(json.dumps(data))
    with pytest.raises(RuntimeError, match="expected release"):
        read_kernel_artifacts(str(path), platform, release=release)


@pytest.mark.parametrize("release", ["2026_R1", "2026-r1", "", "../2026-R1"])
def test_invalid_release_fails_before_subprocess(tmp_path, monkeypatch, release):
    run = Mock(side_effect=AssertionError("must not build"))
    monkeypatch.setattr(prep.subprocess, "run", run)
    monkeypatch.setenv("ADIDT_CIM_RELEASE", release)
    with pytest.raises(ValueError, match="Unsupported CIM release"):
        prep.prepare(options(tmp_path))
    run.assert_not_called()


@pytest.mark.parametrize("explicit", [True, False])
def test_release_environment_and_cli_precedence(
    tmp_path, monkeypatch, capsys, explicit
):
    path, _, _ = manifest(tmp_path, release="2026-R1")
    monkeypatch.setenv("ADIDT_KERNEL_ARTIFACTS_ZYNQ", str(path))
    monkeypatch.setenv("ADIDT_CIM_RELEASE", "2023_R2" if explicit else "2026-R1")
    prep.prepare(options(tmp_path, release="2026-R1" if explicit else None))
    assert "export ADIDT_CIM_RELEASE=2026-R1" in capsys.readouterr().out


def test_wrong_release_artifact_never_rebuilt(tmp_path, monkeypatch):
    path, _, _ = manifest(tmp_path)
    monkeypatch.setenv("ADIDT_KERNEL_ARTIFACTS_ZYNQ", str(path))
    run = Mock(side_effect=AssertionError("must not build"))
    monkeypatch.setattr(prep.subprocess, "run", run)
    with pytest.raises(RuntimeError, match="source ref/commit"):
        prep.prepare(options(tmp_path, release="2026-R1"))
    run.assert_not_called()


@pytest.mark.parametrize("release", ["2023_R2", "2026-R1"])
def test_release_export_and_overlay_preservation(tmp_path, release):
    image = tmp_path / "qualified-image"
    image.write_bytes(b"qualified-overlay-kernel")
    result = run_preflight(
        tmp_path, ADIDT_CIM_RELEASE=release, ADIDT_KERNEL_IMAGE_ZYNQ=str(image)
    )
    assert result.returncode == 0, result.stderr
    assert f"ADIDT_CIM_RELEASE={release}\n" in (tmp_path / "github-env").read_text()
    assert image.read_bytes() == b"qualified-overlay-kernel"


def test_invalid_release_rejected_even_with_disabled_build(tmp_path):
    result = run_preflight(
        tmp_path, ADIDT_CIM_RELEASE="2026_R1", ADI_XSA_BUILD_KERNEL="0"
    )
    assert result.returncode != 0
    assert "Unsupported CIM release" in result.stderr
