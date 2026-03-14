import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .reference import DriverManifest


_NODE_BLOCK_RE = re.compile(
    r'(?P<label>[A-Za-z_][\w\-]*)\s*:[^{;\n]+\{(?P<body>.*?)\};', re.S
)


def _node_bodies_by_label(dts: str) -> dict[str, str]:
    return {m.group("label"): m.group("body") for m in _NODE_BLOCK_RE.finditer(dts)}


def _normalize_property_value(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _pct(matched: int, total: int) -> float:
    if total <= 0:
        return 100.0
    return round((matched / total) * 100.0, 1)


@dataclass
class RoleCoverage:
    role: str
    compatible: str
    found: bool
    label: str | None = None


@dataclass
class LinkCoverage:
    source_label: str
    property_name: str
    target_label: str
    found: bool


@dataclass
class PropertyCoverage:
    source_label: str
    property_name: str
    expected_value: str
    found: bool


@dataclass
class ParityReport:
    total_roles: int
    matched_roles: int
    total_links: int = 0
    matched_links: int = 0
    total_properties: int = 0
    matched_properties: int = 0
    missing_roles: list[str] = field(default_factory=list)
    missing_links: list[str] = field(default_factory=list)
    missing_properties: list[str] = field(default_factory=list)
    mismatched_properties: list[str] = field(default_factory=list)
    items: list[RoleCoverage] = field(default_factory=list)
    link_items: list[LinkCoverage] = field(default_factory=list)
    property_items: list[PropertyCoverage] = field(default_factory=list)


def check_manifest_against_dts(manifest: DriverManifest, merged_dts: str) -> ParityReport:
    items: list[RoleCoverage] = []
    missing_roles: list[str] = []
    node_bodies = _node_bodies_by_label(merged_dts)

    for req in manifest.roles:
        if req.label:
            body = node_bodies.get(req.label, "")
            found = req.compatible in body
        else:
            found = req.compatible in merged_dts
        items.append(
            RoleCoverage(
                role=req.role,
                compatible=req.compatible,
                found=found,
                label=req.label,
            )
        )
        if not found:
            missing_id = req.role if not req.label else f"{req.role}:{req.label}"
            missing_roles.append(missing_id)

    link_items: list[LinkCoverage] = []
    missing_links: list[str] = []
    for req in manifest.links:
        body = node_bodies.get(req.source_label, "")
        pattern = rf"{re.escape(req.property_name)}\s*=\s*[^;]*&{re.escape(req.target_label)}\\b"
        found = re.search(pattern, body) is not None
        link_items.append(
            LinkCoverage(
                source_label=req.source_label,
                property_name=req.property_name,
                target_label=req.target_label,
                found=found,
            )
        )
        if not found:
            missing_links.append(
                f"{req.source_label}.{req.property_name}->{req.target_label}"
            )

    property_items: list[PropertyCoverage] = []
    missing_properties: list[str] = []
    mismatched_properties: list[str] = []
    for req in manifest.properties:
        body = node_bodies.get(req.source_label, "")
        pattern = rf"{re.escape(req.property_name)}\s*=\s*(?P<value>[^;]+);"
        match = re.search(pattern, body)
        if not match:
            found = False
            actual_value = None
        else:
            actual_value = match.group("value").strip()
            found = (
                _normalize_property_value(actual_value)
                == _normalize_property_value(req.expected_value)
            )
        property_items.append(
            PropertyCoverage(
                source_label=req.source_label,
                property_name=req.property_name,
                expected_value=req.expected_value,
                found=found,
            )
        )
        if not found:
            if actual_value is None:
                missing_properties.append(
                    f"{req.source_label}.{req.property_name}={req.expected_value}"
                )
            else:
                mismatched_properties.append(
                    f"{req.source_label}.{req.property_name}: expected {req.expected_value}, got {actual_value}"
                )

    matched_roles = sum(1 for item in items if item.found)
    total_roles = len(items)
    total_links = len(manifest.links)
    matched_links = sum(1 for item in link_items if item.found)
    total_properties = len(manifest.properties)
    matched_properties = sum(1 for item in property_items if item.found)
    return ParityReport(
        total_roles=total_roles,
        matched_roles=matched_roles,
        total_links=total_links,
        matched_links=matched_links,
        total_properties=total_properties,
        matched_properties=matched_properties,
        missing_roles=sorted(set(missing_roles)),
        missing_links=sorted(set(missing_links)),
        missing_properties=sorted(set(missing_properties)),
        mismatched_properties=sorted(set(mismatched_properties)),
        items=items,
        link_items=link_items,
        property_items=property_items,
    )


def write_parity_reports(report: ParityReport, output_dir: Path, name: str) -> tuple[Path, Path]:
    map_path = output_dir / f"{name}.map.json"
    coverage_path = output_dir / f"{name}.coverage.md"

    missing_roles = sorted(report.missing_roles)
    missing_links = sorted(report.missing_links)
    missing_properties = sorted(report.missing_properties)
    mismatched_properties = sorted(report.mismatched_properties)
    roles_pct = _pct(report.matched_roles, report.total_roles)
    links_pct = _pct(report.matched_links, report.total_links)
    properties_pct = _pct(report.matched_properties, report.total_properties)

    map_path.write_text(
        json.dumps(
            {
                "total_roles": report.total_roles,
                "matched_roles": report.matched_roles,
                "total_links": report.total_links,
                "matched_links": report.matched_links,
                "total_properties": report.total_properties,
                "matched_properties": report.matched_properties,
                "missing_roles": missing_roles,
                "missing_links": missing_links,
                "missing_properties": missing_properties,
                "mismatched_properties": mismatched_properties,
                "coverage": {
                    "roles_pct": roles_pct,
                    "links_pct": links_pct,
                    "properties_pct": properties_pct,
                },
                "items": [asdict(item) for item in report.items],
                "link_items": [asdict(item) for item in report.link_items],
                "property_items": [asdict(item) for item in report.property_items],
            },
            indent=2,
        )
        + "\n"
    )

    lines = [
        "# Manifest Coverage",
        "",
        f"- Total roles: {report.total_roles}",
        f"- Matched roles: {report.matched_roles}",
        f"- Total links: {report.total_links}",
        f"- Matched links: {report.matched_links}",
        f"- Total properties: {report.total_properties}",
        f"- Matched properties: {report.matched_properties}",
        f"- Role coverage: {roles_pct}%",
        f"- Link coverage: {links_pct}%",
        f"- Property coverage: {properties_pct}%",
        f"- Missing roles: {', '.join(missing_roles) if missing_roles else 'none'}",
        f"- Missing links: {', '.join(missing_links) if missing_links else 'none'}",
        f"- Missing properties: {', '.join(missing_properties) if missing_properties else 'none'}",
        f"- Mismatched properties: {', '.join(mismatched_properties) if mismatched_properties else 'none'}",
        "",
        "| Role | Compatible | Found |",
        "| --- | --- | --- |",
    ]
    for item in report.items:
        lines.append(
            f"| {item.role} | `{item.compatible}` | {'yes' if item.found else 'no'} |"
        )

    lines.extend(
        [
            "",
            "| Source | Property | Target | Found |",
            "| --- | --- | --- | --- |",
        ]
    )
    for item in report.link_items:
        lines.append(
            f"| {item.source_label} | `{item.property_name}` | `{item.target_label}` | {'yes' if item.found else 'no'} |"
        )

    lines.extend(
        [
            "",
            "| Source | Property | Found |",
            "| --- | --- | --- |",
        ]
    )
    for item in report.property_items:
        lines.append(
            f"| {item.source_label} | `{item.property_name} = {item.expected_value}` | {'yes' if item.found else 'no'} |"
        )
    coverage_path.write_text("\n".join(lines) + "\n")

    return map_path, coverage_path
