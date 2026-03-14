import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .reference import DriverManifest


@dataclass
class RoleCoverage:
    role: str
    compatible: str
    found: bool
    label: str | None = None


@dataclass
class ParityReport:
    total_roles: int
    matched_roles: int
    missing_roles: list[str] = field(default_factory=list)
    items: list[RoleCoverage] = field(default_factory=list)


def check_manifest_against_dts(manifest: DriverManifest, merged_dts: str) -> ParityReport:
    items: list[RoleCoverage] = []
    missing_roles: list[str] = []

    for req in manifest.roles:
        found = req.compatible in merged_dts
        items.append(
            RoleCoverage(
                role=req.role,
                compatible=req.compatible,
                found=found,
                label=req.label,
            )
        )
        if not found and req.role not in missing_roles:
            missing_roles.append(req.role)

    matched_roles = len({item.role for item in items if item.found})
    total_roles = len({item.role for item in items})
    return ParityReport(
        total_roles=total_roles,
        matched_roles=matched_roles,
        missing_roles=missing_roles,
        items=items,
    )


def write_parity_reports(report: ParityReport, output_dir: Path, name: str) -> tuple[Path, Path]:
    map_path = output_dir / f"{name}.map.json"
    coverage_path = output_dir / f"{name}.coverage.md"

    map_path.write_text(
        json.dumps(
            {
                "total_roles": report.total_roles,
                "matched_roles": report.matched_roles,
                "missing_roles": report.missing_roles,
                "items": [asdict(item) for item in report.items],
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
        f"- Missing roles: {', '.join(report.missing_roles) if report.missing_roles else 'none'}",
        "",
        "| Role | Compatible | Found |",
        "| --- | --- | --- |",
    ]
    for item in report.items:
        lines.append(
            f"| {item.role} | `{item.compatible}` | {'yes' if item.found else 'no'} |"
        )
    coverage_path.write_text("\n".join(lines) + "\n")

    return map_path, coverage_path

