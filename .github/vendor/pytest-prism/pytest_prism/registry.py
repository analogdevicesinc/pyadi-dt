"""Entry-point discovery and dispatch tables for renderers and session hooks."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from importlib.metadata import EntryPoint, entry_points

from pytest_prism.api import Renderer, SessionHook

_LOG = logging.getLogger("pytest_prism.registry")

RENDERER_GROUP = "pytest_prism.renderers"
SESSION_HOOK_GROUP = "pytest_prism.session_hooks"


class RegistryError(RuntimeError):
    """Raised on kind-collision (always) or import-failure (strict mode only)."""


@dataclass(frozen=True)
class Registry:
    renderers: dict[str, Renderer] = field(default_factory=dict)
    session_hooks: dict[str, SessionHook] = field(default_factory=dict)


def _discover_entry_points() -> list[EntryPoint]:
    """All entry points in our two groups. Split out for test patching."""
    eps = entry_points()
    out: list[EntryPoint] = []
    out.extend(eps.select(group=RENDERER_GROUP))
    out.extend(eps.select(group=SESSION_HOOK_GROUP))
    return list(out)


def _instantiate(ep: EntryPoint, *, strict: bool) -> object | None:
    try:
        cls: type[object] = ep.load()
    except Exception as exc:
        msg = f"pytest-prism: entry point {ep.group}/{ep.name} failed to import: {exc}"
        if strict:
            raise RegistryError(msg) from exc
        _LOG.warning(msg)
        return None
    try:
        return cls()
    except Exception as exc:
        msg = f"pytest-prism: entry point {ep.group}/{ep.name} failed to instantiate: {exc}"
        if strict:
            raise RegistryError(msg) from exc
        _LOG.warning(msg)
        return None


def load_registry(*, strict: bool = False) -> Registry:
    """Discover entry points and build dispatch tables."""
    renderers: dict[str, Renderer] = {}
    hooks: dict[str, SessionHook] = {}
    for ep in _discover_entry_points():
        instance = _instantiate(ep, strict=strict)
        if instance is None:
            continue
        if ep.group == RENDERER_GROUP:
            kind = getattr(instance, "payload_kind", ep.name)
            if kind in renderers:
                raise RegistryError(
                    f"pytest-prism: duplicate renderer kind {kind!r} "
                    f"(entry points {ep.group}/{ep.name} collides with another)"
                )
            if isinstance(instance, Renderer):
                renderers[kind] = instance
        elif ep.group == SESSION_HOOK_GROUP:
            name = getattr(instance, "name", ep.name)
            if name in hooks:
                raise RegistryError(
                    f"pytest-prism: duplicate session hook name {name!r} "
                    f"(entry points {ep.group}/{ep.name} collides with another)"
                )
            if isinstance(instance, SessionHook):
                hooks[name] = instance
    return Registry(renderers=renderers, session_hooks=hooks)
