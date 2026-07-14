"""Output directory + manifest accumulator (schema v2).

Layout on disk:
  <out>/
    junit.xml                    # pytest writes this
    manifest.json                # written by finalize()
    run_meta.json                # written by finalize()
    session/<hook_name>/...      # session-hook outputs (Task 8 wires these)
    cases/<safe_id>/<kind>/<filename>
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]")
_MAX_SAFE_ID_LEN = 200
SCHEMA_VERSION = 2


def _safe_test_id(nodeid: str) -> str:
    sanitized = _UNSAFE.sub("_", nodeid) or "case"
    if len(sanitized) > _MAX_SAFE_ID_LEN:
        digest = hashlib.blake2b(nodeid.encode(), digest_size=4).hexdigest()
        head_len = _MAX_SAFE_ID_LEN - len(digest) - 1
        sanitized = sanitized[:head_len] + "_" + digest
    return sanitized


@dataclass
class _CaseEntry:
    case_nodeid: str
    artifacts: list[dict[str, Any]] = field(default_factory=list)


class OutputDir:
    """On-disk layout owner. Single-writer; not thread-safe."""

    def __init__(self, root: Path):
        self.root = Path(root)
        self._run_artifacts: list[dict[str, Any]] = []
        self._cases: dict[str, _CaseEntry] = {}
        self._initialized = False

    def initialize(self) -> None:
        if self.root.exists():
            children = list(self.root.iterdir())
            if children:
                sys.stderr.write(
                    f"pytest-prism: refusing to write to non-empty dir "
                    f"{self.root}; pass a fresh path or remove it\n"
                )
                raise SystemExit(4)
        else:
            self.root.mkdir(parents=True)
        (self.root / "cases").mkdir(exist_ok=True)
        (self.root / "session").mkdir(exist_ok=True)
        self._initialized = True

    def session_dir(self, hook_name: str) -> Path:
        d = self.root / "session" / hook_name
        d.mkdir(parents=True, exist_ok=True)
        return d

    def write_run_artifact(self, filename: str, content: bytes, *, kind: str) -> None:
        if not self._initialized:
            raise RuntimeError("OutputDir.initialize() must be called first")
        path = self.root / filename
        path.write_bytes(content)
        self._run_artifacts.append(
            {
                "filename": filename,
                "kind": kind,
                "size": len(content),
            }
        )

    def write_case_artifact(
        self,
        *,
        case_nodeid: str,
        filename: str,
        content: bytes,
        kind: str,
    ) -> None:
        if not self._initialized:
            raise RuntimeError("OutputDir.initialize() must be called first")
        safe = _safe_test_id(case_nodeid)
        case_kind_dir = self.root / "cases" / safe / kind
        case_kind_dir.mkdir(parents=True, exist_ok=True)
        (case_kind_dir / filename).write_bytes(content)
        entry = self._cases.setdefault(case_nodeid, _CaseEntry(case_nodeid))
        entry.artifacts.append(
            {
                "filename": filename,
                "kind": kind,
                "size": len(content),
                "rel_path": f"cases/{safe}/{kind}/{filename}",
            }
        )

    def record_case_artifact(
        self,
        *,
        case_nodeid: str,
        filename: str,
        kind: str,
        size: int | None = None,
    ) -> None:
        """Register a file the renderer wrote directly into the case dir.

        Use this when the renderer has already written the file (so we avoid
        a double-write); the manifest still gets the entry. Size is read from
        disk if not provided.
        """
        if not self._initialized:
            raise RuntimeError("OutputDir.initialize() must be called first")
        safe = _safe_test_id(case_nodeid)
        if size is None:
            size = (self.root / "cases" / safe / kind / filename).stat().st_size
        entry = self._cases.setdefault(case_nodeid, _CaseEntry(case_nodeid))
        entry.artifacts.append(
            {
                "filename": filename,
                "kind": kind,
                "size": size,
                "rel_path": f"cases/{safe}/{kind}/{filename}",
            }
        )

    def case_kind_dir(self, *, case_nodeid: str, kind: str) -> Path:
        """Return (and ensure) the per-case-per-kind directory."""
        safe = _safe_test_id(case_nodeid)
        d = self.root / "cases" / safe / kind
        d.mkdir(parents=True, exist_ok=True)
        return d

    def finalize(self, *, run_meta: dict[str, Any]) -> dict[str, Any]:
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "run_meta": run_meta,
            "run_artifacts": list(self._run_artifacts),
            "cases": [
                {"case_nodeid": e.case_nodeid, "artifacts": list(e.artifacts)}
                for e in self._cases.values()
            ],
        }
        (self.root / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )
        (self.root / "run_meta.json").write_text(
            json.dumps(run_meta, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        return manifest
