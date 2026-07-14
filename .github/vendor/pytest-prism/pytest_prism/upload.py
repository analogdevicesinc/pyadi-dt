"""Upload a finalized OutputDir to a Prism instance.

Delegates the multipart construction to `PrismClient.upload_run`, then polls
until ingest is ready. Local export is left on disk on any failure for
offline retry.
"""

from __future__ import annotations

import io
import json as _json
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import defusedxml.ElementTree as ET

from pytest_prism.client import PrismClient
from pytest_prism.config import Config
from pytest_prism.manifest import OutputDir


class UploadError(RuntimeError):
    """Any failure during login, multipart POST, or polling."""


@dataclass(frozen=True)
class RunResult:
    run_id: str
    status: str
    url: str


def _suite_name_from_junit(junit_xml: bytes) -> str:
    try:
        root = ET.fromstring(junit_xml)
    except ET.ParseError:
        return "pytest"
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is not None and suite.get("name"):
        return suite.get("name") or "pytest"
    return "pytest"


def _build_artifacts_zip(out_root: Path) -> bytes:
    """Build the archive for Prism ingest.

    The pytest-prism v2 layout is `cases/<safe_id>/<kind>/<filename>`. Prism
    parses each archive entry's basename as `{suite}__{case}__{label}.{ext}`
    to attach it to the right case. We rewrite each per-case entry's archive
    name on the fly using:
      - suite name from <testsuite name=""> in junit.xml
      - case name from manifest entry's case_nodeid (the part after "::")
      - kind prefix on the label so different kinds don't clash on filename
    Run-level and session-level artifacts keep bare/prefixed names.
    """
    buf = io.BytesIO()
    manifest_path = out_root / "manifest.json"
    junit_path = out_root / "junit.xml"
    suite_name = (
        _suite_name_from_junit(junit_path.read_bytes()) if junit_path.exists() else "pytest"
    )

    case_dir_to_name: dict[str, str] = {}
    if manifest_path.exists():
        manifest = _json.loads(manifest_path.read_text())
        for case in manifest.get("cases", []):
            nodeid = case.get("case_nodeid", "")
            artifacts = case.get("artifacts", [])
            if not artifacts:
                continue
            sample_rel = artifacts[0].get("rel_path", "")
            parts = sample_rel.split("/")
            if len(parts) >= 2 and parts[0] == "cases":
                safe_id = parts[1]
                case_name = nodeid.rsplit("::", 1)[-1] if "::" in nodeid else nodeid
                case_dir_to_name[safe_id] = case_name

    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in out_root.rglob("*"):
            if not p.is_file():
                continue
            if p.name == "junit.xml":
                continue
            rel = p.relative_to(out_root)
            parts = rel.parts
            if len(parts) >= 4 and parts[0] == "cases":
                # cases/<safe_id>/<kind>/<filename>
                safe_id, kind, filename = parts[1], parts[2], parts[-1]
                case_name = case_dir_to_name.get(safe_id)
                if case_name is None:
                    arcname = f"{kind}__{filename}"
                else:
                    arcname = f"{suite_name}__{case_name}__{kind}__{filename}"
            elif len(parts) >= 3 and parts[0] == "session":
                # session/<hook_name>/<filename> — prefix with hook_name so
                # multiple hooks with same filename don't collide.
                hook_name, filename = parts[1], parts[-1]
                arcname = f"{hook_name}__{filename}"
            else:
                arcname = parts[-1]
            zf.writestr(arcname, p.read_bytes())
    return buf.getvalue()


def upload(
    out_dir: OutputDir, cfg: Config, *, poll_timeout_s: float = 60.0, poll_interval_s: float = 1.0
) -> RunResult:
    if not cfg.upload_url:
        raise UploadError("upload() called with no upload_url")
    if not cfg.upload_token and not (cfg.upload_email and cfg.upload_password):
        raise UploadError("upload() needs an API token or an email + password")
    if not cfg.upload_project:
        raise UploadError("upload() called with no upload_project")
    junit_bytes = (out_dir.root / "junit.xml").read_bytes()
    archive_bytes = _build_artifacts_zip(out_dir.root)

    client = PrismClient(cfg.upload_url, token=cfg.upload_token)
    if not cfg.upload_token:
        try:
            client.login(cfg.upload_email or "", cfg.upload_password or "")
        except Exception as exc:
            raise UploadError(f"login failed: {exc}") from exc

    try:
        result = client.upload_run(
            project_slug=cfg.upload_project,
            run_name=cfg.run_name,
            junit_xml=junit_bytes,
            archive_zip=archive_bytes,
            tags=dict(cfg.user_tags),
        )
    except RuntimeError as exc:
        raise UploadError(f"run create failed: {exc}") from exc

    run_id = result.get("id")
    if not run_id:
        raise UploadError(f"missing run id in response: {result!r}")

    deadline = time.monotonic() + poll_timeout_s
    status = result.get("status", "pending")
    url = result.get("url", f"/runs/{run_id}")
    while status not in ("ready", "failed") and time.monotonic() < deadline:
        time.sleep(poll_interval_s)
        code, resp = client._request("GET", f"/api/v1/runs/{run_id}")
        if code == 200:
            data = _json.loads(resp)
            status = data.get("status", status)
            url = data.get("url", url)
    return RunResult(run_id=run_id, status=status, url=url)
