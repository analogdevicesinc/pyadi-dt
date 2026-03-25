"""Board-level fixups for sdtgen-generated base DTS files.

sdtgen produces a base DTS from the XSA hardware description, but some
boards require post-generation corrections that cannot be derived from the
XSA alone (e.g. external PHY configuration, board-specific node naming).

Each fixup function operates on the ``pl.dtsi`` file inside the sdtgen
``base_dir`` and is keyed to a profile name so it only runs for the
matching hardware combination.
"""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Registry: profile name -> list of fixup callables
_FIXUP_REGISTRY: dict[str, list] = {}


def register_fixup(profile: str):
    """Decorator to register a fixup function for a given profile name."""

    def decorator(fn):
        _FIXUP_REGISTRY.setdefault(profile, []).append(fn)
        return fn

    return decorator


def apply_board_fixups(profile: str | None, base_dir: Path) -> None:
    """Apply all registered board fixups for the given profile.

    Args:
        profile: The active profile name (e.g. ``"ad9084_vcu118"``).
            When ``None``, no fixups are applied.
        base_dir: The sdtgen output directory containing ``pl.dtsi``.
    """
    if profile is None:
        return

    fixups = _FIXUP_REGISTRY.get(profile, [])
    if not fixups:
        return

    pl_dtsi = base_dir / "pl.dtsi"
    if not pl_dtsi.exists():
        logger.warning("board_fixups: %s not found, skipping fixups", pl_dtsi)
        return

    content = pl_dtsi.read_text()

    for fn in fixups:
        content = fn(content, pl_dtsi)

    pl_dtsi.write_text(content)
    logger.info("Applied %d board fixup(s) for profile '%s'", len(fixups), profile)


# ---------------------------------------------------------------------------
# VCU118 Ethernet fixups
# ---------------------------------------------------------------------------


@register_fixup("ad9084_vcu118")
def _fix_vcu118_ethernet(content: str, pl_dtsi: Path) -> str:
    """Fix Ethernet bindings in sdtgen-generated pl.dtsi for VCU118.

    sdtgen generates several incorrect/incomplete properties for the AXI
    Ethernet node compared to the working vcu118.dtsi reference:

    1. PHY address: sdtgen reports internal PCS at MDIO addr 1 via
       pcs-handle; VCU118 has an external TI DP83867 at MDIO addr 3.
    2. Missing clocks property: AXI Ethernet requires
       ``clocks = <&clk_bus_0>`` for the AXI bus clock.
    3. ``managed = "in-band-status"``: sdtgen adds this but the reference
       DTS uses standard PHY polling.
    4. interrupt-names mismatch: sdtgen lists DMA interrupt names that
       belong to the DMA node, not the Ethernet node.
    """
    # 1. Fix pcs-handle -> phy-handle pointing to external PHY label
    content = content.replace(
        "pcs-handle = <&axi_ethernet_0phy1>;",
        "phy-handle = <&phy1>;",
    )

    # 2. Remove managed = "in-band-status" (standard PHY polling is correct)
    content = content.replace(
        '\t\t\tmanaged = "in-band-status";\n',
        "",
    )

    # 3. Fix interrupt-names: drop the DMA interrupt names (wrong node)
    content = content.replace(
        'interrupt-names = "interrupt" , "mm2s_introut" , "s2mm_introut";',
        'interrupt-names = "interrupt";',
    )

    # 4. Add missing clocks property after the reg line of the Ethernet node
    eth_reg_line = "\t\t\treg = <0x40c00000 0x40000>;"
    clocks_line = "\t\t\tclocks = <&clk_bus_0>;"
    eth_clocks_anchor = eth_reg_line + "\n" + clocks_line
    if eth_reg_line in content and eth_clocks_anchor not in content:
        content = content.replace(
            eth_reg_line,
            eth_clocks_anchor,
        )

    # 5. Replace minimal sdtgen PHY stub (address 1) with real DP83867
    old_mdio = (
        "\t\t\taxi_ethernet_0_mdio: mdio {\n"
        "\t\t\t\t#address-cells = <1>;\n"
        "\t\t\t\t#size-cells = <0>;\n"
        "\t\t\t\taxi_ethernet_0phy1: phy@1 {\n"
        "\t\t\t\t\tdevice_type = \"ethernet-phy\";\n"
        "\t\t\t\t\treg = <1>;\n"
        "\t\t\t\t};\n"
        "\t\t\t};"
    )
    new_mdio = (
        "\t\t\taxi_ethernet_0_mdio: mdio {\n"
        "\t\t\t\t#address-cells = <1>;\n"
        "\t\t\t\t#size-cells = <0>;\n"
        "\t\t\t\tphy1: phy@3 {\n"
        "\t\t\t\t\treg = <3>;\n"
        "\t\t\t\t\tdevice_type = \"ethernet-phy\";\n"
        "\t\t\t\t\tti,sgmii-ref-clock-output-enable;\n"
        "\t\t\t\t\tti,dp83867-rxctrl-strap-quirk;\n"
        "\t\t\t\t\tti,rx-internal-delay = <0x8>;\n"
        "\t\t\t\t\tti,tx-internal-delay = <0xa>;\n"
        "\t\t\t\t\tti,fifo-depth = <0x1>;\n"
        "\t\t\t\t};\n"
        "\t\t\t};"
    )
    if old_mdio in content:
        content = content.replace(old_mdio, new_mdio)
        logger.info("Applied VCU118 Ethernet PHY fix to %s", pl_dtsi)
    else:
        logger.warning(
            "VCU118 Ethernet PHY fix — pattern not found in %s", pl_dtsi
        )

    return content


# ---------------------------------------------------------------------------
# VCU118 IIO node name fixups
# ---------------------------------------------------------------------------


@register_fixup("ad9084_vcu118")
def _fix_vcu118_iio_names(content: str, pl_dtsi: Path) -> str:
    """Rename sdtgen TPL node names to match ADI reference naming.

    sdtgen uses generic Xilinx IP names (``ad_ip_jesd204_tpl_adc`` /
    ``_dac``) for the JESD204 TPL cores.  The Linux IIO driver sets
    ``indio_dev->name`` from the OF node name, so pyadi-iio expects the
    ADI reference naming convention.
    """
    renames = [
        ("ad_ip_jesd204_tpl_adc@44a10000", "axi-ad9084-rx-hpc@44a10000"),
        ("ad_ip_jesd204_tpl_adc@44ab0000", "axi-ad9084b-rx-b@44ab0000"),
        ("ad_ip_jesd204_tpl_dac@44b10000", "axi-ad9084-tx-hpc@44b10000"),
        ("ad_ip_jesd204_tpl_dac@44bb0000", "axi-ad9084b-tx-b@44bb0000"),
    ]

    applied = []
    for old, new in renames:
        if old in content:
            content = content.replace(old, new)
            applied.append(f"{old} -> {new}")

    if applied:
        logger.info(
            "Applied VCU118 IIO name fixes to %s: %s",
            pl_dtsi,
            "; ".join(applied),
        )

    return content
