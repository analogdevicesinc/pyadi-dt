"""Tests for the AD9371 profile-driven pyadi-jif XSA example."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]
EXAMPLE = ROOT / "examples" / "xsa" / "adrv937x_zc706.py"
PROFILE = (
    ROOT
    / "examples"
    / "xsa"
    / "profiles"
    / "ad9371_5"
    / "profile_TxBW200_ORxBW200_RxBW100.txt"
)


def _load_example():
    spec = importlib.util.spec_from_file_location("adrv937x_zc706_example", EXAMPLE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _require_new_adijif() -> None:
    import adijif

    if not hasattr(adijif, "ad9371"):
        pytest.skip("requires pyadi-jif AD9371 support newer than v0.1.7")


def test_ad9371_profile_drives_all_mykonos_links() -> None:
    """The new pyadi-jif model must replace the old hard-coded framing."""
    _require_new_adijif()
    module = _load_example()

    cfg, summary = module._resolve_config_from_adijif(PROFILE, solve=False)

    assert cfg["jesd"]["rx"] == {
        "F": 4,
        "K": 32,
        "M": 4,
        "L": 2,
        "N": 14,
        "Np": 16,
        "S": 1,
        "CS": 2,
    }
    assert cfg["jesd"]["obs"] == {
        "F": 2,
        "K": 32,
        "M": 2,
        "L": 2,
        "N": 14,
        "Np": 16,
        "S": 1,
        "CS": 2,
    }
    assert cfg["jesd"]["tx"] == {
        "F": 2,
        "K": 32,
        "M": 4,
        "L": 4,
        "N": 14,
        "Np": 16,
        "S": 1,
        "CS": 2,
    }
    assert cfg["adrv9009_board"]["ad9371_profile_path"] == str(PROFILE.resolve())
    assert cfg["adrv9009_board"]["ad9528_vcxo_freq"] == 122_880_000
    assert cfg["adrv9009_board"]["ad9528_jesd204_max_sysref_hz"] == 78_125
    assert summary["rates_hz"] == {
        "rx": 122_880_000,
        "obs": 245_760_000,
        "tx": 245_760_000,
    }
    assert summary["solver_attempted"] is False


def test_ad9371_profile_can_be_solved_with_shared_sysref() -> None:
    """Exercise the corrected three-link solver result when CPLEX is available."""
    _require_new_adijif()
    module = _load_example()
    try:
        cfg, summary = module._resolve_config_from_adijif(PROFILE, solve=True)
    except Exception as exc:
        if "CPLEX" in str(exc) or "docplex" in str(exc):
            pytest.skip(f"CPLEX unavailable: {exc}")
        raise

    assert summary["solver_succeeded"] is True
    clocks = summary["clock_output_clocks"]
    assert clocks["AD9371_ref_clk"]["rate"] == 122_880_000
    assert clocks["adc_sysref"]["rate"] == clocks["obs_sysref"]["rate"]
    assert clocks["obs_sysref"]["rate"] == clocks["dac_sysref"]["rate"]
    assert cfg["fpga_adc"]["type"] == "qpll"
    assert cfg["fpga_obs"]["type"] == "qpll"
    assert cfg["fpga_dac"]["type"] == "qpll"


def test_show_jif_config_runs_without_xsa_or_network() -> None:
    """The profile/JIF part of the example remains executable in examples CI."""
    _require_new_adijif()
    result = subprocess.run(
        [
            sys.executable,
            str(EXAMPLE),
            "--ad9371-profile",
            str(PROFILE),
            "--show-jif-config",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["config"]["jesd"]["rx"]["L"] == 2
    assert payload["config"]["jesd"]["obs"]["M"] == 2
    assert payload["config"]["jesd"]["tx"]["F"] == 2
    assert payload["summary"]["solver_attempted"] is False
