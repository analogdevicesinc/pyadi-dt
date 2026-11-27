"""Derive a declarative design profile from a kernel reference device tree.

The kernel reference tree for an HDL design is the base board tree plus the
design's own nodes: the PL cores under an ``fpga-axi`` bus, the devices on
the PS SPI/I2C buses, and a few root-level clocks and regulators.  Seeding
separates the two by source file, then ties every PL node to the IP the XSA
has at that address.  The result is a profile that
:class:`~adidt.xsa.build.builders.declarative.DeclarativeBuilder` can render
on top of the sdtgen base tree, taking addresses and interrupts from the
XSA rather than from the reference.
"""

from __future__ import annotations

import re

# Fixed argv lists for git, tar and cpp; no shell and no untrusted input.
import subprocess  # nosec B404
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..parse.sdtgen import SdtgenRunner
from ..parse.topology import AxiIpInstance, XsaParser, XsaTopology
from .dts_source import DtsNode, DtsTree, parse_cells

# Root-level nodes that describe the system rather than the design.
_SYSTEM_ROOT_NODES = {"chosen", "aliases", "memory", "cpus"}
_MAX_CLOSURE_PASSES = 8


# What a reference DTS needs from a kernel checkout to preprocess.
KERNEL_DTS_PATHS = (
    "arch/arm/boot/dts/xilinx",
    "arch/arm64/boot/dts/xilinx",
    "arch/microblaze/boot/dts",
    # FMC-card files shared between carriers live one level up.
    ":(glob)arch/arm/boot/dts/*.dtsi",
    "include/dt-bindings",
    # dt-bindings/input/linux-event-codes.h is a symlink to this file.
    "include/uapi/linux/input-event-codes.h",
)


class SeedError(RuntimeError):
    """Raised when a reference tree cannot be turned into a profile."""


@dataclass
class SeedResult:
    """A seeded profile and what the seeder had to leave out or assume."""

    profile: dict[str, Any]
    notes: list[str] = field(default_factory=list)


def export_kernel_tree(linux: Path, commit: str, dest: Path) -> Path:
    """Extract the device-tree sources of kernel *commit* into *dest*."""
    archive = subprocess.run(  # nosec B603 B607
        ["git", "-C", str(linux), "archive", commit, *KERNEL_DTS_PATHS],
        capture_output=True,
        check=False,
    )
    if archive.returncode != 0:
        raise SeedError(
            f"cannot read {commit} from {linux}: "
            f"{archive.stderr.decode(errors='replace').strip()}"
        )
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(  # nosec B603 B607
        ["tar", "-x", "-C", str(dest)], input=archive.stdout, check=True
    )
    return dest


def preprocess(dts_path: Path, include_dirs: list[Path]) -> str:
    """Run the C preprocessor over *dts_path*, keeping line markers."""
    cmd = ["cpp", "-nostdinc", "-undef", "-D__DTS__", "-x", "assembler-with-cpp"]
    for directory in include_dirs:
        cmd += ["-I", str(directory)]
    proc = subprocess.run(  # nosec B603
        [*cmd, str(dts_path)], capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise SeedError(f"cpp failed for {dts_path.name}: {proc.stderr.strip()[:400]}")
    return proc.stdout


# Source files that describe the SoC or the carrier board, not the design
# on it.  Their nodes are only used when the design refers to them.
_CARRIER_FILE_RE = re.compile(
    r"^(?:"
    r"zynq-7000|zynq|zynqmp|zynqmp-clk-ccf|versal(?:-[\w.]+)?"
    r"|zynq(?:mp)?-(?:zc702|zc706|zed|coraz7s|microzed|zcu102|zcu104|kv260)"
    r"(?:-rev[\w.]+)?(?:-adv7511)?"
    r")\.dtsi?$"
)


def design_source_file(origin: str) -> bool:
    """Return True when the source file *origin* belongs to the HDL design.

    SoC and carrier-board files are shared by every design on a carrier;
    everything else (the design's own ``.dts`` and the ``adi-*.dtsi`` files
    for its FMC card) is design content.
    """
    return _CARRIER_FILE_RE.match(Path(origin).name) is None


def _copy(node: DtsNode) -> DtsNode:
    """Return a deep copy of *node* detached from its parent."""
    clone = DtsNode(name=node.name, labels=list(node.labels), origin=node.origin)
    clone.properties = dict(node.properties)
    for child in node.children:
        sub = _copy(child)
        sub.parent = clone
        clone.children.append(sub)
    return clone


def _body_lines(node: DtsNode) -> list[str]:
    """Return *node*'s contents (without its own header) as source lines."""
    lines = [prop.render("") for prop in node.properties.values()]
    for child in node.children:
        if lines:
            lines.append("")
        lines.extend(child.render("").split("\n"))
    return lines


class _Seeder:
    def __init__(
        self,
        reference: DtsTree,
        topology: XsaTopology,
        base: DtsTree,
        is_design: Callable[[str], bool],
        bound: bool = True,
    ) -> None:
        self.bound = bound
        self.ref = reference
        self.topology = topology
        self.base = base
        self.is_design = is_design
        self.notes: list[str] = []
        self.needed: set[int] = set()  # id() of base nodes a reference pulled in
        self.dropped_labels: set[str] = set()
        self.kept: list[DtsNode] = []  # PL nodes matched to an XSA IP
        self.overlays: list[tuple[str, DtsNode]] = []
        self.by_addr: dict[int, AxiIpInstance] = {}
        for inst in topology.ip_instances:
            self.by_addr.setdefault(inst.base_addr, inst)
        self.bus_nodes: list[DtsNode] = []  # PL-bus nodes with no register block
        self.shared_buses: set[int] = set()  # id() of buses the base tree has too
        # sdtgen and the kernel disagree on the ZynqMP GIC label.
        self.aliases: dict[str, str] = {}
        if "gic" not in base.labels:
            for label in ("gic_a53", "gic_a72"):
                if label in base.labels:
                    self.aliases["gic"] = label
                    break

    def _instance_at(self, addr: int | None) -> AxiIpInstance | None:
        """Return the IP whose register block contains *addr*.

        One core can back several nodes (an ``axi_ad9361`` holds the ADC
        core and, 0x4000 further on, the DAC core), so a node need not sit
        at the start of the block.
        """
        if addr is None:
            return None
        if addr in self.by_addr:
            return self.by_addr[addr]
        for inst in self.topology.ip_instances:
            if inst.base_addr <= addr < inst.base_addr + inst.size:
                return inst
        return None

    # -- classification -------------------------------------------------

    def _design(self, node: DtsNode) -> bool:
        return self.is_design(node.origin) or id(node) in self.needed

    def _in_base(self, node: DtsNode) -> bool:
        if any(self.aliases.get(l, l) in self.base.labels for l in node.labels):
            return True
        return self.base.node_at(node.path()) is not None

    def _target(self, node: DtsNode) -> str:
        for label in node.labels:
            label = self.aliases.get(label, label)
            if label in self.base.labels:
                return f"&{label}"
        return f"&{{{node.path()}}}"

    def _pl_buses(self) -> list[DtsNode]:
        """Return the buses holding the bitstream's cores.

        Found by what they contain, not by who wrote them: a root-level
        ``simple-bus`` the generated base lacks, with at least one child at
        the address of an IP in the XSA.  That also covers the carrier's own
        PL cores (HDMI, audio), which ship in carrier files.
        """
        buses = []
        for child in self.ref.root.children:
            if "simple-bus" not in child.compatible():
                continue
            if any(label in self.base.labels for label in child.labels):
                # MicroBlaze systems are all PL: carrier and design share the
                # one bus the base tree already has.
                if self.bound and any(
                    self._design(c) and c.unit_address in self.by_addr
                    for c in child.children
                ):
                    buses.append(child)
                    self.shared_buses.add(id(child))
                continue
            if not self.bound:
                # No XSA to compare with: the design's own bus is the one
                # the base tree does not already provide.
                if any(c.unit_address for c in child.children):
                    buses.append(child)
            elif any(c.unit_address in self.by_addr for c in child.children):
                buses.append(child)
        return buses

    # -- PL nodes -------------------------------------------------------

    def _pl_entries(self, buses: list[DtsNode]) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for bus in buses:
            addr_cells = (parse_cells(_value(bus, "#address-cells")) or [1])[0]
            size_cells = (parse_cells(_value(bus, "#size-cells")) or [1])[0]
            stride = addr_cells + size_cells
            for node in bus.children:
                if id(bus) in self.shared_buses and not self._design(node):
                    continue  # a carrier core: the base tree describes it
                cells = parse_cells(_value(node, "reg")) or []
                pairs = [
                    (
                        _join(cells[i : i + addr_cells]),
                        _join(cells[i + addr_cells : i + stride]),
                    )
                    for i in range(0, len(cells) - stride + 1, stride)
                ]
                addr = pairs[0][0] if pairs else node.unit_address
                inst = self._instance_at(addr)
                if not self.bound and pairs:
                    self.kept.append(node)
                    entries.append(self._unbound_entry(node, pairs))
                elif inst is not None:
                    self.kept.append(node)
                    entries.append(self._pl_entry(node, inst, pairs, addr))
                elif "reg" not in node.properties:
                    # A platform device (clock, IIO consumer) that merely
                    # lives on the bus; it has no IP to tie to.
                    self.kept.append(node)
                    self.bus_nodes.append(node)
                else:
                    self.notes.append(
                        f"dropped {node.name}: the XSA has no IP at {addr:#x}"
                    )
                    self.dropped_labels |= node.defined_labels()
        return entries

    def _unbound_entry(
        self, node: DtsNode, pairs: list[tuple[int, int]]
    ) -> dict[str, Any]:
        """Describe a PL node by address, for designs seeded without an XSA."""
        body = _copy(node)
        body.properties.pop("reg", None)
        return {
            "address": pairs[0][0],
            "labels": list(node.labels),
            "node": node.base_name,
            "reg": [[start - pairs[0][0], size] for start, size in pairs],
            "body": _body_lines(body),
        }

    def _pl_entry(
        self,
        node: DtsNode,
        inst: AxiIpInstance,
        pairs: list[tuple[int, int]],
        addr: int,
    ) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "instance": inst.name,
            "ip_type": inst.ip_type,
            "labels": list(node.labels),
            "node": node.base_name,
        }
        if addr != inst.base_addr:
            entry["offset"] = addr - inst.base_addr
        body = _copy(node)
        if pairs:
            body.properties.pop("reg", None)
            entry["reg"] = [[start - inst.base_addr, size] for start, size in pairs]
        irq = parse_cells(_value(node, "interrupts"))
        if irq is not None:
            gic = len(irq) == 3 and irq[0] == 0
            if (gic or len(irq) == 2) and inst.irq is not None:
                # The XSA is the authority on how this bitstream is wired.
                body.properties.pop("interrupts", None)
                entry["interrupt_flags"] = irq[-1]
                if not gic:
                    entry["interrupt_cells"] = 2  # <line flags> of an axi_intc
                if inst.irq != irq[-2]:
                    self.notes.append(
                        f"{node.name}: reference interrupt {irq[-2]} differs from "
                        f"the XSA's {inst.irq} for {inst.name}; the XSA value is used"
                    )
            else:
                self.notes.append(
                    f"{node.name}: kept reference interrupts {irq} "
                    f"(XSA reports {inst.irq} for {inst.name})"
                )
        entry["body"] = _body_lines(body)
        return entry

    # -- everything outside the PL bus ----------------------------------

    def _prune(self, node: DtsNode, exists: bool) -> tuple[DtsNode, bool]:
        """Return the part of base node *node* the generated tree must add."""
        clone = DtsNode(name=node.name, labels=list(node.labels))
        has_design = False
        for name, prop in node.properties.items():
            if self.is_design(prop.origin):
                clone.properties[name] = prop
                has_design = True
            elif not exists:
                # The generated base lacks this node, so it is created whole.
                clone.properties[name] = prop
        for child in node.children:
            if self._design(child):
                clone.children.append(_copy(child))
                has_design = True
                continue
            child_exists = exists and self._in_base(child)
            sub, sub_design = self._prune(child, child_exists)
            if not sub_design:
                continue
            if child_exists and any(
                self.aliases.get(l, l) in self.base.labels for l in child.labels
            ):
                self.overlays.append((self._target(child), sub))
            else:
                if not child_exists:
                    self.notes.append(
                        f"created {child.path()}: the generated base tree "
                        "does not have it"
                    )
                clone.children.append(sub)
                has_design = True
        return clone, has_design

    def _collect(
        self, buses: list[DtsNode]
    ) -> tuple[list[DtsNode], list[tuple[str, DtsNode]]]:
        self.overlays = []
        root_nodes: list[DtsNode] = []
        for child in self.ref.root.children:
            if id(child) in self.shared_buses:
                # Design edits to the carrier's own cores (``&axi_intc``...).
                for core in child.children:
                    if self._design(core):
                        continue
                    sub, has_design = self._prune(core, True)
                    if has_design:
                        self.overlays.append((self._target(core), sub))
                continue
            if child in buses:
                continue
            if child.base_name in _SYSTEM_ROOT_NODES:
                continue
            if self._design(child):
                root_nodes.append(_copy(child))
                continue
            exists = self._in_base(child)
            sub, has_design = self._prune(child, exists)
            if not has_design:
                continue
            if exists:
                self.overlays.append((self._target(child), sub))
            else:
                self.notes.append(
                    f"created {child.path()}: the generated base tree does not have it"
                )
                root_nodes.append(sub)
        return root_nodes, self.overlays

    # -- driver ---------------------------------------------------------

    def run(self) -> dict[str, Any]:
        buses = self._pl_buses()
        if not buses:
            self.notes.append("reference tree has no PL bus matching the XSA")
        pl = self._pl_entries(buses)
        pl_labels = {label for entry in pl for label in entry["labels"]}
        bus_labels = {label for bus in buses for label in bus.labels}

        root_nodes: list[DtsNode] = []
        overlays: list[tuple[str, DtsNode]] = []
        unresolved: set[str] = set()
        for _ in range(_MAX_CLOSURE_PASSES):
            root_nodes, overlays = self._collect(buses)
            emitted = [*root_nodes, *(node for _, node in overlays)]
            defined = set(self.base.labels) | pl_labels | set(self.aliases)
            refs: set[str] = set()
            for node in emitted:
                defined |= node.defined_labels()
                refs |= node.references()
            for node in self.kept:
                defined |= node.defined_labels()
                refs |= node.references()
            missing = refs - defined
            grew = False
            unresolved = set()
            for label in sorted(missing):
                target = self.ref.labels.get(label)
                if (
                    target is None
                    or label in self.dropped_labels
                    or label in bus_labels
                    or target is self.ref.root
                ):
                    unresolved.add(label)
                elif id(target) not in self.needed:
                    self.needed.add(id(target))
                    self.notes.append(
                        f"pulled in {target.path()}: referenced as &{label}"
                    )
                    grew = True
            if not grew:
                break
        for label in sorted(unresolved):
            self.notes.append(f"unresolved reference &{label}")

        design = {
            "pl": pl,
            "bus": [node.render("").split("\n") for node in self.bus_nodes],
            "root": [
                line for node in root_nodes for line in node.render("").split("\n")
            ],
            "overlays": [
                {"target": target, "body": _body_lines(node)}
                for target, node in overlays
            ],
            "unresolved": sorted(unresolved),
        }
        return self._apply_aliases(design)

    def _apply_aliases(self, value: Any) -> Any:
        """Rewrite references to labels the generated base spells differently."""
        if not self.aliases:
            return value
        if isinstance(value, str):
            for old, new in self.aliases.items():
                value = re.sub(rf"&{old}\b", f"&{new}", value)
            return value
        if isinstance(value, list):
            return [self._apply_aliases(item) for item in value]
        if isinstance(value, dict):
            return {key: self._apply_aliases(item) for key, item in value.items()}
        return value


def _value(node: DtsNode, name: str) -> str | None:
    prop = node.properties.get(name)
    return prop.value if prop is not None else None


def _join(cells: list[int]) -> int:
    value = 0
    for cell in cells:
        value = (value << 32) | cell
    return value


def seed_design(
    reference: DtsTree,
    topology: XsaTopology | None,
    base: DtsTree,
    *,
    is_design: Callable[[str], bool] = design_source_file,
) -> SeedResult:
    """Turn a parsed reference tree into the ``design`` section of a profile.

    Args:
        reference: The kernel reference tree, preprocessed with line markers.
        topology: The XSA the profile is for.  ``None`` seeds without one:
            PL nodes are then keyed by address, keep the reference's
            interrupts, and are bound to an IP only when a tree is built.
        base: The sdtgen base tree generated from the same XSA; it decides
            which labels the profile may refer to without defining them.
        is_design: Tells design source files from carrier/SoC ones.

    Returns:
        The ``design`` mapping (without identity fields) and the seeder's
        notes about anything dropped, created or left unresolved.
    """
    seeder = _Seeder(
        reference,
        topology if topology is not None else XsaTopology(),
        base,
        is_design,
        bound=topology is not None,
    )
    design = seeder.run()
    return SeedResult(profile=design, notes=list(dict.fromkeys(seeder.notes)))


def kernel_include_dirs(kernel_tree: Path, reference_dts: Path) -> list[Path]:
    """Return the include search path for a reference DTS inside *kernel_tree*."""
    return [
        kernel_tree / "include",
        reference_dts.parent,
        kernel_tree / "arch/arm/boot/dts",
        kernel_tree / "arch/arm64/boot/dts",
    ]


def seed_profile_for_xsa(
    xsa_path: Path,
    reference_dts: Path,
    kernel_tree: Path,
    work_dir: Path,
    *,
    sdtgen_timeout: int = 300,
) -> tuple[SeedResult, XsaTopology]:
    """Seed a design section for *xsa_path* from *reference_dts*.

    Runs sdtgen on the XSA (into ``work_dir/base``) so the seeder knows which
    labels the generated base tree offers, then parses both trees.

    Returns:
        The seed result and the parsed topology (whose HDL identity names
        the profile).
    """
    base_dir = work_dir / "base"
    base_dir.mkdir(parents=True, exist_ok=True)
    base_dts = base_dir / "system-top.dts"
    if not base_dts.exists():  # sdtgen is slow; reuse a finished run
        base_dts = SdtgenRunner().run(xsa_path, base_dir, timeout=sdtgen_timeout)
    base = DtsTree.parse(
        preprocess(base_dts, [base_dir, base_dir / "include"]), str(base_dts)
    )
    reference = DtsTree.parse(
        preprocess(reference_dts, kernel_include_dirs(kernel_tree, reference_dts)),
        str(reference_dts),
    )
    topology = XsaParser().parse(xsa_path)
    return seed_design(reference, topology, base), topology


def seed_profile_without_xsa(
    reference_dts: Path, kernel_tree: Path, base_dts: Path
) -> SeedResult:
    """Seed a design section from *reference_dts* when no XSA is released.

    *base_dts* is an sdtgen base tree of another design on the same carrier;
    it stands in for the labels the generated base will offer.  Nothing in
    the result has been checked against a bitstream.
    """
    base = DtsTree.parse(
        preprocess(base_dts, [base_dts.parent, base_dts.parent / "include"]),
        str(base_dts),
    )
    reference = DtsTree.parse(
        preprocess(reference_dts, kernel_include_dirs(kernel_tree, reference_dts)),
        str(reference_dts),
    )
    return seed_design(reference, None, base)
