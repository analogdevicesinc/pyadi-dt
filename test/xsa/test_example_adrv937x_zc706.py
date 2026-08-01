"""Tests for the AD9371 profile-driven pyadi-jif XSA example."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from adidt.profiles import resolve_ad9371_jif_config

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
PROFILE_DIR = ROOT / "examples" / "xsa" / "profiles" / "ad9371_5"

# Expected per-profile ADC/OBS/TX sample rates (Hz).  The Mykonos JESD
# framing (M/L/F/K) is identical across profiles — only the sample rates
# change with bandwidth — so the framing is asserted once against the
# canonical profile above and the rate table is the per-profile contract.
PROFILE_RATE_TABLE = {
    "profile_TxBW200_ORxBW200_RxBW100.txt": {
        "rx": 122_880_000,
        "obs": 245_760_000,
        "tx": 245_760_000,
    },
    "profile_TxBW100_ORxBW100_RxBW100.txt": {
        "rx": 122_880_000,
        "obs": 122_880_000,
        "tx": 122_880_000,
    },
    "profile_TxBW100_ORxBW100_RxBW50.txt": {
        "rx": 61_440_000,
        "obs": 122_880_000,
        "tx": 122_880_000,
    },
    "profile_TxBW100_ORxBW100_RxBW20.txt": {
        "rx": 30_720_000,
        "obs": 122_880_000,
        "tx": 122_880_000,
    },
    "profile_TxBW50_ORxBW50_RxBW50.txt": {
        "rx": 61_440_000,
        "obs": 61_440_000,
        "tx": 61_440_000,
    },
    "profile_TxBW50_ORxBW50_RxBW25.txt": {
        "rx": 30_720_000,
        "obs": 61_440_000,
        "tx": 61_440_000,
    },
}

# Framing shared by every AD9371 profile (bandwidth changes rates, not
# lane/converter geometry).
_EXPECTED_FRAMING = {
    "rx": {"M": 4, "L": 2, "F": 4, "K": 32},
    "obs": {"M": 2, "L": 2, "F": 2, "K": 32},
    "tx": {"M": 4, "L": 4, "F": 2, "K": 32},
}


def _require_new_adijif() -> None:
    import adijif

    if not hasattr(adijif, "ad9371"):
        pytest.skip("requires pyadi-jif AD9371 support newer than v0.1.7")


def test_ad9371_profile_drives_all_mykonos_links() -> None:
    """The new pyadi-jif model must replace the old hard-coded framing."""
    _require_new_adijif()
    cfg, summary = resolve_ad9371_jif_config(PROFILE, solve=False)

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
    try:
        cfg, summary = resolve_ad9371_jif_config(PROFILE, solve=True)
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


def test_profile_rate_table_covers_all_shipped_profiles() -> None:
    """Guard against a new profile being added without rate coverage."""
    shipped = {p.name for p in PROFILE_DIR.glob("profile_TxBW*.txt")}
    assert shipped == set(PROFILE_RATE_TABLE), (
        "AD9371 profile set changed; update PROFILE_RATE_TABLE. "
        f"shipped={sorted(shipped)} table={sorted(PROFILE_RATE_TABLE)}"
    )


@pytest.mark.parametrize("profile_name", sorted(PROFILE_RATE_TABLE))
def test_every_ad9371_profile_resolves_with_expected_rates(profile_name) -> None:
    """Each shipped AD9371 profile resolves to its documented rates + framing.

    This is the software half of the alternate-profile coverage: it proves
    pyadi-dt correctly parses and models every profile the repo ships, not
    just the one booted in the hardware matrix.  The hardware boot/capture
    sweep is opt-in via ``ADIDT_AD9371_PROFILE_SWEEP`` (see the hw test).
    """
    _require_new_adijif()
    profile = PROFILE_DIR / profile_name
    cfg, summary = resolve_ad9371_jif_config(profile, solve=False)

    assert summary["rates_hz"] == PROFILE_RATE_TABLE[profile_name]
    for link, expected in _EXPECTED_FRAMING.items():
        got = cfg["jesd"][link]
        for key, value in expected.items():
            assert got[key] == value, (
                f"{profile_name} jesd.{link}.{key} = {got[key]!r}, "
                f"expected {value!r}"
            )


@pytest.mark.parametrize("profile_name", sorted(PROFILE_RATE_TABLE))
def test_every_ad9371_profile_show_jif_config(profile_name) -> None:
    """``--show-jif-config`` produces a valid payload for every profile."""
    _require_new_adijif()
    profile = PROFILE_DIR / profile_name
    result = subprocess.run(
        [
            sys.executable,
            str(EXAMPLE),
            "--ad9371-profile",
            str(profile),
            "--show-jif-config",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    payload = json.loads(result.stdout)
    assert payload["summary"]["rates_hz"] == PROFILE_RATE_TABLE[profile_name]
    assert payload["config"]["jesd"]["rx"]["L"] == 2
    assert payload["config"]["jesd"]["obs"]["M"] == 2
    assert payload["config"]["jesd"]["tx"]["F"] == 2
