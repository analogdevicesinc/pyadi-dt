"""Pytest configuration shared across the overlay-lifecycle tests.

Each per-board ``test_*_overlay.py`` declares a ``SPEC`` constant
(a :class:`~test.hw.xsa._overlay_spec.BoardOverlayProfile` instance).
The collection hook below reads ``SPEC.lg_features`` at collection
time and applies ``@pytest.mark.lg_feature(...)`` to every test in the
module — so the per-board labgrid place feature gate stays a single
declaration in the SPEC instead of a decorator on every test function.

``tryfirst=True`` is critical: labgrid's pytest plugin filters tests
by ``lg_feature`` marker during collection, so this hook must run
*before* labgrid's filtering pass.  Without the marker, labgrid would
either run every test against every place or skip every test
unconditionally (depending on env), defeating the per-place isolation.
"""

from __future__ import annotations

import pytest


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(config, items):
    for item in items:
        spec = getattr(item.module, "SPEC", None)
        if spec is None:
            continue
        features = getattr(spec, "lg_features", None)
        if not features:
            continue
        item.add_marker(pytest.mark.lg_feature(list(features)))


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "lg_feature(features): labgrid place feature gate"
    )
