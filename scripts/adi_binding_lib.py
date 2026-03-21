#!/usr/bin/env python3
"""Helpers for ADI binding discovery and auditing from Linux devicetree bindings."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import tempfile
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    yaml = None


_KNOWN_PREFIXES = {
    "adi,axi-jesd204-rx",
    "adi,axi-jesd204-tx",
    "adi,axi-jesd204-link",
}

_ADICOMPAT_TOKEN_RE = re.compile(r"adi,[A-Za-z0-9._+-]+")
_QUOTED_VALUE_RE = re.compile(r"[\"']([^\"']+)[\"']")
_YAML_COMPAT_KEY_RE = re.compile(r"^(?P<indent>[ \t]*)compatible[ \t]*:(?P<value>.*)$")
_TXT_LIST_ITEM_RE = re.compile(r"^\s*-\s*(?P<value>.+)$")
_TXT_COMPAT_KEY_RE = re.compile(r"^(?P<indent>[ \t]*)compatible[ \t]*:(?P<value>.*)$")
_TXT_PROPERTIES_HEADER_RE = re.compile(r"^\s*Properties\s*:?\s*$")
_TEMPLATE_COMPATIBLE_RE = re.compile(
    r"\bcompatible\s*=\s*['\"](?P<compatible>adi,[^'\"]+)['\"]"
)
_PART_COMPATIBLE_RE = re.compile(
    r"\bcompatible_id\s*=\s*['\"](?P<compatible>adi,[^'\"]+)['\"]"
)


@dataclass
class BindingRecord:
    source_file: str
    binding_name: str
    compatibles: list[str]
    kind: str
    source_hints: list[str] = field(default_factory=list)
    adi_properties: list[str] = field(default_factory=list)


@dataclass
class TemplateCandidate:
    compatible: str
    binding_name: str
    source_file: str
    source_kind: str
    board: str | None
    platform: str | None
    template_name: str | None
    output_path: str | None
    reference_dts: str | None
    status: str
    reason: str
    source_hints: list[str] = field(default_factory=list)


def _normalize(value: str) -> str:
    return value.strip().lower()


def _extract_adi_tokens(text: str) -> set[str]:
    values = set(_normalize(value) for value in _ADICOMPAT_TOKEN_RE.findall(text))
    for match in _QUOTED_VALUE_RE.finditer(text):
        quoted = _normalize(match.group(1))
        if quoted.startswith("adi,"):
            values.add(quoted)
    return {value for value in values if value.startswith("adi,")}


def _extract_filename_compatibles(path: Path) -> set[str]:
    return _extract_adi_tokens(path.name)


def _collect_yaml_compatibles_from_object(obj: object) -> set[str]:
    compatibles: set[str] = set()
    if isinstance(obj, str):
        return _extract_adi_tokens(obj)
    if isinstance(obj, list):
        for item in obj:
            compatibles.update(_collect_yaml_compatibles_from_object(item))
    elif isinstance(obj, dict):
        for key, value in obj.items():
            if key == "compatible":
                compatibles.update(_extract_adi_tokens(str(value)))
            compatibles.update(_collect_yaml_compatibles_from_object(value))
    return compatibles


def _collect_yaml_adi_properties(obj: object) -> set[str]:
    properties: set[str] = set()
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "properties":
                if isinstance(value, dict):
                    for prop in value:
                        if _normalize(prop).startswith("adi,"):
                            properties.add(_normalize(prop))
                continue
            properties.update(_collect_yaml_adi_properties(value))
    elif isinstance(obj, list):
        for item in obj:
            properties.update(_collect_yaml_adi_properties(item))
    return properties


def _collect_yaml_compatibles_from_text(text: str) -> set[str]:
    compatibles: set[str] = set()
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        match = _YAML_COMPAT_KEY_RE.match(lines[i])
        if not match:
            i += 1
            continue

        base_indent = len(match.group("indent"))
        value = match.group("value").strip()
        if value:
            compatibles.update(_extract_adi_tokens(value))
            if "[" in value and "]" not in value:
                i += 1
                while i < len(lines):
                    continuation = lines[i].strip()
                    compatibles.update(_extract_adi_tokens(continuation))
                    if "]" in continuation:
                        break
                    i += 1
            i += 1
            continue

        i += 1
        while i < len(lines):
            line = lines[i]
            line_indent = len(line) - len(line.lstrip(" "))
            if line_indent <= base_indent:
                break

            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                i += 1
                continue

            list_match = _TXT_LIST_ITEM_RE.match(line)
            if list_match:
                compatibles.update(_extract_adi_tokens(list_match.group("value")))
            else:
                compatibles.update(_extract_adi_tokens(stripped))
            i += 1
    return compatibles


def _parse_yaml_binding_file(path: Path, text: str) -> BindingRecord:
    compatibles: set[str] = set()
    properties: set[str] = set()
    source_hints: list[str] = ["yaml"]

    if yaml is not None:
        try:
            parsed = yaml.safe_load(text)
        except Exception:
            parsed = None
            source_hints.append("yaml-parse-error")
        else:
            if parsed is not None:
                compatibles.update(_collect_yaml_compatibles_from_object(parsed))
                properties.update(_collect_yaml_adi_properties(parsed))
                if compatibles:
                    source_hints.append("yaml-parser")

    if not compatibles:
        compatibles.update(_collect_yaml_compatibles_from_text(text))
        source_hints.append("text-heuristic")

    if not compatibles:
        compatibles.update(_extract_filename_compatibles(path))
        if compatibles:
            source_hints.append("filename")

    if not properties:
        properties.update(_extract_adi_tokens(text))
        if properties:
            source_hints.append("property-heuristic")

    return BindingRecord(
        source_file=str(path),
        binding_name=path.name,
        compatibles=sorted(compatibles),
        kind="yaml",
        source_hints=sorted(set(source_hints)),
        adi_properties=sorted(properties),
    )


def _parse_txt_binding_file(path: Path, text: str) -> BindingRecord:
    compatibles: set[str] = set()
    properties: set[str] = set()
    in_compat_list = False
    compat_indent = 0
    in_properties = False
    properties_indent = 0

    for line in text.splitlines():
        stripped_comment = line.split("#", 1)[0]
        if not stripped_comment.strip():
            if in_properties and not stripped_comment.startswith(" " * (properties_indent + 1)):
                in_properties = False
            if in_compat_list and not stripped_comment.startswith(" " * (compat_indent + 1)):
                in_compat_list = False
            continue

        compat_match = _TXT_COMPAT_KEY_RE.match(stripped_comment)
        if compat_match:
            in_compat_list = False
            compat_indent = len(compat_match.group("indent"))
            value = compat_match.group("value").strip()
            if value:
                compatibles.update(_extract_adi_tokens(value))
            else:
                in_compat_list = True
            continue

        if in_compat_list:
            if len(stripped_comment) - len(stripped_comment.lstrip(" ")) <= compat_indent:
                in_compat_list = False
            else:
                list_match = _TXT_LIST_ITEM_RE.match(stripped_comment)
                if list_match:
                    compatibles.update(_extract_adi_tokens(list_match.group("value")))
                else:
                    compatibles.update(_extract_adi_tokens(stripped_comment))
                continue

        if _TXT_PROPERTIES_HEADER_RE.match(stripped_comment):
            in_properties = True
            properties_indent = len(stripped_comment) - len(stripped_comment.lstrip(" "))
            continue

        if in_properties:
            current_indent = len(line) - len(line.lstrip(" "))
            if current_indent <= properties_indent:
                in_properties = False
            else:
                cleaned = stripped_comment
                if cleaned.startswith("-"):
                    cleaned = cleaned[1:].strip()
                properties.update(_extract_adi_tokens(cleaned))

    source_hints = ["txt"]
    if not compatibles:
        compatibles.update(_extract_filename_compatibles(path))
        if compatibles:
            source_hints.append("filename")
    if compatibles:
        source_hints.append("compatible-heuristic")
    if not properties:
        properties_from_text = _extract_adi_tokens(text)
        if properties_from_text:
            properties.update(properties_from_text)
            source_hints.append("property-heuristic")

    return BindingRecord(
        source_file=str(path),
        binding_name=path.name,
        compatibles=sorted(compatibles),
        kind="txt",
        source_hints=sorted(set(source_hints)),
        adi_properties=sorted(properties),
    )


def parse_adi_binding_file(path: Path) -> BindingRecord:
    text = path.read_text(errors="ignore")
    if path.suffix.lower() in {".yml", ".yaml"}:
        return _parse_yaml_binding_file(path, text)
    return _parse_txt_binding_file(path, text)


def discover_binding_files(
    linux_root: Path,
    include_yaml: bool = True,
    include_txt: bool = True,
) -> list[Path]:
    bindings_root = linux_root / "Documentation" / "devicetree" / "bindings"
    if not bindings_root.exists():
        raise FileNotFoundError(f"Missing bindings directory: {bindings_root}")

    paths: list[Path] = []
    if include_yaml:
        paths.extend(bindings_root.rglob("*.yaml"))
        paths.extend(bindings_root.rglob("*.yml"))
    if include_txt:
        paths.extend(bindings_root.rglob("*.txt"))

    return sorted({path for path in paths if path.is_file()}, key=lambda p: str(p))


def collect_bindings(
    linux_root: Path,
    include_yaml: bool = True,
    include_txt: bool = True,
    only_adi: bool = True,
) -> list[BindingRecord]:
    records: list[BindingRecord] = []
    for path in discover_binding_files(
        linux_root=linux_root,
        include_yaml=include_yaml,
        include_txt=include_txt,
    ):
        record = parse_adi_binding_file(path)
        if only_adi and not record.compatibles:
            continue
        records.append(record)
    return sorted(records, key=lambda item: item.source_file)


def _collect_compatibles_from_templates(template_root: Path) -> set[str]:
    compatibles: set[str] = set()
    if not template_root.exists():
        return compatibles

    for path in template_root.rglob("*.tmpl"):
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for match in _TEMPLATE_COMPATIBLE_RE.finditer(text):
            compatible = _normalize(match.group("compatible"))
            if compatible.startswith("adi,"):
                compatibles.add(compatible)
    return compatibles


def _collect_compatibles_from_parts(parts_root: Path) -> set[str]:
    compatibles: set[str] = set()
    if not parts_root.exists():
        return compatibles

    for path in parts_root.rglob("*.py"):
        try:
            text = path.read_text(errors="ignore")
        except OSError:
            continue
        for match in _PART_COMPATIBLE_RE.finditer(text):
            compatible = _normalize(match.group("compatible"))
            if compatible.startswith("adi,"):
                compatibles.add(compatible)
    return compatibles


def _collect_compatibles_from_json_files(project_root: Path) -> set[str]:
    compatibles: set[str] = set()
    profiles_root = project_root / "adidt" / "xsa" / "profiles"
    if not profiles_root.exists():
        return compatibles

    for path in profiles_root.rglob("*.json"):
        try:
            payload = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        compatibles.update(_extract_adi_tokens(json.dumps(payload)))
    return compatibles


def collect_supported_compatibles(project_root: Path) -> set[str]:
    template_root = project_root / "adidt" / "templates"
    parts_root = project_root / "adidt" / "parts"
    compatible_set = set(_KNOWN_PREFIXES)
    compatible_set.update(_collect_compatibles_from_templates(template_root))
    compatible_set.update(_collect_compatibles_from_parts(parts_root))
    compatible_set.update(_collect_compatibles_from_json_files(project_root))
    return {compatible for compatible in compatible_set if compatible.startswith("adi,")}


def collect_supported_prefixes(known_compatibles: set[str]) -> set[str]:
    prefixes = set(_KNOWN_PREFIXES)
    for compatible in known_compatibles:
        if "-" in compatible:
            prefixes.add(compatible.rsplit("-", 1)[0])
        if "." in compatible:
            prefixes.add(compatible.rsplit(".", 1)[0])
    return prefixes


def is_supported_compatible(
    candidate: str,
    known_compatibles: set[str],
    known_prefixes: set[str],
) -> bool:
    candidate = _normalize(candidate)
    if candidate in known_compatibles:
        return True
    for known in known_compatibles:
        if candidate.startswith(f"{known}-") or candidate.startswith(f"{known}."):
            return True
    for prefix in known_prefixes:
        if candidate == prefix or candidate.startswith(f"{prefix}-") or candidate.startswith(f"{prefix}."):
            return True
    if "-" in candidate and candidate.rsplit("-", 1)[0] in known_compatibles:
        return True
    if "." in candidate and candidate.rsplit(".", 1)[0] in known_compatibles:
        return True
    return False


def collect_supported_prefixes_for_audit(project_root: Path) -> set[str]:
    return collect_supported_prefixes(collect_supported_compatibles(project_root))


def _build_board_aliases(reference_targets: dict) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for board_name in reference_targets.get("boards", {}):
        normalized = _normalize(board_name)
        variants = {
            normalized,
            normalized.replace("_", ""),
            normalized.replace("-", ""),
            f"{normalized}_fmc",
            f"{normalized}-fmc",
            f"fmc{normalized}",
        }
        if normalized.startswith("daq"):
            variants.add(f"fmc{normalized}")
        for alias in variants:
            aliases[alias] = normalized
    return aliases


def load_reference_targets(path: Path | None) -> dict:
    if path is None or not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return payload


def _normalize_compatible_token(compatible: str) -> str:
    token = compatible.split(",", 1)[-1]
    token = token.split(".", 1)[0]
    token = token.split("-", 1)[0]
    return _normalize(token)


def derive_template_basename(
    compatible: str,
    binding_name: str,
    source_file: str,
    reference_targets: dict,
) -> tuple[str | None, str | None]:
    boards = reference_targets.get("boards", {})
    aliases = _build_board_aliases(reference_targets)
    candidate_tokens = [
        _normalize_compatible_token(compatible),
        _normalize(Path(binding_name).stem),
        _normalize(Path(source_file).stem),
    ]
    for token in candidate_tokens:
        for alias, board in aliases.items():
            if token == alias or token.startswith(f"{alias}_") or token.startswith(f"{alias}-"):
                if board in boards:
                    return board, None
        if token in boards:
            return token, None
    return None, "no board mapping found in reference_dts_targets.json"


def _derive_template_name(board: str, platform: str | None) -> str:
    return f"{board}_fmc_{platform}.tmpl" if platform else f"{board}.tmpl"


def _render_template_stub(
    candidate: TemplateCandidate,
    *,
    generated_at: str,
    linux_ref: str | None,
    base_includes: list[str],
    spi_bus: str,
    clock_reference: str,
) -> str:
    include_lines = "\n".join(f'#include "{include_name}"' for include_name in base_includes)
    if not include_lines:
        include_lines = "// TODO: add platform base include(s)"
    reference_line = candidate.reference_dts or "unknown"
    linux_ref_value = linux_ref or "local-checkout"
    platform_value = candidate.platform or "generic"
    return f"""// SPDX-License-Identifier: GPL-2.0
// AUTOGENERATED TEMPLATE STUB {generated_at}
/*
 * Starter template for {candidate.compatible}
 * Platform: {platform_value}
 * Generated from binding: {candidate.source_file}
 * Linux ref: {linux_ref_value}
 * Reference DTS: {reference_line}
 *
 * TODO:
 * - Replace placeholder nodes, clocks, GPIOs, and interrupts.
 * - Add the actual include list and board-specific wiring.
 * - Review child nodes and ADI properties against the binding YAML/TXT.
 */

{include_lines}

&{spi_bus} {{
    status = "okay";

    generated_device: device@0 {{
        compatible = "{candidate.compatible}";
        reg = <0>;
        spi-max-frequency = <1000000>;

        clocks = <&{clock_reference} 0>;
        clock-names = "ref_clk";

        /* TODO: add interrupts, GPIOs, and binding-specific child nodes. */
    }};
}};
"""


def collect_undocumented_bindings_for_templateing(
    audit_report: dict,
    reference_targets: dict,
    template_out_dir: Path,
) -> list[TemplateCandidate]:
    candidates: list[TemplateCandidate] = []
    seen: set[tuple[str, str | None, str | None]] = set()

    for group in ("partial_bindings", "undocumented_bindings"):
        for item in audit_report.get(group, []):
            for compatible in item.get("undocumented_compatibles", []):
                board, reason = derive_template_basename(
                    compatible=compatible,
                    binding_name=item["binding_name"],
                    source_file=item["source_file"],
                    reference_targets=reference_targets,
                )
                if not board:
                    key = (compatible, None, None)
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append(
                        TemplateCandidate(
                            compatible=compatible,
                            binding_name=item["binding_name"],
                            source_file=item["source_file"],
                            source_kind=item["kind"],
                            board=None,
                            platform=None,
                            template_name=None,
                            output_path=None,
                            reference_dts=None,
                            status="not_generated",
                            reason=reason or "unknown board mapping",
                            source_hints=item.get("source_hints", []),
                        )
                    )
                    continue

                board_entry = reference_targets.get("boards", {}).get(board, {})
                platforms = board_entry.get("platforms", {})
                if not platforms:
                    template_name = _derive_template_name(board, None)
                    key = (compatible, board, None)
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append(
                        TemplateCandidate(
                            compatible=compatible,
                            binding_name=item["binding_name"],
                            source_file=item["source_file"],
                            source_kind=item["kind"],
                            board=board,
                            platform=None,
                            template_name=template_name,
                            output_path=str((template_out_dir / template_name).resolve()),
                            reference_dts=None,
                            status="pending",
                            reason="generic board template",
                            source_hints=item.get("source_hints", []),
                        )
                    )
                    continue

                for platform_name, platform_data in sorted(platforms.items()):
                    template_name = platform_data.get("template") or _derive_template_name(
                        board,
                        platform_name,
                    )
                    key = (compatible, board, platform_name)
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append(
                        TemplateCandidate(
                            compatible=compatible,
                            binding_name=item["binding_name"],
                            source_file=item["source_file"],
                            source_kind=item["kind"],
                            board=board,
                            platform=platform_name,
                            template_name=template_name,
                            output_path=str((template_out_dir / template_name).resolve()),
                            reference_dts=platform_data.get("reference_dts"),
                            status="pending",
                            reason="mapped from reference targets",
                            source_hints=item.get("source_hints", []),
                        )
                    )
    return sorted(
        candidates,
        key=lambda item: (
            item.status,
            item.board or "",
            item.platform or "",
            item.compatible,
        ),
    )


def generate_template_artifacts(
    audit_report: dict,
    *,
    project_root: Path,
    template_out_dir: Path | None = None,
    reference_targets_path: Path | None = None,
    template_doc_out: Path | None = None,
    linux_ref: str | None = None,
    force: bool = False,
) -> dict:
    generated_at = datetime.now(tz=timezone.utc).isoformat(timespec="seconds")
    output_dir = (template_out_dir or (project_root / "adidt" / "templates" / "boards")).resolve()
    reference_targets = load_reference_targets(
        reference_targets_path
        or (project_root / "adidt" / "templates" / "reference_dts_targets.json")
    )
    candidates = collect_undocumented_bindings_for_templateing(
        audit_report=audit_report,
        reference_targets=reference_targets,
        template_out_dir=output_dir,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    generated: list[dict] = []
    skipped_existing: list[dict] = []
    not_generated: list[dict] = []
    by_board_platform: dict[tuple[str, str | None], list[TemplateCandidate]] = defaultdict(list)
    for candidate in candidates:
        if candidate.status != "pending" or not candidate.board:
            not_generated.append(asdict(candidate))
            continue
        by_board_platform[(candidate.board, candidate.platform)].append(candidate)

    boards = reference_targets.get("boards", {})
    for (board, platform), scoped_candidates in sorted(by_board_platform.items()):
        first = scoped_candidates[0]
        destination = Path(first.output_path) if first.output_path else None
        if destination is None or first.template_name is None:
            for candidate in scoped_candidates:
                candidate.status = "not_generated"
                candidate.reason = "missing template output path"
                not_generated.append(asdict(candidate))
            continue

        board_entry = boards.get(board, {})
        platform_entry = board_entry.get("platforms", {}).get(platform, {}) if platform else {}
        if destination.exists() and not force:
            for candidate in scoped_candidates:
                candidate.status = "skipped_existing"
                candidate.reason = "template already exists"
                skipped_existing.append(asdict(candidate))
            continue

        merged_compatibles = sorted({candidate.compatible for candidate in scoped_candidates})
        stub_compatible = merged_compatibles[0]
        stub_candidate = TemplateCandidate(
            compatible=stub_compatible,
            binding_name=first.binding_name,
            source_file=first.source_file,
            source_kind=first.source_kind,
            board=board,
            platform=platform,
            template_name=first.template_name,
            output_path=first.output_path,
            reference_dts=first.reference_dts,
            status="generated",
            reason=f"starter template for {len(merged_compatibles)} compatible(s)",
            source_hints=sorted({hint for item in scoped_candidates for hint in item.source_hints}),
        )
        content = _render_template_stub(
            stub_candidate,
            generated_at=generated_at,
            linux_ref=linux_ref,
            base_includes=platform_entry.get("base_includes", []),
            spi_bus=platform_entry.get("spi_bus", "spi0"),
            clock_reference=platform_entry.get("clock_reference", "clkc"),
        )
        compatible_comment = "".join(
            f"// compatible-covered: {compatible}\n" for compatible in merged_compatibles
        )
        destination.write_text(content.replace("\n\n&", f"\n\n{compatible_comment}\n&", 1), encoding="utf-8")
        for candidate in scoped_candidates:
            candidate.status = "generated"
            candidate.reason = f"generated into {first.template_name}"
            generated.append(asdict(candidate))

    template_report = {
        "generated_at": generated_at,
        "linux_root": audit_report.get("linux_root", ""),
        "template_out_dir": str(output_dir),
        "reference_targets_path": str(
            (
                reference_targets_path
                or (project_root / "adidt" / "templates" / "reference_dts_targets.json")
            ).resolve()
        ),
        "documentation_path": str(template_doc_out.resolve()) if template_doc_out else None,
        "generated_templates": generated,
        "skipped_existing_templates": skipped_existing,
        "not_generated_templates": not_generated,
        "summary": {
            "generated_templates": len(generated),
            "skipped_existing_templates": len(skipped_existing),
            "not_generated_templates": len(not_generated),
        },
    }
    return template_report


def audit_bindings(
    linux_root: Path,
    project_root: Path,
    include_yaml: bool = True,
    include_txt: bool = True,
    only_adi: bool = True,
) -> dict:
    known_compatibles = collect_supported_compatibles(project_root)
    known_prefixes = collect_supported_prefixes(known_compatibles)
    binding_records = collect_bindings(
        linux_root=linux_root,
        include_yaml=include_yaml,
        include_txt=include_txt,
        only_adi=only_adi,
    )

    known_bindings: list[dict] = []
    partial_bindings: list[dict] = []
    undocumented_bindings: list[dict] = []

    for record in binding_records:
        if not record.compatibles:
            continue

        unknown = [
            compatible
            for compatible in record.compatibles
            if not is_supported_compatible(
                compatible,
                known_compatibles,
                known_prefixes,
            )
        ]

        if not unknown:
            known_bindings.append(asdict(record))
            continue

        if len(unknown) == len(record.compatibles):
            undocumented_bindings.append(
                asdict(record) | {"undocumented_compatibles": unknown}
            )
            continue

        partial_bindings.append(
            asdict(record)
            | {
                "known_compatibles": [
                    compatible
                    for compatible in record.compatibles
                    if is_supported_compatible(
                        compatible,
                        known_compatibles,
                        known_prefixes,
                    )
                ],
                "undocumented_compatibles": unknown,
            }
        )

    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "linux_root": str(linux_root),
        "known_compatibles": sorted(known_compatibles),
        "known_prefixes": sorted(known_prefixes),
        "all_bindings": [asdict(record) for record in binding_records],
        "known_bindings": known_bindings,
        "partial_bindings": partial_bindings,
        "undocumented_bindings": undocumented_bindings,
        "summary": {
            "total_bindings": len(binding_records),
            "total_compatibles": sum(len(record.compatibles) for record in binding_records),
            "known_bindings": len(known_bindings),
            "partial_bindings": len(partial_bindings),
            "undocumented_bindings": len(undocumented_bindings),
            "undocumented_compatibles": sum(
                len(item["undocumented_compatibles"]) for item in partial_bindings + undocumented_bindings
            ),
        },
    }


def build_collection_report(records: list[BindingRecord], linux_root: Path) -> dict:
    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "linux_root": str(linux_root),
        "bindings": [asdict(record) for record in records],
        "summary": {
            "total_bindings": len(records),
            "total_compatibles": sum(len(record.compatibles) for record in records),
        },
    }


def render_markdown_summary(report: dict, kind: str) -> str:
    summary = report.get("summary", {})
    lines = [
        "# ADI Binding Collection Report"
        if kind == "collect"
        else "# ADI Binding Audit Report"
        if kind == "audit"
        else "# ADI Template Generation Report",
        "",
        f"- Source: {report.get('linux_root', 'n/a')}",
        f"- Generated: {report['generated_at']}",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Total bindings | {summary.get('total_bindings', 0)} |",
        f"| Total compatibles | {summary.get('total_compatibles', 0)} |",
        f"| Known bindings | {summary.get('known_bindings', 0)} |",
        f"| Partially known bindings | {summary.get('partial_bindings', 0)} |",
        f"| Undocumented bindings | {summary.get('undocumented_bindings', 0)} |",
        f"| Undocumented compatible entries | {summary.get('undocumented_compatibles', 0)} |",
        f"| Generated templates | {summary.get('generated_templates', 0)} |",
        f"| Skipped existing templates | {summary.get('skipped_existing_templates', 0)} |",
        f"| Not generated templates | {summary.get('not_generated_templates', 0)} |",
        "",
    ]

    if kind == "collect":
        lines.extend(
            [
                "## Parsed ADI bindings",
                "",
                "| Binding | Compatibles | Properties | Hints |",
                "| --- | --- | --- | --- |",
            ]
        )
        for item in report.get("bindings", []):
            lines.append(
                "| "
                + " | ".join(
                    [
                        Path(item["source_file"]).name,
                        ", ".join(item["compatibles"]),
                        ", ".join(item["adi_properties"]),
                        ", ".join(item["source_hints"]),
                    ]
                )
                + " |"
            )
        return "\n".join(lines)

    if kind == "template-audit":
        lines.extend(
            [
                "## Generated templates",
                "",
                "| Compatible | Template | Board | Platform | Reference DTS |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for item in report.get("generated_templates", []):
            lines.append(
                f"| {item['compatible']} | {item.get('template_name') or 'n/a'} | "
                f"{item.get('board') or 'n/a'} | {item.get('platform') or 'n/a'} | "
                f"{item.get('reference_dts') or 'n/a'} |"
            )
        lines.extend(
            [
                "",
                "## Skipped (already exists)",
                "",
                "| Compatible | Template | Reason |",
                "| --- | --- | --- |",
            ]
        )
        for item in report.get("skipped_existing_templates", []):
            lines.append(
                f"| {item['compatible']} | {item.get('template_name') or 'n/a'} | {item['reason']} |"
            )
        lines.extend(
            [
                "",
                "## Not generated (insufficient mapping)",
                "",
                "| Compatible | Binding | Reason |",
                "| --- | --- | --- |",
            ]
        )
        for item in report.get("not_generated_templates", []):
            lines.append(
                f"| {item['compatible']} | {Path(item['source_file']).name} | {item['reason']} |"
            )
        return "\n".join(lines)

    lines.extend(
        [
            "## Undocumented bindings",
            "",
            "| Binding | Undocumented compatibles |",
            "| --- | --- |",
        ]
    )
    for item in report.get("undocumented_bindings", []):
        lines.append(
            f"| {Path(item['source_file']).name} | {', '.join(item['undocumented_compatibles'])} |"
        )

    if report.get("partial_bindings"):
        lines.extend(
            [
                "",
                "## Partially known bindings",
                "",
                "| Binding | Known compatibles | Undocumented compatibles |",
                "| --- | --- | --- |",
            ]
        )
        for item in report.get("partial_bindings", []):
            lines.append(
                f"| {Path(item['source_file']).name} | "
                f"{', '.join(item.get('known_compatibles', []))} | "
                f"{', '.join(item.get('undocumented_compatibles', []))} |"
            )
    return "\n".join(lines)


def write_json(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, sort_keys=True)


def write_markdown(path: Path, report: dict, kind: str) -> None:
    path.write_text(render_markdown_summary(report, kind), encoding="utf-8")


def resolve_linux_source(
    linux_path: Path | None = None,
    linux_url: str | None = None,
    linux_ref: str | None = None,
) -> tuple[Path, Path | None]:
    if linux_path is not None:
        source = Path(linux_path).resolve()
        if not source.exists():
            raise FileNotFoundError(f"linux path does not exist: {source}")
        if not source.is_dir():
            raise ValueError(f"linux path is not a directory: {source}")
        return source, None

    if not linux_url:
        raise ValueError("Either --linux-path or --linux-url must be provided.")

    if shutil.which("git") is None:
        raise RuntimeError("git is required to clone linux URL sources.")

    temp_dir = Path(tempfile.mkdtemp(prefix="adi-linux-"))
    clone_command = ["git", "clone", "--depth", "1", linux_url, str(temp_dir)]
    if linux_ref:
        clone_command = [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            linux_ref,
            linux_url,
            str(temp_dir),
        ]
    subprocess.run(clone_command, check=True)
    return temp_dir, temp_dir
