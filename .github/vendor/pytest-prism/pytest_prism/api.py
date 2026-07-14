"""Public API for pytest-prism.

Consumer-facing surface: `attach()`, `Renderer`, `SessionHook`, `RenderContext`,
`SessionContext`, `RenderResult`. Everything else in this package is internal.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar, Protocol, runtime_checkable

import pytest

# Stash key used by the plugin to read payloads attached during test execution.
# Module-private; tests should use the public `attach()` function.
_PRISM_PAYLOADS_STASH = pytest.StashKey[list[tuple[str, Mapping[str, Any]]]]()


@dataclass(frozen=True)
class RenderResult:
    """What a Renderer returns. Files are paths relative to RenderContext.case_dir."""

    files: list[Path] = field(default_factory=list)
    metrics: Mapping[str, float] = field(default_factory=dict)
    primary_artifact: str | None = None


@dataclass(frozen=True)
class RenderContext:
    case_dir: Path
    case_id: str
    logger: logging.Logger


@dataclass(frozen=True)
class SessionContext:
    run_dir: Path
    hook_dir: Path
    config: Any  # pytest_prism.config.Config; avoid import cycle
    logger: logging.Logger


@runtime_checkable
class Renderer(Protocol):
    payload_kind: ClassVar[str]

    def render(self, payload: Mapping[str, Any], ctx: RenderContext) -> RenderResult: ...


@runtime_checkable
class SessionHook(Protocol):
    name: ClassVar[str]

    def session_pre(self, ctx: SessionContext) -> Mapping[str, Any]: ...
    def session_post(self, ctx: SessionContext) -> Mapping[str, Any]: ...


def record_measurement(
    name: str,
    value: float,
    *,
    unit: str | None = None,
    spec_min: float | None = None,
    spec_max: float | None = None,
) -> None:
    """Record a numeric measurement on the current test.

    Writes the value (and optional unit / spec limits) into the test's JUnit
    ``<properties>`` using the convention Prism's ingest understands
    (``{name}``, ``{name}__unit``, ``{name}__min``, ``{name}__max``). Prism
    turns these into first-class Measurement rows with pass/fail margins.

    No-op when called outside a running test. Must be called during the test
    body (not in ``makereport``), so the values are captured before pytest
    serialises the JUnit report.
    """
    item = _current_item()
    if item is None:
        return
    props: list[tuple[str, object]] = item.user_properties
    props.append((name, value))
    if unit is not None:
        props.append((f"{name}__unit", unit))
    if spec_min is not None:
        props.append((f"{name}__min", spec_min))
    if spec_max is not None:
        props.append((f"{name}__max", spec_max))


def attach(kind: str, payload: Mapping[str, Any]) -> None:
    """Attach a payload to the current pytest item.

    The plugin reads attached payloads in `pytest_runtest_makereport` and
    dispatches to the matching renderer. May be called multiple times per test
    with different `kind`s; each renders independently.
    """
    item = _current_item()
    if item is None:
        # Called outside a test (e.g., session fixture). Silently no-op rather
        # than raise — caller may not have control over execution context.
        return
    payloads = item.stash.get(_PRISM_PAYLOADS_STASH, None)
    if payloads is None:
        payloads = []
        item.stash[_PRISM_PAYLOADS_STASH] = payloads
    # Defensive copy so callers can mutate their payload without affecting the renderer.
    payloads.append((kind, dict(payload)))


def _current_item() -> pytest.Item | None:
    """Walk up the stack to find the active pytest Item. Returns None if not in a test."""
    import inspect

    frame = inspect.currentframe()
    try:
        while frame is not None:
            for var in frame.f_locals.values():
                if isinstance(var, pytest.Item):
                    return var
            frame = frame.f_back
    finally:
        del frame
    return None


__all__ = [
    "RenderContext",
    "RenderResult",
    "Renderer",
    "SessionContext",
    "SessionHook",
    "attach",
    "record_measurement",
]
