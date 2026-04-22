"""``adidtc jif`` — apply pyadi-jif solver output to a device tree.

The ``jif`` group currently exposes one subcommand, ``clock``, which
updates the per-channel divider properties on the clock chip described
in the loaded DT.  The solver JSON may be in either of two shapes:

- ``out_dividers``: ``list[int]`` — positional per channel index.  This
  matches the pyadi-jif solver output directly.
- ``channels``: ``dict[str, dict]`` — per-channel overrides keyed by
  channel index as a string (e.g. ``{"2": {"divider": 4}}``).

If both are present, ``channels`` wins.  Writing live ``remote_sysfs``
is not yet supported by :meth:`adidt.dt.update_current_dt`; use
``local_file`` (edit a local DTB) or ``remote_sd`` (edit the board's SD
card) instead.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

import adidt


_DEFAULT_COMPATIBLES = ["adi,hmc7044", "adi,ad9523-1", "adi,ad9528"]
_SUPPORTED_CONTEXTS = {"local_file", "remote_sd"}


def _find_clock_node(d: "adidt.dt", compatible: str | None) -> Any:
    """Locate the clock chip node; raise if not found."""
    if compatible:
        nodes = d.get_node_by_compatible(compatible)
        if not nodes:
            raise click.ClickException(
                f"No node found with compatible {compatible!r}"
            )
        return nodes[0]

    for candidate in _DEFAULT_COMPATIBLES:
        nodes = d.get_node_by_compatible(candidate)
        if nodes:
            return nodes[0]
    raise click.ClickException(
        "No clock chip found; pass --compatible to select one. "
        f"Tried: {', '.join(_DEFAULT_COMPATIBLES)}"
    )


def _channel_subnodes(parent_node: Any) -> dict[int, Any]:
    """Return ``{channel_reg: node}`` for each child node with a ``reg``."""
    result: dict[int, Any] = {}
    for child in parent_node.nodes:
        reg = child.get_property("reg")
        if reg is None:
            continue
        try:
            # fdt prop value is either an int or a list of ints
            val = reg.value if not isinstance(reg.value, list) else reg.value[0]
            result[int(val)] = child
        except (TypeError, ValueError):
            continue
    return result


def _updates_from_cfg(cfg: dict) -> dict[int, int]:
    """Normalize cfg into a ``{channel: divider}`` dict."""
    updates: dict[int, int] = {}
    for idx, divider in enumerate(cfg.get("out_dividers", []) or []):
        updates[idx] = int(divider)
    for ch_str, entry in (cfg.get("channels") or {}).items():
        if "divider" in entry:
            updates[int(ch_str)] = int(entry["divider"])
    return updates


def _set_divider(node: Any, prop_name: str, value: int) -> None:
    """Set an integer property on an fdt node, replacing any existing value."""
    import fdt

    existing = node.get_property(prop_name)
    if existing is not None:
        node.remove_property(prop_name)
    node.append(fdt.PropWords(prop_name, value))


def register(cli_group: click.Group) -> None:
    """Register the ``jif`` group on the given top-level CLI group."""

    @cli_group.group("jif")
    @click.pass_context
    def jif(ctx: click.Context) -> None:
        """Apply pyadi-jif solver output to a device tree."""

    @jif.command("clock")
    @click.option(
        "--file",
        "-f",
        "solver_file",
        required=True,
        type=click.Path(exists=True, dir_okay=False),
        help="pyadi-jif solver output JSON.",
    )
    @click.option(
        "--compatible",
        default=None,
        help=(
            "Compatible string of the clock chip to update (e.g. "
            "'adi,hmc7044').  Auto-detected when omitted."
        ),
    )
    @click.option(
        "--property",
        "-p",
        "property_name",
        default="adi,divider",
        show_default=True,
        help="Per-channel divider property name.",
    )
    @click.option(
        "--reboot",
        "-r",
        is_flag=True,
        help="Reboot the board after a successful remote_sd write.",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Print the planned property changes without writing the DT.",
    )
    @click.pass_context
    def jif_clock(
        ctx: click.Context,
        solver_file: str,
        compatible: str | None,
        property_name: str,
        reboot: bool,
        dry_run: bool,
    ) -> None:
        """Update clock-chip channel dividers from a pyadi-jif solver JSON.

        \b
        Examples:
          Edit a local DTB in place:
            adidtc -c local_file -f devicetree.dtb -a arm64 jif clock \
                -f solved.json
        \b
          Edit the remote board's SD card and reboot:
            adidtc -c remote_sd -i 192.168.2.1 jif clock \
                -f solved.json --reboot
        """
        context = ctx.obj["context"]
        if context not in _SUPPORTED_CONTEXTS:
            raise click.UsageError(
                f"jif clock requires --context in {sorted(_SUPPORTED_CONTEXTS)}; "
                f"got {context!r}.  remote_sysfs write-back is not supported."
            )

        cfg = json.loads(Path(solver_file).read_text())
        clock_block = cfg.get("clock", cfg)  # tolerate nested or flat form
        updates = _updates_from_cfg(clock_block)
        if not updates:
            raise click.UsageError(
                "No 'out_dividers' or 'channels' entries in solver JSON."
            )

        d = adidt.dt(
            dt_source=context,
            ip=ctx.obj["ip"],
            username=ctx.obj["username"],
            password=ctx.obj["password"],
            arch=ctx.obj["arch"],
            local_dt_filepath=ctx.obj["filepath"],
        )

        node = _find_clock_node(d, compatible)
        channels = _channel_subnodes(node)
        applied: list[str] = []
        missing: list[int] = []
        for ch, divider in sorted(updates.items()):
            child = channels.get(ch)
            if child is None:
                missing.append(ch)
                continue
            if not dry_run:
                _set_divider(child, property_name, divider)
            applied.append(f"channel {ch}: {property_name} = {divider}")

        for line in applied:
            click.echo(line)
        if missing:
            click.echo(
                f"warning: no channel subnodes for indices {missing}", err=True
            )

        if dry_run:
            click.echo("dry-run: no changes written.")
            return

        d.update_current_dt(reboot=reboot)
        click.echo(f"Updated device tree via {context}.")
