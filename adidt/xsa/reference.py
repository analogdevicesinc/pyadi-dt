import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class RoleRequirement:
    role: str
    compatible: str
    label: str | None
    source_file: Path


@dataclass
class DriverManifest:
    roles: list[RoleRequirement] = field(default_factory=list)
    included_files: list[Path] = field(default_factory=list)


class ReferenceManifestExtractor:
    _include_re = re.compile(r'^\s*(?:#include|/include/)\s+[<"]([^">]+)[">]\s*$', re.M)
    _compatible_re = re.compile(
        r'(?P<label>[A-Za-z_][\w\-]*)?\s*:?[^{;\n]*\{[^}]*?compatible\s*=\s*(?P<value>[^;]+);',
        re.S,
    )
    _string_re = re.compile(r'"([^"]+)"')

    _ROLE_BY_PREFIX = {
        "adi,axi-jesd204-rx": "jesd_rx_link",
        "adi,axi-jesd204-tx": "jesd_tx_link",
        "adi,ad9081": "ad9081_core",
        "adi,hmc7044": "clock_chip",
        "adi,ad9528": "clock_chip",
        "adi,adrv9009": "adrv9009_phy",
        "adrv9009": "adrv9009_phy",
    }

    def extract(self, root_dts: Path) -> DriverManifest:
        root_dts = root_dts.resolve()
        if not root_dts.exists():
            raise FileNotFoundError(root_dts)

        manifest = DriverManifest()
        seen: set[Path] = set()
        self._walk(root_dts, seen, manifest)
        return manifest

    def _walk(self, path: Path, seen: set[Path], manifest: DriverManifest) -> None:
        path = path.resolve()
        if path in seen:
            return
        seen.add(path)
        manifest.included_files.append(path)

        text = path.read_text()

        for include in self._include_re.findall(text):
            inc = (path.parent / include).resolve()
            if inc.exists():
                self._walk(inc, seen, manifest)

        for match in self._compatible_re.finditer(text):
            compatibles = self._string_re.findall(match.group("value"))
            role, compatible = self._resolve_role(compatibles)
            if not role:
                continue
            manifest.roles.append(
                RoleRequirement(
                    role=role,
                    compatible=compatible,
                    label=match.group("label"),
                    source_file=path,
                )
            )

    def _resolve_role(self, compatibles: list[str]) -> tuple[str | None, str | None]:
        for compatible in compatibles:
            for prefix, role in self._ROLE_BY_PREFIX.items():
                if compatible.startswith(prefix):
                    return role, compatible
        return None, None

