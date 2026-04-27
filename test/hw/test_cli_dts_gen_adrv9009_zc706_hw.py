"""ADRV9009 + ZC706 hardware tests for the DTS-generation CLI commands.

Mirrors :mod:`test.hw.test_cli_dts_gen_ad9081_zcu102_hw` for the
Zynq-7000 + TFTP-boot path.  Only ``xsa2dt`` is tested end-to-end:
``gen-dts`` does not yet support the ``adrv9009_fmc`` + ``zc706``
combination (see :data:`adidt.cli.gen_dts.BUILDERS`), so that test
asserts the CLI rejects the unsupported combo with a clear error.
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
from test.hw.test_adrv9009_zc706_hw import (
    _adrv9009_cfg,
    _filter_si570_probe_noise,
    _topology_assert,
)


DEFAULT_KUIPER_RELEASE = "2023_r2"
DEFAULT_KUIPER_PROJECT = "zynq-zc706-adv7511-adrv9009"


SPEC = BoardSystemProfile(
    lg_features=("adrv9009", "zc706"),
    cfg_builder=_adrv9009_cfg,
    xsa_resolver=acquire_or_local_xsa(
        "system_top_adrv9009_zc706.xsa",
        DEFAULT_KUIPER_RELEASE,
        DEFAULT_KUIPER_PROJECT,
    ),
    sdtgen_profile="adrv9009_zc706",
    topology_assert=_topology_assert,
    boot_mode="tftp",
    kernel_fixture_name="built_kernel_image_zynq",
    out_label="adrv9009_cli_xsa2dt",
    dmesg_grep_pattern="adrv9009|hmc7044|ad9528|jesd204|talise|probe|failed|error",
    dmesg_filter=_filter_si570_probe_noise,
    merged_dts_must_contain=('compatible = "adi,adrv9009"',),
    probe_signature_any=("adrv9009", "talise"),
    probe_signature_message="ADRV9009 driver probe signature not found in dmesg",
    iio_required_any_groups=(
        ("adrv9009-phy", "talise"),
        ("ad9528-1", "hmc7044"),
    ),
)


@requires_lg
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_xsa2dt_cli_produces_bootable_dtb(board, tmp_path, request):
    """``adidtc xsa2dt`` for ADRV9009+ZC706 -> merged DTS -> TFTP boot + verify."""
    xsa_path = SPEC.xsa_resolver(tmp_path)
    assert xsa_path.exists(), f"XSA not found: {xsa_path}"

    cfg_path = tmp_path / "adrv9009_cli_cfg.json"
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


def test_gen_dts_cli_rejects_unsupported_combo(tmp_path: Path):
    """``adidtc gen-dts -b adrv9009_fmc -p zc706`` errors clearly.

    The declarative ``System`` API path only registers builders for
    ``ad9081_fmc + zcu102`` and ``ad9084_fmc + vpk180``.  Confirm the
    CLI surface produces a usable error message rather than a stack
    trace when run against this board.
    """
    cfg_path = tmp_path / "gen_dts_cfg.json"
    cfg_path.write_text("{}")
    out_dts = tmp_path / "should_not_exist.dts"

    result = run_adidtc(
        [
            "gen-dts",
            "--board",
            "adrv9009_fmc",
            "--platform",
            "zc706",
            "--config",
            str(cfg_path),
            "--output",
            str(out_dts),
        ],
        expect_exit=2,
    )
    assert "Supported combos" in result.output
    assert not out_dts.exists()
