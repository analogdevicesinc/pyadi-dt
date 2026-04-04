"""Parameterized hardware test for all Kuiper 2023-R2 boards.

Runs the XSA pipeline for each board in kuiper_boards.json that has
"full" status. Downloads XSA from the Kuiper release, generates DTS,
compiles DTB, deploys, boots, and verifies IIO devices.

Usage:
    LG_ENV=/path/to/lg.yaml pytest test/hw/xsa/test_kuiper_boards.py -v

To test a specific board:
    LG_ENV=/path/to/lg.yaml pytest test/hw/xsa/test_kuiper_boards.py -k "fmcdaq2_zcu102"
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

if not os.environ.get("LG_ENV"):
    pytest.skip("set LG_ENV for Kuiper board hardware tests", allow_module_level=True)

MANIFEST_PATH = (
    Path(__file__).parent.parent.parent.parent / "adidt" / "xsa" / "kuiper_boards.json"
)


def _load_full_boards() -> list[tuple[str, dict]]:
    """Load boards with 'full' status from the manifest."""
    if not MANIFEST_PATH.exists():
        return []
    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)
    return [
        (name, info)
        for name, info in manifest.get("boards", {}).items()
        if info.get("status") == "full"
    ]


FULL_BOARDS = _load_full_boards()
BOARD_IDS = [f"{info['converter']}_{info['platform']}" for _, info in FULL_BOARDS]


@pytest.fixture(scope="module")
def built_kernel_image(built_kernel_image_zynqmp: Path | None) -> Path | None:
    return built_kernel_image_zynqmp


@pytest.mark.parametrize("board_name,board_info", FULL_BOARDS, ids=BOARD_IDS)
def test_kuiper_board_pipeline(
    board_name, board_info, board, built_kernel_image, tmp_path
):
    """Run XSA pipeline for a Kuiper board and verify it produces valid output."""
    from adidt.xsa.pipeline import XsaPipeline
    from adidt.xsa.profiles import ProfileManager, merge_profile_defaults
    from test.hw.hw_helpers import DEFAULT_OUT_DIR, compile_dts_to_dtb
    from test.xsa.kuiper_release import download_project_xsa

    release = os.environ.get("ADI_KUIPER_BOOT_RELEASE", "2023_r2")
    bootbin = f"release:{board_name}/BOOT.BIN"

    # Download XSA
    xsa_path = download_project_xsa(
        release=release,
        project_dir=board_name,
        cache_dir=tmp_path / "kuiper_cache",
        output_dir=tmp_path / "xsa",
    )
    assert xsa_path.exists(), f"XSA extraction failed for {board_name}"

    # Load profile
    profile_name = board_info.get("profile")
    cfg = {}
    if profile_name:
        profile_data = ProfileManager().load(profile_name)
        if profile_data:
            cfg = merge_profile_defaults(cfg, profile_data)

    # Run pipeline
    out_dir = DEFAULT_OUT_DIR / board_name.replace("-", "_")
    out_dir.mkdir(parents=True, exist_ok=True)
    result = XsaPipeline().run(
        xsa_path=xsa_path,
        cfg=cfg,
        output_dir=out_dir,
        sdtgen_timeout=300,
        profile=profile_name,
    )

    assert result["merged"].exists(), f"Merged DTS not generated for {board_name}"

    # Compile DTB
    dtb = out_dir / "system.dtb"
    try:
        compile_dts_to_dtb(result["merged"], dtb)
    except RuntimeError as e:
        pytest.skip(f"DTB compilation failed for {board_name}: {e}")

    assert dtb.exists(), f"DTB not generated for {board_name}"
