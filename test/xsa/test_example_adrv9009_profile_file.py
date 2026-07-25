"""Tests for the ADRV9009 board- and Talise-profile example."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = REPO_ROOT / "examples" / "xsa" / "adrv9009_profile_file.py"
BOARD_PROFILE = (
    REPO_ROOT
    / "examples"
    / "xsa"
    / "profiles"
    / "adrv9009_zc706_custom.json"
)
TUTORIAL = REPO_ROOT / "doc" / "source" / "examples" / "xsa_tutorial.md"
EXPECTED_TALISE_PROFILES = {
    "tx100-rx100-orx100": (
        "Tx_BW100_IR122p88_Rx_BW100_OR122p88_ORx_BW100_OR122p88_DC245p76.txt",
        "d1f6cf05c9f39a63d2cc3bbf18ebaf63e7d0ca4df0c8c9b29733c93386555edd",
    ),
    "tx200-rx100-orx200": (
        "Tx_BW200_IR245p76_Rx_BW100_OR122p88_ORx_BW200_OR245p76_DC245p76.txt",
        "58fe2c44a69b4cced645b952d14b6d746de39e5a8e7f14e8b600d3121bf38b4b",
    ),
    "tx200-rx200-orx200": (
        "Tx_BW200_IR245p76_Rx_BW200_OR245p76_ORx_BW200_OR245p76_DC245p76.txt",
        "85e93c550f7b5ca87ec15e5720551bd75eb47753f82f12bc8d740834cc8c4bb7",
    ),
    "tx400-rx100-orx400": (
        "Tx_BW400_IR491p52_Rx_BW100_OR122p88_ORx_BW400_OR491p52_DC245p76.txt",
        "ad8111a7abbcde2cb4e6505c8cf6e56a81ebd1e3c454d33ccbded93f61c02087",
    ),
}


def _load_example_module():
    spec = importlib.util.spec_from_file_location("adrv9009_profile_file", EXAMPLE)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_show_config_executes_with_checked_in_board_profile() -> None:
    """The no-hardware path must validate and merge both board profiles."""
    result = subprocess.run(
        [
            sys.executable,
            str(EXAMPLE),
            "--board-profile-file",
            str(BOARD_PROFILE),
            "--show-config",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    config = json.loads(result.stdout)

    board = config["adrv9009_board"]
    assert board["spi_bus"] == "spi0"  # inherited from the built-in profile
    assert board["trx_spi_max_frequency"] == 10_000_000  # file override
    assert board["trx_reset_gpio"] == 130  # inherited built-in wiring


def test_canonical_talise_manifest_is_pinned_and_complete() -> None:
    """Expose all four upstream profiles with reviewed content hashes."""
    module = _load_example_module()

    assert module.IIO_OSCILLOSCOPE_COMMIT == "c4baaaafe2f91c41c2d4c800f017655296f8a001"
    assert {
        alias: (profile.filename, profile.sha256)
        for alias, profile in module.TALISE_PROFILES.items()
    } == EXPECTED_TALISE_PROFILES


def test_download_talise_profile_verifies_source_and_caches(monkeypatch, tmp_path) -> None:
    """A fetched profile must be XML from the pinned URL with the expected hash."""
    module = _load_example_module()
    body = b"<profile Talise version=1 name=test>\n</profile>\n"
    sha256 = hashlib.sha256(body).hexdigest()
    profile = module.TaliseProfile("fixture.txt", sha256)
    monkeypatch.setitem(module.TALISE_PROFILES, "fixture", profile)
    response = MagicMock()
    response.__enter__.return_value.read.return_value = body
    response.__exit__.return_value = False
    urlopen = MagicMock(return_value=response)
    monkeypatch.setattr(module.urllib.request, "urlopen", urlopen)

    downloaded = module.download_talise_profile("fixture", tmp_path)
    cached = module.download_talise_profile("fixture", tmp_path)

    assert downloaded == cached == tmp_path / "fixture.txt"
    assert downloaded.read_bytes() == body
    assert module.IIO_OSCILLOSCOPE_COMMIT in urlopen.call_args.args[0]
    urlopen.assert_called_once()


def test_download_talise_profile_rejects_checksum_mismatch(monkeypatch, tmp_path) -> None:
    """Never cache unreviewed or truncated hardware profile content."""
    module = _load_example_module()
    profile = module.TaliseProfile("fixture.txt", "0" * 64)
    monkeypatch.setitem(module.TALISE_PROFILES, "fixture", profile)
    response = MagicMock()
    response.__enter__.return_value.read.return_value = b"<profile bad>\n"
    response.__exit__.return_value = False
    monkeypatch.setattr(module.urllib.request, "urlopen", MagicMock(return_value=response))

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        module.download_talise_profile("fixture", tmp_path)

    assert not (tmp_path / "fixture.txt").exists()


def test_pipeline_downloads_selected_talise_profile(monkeypatch, tmp_path, capsys) -> None:
    """A pipeline run must fetch and identify the runtime profile to apply."""
    module = _load_example_module()
    fake_xsa = tmp_path / "system_top.xsa"
    fake_xsa.write_text("xsa")
    talise_path = tmp_path / "profiles" / "canonical.txt"
    runner = MagicMock()
    runner.run.return_value = {"merged": tmp_path / "adrv9009_zc706.dts"}
    downloader = MagicMock(return_value=talise_path)
    monkeypatch.setattr(module, "XsaPipeline", lambda: runner)
    monkeypatch.setattr(module, "download_talise_profile", downloader)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "adrv9009_profile_file.py",
            "--board-profile-file",
            str(BOARD_PROFILE),
            "--talise-profile",
            "tx200-rx200-orx200",
            "--xsa",
            str(fake_xsa),
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )

    module.main()

    kwargs = runner.run.call_args.kwargs
    assert kwargs["profile"] == "adrv9009_zc706"
    assert kwargs["cfg"]["adrv9009_board"]["trx_spi_max_frequency"] == 10_000_000
    downloader.assert_called_once_with("tx200-rx200-orx200", tmp_path / "out" / "profiles")
    output = capsys.readouterr().out
    assert str(talise_path) in output
    assert "profile_config" in output
    assert "does not write hardware automatically" in output


def test_profile_file_example_is_documented() -> None:
    """Keep canonical retrieval and hardware application guidance discoverable."""
    tutorial = TUTORIAL.read_text()
    assert "ADRV9009 board and Talise profile files" in tutorial
    assert "analogdevicesinc/iio-oscilloscope" in tutorial
    assert "--talise-profile tx200-rx200-orx200" in tutorial
    assert "--download-talise-profile" in tutorial
    assert "profile_config" in tutorial
