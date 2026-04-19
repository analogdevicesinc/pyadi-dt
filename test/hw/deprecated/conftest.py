"""Deprecated hardware tests — skipped unless explicitly invoked.

Every test under ``test/hw/deprecated/`` has been superseded by the
declarative ``adidt.System`` hardware test pattern; see
:mod:`test.hw.test_ad9081_zcu102_system_hw` for the reference flow.

The tests are retained for historical reference and to make it
possible to compare behaviour against the prior ``BoardModel`` +
``XsaPipeline`` rendering paths.

By default pytest never collects this directory — the ``collect_ignore_glob``
below hides every ``test_*.py`` underneath it.  To run a specific
deprecated test for diagnostic purposes, invoke pytest with the explicit
path *and* set ``RUN_DEPRECATED_HW=1``::

    RUN_DEPRECATED_HW=1 pytest test/hw/deprecated/test_ad9081_board_model_hw.py
"""

from __future__ import annotations

import os
import warnings

if not os.environ.get("RUN_DEPRECATED_HW"):
    collect_ignore_glob = ["test_*.py", "xsa/test_*.py"]
else:
    warnings.warn(
        "Collecting tests under test/hw/deprecated/. These are superseded "
        "by test/hw/test_ad9081_zcu102_system_hw.py — prefer the System-API "
        "pattern for new hardware coverage.",
        DeprecationWarning,
        stacklevel=2,
    )
