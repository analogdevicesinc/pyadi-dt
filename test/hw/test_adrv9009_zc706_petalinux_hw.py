"""ADRV9009 + ZC706 hardware test driven by the PetaLinux flow.

PetaLinux variant of :mod:`test.hw.test_adrv9009_zc706_hw`.  Same SPEC,
same diagnostic tail (JESD sysfs status + ILAS report), only the DTB
source differs.

LG_ENV: ``test/hw/env/nemo.yaml``.  The ``nemo`` host owns the local
``TFTPServerResource`` so this test must be invoked from there.
"""

from __future__ import annotations

import dataclasses

import pytest

from test.hw._petalinux_base import (
    requires_lg,
    requires_petalinux,
    run_petalinux_build_and_verify,
)
from test.hw.test_adrv9009_zc706_hw import SPEC as XSA_SPEC


SPEC = dataclasses.replace(XSA_SPEC, out_label="adrv9009_zc706_petalinux")


@requires_lg
@requires_petalinux
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_adrv9009_zc706_petalinux_hw(board, tmp_path, request):
    """End-to-end pyadi-dt ADRV9009+ZC706 boot + verify (PetaLinux path)."""
    from test.hw.hw_helpers import (
        assert_ilas_aligned,
        parse_ilas_status,
        read_jesd_status,
    )

    shell, _ctx, dmesg_txt = run_petalinux_build_and_verify(
        SPEC, board=board, request=request, tmp_path=tmp_path
    )

    rx_status, tx_status = read_jesd_status(shell)
    print("=== JESD204 RX status (sysfs) ===")
    print(rx_status)
    print("=== JESD204 TX status (sysfs) ===")
    print(tx_status)

    ilas_report = parse_ilas_status(dmesg_txt)
    print("=== ADRV9009 ILAS report ===")
    print(ilas_report.summary())
    if ilas_report.fields:
        for name in ilas_report.fields:
            print(f"  mismatched: {name}")
    assert_ilas_aligned(dmesg_txt, context=SPEC.out_label)
