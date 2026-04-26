"""AD9081 + ZCU102 hardware test driven by the PetaLinux flow.

PetaLinux variant of :mod:`test.hw.test_ad9081_zcu102_xsa_hw`.  Reuses
the same :class:`BoardSystemProfile`; only the DTB source differs.

Pipeline:

    XSA → petalinux-create → petalinux-config --get-hw-description
        → pyadi-dt system-user.dtsi (PetalinuxFormatter)
        → petalinux-build -c device-tree
        → images/linux/system.dtb
        → boot via labgrid (Kuiper kernel + rootfs on SD)
        → standard verify (probes, IIO, JESD DATA, RX capture)

Prereqs:

* ``PETALINUX_INSTALL`` pointing at a 2023.2+ install root (default
  ``/opt/Xilinx/PetaLinux/2023.2``).
* Project + sstate cache under ``${PETALINUX_PROJECT_CACHE_DIR}``
  (default ``~/.cache/adidt/petalinux``).
* ``LG_COORDINATOR`` / ``LG_ENV`` for the ``mini2`` place.
"""

from __future__ import annotations

import dataclasses

import pytest

from test.hw._petalinux_base import (
    requires_lg,
    requires_petalinux,
    run_petalinux_build_and_verify,
)
from test.hw.test_ad9081_zcu102_xsa_hw import SPEC as XSA_SPEC


SPEC = dataclasses.replace(XSA_SPEC, out_label="ad9081_zcu102_petalinux")


@requires_lg
@requires_petalinux
@pytest.mark.lg_feature(list(SPEC.lg_features))
def test_ad9081_zcu102_petalinux_hw(board, tmp_path, request):
    """End-to-end pyadi-dt AD9081+ZCU102 boot + verify (PetaLinux path)."""
    run_petalinux_build_and_verify(
        SPEC, board=board, request=request, tmp_path=tmp_path
    )
