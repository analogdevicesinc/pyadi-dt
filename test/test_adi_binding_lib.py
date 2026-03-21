"""Tests for ADI Linux binding discovery and support audit helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from adi_binding_lib import (  # noqa: E402
    BindingRecord,
    audit_bindings,
    collect_bindings,
    collect_supported_compatibles,
    collect_supported_prefixes,
    discover_binding_files,
    is_supported_compatible,
    parse_adi_binding_file,
    _ADICOMPAT_TOKEN_RE,
)


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def test_parse_yaml_and_txt_binding_records(tmp_path: Path) -> None:
    linux_root = tmp_path / "linux"
    yaml_path = linux_root / "Documentation/devicetree/bindings/adi/test.yaml"
    txt_path = linux_root / "Documentation/devicetree/bindings/adi/test.txt"

    _write(
        yaml_path,
        """
title: Example ADI compatible binding
description: used in parser tests
compatible:
  - "adi,axi-ad9081-rx-1.0"
  - "adi,axi-ad9081-tx-1.0"
properties:
  adi,jesd-phy: {}
  adi,sysref-mode: {}
""",
    )
    _write(
        txt_path,
        """
Properties:
  - adi,axi-hsci-link

Compatible:
  - adi,axi-ad9081-rx-1.0
""",
    )

    yaml_record = parse_adi_binding_file(yaml_path)
    txt_record = parse_adi_binding_file(txt_path)

    assert isinstance(yaml_record, BindingRecord)
    assert yaml_record.compatibles == [
        "adi,axi-ad9081-rx-1.0",
        "adi,axi-ad9081-tx-1.0",
    ]
    assert yaml_record.adi_properties == ["adi,jesd-phy", "adi,sysref-mode"]

    assert txt_record.compatibles == ["adi,axi-ad9081-rx-1.0"]
    assert txt_record.adi_properties == ["adi,axi-hsci-link"]


def test_discover_and_collect_bindings(tmp_path: Path) -> None:
    linux_root = tmp_path / "linux"
    _write(
        linux_root / "Documentation/devicetree/bindings/adi/a.yaml",
        """
title: yaml
compatible: adi,axi-ad9081-rx-1.0
""",
    )
    _write(
        linux_root / "Documentation/devicetree/bindings/adi/b.txt",
        """
compatible: adi,ad9528
Properties:
  - adi,vcxo-frequency
""",
    )
    _write(
        linux_root / "Documentation/devicetree/bindings/adi/ignore.txt",
        """
This file has no compatible string.
""",
    )

    discovered = discover_binding_files(linux_root=linux_root, include_yaml=True, include_txt=True)
    assert len(discovered) == 3

    records = collect_bindings(linux_root=linux_root)
    assert len(records) == 2
    assert any(record.binding_name == "a.yaml" for record in records)
    assert any(record.binding_name == "b.txt" for record in records)
    assert all(isinstance(record, BindingRecord) for record in records)


def test_supported_compatibles_and_prefixes_and_audit(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    linux_root = project_root / "linux"
    template_root = project_root / "adidt/templates"
    parts_root = project_root / "adidt/parts"
    profiles_root = project_root / "adidt/xsa/profiles"

    _write(
        template_root / "boards/sample.tmpl",
        """
compatible = "adi,known-tx-1.0";
""",
    )
    _write(
        parts_root / "chip.py",
        "compatible_id = \"adi,known-rx-1.0\"",
    )
    _write(
        profiles_root / "sample.json",
        json.dumps({"board": "example", "defaults": {"adi,profile": true}}),
    )

    _write(
        linux_root / "Documentation/devicetree/bindings/adi/known.yaml",
        "compatible: adi,known-rx-1.0\n",
    )
    _write(
        linux_root / "Documentation/devicetree/bindings/adi/partial.yaml",
        "compatible: adi,known-tx-2.0\n",
    )
    _write(
        linux_root / "Documentation/devicetree/bindings/adi/unknown.yaml",
        "compatible: adi,unknown-device-1.0\n",
    )

    known = collect_supported_compatibles(project_root)
    assert "adi,known-tx-1.0" in known
    assert "adi,known-rx-1.0" in known
    assert any(token.startswith("adi,") for token in known)

    prefixes = collect_supported_prefixes(known)
    assert "adi,known-tx" in prefixes
    assert "adi,known-rx" in prefixes

    report = audit_bindings(
        linux_root=linux_root,
        project_root=project_root,
        include_yaml=True,
        include_txt=False,
        only_adi=True,
    )

    assert report["summary"]["total_bindings"] == 3
    assert report["summary"]["known_bindings"] == 2
    assert report["summary"]["undocumented_bindings"] == 1
    assert report["summary"]["partial_bindings"] == 0

    parsed = collect_bindings(
        linux_root=linux_root,
        include_yaml=True,
        include_txt=False,
        only_adi=False,
    )
    assert len(parsed) == 3

    compatible = "adi,known-rx-1.0"
    assert is_supported_compatible(
        compatible,
        known_compatibles=known,
        known_prefixes=prefixes,
    )
    assert not is_supported_compatible(
        "adi,unknown-device-1.0",
        known_compatibles=known,
        known_prefixes=prefixes,
    )
    assert _ADICOMPAT_TOKEN_RE.search("adi,axi-sample-1.0")
