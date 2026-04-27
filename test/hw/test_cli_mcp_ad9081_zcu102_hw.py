"""``adidt-mcp`` end-to-end hardware test for AD9081 + ZCU102.

Calls :func:`adidt.mcp_server.generate_devicetree` in-process — the
same entry point the FastMCP server exposes to MCP clients — and
boots the resulting merged DTS on real hardware.  Verifies the MCP
path (separate from the ``adidtc`` Click CLI) produces a bootable
artifact end-to-end.

The other four MCP tools (``list_xsa_profiles``, ``show_xsa_profile``,
``read_dt_property``, ``lint_devicetree``) are file-/local-only and
have no hardware-dependent behavior; they are already covered by
:mod:`test.test_mcp_server`.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

pytest.importorskip("fastmcp", reason="fastmcp not installed")

from test.hw._system_base import (
    boot_and_verify_from_merged_dts,
    requires_lg,
)
from test.hw.hw_helpers import DEFAULT_OUT_DIR
from test.hw.test_ad9081_zcu102_xsa_hw import SPEC as XSA_SPEC


SPEC = dataclasses.replace(XSA_SPEC, out_label="ad9081_cli_mcp")


@requires_lg
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_mcp_generate_devicetree_produces_bootable_dtb(board, tmp_path: Path, request):
    """``mcp_server.generate_devicetree`` -> merged DTS -> dtc -> boot + verify."""
    from adidt.mcp_server import generate_devicetree

    xsa_path = SPEC.xsa_resolver(tmp_path)
    assert xsa_path.exists(), f"XSA not found: {xsa_path}"

    output_dir = tmp_path / "mcp_out"
    cfg_json = json.dumps(SPEC.cfg_builder())

    data = generate_devicetree(
        xsa_path=str(xsa_path),
        output_dir=str(output_dir),
        config_json=cfg_json,
        profile=SPEC.sdtgen_profile,
        sdtgen_timeout=SPEC.sdtgen_timeout,
    )
    assert "error" not in data, f"generate_devicetree returned error: {data!r}"
    assert "merged" in data, f"no merged key in MCP result: {data!r}"

    merged_dts = Path(data["merged"])
    assert merged_dts.exists(), f"MCP-reported merged DTS missing: {merged_dts}"

    merged_text = merged_dts.read_text()
    for needle in SPEC.merged_dts_must_contain:
        assert needle in merged_text, (
            f"Required substring {needle!r} missing from MCP-produced DTS "
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
