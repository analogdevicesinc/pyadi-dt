"""AD9081 + ZCU102 hardware tests for the DTS-generation CLI commands.

Drives ``adidtc xsa2dt`` and ``adidtc gen-dts`` as a user would (via
:class:`click.testing.CliRunner`) and validates that the produced
artifacts are usable end-to-end:

* ``xsa2dt`` — runs the full 5-stage XSA pipeline through the CLI
  surface, then hands the merged DTS to the standard
  :func:`boot_and_verify_from_merged_dts` path so the same boot + IIO
  + JESD checks the python-API test runs are exercised against
  CLI-produced output.
* ``gen-dts`` — composes via the declarative ``System`` API; the CLI
  emits an overlay-style DTS that is not bootable on its own (no base
  platform DTS), so the CLI's own ``--compile`` flag is asserted to
  succeed.  The bootable path for the System API is already covered
  by :mod:`test.hw.test_ad9081_zcu102_system_hw`.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from test.hw._cli_base import run_adidtc
from test.hw._system_base import (
    BoardSystemProfile,
    acquire_or_local_xsa,
    boot_and_verify_from_merged_dts,
    requires_lg,
)
from test.hw.hw_helpers import DEFAULT_OUT_DIR
from test.hw.test_ad9081_zcu102_xsa_hw import _solve_ad9081_config, _topology_assert


DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynqmp-zcu102-rev10-ad9081"


SPEC = BoardSystemProfile(
    lg_features=("ad9081", "zcu102"),
    cfg_builder=_solve_ad9081_config,
    xsa_resolver=acquire_or_local_xsa(
        "system_top_ad9081_zcu102.xsa",
        DEFAULT_KUIPER_RELEASE,
        DEFAULT_KUIPER_PROJECT,
    ),
    sdtgen_profile="ad9081_zcu102",
    topology_assert=_topology_assert,
    boot_mode="sd",
    kernel_fixture_name="built_kernel_image_zynqmp",
    out_label="ad9081_cli_xsa2dt",
    dmesg_grep_pattern="ad9081|hmc7044|jesd204|probe|failed|error",
    merged_dts_must_contain=(
        'compatible = "adi,ad9081"',
        'compatible = "adi,hmc7044"',
    ),
    probe_signature_any=("AD9081 Rev.", "probed ADC AD9081"),
    probe_signature_message="AD9081 probe signature not found in dmesg",
    iio_required_all=("hmc7044",),
    iio_required_any_groups=(
        ("axi-ad9081-rx-hpc", "ad_ip_jesd204_tpl_adc"),
        ("axi-ad9081-tx-hpc", "ad_ip_jesd204_tpl_dac"),
    ),
    jesd_rx_glob="84a90000.axi[_-]jesd204[_-]rx",
    jesd_tx_glob="84b90000.axi[_-]jesd204[_-]tx",
    rx_capture_target_names=("axi-ad9081-rx-hpc", "ad_ip_jesd204_tpl_adc"),
)


@requires_lg
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_xsa2dt_cli_produces_bootable_dtb(board, tmp_path, request):
    """``adidtc xsa2dt`` -> merged DTS -> dtc -> labgrid boot + verify."""
    xsa_path = SPEC.xsa_resolver(tmp_path)
    assert xsa_path.exists(), f"XSA not found: {xsa_path}"

    cfg_path = tmp_path / "ad9081_cli_cfg.json"
    cfg_path.write_text(json.dumps(SPEC.cfg_builder()))

    out_dir = tmp_path / "xsa2dt_out"
    result = run_adidtc(
        [
            "xsa2dt",
            "--xsa",
            str(xsa_path),
            "--config",
            str(cfg_path),
            "--output",
            str(out_dir),
            "--profile",
            SPEC.sdtgen_profile,
            "--timeout",
            str(SPEC.sdtgen_timeout),
        ],
    )
    print(result.output)

    merged_candidates = sorted(out_dir.glob("*.dts"))
    assert merged_candidates, f"xsa2dt produced no DTS in {out_dir}"
    merged_dts = merged_candidates[0]

    merged_text = merged_dts.read_text()
    for needle in SPEC.merged_dts_must_contain:
        assert needle in merged_text, (
            f"Required substring {needle!r} missing from CLI-produced DTS "
            f"({merged_dts})"
        )

    boot_out = DEFAULT_OUT_DIR
    boot_out.mkdir(parents=True, exist_ok=True)
    boot_and_verify_from_merged_dts(
        SPEC,
        merged_dts,
        board=board,
        request=request,
        out_dir=boot_out,
    )


def test_gen_dts_cli_compiles_to_dtb(tmp_path: Path):
    """``adidtc gen-dts --compile`` for ad9081_fmc+zcu102 emits a valid DTB.

    The System-API CLI path produces an overlay-style DTS without a
    platform base, so booting it standalone is not meaningful; the
    bootable composition is validated elsewhere by
    :mod:`test.hw.test_ad9081_zcu102_system_hw`.  This test asserts the
    CLI flow itself (argument parsing, ``System.generate_dts`` ->
    ``dtc`` invocation) succeeds and produces a non-empty DTB.
    """
    cfg_path = tmp_path / "gen_dts_cfg.json"
    cfg_path.write_text("{}")
    out_dts = tmp_path / "ad9081_zcu102.dts"
    out_dtb = out_dts.with_suffix(".dtb")

    result = run_adidtc(
        [
            "gen-dts",
            "--board",
            "ad9081_fmc",
            "--platform",
            "zcu102",
            "--config",
            str(cfg_path),
            "--output",
            str(out_dts),
            "--compile",
        ],
    )
    print(result.output)

    assert out_dts.exists(), f"gen-dts did not write DTS to {out_dts}"
    dts_text = out_dts.read_text()
    assert "/dts-v1/;" in dts_text
    assert "ad9081" in dts_text.lower()

    assert out_dtb.exists(), f"--compile did not produce DTB at {out_dtb}"
    assert out_dtb.stat().st_size > 0, f"DTB is empty: {out_dtb}"
