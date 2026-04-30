"""AD9081 + ZCU102: XSA → Device Tree overlay generation.

Pipeline
--------
1. Parse ``system_top.xsa`` with :class:`~adidt.xsa.parse.topology.XsaParser`.
2. Patch the topology with the correct hardware values (the ZCU102 HWH uses
   a slightly older Vivado schema, so base addresses, lane count, and IRQ are
   recovered from the parameter block rather than the elements the parser
   normally reads).
3. Use :mod:`adijif` to look up the JESD204B quick-configuration mode for the
   AD9081 operating at M=8, L=4, S=1, Np=16 – yielding F=4, K=32.
4. Feed the topology + config into :class:`~adidt.xsa.build.node_builder.NodeBuilder`
   to render the ADI DTS nodes, then write a ``.dtso`` overlay file.

Usage::

    # install the optional xsa dependency group first
    pip install "adidt[xsa]"

    # adijif must also be available (pyadi-jif)
    pip install pyadi-jif[cplex]   # or [gekko]

    python examples/xsa/ad9081_zcu102_xsa_parse.py
"""

import warnings
from pathlib import Path

import adijif as jif

from adidt.xsa.merge.merger import DtsMerger
from adidt.xsa.build.node_builder import NodeBuilder
from adidt.xsa.parse.topology import ClkgenInstance, Jesd204Instance, XsaParser

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
HERE = Path(__file__).parent
XSA = HERE / "system_top.xsa"
OUT_DIR = HERE / "output"

# HMC7044 output channel numbers that feed the FPGA device clocks.
# These match the ZCU102 reference design clock tree.
HMC_RX_CHANNEL = 12
HMC_TX_CHANNEL = 13


# ---------------------------------------------------------------------------
# Step 1 – Parse the XSA
# ---------------------------------------------------------------------------


def parse_xsa(xsa_path: Path):
    """Return topology, patching values the parser cannot read from this HWH."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        topology = XsaParser().parse(xsa_path)

    if caught:
        print("Parser warnings:")
        for w in caught:
            print(f"  [{w.category.__name__}] {w.message}")
        print()

    # Print all nodes
    print("All nodes:")
    from pprint import pprint

    pprint(topology)
    for node in topology.nodes:
        print(node)
    print()

    # The ZCU102 Vivado 2023.2 HWH uses a different schema from the parser's
    # primary fixture:
    #
    #   * Part info: stored in <SYSTEMINFO DEVICE="..." PACKAGE="..."/>
    #     (attribute) instead of a <DEVICE> child element.
    #   * Lane count: parameter name is NUM_LANES, not C_NUM_LANES.
    #   * Base addresses: stored as C_BASEADDR parameters, not MEMRANGE elements.
    #   * IRQ: port is named "irq", not "interrupt".
    #
    # Patch the known hardware values so the downstream pipeline is accurate.
    topology.fpga_part = "xczu9eg-ffvb1156-2"

    # Patch RX JESD204 instance
    rx = topology.jesd204_rx[0]
    topology.jesd204_rx[0] = Jesd204Instance(
        name=rx.name,
        base_addr=0x84A90000,
        num_lanes=4,
        irq=54,
        link_clk=rx.link_clk,
        direction="rx",
    )

    # Patch TX JESD204 instance
    tx = topology.jesd204_tx[0]
    topology.jesd204_tx[0] = Jesd204Instance(
        name=tx.name,
        base_addr=0x84B90000,
        num_lanes=4,
        irq=55,
        link_clk=tx.link_clk,
        direction="tx",
    )

    # The HMC7044 drives the device clocks externally (no axi_clkgen in this
    # design). Register a synthetic ClkgenInstance so NodeBuilder can resolve
    # the clock net to a label for the DTS "clocks" property.
    topology.clkgens.append(
        ClkgenInstance(
            name="hmc7044_car",
            base_addr=0,
            output_clks=[
                topology.jesd204_rx[0].link_clk,
                topology.jesd204_tx[0].link_clk,
            ],
        )
    )

    return topology


# ---------------------------------------------------------------------------
# Step 2 – Resolve JESD204 link parameters from adijif
# ---------------------------------------------------------------------------


def resolve_jesd_params(vcxo: float = 122.88e6):
    """Return (rx_params, tx_params) dicts with F and K for this AD9081 config.

    Uses :func:`adijif.utils.get_jesd_mode_from_params` to look up the
    JESD204B mode without running the full clock solver.

    ADC: 4 GHz converter / (4 CDDC × 4 FDDC) = 250 MSPS per channel
    DAC: 12 GHz converter / (8 CDUC × 6 FDUC) ≈ 250 MSPS per channel
    """
    cddc, fddc = 4, 4
    cduc, fduc = 8, 6

    sys = jif.system("ad9081", "hmc7044", "xilinx", vcxo, solver="CPLEX")
    sys.fpga.setup_by_dev_kit_name("zcu102")
    sys.fpga.ref_clock_constraint = "Unconstrained"
    sys.converter.clocking_option = "integrated_pll"

    sys.converter.adc.sample_clock = 4e9 / (cddc * fddc)
    sys.converter.dac.sample_clock = 12e9 / (cduc * fduc)

    sys.converter.adc.datapath.cddc_decimations = [cddc] * 4
    sys.converter.adc.datapath.fddc_decimations = [fddc] * 8
    sys.converter.adc.datapath.fddc_enabled = [True] * 8
    sys.converter.dac.datapath.cduc_interpolation = cduc
    sys.converter.dac.datapath.fduc_interpolation = fduc
    sys.converter.dac.datapath.fduc_enabled = [True] * 8

    # get_jesd_mode_from_params only inspects the converter datapath and lane
    # constraints – it does NOT call the constraint solver, so it works even
    # without cpoptimizer/gekko installed.
    modes_rx = jif.utils.get_jesd_mode_from_params(
        sys.converter.adc, M=8, L=4, S=1, Np=16, jesd_class="jesd204b"
    )
    modes_tx = jif.utils.get_jesd_mode_from_params(
        sys.converter.dac, M=8, L=4, S=1, Np=16, jesd_class="jesd204b"
    )

    if not modes_rx or not modes_tx:
        raise RuntimeError(
            "No matching JESD204 mode found for the requested parameters"
        )

    rx_mode = modes_rx[0]["settings"]
    tx_mode = modes_tx[0]["settings"]

    print(
        f"JESD mode (RX): mode={modes_rx[0]['mode']}  "
        f"F={rx_mode['F']} K={rx_mode['K']} L={rx_mode['L']} M={rx_mode['M']}"
    )
    print(
        f"JESD mode (TX): mode={modes_tx[0]['mode']}  "
        f"F={tx_mode['F']} K={tx_mode['K']} L={tx_mode['L']} M={tx_mode['M']}"
    )
    print()

    return (
        {"F": rx_mode["F"], "K": rx_mode["K"]},
        {"F": tx_mode["F"], "K": tx_mode["K"]},
    )


# ---------------------------------------------------------------------------
# Step 3 – Build NodeBuilder config
# ---------------------------------------------------------------------------


def build_node_config(rx_params: dict, tx_params: dict) -> dict:
    """Map adijif JESD params to the format :class:`NodeBuilder` expects."""
    return {
        "jesd": {
            "rx": rx_params,
            "tx": tx_params,
        },
        "clock": {
            "hmc7044_rx_channel": HMC_RX_CHANNEL,
            "hmc7044_tx_channel": HMC_TX_CHANNEL,
        },
    }


# ---------------------------------------------------------------------------
# Step 4 – Generate DTS overlay
# ---------------------------------------------------------------------------


def generate_overlay(topology, cfg: dict, output_dir: Path) -> Path:
    """Render ADI DTS nodes and write a ``.dtso`` overlay file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    nodes = NodeBuilder().build(topology, cfg)

    print("Generated DTS nodes:")
    for key, node_list in nodes.items():
        for node in node_list:
            print(node)

    # DtsMerger needs a base DTS string to find the bus label and to produce
    # the merged .dts.  Without sdtgen/lopper we pass a minimal stub that
    # just declares the "amba" bus so the merger can produce a valid overlay.
    minimal_base = (
        "/dts-v1/;\n"
        "/ {\n"
        "\tamba: amba {\n"
        "\t\t#address-cells = <0x2>;\n"
        "\t\t#size-cells = <0x2>;\n"
        "\t};\n"
        "};\n"
    )

    name = "ad9081_zcu102"
    overlay_content, _ = DtsMerger().merge(minimal_base, nodes, output_dir, name)

    overlay_path = output_dir / f"{name}.dtso"
    print(f"Overlay written to: {overlay_path}")
    return overlay_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("=" * 60)
    print("AD9081 + ZCU102: XSA → Device Tree overlay")
    print("=" * 60)
    print()

    # 1. Parse & patch topology
    print("Step 1 – Parsing XSA …")
    topology = parse_xsa(XSA)
    print(f"  FPGA part  : {topology.fpga_part}")
    print(
        f"  JESD RX    : {topology.jesd204_rx[0].name}  base={topology.jesd204_rx[0].base_addr:#010x}  lanes={topology.jesd204_rx[0].num_lanes}"
    )
    print(
        f"  JESD TX    : {topology.jesd204_tx[0].name}  base={topology.jesd204_tx[0].base_addr:#010x}  lanes={topology.jesd204_tx[0].num_lanes}"
    )
    print(
        f"  Clock gen  : {topology.clkgens[0].name}  clocks={topology.clkgens[0].output_clks}"
    )
    print()

    # 2. Resolve JESD params via adijif
    print("Step 2 – Resolving JESD204 parameters via adijif …")
    rx_params, tx_params = resolve_jesd_params()

    # 3. Build NodeBuilder config
    cfg = build_node_config(rx_params, tx_params)

    # 4. Render and write overlay
    print("Step 3 – Generating DTS overlay …")
    print()
    overlay_path = generate_overlay(topology, cfg, OUT_DIR)
    print()
    print("=" * 60)
    print(f"Done.  Overlay: {overlay_path}")
    print("=" * 60)
    print()
    print("Next steps:")
    print("  • With lopper/sdtgen installed, run the full pipeline:")
    print("      adidtc xsa2dt examples/xsa/system_top.xsa config.json \\")
    print("             --output-dir out/ad9081_zcu102")
    print("  • Compile the overlay with dtc:")
    print(f"      dtc -@ -I dts -O dtb -o {OUT_DIR}/ad9081_zcu102.dtbo \\")
    print(f"          {overlay_path}")


if __name__ == "__main__":
    main()
