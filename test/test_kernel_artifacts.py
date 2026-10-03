"""CIM handoff validation without toolchains or hardware."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from test.hw import conftest, hw_helpers
from test.hw.kernel_artifacts import read_kernel_artifacts, resolve_kernel_image


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch):
    for platform in ("ZYNQ", "ZYNQMP"):
        for prefix in (
            "ADIDT_KERNEL_IMAGE",
            "ADIDT_KERNEL_ARTIFACTS",
            "ADIDT_OVERLAY_KERNEL_IMAGE",
        ):
            monkeypatch.delenv(f"{prefix}_{platform}", raising=False)
    monkeypatch.delenv("ADI_XSA_BUILD_KERNEL", raising=False)
    monkeypatch.setattr(hw_helpers, "DEFAULT_BUILD_KERNEL", True)


def manifest(tmp_path, platform="zynq"):
    image = tmp_path / ("uImage" if platform == "zynq" else "Image")
    image.write_bytes(b"test kernel payload")
    data = dict(
        schema_version=1,
        platform=platform,
        kernel_image=str(image),
        sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
        provenance={"target": f"adi-linux-2023-r2-{platform}"},
    )
    path = tmp_path / "artifacts.json"
    path.write_text(json.dumps(data))
    return path, image, data


@pytest.mark.parametrize("platform", ["zynq", "zynqmp"])
def test_valid_handoff_and_revalidation(tmp_path, monkeypatch, platform):
    path, image, _ = manifest(tmp_path, platform)
    monkeypatch.setenv(f"ADIDT_KERNEL_ARTIFACTS_{platform.upper()}", str(path))
    assert hw_helpers.build_kernel_image(platform) == image
    image.write_bytes(b"tampered")
    with pytest.raises(RuntimeError, match="SHA-256 mismatch"):
        hw_helpers.build_kernel_image(platform)


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("schema_version", 2, "schema_version"),
        ("schema_version", True, "schema_version"),
        ("schema_version", "1", "schema_version"),
        ("platform", "zynqmp", "expected platform"),
        ("kernel_image", "relative/uImage", "absolute path"),
        ("kernel_image", None, "non-empty string"),
        ("sha256", "not hex", "hexadecimal"),
        ("sha256", "0" * 64, "SHA-256 mismatch"),
    ],
)
def test_invalid_fields(tmp_path, field, value, error):
    path, _, data = manifest(tmp_path)
    data[field] = value
    path.write_text(json.dumps(data))
    with pytest.raises(RuntimeError, match=error):
        read_kernel_artifacts(str(path), "zynq")


@pytest.mark.parametrize("payload", ["not json", "[]", "null", "{}"])
def test_invalid_json(tmp_path, payload):
    path = tmp_path / "artifacts.json"
    path.write_text(payload)
    with pytest.raises(RuntimeError):
        read_kernel_artifacts(str(path), "zynq")


@pytest.mark.parametrize("kind", ["missing", "empty", "directory"])
def test_image_must_be_nonempty_file(tmp_path, kind):
    path, image, _ = manifest(tmp_path)
    image.unlink()
    if kind == "empty":
        image.touch()
    elif kind == "directory":
        image.mkdir()
    with pytest.raises(RuntimeError, match="non-empty file"):
        read_kernel_artifacts(str(path), "zynq")


def test_missing_manifest(tmp_path):
    with pytest.raises(RuntimeError, match="manifest is not a file"):
        read_kernel_artifacts(str(tmp_path / "missing.json"), "zynq")


@pytest.mark.parametrize("value", ["0", "false", "no", "FALSE"])
def test_disabled_semantics_and_override_priority(tmp_path, monkeypatch, value):
    monkeypatch.setenv("ADI_XSA_BUILD_KERNEL", value)
    monkeypatch.setenv("ADIDT_KERNEL_ARTIFACTS_ZYNQ", "/missing.json")
    assert resolve_kernel_image("zynq") is None
    image = tmp_path / "known-good"
    image.write_bytes(b"prebuilt")
    monkeypatch.setenv("ADIDT_KERNEL_IMAGE_ZYNQ", str(image))
    assert resolve_kernel_image("zynq") == image
    image.unlink()
    with pytest.raises(RuntimeError, match="ADIDT_KERNEL_IMAGE_ZYNQ"):
        resolve_kernel_image("zynq")


def test_missing_artifact_is_actionable_failure():
    with pytest.raises(RuntimeError, match="ADIDT_KERNEL_ARTIFACTS_ZYNQ"):
        hw_helpers.build_kernel_image("zynq")
    with pytest.raises(ValueError, match="Unknown platform"):
        resolve_kernel_image("microblaze", enabled=False)


def session_for(*specs):
    return SimpleNamespace(
        config=SimpleNamespace(option=SimpleNamespace(collectonly=False)),
        items=[
            SimpleNamespace(
                module=SimpleNamespace(
                    SPEC=SimpleNamespace(kernel_fixture_name=fixture)
                ),
                path=Path(name),
            )
            for fixture, name in specs
        ],
    )


def test_preflight_only_checks_selected_platform(monkeypatch):
    monkeypatch.setenv("LG_ENV", "test-env.yaml")
    resolver = Mock()
    monkeypatch.setattr(conftest, "build_kernel_image", resolver)
    session = session_for(
        ("built_kernel_image_zynq", "test_zc706_hw.py"),
        ("built_kernel_image_zynq", "test_zc706_hw.py"),
        (None, "test_fabric_overlay.py"),
    )
    conftest.pytest_collection_finish(session)
    resolver.assert_called_once_with("zynq")


def test_overlay_only_preflight_preserves_override(monkeypatch, tmp_path):
    monkeypatch.setenv("LG_ENV", "test-env.yaml")
    image = tmp_path / "runtime-uImage"
    image.write_bytes(b"runtime")
    monkeypatch.setenv("ADIDT_OVERLAY_KERNEL_IMAGE_ZYNQ", str(image))
    resolver = Mock(side_effect=RuntimeError("missing ordinary image"))
    monkeypatch.setattr(conftest, "build_kernel_image", resolver)
    session = session_for(("built_kernel_image_zynq", "test_zc706_overlay.py"))
    conftest.pytest_collection_finish(session)
    resolver.assert_not_called()
    session.items += session_for(("built_kernel_image_zynq", "test_zc706_hw.py")).items
    with pytest.raises(pytest.UsageError, match="missing ordinary image"):
        conftest.pytest_collection_finish(session)


def test_collect_only_does_not_require_kernels(monkeypatch):
    monkeypatch.setenv("LG_ENV", "test-env.yaml")
    session = session_for(("built_kernel_image_zynq", "test_zc706_hw.py"))
    session.config.option.collectonly = True
    conftest.pytest_collection_finish(session)


def test_collection_failure_precedes_hardware_fixture(tmp_path, monkeypatch):
    import os
    import subprocess
    import sys

    (tmp_path / "conftest.py").write_text(
        "from test.hw.conftest import pytest_collection_finish\n"
    )
    (tmp_path / "test_probe.py").write_text(
        "from types import SimpleNamespace\n"
        "import pytest\n"
        "SPEC = SimpleNamespace(kernel_fixture_name='built_kernel_image_zynq')\n"
        "@pytest.fixture\n"
        "def strategy():\n"
        "    open('acquired', 'w').close()\n"
        "def test_probe(strategy): pass\n"
    )
    env = dict(
        os.environ,
        PYTHONPATH=str(Path(__file__).resolve().parents[1]),
        PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
        LG_ENV="unused.yaml",
    )
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 4, result.stdout + result.stderr
    assert "ADIDT_KERNEL_ARTIFACTS_ZYNQ" in result.stderr
    assert not (tmp_path / "acquired").exists()
