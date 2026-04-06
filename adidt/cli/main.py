import adidt
import fdt
import click
import json
from .helpers import list_node_props, list_node_prop, list_node_subnodes
from pathlib import Path
from adidt.utils.parsers import DTDependencyParser


@click.group()
@click.option(
    "--no-color",
    "-nc",
    is_flag=True,
    help="Disable formatting",
)
@click.option(
    "--board",
    "-b",
    default="adrv9009_pcbz",
    help="Set board configuration",
    type=click.Choice(
        [
            "ad9081_fmc",
            "adrv9009_pcbz",
            "adrv9009_zu11eg",
            "adrv9361_z7035",
            "adrv9364_z7020",
            "daq2",
        ]
    ),
    show_default=True,
)
@click.option(
    "--context",
    "-c",
    default="local_sysfs",
    help="Set context",
    type=click.Choice(
        ["local_file", "local_sd", "local_sysfs", "remote_sysfs", "remote_sd"]
    ),
    show_default=True,
)
@click.option(
    "--ip",
    "-i",
    default="192.168.2.1",
    help="Set ip used by remote contexts",
    show_default=True,
)
@click.option(
    "--username",
    "-u",
    default="root",
    help="Set username used by remote SSH sessions (default is root)",
    show_default=True,
)
@click.option(
    "--password",
    "-w",
    default="analog",
    help="Set password used by remote SSH sessions (default is analog)",
    show_default=True,
)
@click.option(
    "--arch",
    "-a",
    default="auto",
    help="Set target architecture which will set the target DT. auto with determine from running system",
    show_default=True,
    type=click.Choice(["arm", "arm64", "auto"]),
)
@click.option(
    "--filepath",
    "-f",
    default="devicetree.dtb",
    help="Path of the target devicetree blob to be used in local_file mode (default is devicetree.dtb)",
    show_default=True,
)
@click.pass_context
def cli(ctx, no_color, board, context, ip, username, password, arch, filepath):
    """ADI device tree utility"""
    ctx.ensure_object(dict)

    ctx.obj["no_color"] = no_color
    ctx.obj["board"] = board
    ctx.obj["context"] = context
    ctx.obj["ip"] = ip
    ctx.obj["username"] = username
    ctx.obj["password"] = password
    ctx.obj["arch"] = arch
    ctx.obj["filepath"] = filepath


@cli.command()
@click.argument("node_name", required=False)
@click.argument("prop", required=False)
@click.argument("value", required=False)
@click.option(
    "--reboot",
    "-r",
    is_flag=True,
    help="Reboot boards after successful write",
)
@click.option(
    "--compat",
    "-cp",
    is_flag=True,
    help="Use node name to check against compatible id of node during search",
)
@click.option(
    "--children",
    "-ch",
    is_flag=True,
    help="Show properties of child nodes 1 level down",
)
@click.pass_context
def prop(ctx, node_name, prop, value, reboot, compat, children):
    """Get and set device tree properties

    \b
    NODE_NAME      - Name of node to address
    PROP           - Name property to get/set
    VALUE          - Value to write to property of node
    """
    d = adidt.dt(
        dt_source=ctx.obj["context"],
        ip=ctx.obj["ip"],
        username=ctx.obj["username"],
        password=ctx.obj["password"],
        arch=ctx.obj["arch"],
    )
    # List all node names/compatible ids
    if not node_name:
        print("No node name provided. Options are:")
        if compat:
            nodes = d._dt.search("compatible")
            for node in nodes:
                print(node.value)
        else:
            nodes = d._dt.search("*")
            for node in nodes:
                print(node.value)
        return

    if compat:
        nodes = d.get_node_by_compatible(node_name)
        if len(nodes) == 0:
            click.echo(f"No nodes found with compatible_id {node_name}")
            return
    else:
        nodes = d._dt.search(node_name, itype=fdt.ItemType.NODE)
        if len(nodes) == 0:
            click.echo(f"No nodes found with name {node_name}")
            return

    # List all properties of node with compatible id
    if not value:
        for node in nodes:
            if not prop:
                list_node_props(node, ctx.obj["no_color"])
            else:
                list_node_prop(node, prop, ctx.obj["no_color"])
            if children:
                print("Children:")
                if node.nodes:
                    for n in node.nodes:
                        list_node_props(n, ctx.obj["no_color"])
        return

    # Set property to value of node with compatible id
    for node in nodes:
        for p in node.props:
            if p.name == prop:
                isstring = isinstance(p, fdt.items.PropStrings)
                if "," in value:
                    vals = value.split(",")
                    if ~isstring:
                        vals = [int(v) for v in vals]
                        node.set_property(prop, vals)
                    else:
                        node.set_property(prop, vals)
                else:
                    if ~isstring:
                        node.set_property(prop, int(value))
                    else:
                        node.set_property(prop, value)
                d.update_current_dt(reboot=reboot)
                return
    click.echo(f"ERROR: No property found {prop}")


@cli.command()
@click.argument("rd", required=False)
@click.option(
    "--reboot",
    "-r",
    is_flag=True,
    help="Reboot boards after successful write",
)
@click.option(
    "--show",
    "-s",
    is_flag=True,
    help="Print commands as run",
)
@click.option(
    "--dry-run",
    "-d",
    is_flag=True,
    help="Dryrun, do not run commands",
)
@click.pass_context
def sd_move(ctx, rd, reboot, show, dry_run):
    """Move files on existing SD card

    \b
    REFERENCE_DESIGN  - Name of reference design folder on SD card
    """
    if ctx.obj["context"] in ["remote_sysfs", "local_file", "local_sysfs"]:
        s = f"ERROR: {ctx.obj['context']} context does not apply for sd-move"
        if ctx.obj["no_color"]:
            print(s)
        else:
            click.echo(click.style(s, fg="red"))
        return
    d = adidt.dt(
        dt_source=ctx.obj["context"],
        ip=ctx.obj["ip"],
        username=ctx.obj["username"],
        password=ctx.obj["password"],
        arch=ctx.obj["arch"],
    )
    d.update_existing_boot_files(rd, show=show, dryrun=dry_run)
    if reboot and not dry_run:
        d._runr("reboot", warn=True)
        if ctx.obj["no_color"]:
            print("Board rebooting")
        else:
            click.echo(click.style("Board rebooting", bg="red", fg="black", bold=True))


@cli.command()
@click.argument("files", required=False)
@click.option(
    "--reboot",
    "-r",
    is_flag=True,
    help="Reboot boards after successful write",
)
@click.option(
    "--show",
    "-s",
    is_flag=True,
    help="Print commands as run",
)
@click.option(
    "--dry-run",
    "-d",
    is_flag=True,
    help="Dryrun, do not run commands",
)
@click.pass_context
def sd_remote_copy(ctx, files, reboot, show, dry_run):
    """Copy local boot files to remote existing SD card

    \b
    FILES  - List of files to copy (comma separated)
    """
    if ctx.obj["context"] in ["remote_sysfs", "local_file", "local_sysfs"]:
        s = f"ERROR: {ctx.obj['context']} context does not apply for sd-move"
        if ctx.obj["no_color"]:
            print(s)
        else:
            click.echo(click.style(s, fg="red"))
        return
    d = adidt.dt(
        dt_source=ctx.obj["context"],
        ip=ctx.obj["ip"],
        username=ctx.obj["username"],
        password=ctx.obj["password"],
        arch=ctx.obj["arch"],
    )
    file_list = files.split(",")
    d.copy_local_files_to_remote_sd_card(file_list, show=show, dryrun=dry_run)
    if reboot and not dry_run:
        d._runr("reboot", warn=True)
        if ctx.obj["no_color"]:
            print("Board rebooting")
        else:
            click.echo(click.style("Board rebooting", bg="red", fg="black", bold=True))


@cli.command()
@click.argument("node_name", nargs=-1)
@click.option(
    "--compat",
    "-cp",
    is_flag=True,
    help="Use node name to check against compatible id of node during search. This is only used for the first node",
)
@click.option(
    "--reboot",
    "-r",
    is_flag=True,
    help="Reboot boards after successful write",
)
@click.option(
    "--prop",
    "-p",
    default=None,
    help="Property of node to read to set",
)
@click.option(
    "--value",
    "-v",
    default=None,
    help="Value to set property to",
)
@click.pass_context
def props(ctx, node_name, compat, reboot, prop, value):
    """Get and set device tree properties

    \b
    NODE_NAME      - Name of node(s) to address
    """
    d = adidt.dt(
        dt_source=ctx.obj["context"],
        ip=ctx.obj["ip"],
        username=ctx.obj["username"],
        password=ctx.obj["password"],
        arch=ctx.obj["arch"],
        local_dt_filepath=ctx.obj["filepath"],
    )
    # List all node names/compatible ids
    if not node_name:
        print("No node name provided. Options are:")
        if compat:
            nodes = d._dt.search("compatible")
            for node in nodes:
                print(node.value)
        else:
            # List all node names
            def print_node(node):
                print(node.name)
                if len(node.nodes) > 0:
                    for n in node.nodes:
                        print_node(n)

            print_node(d._dt.root)
        return

    if compat:
        parent = d.get_node_by_compatible(node_name[0])
        if not parent:
            raise Exception("No nodes found")

        if len(parent) > 1:
            print("Multiple nodes found, please pick 1\n")
            for node in parent:
                for prop in node.props:
                    if prop.name == "compatible":
                        print(prop.value, f"(Node name {node.name})")
            return
        parent = parent[0]

    else:
        parent = d._dt.search(node_name[0], itype=fdt.ItemType.NODE)
        if not parent:
            print(f"No nodes found with name {node_name[0]}")
            return
        parent = parent[0]

    # Drill down through secondary node name inputs
    node_name = node_name[1:]
    num_nodes = len(node_name)
    nodes = []
    if num_nodes > 0:
        done = False
        for indx, name in enumerate(node_name):
            found = False
            for node in parent.nodes:
                if name in node.name:
                    found = True
                    if indx == num_nodes - 1:
                        parent = node
                        nodes = parent.nodes
                        done = True
                        break
                    else:
                        parent = node
                        break
            if not found:
                print(f"No node found with associated name {name}")
                return
            if done:
                break
    else:
        nodes = parent.nodes

    if not prop:
        list_node_props(parent, ctx.obj["no_color"])
        if nodes:
            list_node_subnodes(nodes, ctx.obj["no_color"])
        return

    if not value:
        list_node_prop(parent, prop, ctx.obj["no_color"])
        return

    # Set property to value of node
    for p in parent.props:
        if p.name == prop:
            isstring = isinstance(p, fdt.items.PropStrings)
            if "," in value:
                vals = value.split(",")
                if ~isstring:
                    vals = [int(v) for v in vals]
                    parent.set_property(prop, vals)
                else:
                    parent.set_property(prop, vals)
            else:
                if ~isstring:
                    parent.set_property(prop, int(value))
                else:
                    parent.set_property(prop, value)
            d.update_current_dt(reboot=reboot)
            return
    click.echo(f"ERROR: No property found {prop}")


@cli.command()
@click.argument(
    "node_type",
    required=True,
    type=click.Choice(["clock", "converter", "system", "fpga"]),
)
@click.option(
    "--reboot",
    "-r",
    is_flag=True,
    help="Reboot boards after successful write",
)
@click.option(
    "--filename",
    "-f",
    default=None,
    help="Name of json file to import with JIF config",
    type=click.Path(exists=True),
)
@click.pass_context
def jif(ctx, node_type, reboot, filename):
    """JIF supported updates of DT

    \b
    NODE_TYPE      - Type of device the configuration is to address
    """
    if node_type == "clock":
        d = adidt.clock(
            dt_source=ctx.obj["context"],
            ip=ctx.obj["ip"],
            username=ctx.obj["username"],
            password=ctx.obj["password"],
            arch=ctx.obj["arch"],
        )
        import json

        with open(filename, "r") as file:
            cfg = json.load(file)
        d.set(cfg["clock"]["part"], cfg["clock"], append=True)
        d.update_current_dt(reboot=reboot)
    else:
        raise Exception("Other node types not implemented")


@cli.command()
@click.option(
    "--profile",
    "-p",
    default=None,
    help="",
    type=Path,
)
@click.option(
    "--config",
    "-c",
    required=False,
    default=None,
    help="path to talise_config.c",
    type=Path,
)
@click.pass_context
def profile2dt(ctx, profile, config):
    """Generate devicetree from Profile Configuration Wizard files"""
    b = ctx.obj["board"]
    if b not in ["adrv9009_pcbz"]:
        print(f"board type {b} not supported")
        return

    board = eval(f"adidt.{b}()")
    board.parse_profile(profile)
    board.parse_talInit(config)
    board.gen_dt()
    print(f"Wrote {board.output_filename}")


@cli.command()
@click.argument("dt_file", type=click.Path(exists=True))
@click.option(
    "--format",
    "-f",
    default="tree",
    type=click.Choice(["tree", "json", "dot"]),
    help="Output format (tree, json, or dot)",
)
@click.option(
    "--max-depth",
    "-d",
    default=None,
    type=int,
    help="Maximum depth to display in tree format",
)
@click.option(
    "--show-missing/--hide-missing",
    default=True,
    help="Show or hide missing dependencies",
)
@click.option(
    "--output",
    "-o",
    default=None,
    type=click.Path(),
    help="Output file (for json/dot formats)",
)
@click.pass_context
def deps(ctx, dt_file, format, max_depth, show_missing, output):
    """Analyze device tree dependencies

    \b
    DT_FILE  - Path to device tree source file (.dts, .dtsi)

    Examples:
        View dependency tree:
            adidtc deps system.dts

        Export to GraphViz and generate image:
            adidtc deps system.dts --format dot -o deps.dot
            dot -Tpng deps.dot -o deps.png

        Export to JSON with missing dependencies:
            adidtc deps system.dts --format json --show-missing -o deps.json

        Limit depth of tree display:
            adidtc deps system.dts --max-depth 3
    """
    parser = DTDependencyParser()

    try:
        parser.parse(dt_file)
    except FileNotFoundError as e:
        click.echo(click.style(f"Error: {e}", fg="red"))
        return
    except Exception as e:
        click.echo(click.style(f"Error parsing file: {e}", fg="red"))
        return

    # Check for circular dependencies
    cycles = parser.detect_circular_dependencies()
    if cycles:
        click.echo(
            click.style(
                "Warning: Circular dependencies detected!", fg="yellow", bold=True
            )
        )
        for cycle in cycles:
            click.echo(click.style(f"  Cycle: {' -> '.join(cycle)}", fg="yellow"))
        click.echo()

    # Generate output based on format
    if format == "tree":
        tree_output = parser.render_tree(max_depth=max_depth, show_missing=show_missing)
        if output:
            with open(output, "w") as f:
                f.write(tree_output)
            click.echo(f"Tree output written to {output}")
        else:
            click.echo(tree_output)

    elif format == "dot":
        dot_content = parser.export_dot(show_missing=show_missing)
        if output:
            with open(output, "w") as f:
                f.write(dot_content)
            click.echo(f"DOT output written to {output}")
            click.echo(
                f"Generate image with: dot -Tpng {output} -o {output.replace('.dot', '.png')}"
            )
        else:
            click.echo(dot_content)

    else:  # json
        json_data = parser.export_json()
        if output:
            with open(output, "w") as f:
                json.dump(json_data, f, indent=2)
            click.echo(f"JSON output written to {output}")
        else:
            click.echo(json.dumps(json_data, indent=2))


_BOARD_CLASSES = {
    "daq2": ("adidt.boards.daq2", "daq2"),
    "ad9081_fmc": ("adidt.boards.ad9081_fmc", "ad9081_fmc"),
    "ad9082_fmc": ("adidt.boards.ad9082_fmc", "ad9082_fmc"),
    "ad9083_fmc": ("adidt.boards.ad9083_fmc", "ad9083_fmc"),
    "ad9084_fmc": ("adidt.boards.ad9084_fmc", "ad9084_fmc"),
    "adrv9002_fmc": ("adidt.boards.adrv9002_fmc", "adrv9002_fmc"),
    "adrv9008_fmc": ("adidt.boards.adrv9008_fmc", "adrv9008_fmc"),
    "fmcomms_fmc": ("adidt.boards.fmcomms_fmc", "fmcomms_fmc"),
    "adrv9009_fmc": ("adidt.boards.adrv9009_fmc", "adrv9009_fmc"),
    "adrv9025_fmc": ("adidt.boards.adrv9025_fmc", "adrv9025_fmc"),
    "adrv937x_fmc": ("adidt.boards.adrv937x_fmc", "adrv937x_fmc"),
}


@cli.command()
@click.option(
    "--board",
    "-b",
    required=True,
    type=click.Choice(sorted(_BOARD_CLASSES.keys())),
    help="Board class to use for generation",
)
@click.option(
    "--platform",
    "-p",
    required=True,
    help="Target platform (e.g., zcu102, vpk180, zc706, vcu118)",
)
@click.option(
    "--config",
    "-c",
    required=True,
    type=click.Path(exists=True),
    help="Path to JSON configuration file",
)
@click.option(
    "--kernel-path",
    "-k",
    default=None,
    type=click.Path(exists=True),
    help="Path to Linux kernel source tree (overrides LINUX_KERNEL_PATH env var)",
)
@click.option(
    "--output",
    "-o",
    default=None,
    type=click.Path(),
    help="Output DTS file path",
)
@click.option("--compile", is_flag=True, help="Compile DTS to DTB using dtc")
@click.pass_context
def gen_dts(ctx, board, platform, config, kernel_path, output, compile):
    """Generate device tree source from a board class and config.

    \b
    Uses the BoardModel workflow: config → to_board_model() → render → DTS.
    Supports all board classes with to_board_model().

    \b
    Examples:
      Generate DTS for FMCDAQ2 on ZCU102:
        adidtc gen-dts -b daq2 -p zcu102 -c solver_config.json

      Generate DTS for AD9081 FMC on VPK180:
        adidtc gen-dts -b ad9081_fmc -p vpk180 -c config.json

      Generate and compile to DTB:
        adidtc gen-dts -b adrv9009_fmc -p zcu102 -c cfg.json --compile

      Custom output path:
        adidtc gen-dts -b daq2 -p zc706 -c cfg.json -o custom.dts
    """
    try:
        # Load configuration
        with open(config, "r") as f:
            cfg = json.load(f)

        # Import and instantiate the board class
        module_path, class_name = _BOARD_CLASSES[board]
        import importlib

        mod = importlib.import_module(module_path)
        board_cls = getattr(mod, class_name)
        board_inst = board_cls(platform=platform, kernel_path=kernel_path)

        # Override output filename if specified
        if output:
            board_inst.output_filename = output

        # Generate DTS via BoardModel
        output_file = board_inst.gen_dt_from_config(cfg, config_source=config)

        click.echo(click.style(f"Generated DTS: {output_file}", fg="green", bold=True))

        # Compile if requested
        if compile:
            import subprocess

            dtb_file = output_file.replace(".dts", ".dtb")
            include_paths = board_inst.get_dtc_include_paths()

            # Build dtc command with include paths
            dtc_cmd = ["dtc", "-I", "dts", "-O", "dtb"]
            for inc_path in include_paths:
                dtc_cmd.extend(["-i", inc_path])
            dtc_cmd.extend(["-o", dtb_file, output_file])

            click.echo("Compiling DTS to DTB...")
            click.echo(f"Command: {' '.join(dtc_cmd)}")

            try:
                result = subprocess.run(
                    dtc_cmd, check=True, capture_output=True, text=True
                )
                click.echo(
                    click.style(f"Compiled DTB: {dtb_file}", fg="green", bold=True)
                )

                if result.stderr:
                    click.echo(click.style("Compiler warnings:", fg="yellow"))
                    click.echo(result.stderr)

            except subprocess.CalledProcessError as e:
                click.echo(click.style(f"Compilation failed: {e}", fg="red"))
                if e.stderr:
                    click.echo(click.style("Error output:", fg="red"))
                    click.echo(e.stderr)
                return
            except FileNotFoundError:
                click.echo(
                    click.style("Error: 'dtc' compiler not found in PATH", fg="red")
                )
                click.echo("Please install device tree compiler (dtc)")
                return

    except FileNotFoundError as e:
        click.echo(click.style(f"Error: {e}", fg="red"))
        return
    except ValueError as e:
        click.echo(click.style(f"Error: {e}", fg="red"))
        return
    except Exception as e:
        click.echo(click.style(f"Unexpected error: {e}", fg="red"))
        import traceback

        traceback.print_exc()
        return


@cli.command("xsa2dt")
@click.option(
    "--xsa",
    "-x",
    required=True,
    type=click.Path(exists=True),
    help="Path to Vivado .xsa file",
)
@click.option(
    "--config",
    "-c",
    required=True,
    type=click.Path(exists=True),
    help="Path to pyadi-jif JSON configuration file",
)
@click.option(
    "--output",
    "-o",
    default="./generated",
    type=click.Path(),
    show_default=True,
    help="Output directory",
)
@click.option(
    "--timeout",
    "-t",
    default=120,
    type=int,
    show_default=True,
    help="sdtgen subprocess timeout in seconds",
)
@click.option(
    "--profile",
    type=str,
    default=None,
    help="Optional board profile name (for example: ad9081_zcu102, adrv9009_zcu102)",
)
@click.option(
    "--reference-dts",
    type=click.Path(exists=True),
    default=None,
    help="Optional reference DTS root file used to generate parity reports",
)
@click.option(
    "--strict-parity",
    is_flag=True,
    help="Fail when manifest parity reports missing required roles",
)
@click.option(
    "--lint/--no-lint",
    default=False,
    show_default=True,
    help="Run structural DTS linter on generated output",
)
@click.option(
    "--strict-lint",
    is_flag=True,
    help="Fail when DTS linter finds errors (implies --lint)",
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["default", "petalinux"]),
    default="default",
    show_default=True,
    help="Output format. 'petalinux' generates system-user.dtsi and device-tree.bbappend",
)
@click.option(
    "--petalinux-project",
    type=click.Path(exists=True, file_okay=False),
    default=None,
    help="PetaLinux project directory. When set with --format petalinux, copies system-user.dtsi into the project",
)
@click.pass_context
def xsa2dt(
    ctx,
    xsa,
    config,
    output,
    timeout,
    profile,
    reference_dts,
    strict_parity,
    lint,
    strict_lint,
    output_format,
    petalinux_project,
):
    """Generate ADI device tree from Vivado XSA file

    \b
    Invokes sdtgen against the XSA, detects ADI IPs, generates JESD204
    FSM-compatible nodes, and produces overlay (.dtso), merged (.dts), and
    interactive HTML visualization report.

    \b
    Requires sdtgen (lopper); if it is not on PATH, the runner will try
    to discover and source a local Vitis/Vivado settings script.
    Install from: https://github.com/devicetree-org/lopper

    \b
    Examples:
      adidtc xsa2dt -x design_1.xsa -c ad9081_cfg.json
      adidtc xsa2dt -x design_1.xsa -c cfg.json -o ./out --timeout 180
      adidtc xsa2dt -x design_1.xsa -c cfg.json --profile ad9081_zcu102
      adidtc xsa2dt -x design_1.xsa -c cfg.json --reference-dts ref.dts
      adidtc xsa2dt -x design_1.xsa -c cfg.json --format petalinux
      adidtc xsa2dt -x design_1.xsa -c cfg.json --format petalinux --petalinux-project /path/to/project
    """
    try:
        from adidt.xsa.pipeline import XsaPipeline
        from adidt.xsa.exceptions import (
            SdtgenNotFoundError,
            SdtgenError,
            XsaParseError,
            ConfigError,
            DtsLintError,
            ParityError,
        )
    except ImportError:
        click.echo(
            click.style(
                "Error: xsa support not installed. Run: pip install adidt[xsa]",
                fg="red",
            )
        )
        return

    try:
        with open(config, "r") as f:
            cfg = json.load(f)
        parity_requested = bool(reference_dts or strict_parity)

        result = XsaPipeline().run(
            Path(xsa),
            cfg,
            Path(output),
            sdtgen_timeout=timeout,
            profile=profile,
            reference_dts=Path(reference_dts) if reference_dts else None,
            strict_parity=strict_parity,
            lint=lint,
            strict_lint=strict_lint,
            output_format=output_format,
        )
        if not isinstance(result, dict):
            raise click.ClickException(
                f"pipeline returned invalid result type: {type(result).__name__}"
            )
        required_artifacts = ("overlay", "merged")
        missing_required = [key for key in required_artifacts if key not in result]
        if missing_required:
            missing_joined = ", ".join(missing_required)
            raise click.ClickException(
                f"pipeline result missing required artifacts: {missing_joined}"
            )
        empty_required = []
        for key in required_artifacts:
            value = result.get(key)
            if value is None:
                empty_required.append(key)
                continue
            if isinstance(value, str) and not value.strip():
                empty_required.append(key)
        if empty_required:
            empty_joined = ", ".join(empty_required)
            raise click.ClickException(
                f"pipeline result has empty required artifacts: {empty_joined}"
            )
        non_path_required = []
        for key in required_artifacts:
            value = result.get(key)
            if value is None:
                continue
            try:
                Path(value)
            except (TypeError, ValueError):
                non_path_required.append(key)
        if non_path_required:
            non_path_joined = ", ".join(non_path_required)
            raise click.ClickException(
                f"pipeline result has non-path required artifacts: {non_path_joined}"
            )

        click.echo(click.style("Done!", fg="green", bold=True))
        click.echo(f"  Overlay:  {result['overlay']}")
        click.echo(f"  Merged:   {result['merged']}")
        if "report" in result:
            click.echo(f"  Report:   {result['report']}")

        if "system_user_dtsi" in result:
            click.echo(f"  system-user.dtsi: {result['system_user_dtsi']}")
            click.echo(f"  bbappend:         {result['bbappend']}")

            if petalinux_project:
                from adidt.xsa.petalinux import validate_petalinux_project

                proj = Path(petalinux_project)
                validate_petalinux_project(proj)

                dt_files = (
                    proj
                    / "project-spec"
                    / "meta-user"
                    / "recipes-bsp"
                    / "device-tree"
                    / "files"
                )
                dt_recipe = dt_files.parent

                # Back up existing system-user.dtsi
                dest_dtsi = dt_files / "system-user.dtsi"
                if dest_dtsi.exists():
                    import shutil

                    bak = dt_files / "system-user.dtsi.bak"
                    shutil.copy2(dest_dtsi, bak)
                    click.echo(f"  Backed up existing system-user.dtsi to {bak}")

                import shutil

                shutil.copy2(result["system_user_dtsi"], dest_dtsi)
                shutil.copy2(result["bbappend"], dt_recipe / "device-tree.bbappend")
                click.echo(
                    click.style(
                        f"  Installed into PetaLinux project: {proj}", fg="green"
                    )
                )

        def _path_or_none(value, label):
            if value is None:
                click.echo(f"  Warning: {label} path is null")
                return None
            if isinstance(value, str) and not value.strip():
                click.echo(f"  Warning: {label} path is empty")
                return None
            try:
                return Path(value)
            except TypeError:
                click.echo(f"  Warning: {label} path is not path-like: {value!r}")
                return None
            except ValueError as ex:
                click.echo(f"  Warning: {label} path is invalid: {ex}")
                return None

        def _print_unavailable_map_summary():
            click.echo("  Coverage % (roles/links/properties/overall): n/a/n/a/n/a/n/a")
            click.echo(
                "  Missing gaps (roles/links/properties/mismatched): n/a/n/a/n/a/n/a"
            )

        if "map" in result:
            click.echo(f"  Map:      {result['map']}")
            if parity_requested:
                map_path = _path_or_none(result["map"], "parity map")
                if map_path is None:
                    _print_unavailable_map_summary()
                elif not map_path.exists():
                    click.echo(f"  Warning: parity map not found: {map_path}")
                    _print_unavailable_map_summary()
                else:
                    try:
                        map_data = json.loads(map_path.read_text())
                        if not isinstance(map_data, dict):
                            click.echo(
                                f"  Warning: parity map JSON root is not an object: {map_path}"
                            )
                            _print_unavailable_map_summary()
                            map_data = None
                        if map_data is not None:
                            raw_cov = map_data.get("coverage", {})
                            cov = raw_cov if isinstance(raw_cov, dict) else {}
                            click.echo(
                                "  Coverage % (roles/links/properties/overall): "
                                f"{cov.get('roles_pct', 'n/a')}/"
                                f"{cov.get('links_pct', 'n/a')}/"
                                f"{cov.get('properties_pct', 'n/a')}/"
                                f"{cov.get('overall_pct', 'n/a')}"
                            )
                            if (
                                cov.get("overall_matched") is not None
                                and cov.get("overall_total") is not None
                            ):
                                click.echo(
                                    "  Overall matched items: "
                                    f"{cov.get('overall_matched')}/{cov.get('overall_total')}"
                                )

                            def _as_list(value):
                                return value if isinstance(value, list) else []

                            missing_roles = _as_list(map_data.get("missing_roles", []))
                            missing_links = _as_list(map_data.get("missing_links", []))
                            missing_props = _as_list(
                                map_data.get("missing_properties", [])
                            )
                            mismatched_props = _as_list(
                                map_data.get("mismatched_properties", [])
                            )
                            click.echo(
                                "  Missing gaps (roles/links/properties/mismatched): "
                                f"{len(missing_roles)}/{len(missing_links)}/"
                                f"{len(missing_props)}/{len(mismatched_props)}"
                            )
                    except Exception as ex:
                        click.echo(
                            f"  Warning: unable to parse parity map JSON at {map_path} ({ex})"
                        )
                        _print_unavailable_map_summary()
        elif parity_requested:
            click.echo("  Warning: parity map not provided by pipeline result")
            _print_unavailable_map_summary()
        if "coverage" in result:
            click.echo(f"  Coverage: {result['coverage']}")
            if parity_requested:
                cov_path = _path_or_none(result["coverage"], "parity coverage report")
                if cov_path is None:
                    pass
                elif not cov_path.exists():
                    click.echo(
                        f"  Warning: parity coverage report not found: {cov_path}"
                    )
        elif parity_requested:
            click.echo(
                "  Warning: parity coverage report not provided by pipeline result"
            )

        if "diagnostics" in result:
            diag_path = _path_or_none(result["diagnostics"], "diagnostics")
            if diag_path is not None and diag_path.exists():
                click.echo(f"  Diagnostics: {diag_path}")
                try:
                    diag_data = json.loads(diag_path.read_text())
                    summary = diag_data.get("summary", {})
                    click.echo(
                        f"  Lint: {summary.get('errors', 0)} errors, "
                        f"{summary.get('warnings', 0)} warnings, "
                        f"{summary.get('info', 0)} info"
                    )
                    for item in diag_data.get("diagnostics", []):
                        sev = item.get("severity", "?")
                        rule = item.get("rule", "?")
                        msg = item.get("message", "?")
                        click.echo(f"    [{sev}] {rule}: {msg}")
                except Exception as ex:
                    click.echo(f"  Warning: unable to display diagnostics: {ex}")

    except FileNotFoundError as e:
        raise click.ClickException(str(e))
    except json.JSONDecodeError as e:
        raise click.ClickException(f"invalid JSON in config file: {e}")
    except SdtgenNotFoundError as e:
        raise click.ClickException(str(e))
    except SdtgenError as e:
        message = f"sdtgen failed: {e}"
        if e.stderr:
            message = f"{message}\n{e.stderr}"
        raise click.ClickException(message)
    except (XsaParseError, ConfigError) as e:
        raise click.ClickException(str(e))
    except ParityError as e:
        raise click.ClickException(str(e))
    except DtsLintError as e:
        raise click.ClickException(str(e))
    except click.ClickException:
        raise
    except Exception as e:
        raise click.ClickException(f"Unexpected error: {e}")


@cli.command("xsa-profiles")
def xsa_profiles():
    """List available built-in XSA board profiles."""
    try:
        from adidt.xsa.profiles import ProfileManager
    except ImportError:
        click.echo(
            click.style(
                "Error: xsa support not installed. Run: pip install adidt[xsa]",
                fg="red",
            )
        )
        return

    names = ProfileManager().list_profiles()
    if not names:
        click.echo("No XSA profiles found.")
        return

    click.echo("Available XSA profiles:")
    for name in names:
        click.echo(f"  - {name}")


@cli.command("xsa-profile-show")
@click.argument("name", type=str)
def xsa_profile_show(name):
    """Show one built-in XSA board profile as JSON."""
    try:
        from adidt.xsa.profiles import ProfileManager
        from adidt.xsa.exceptions import ProfileError
    except ImportError:
        click.echo(
            click.style(
                "Error: xsa support not installed. Run: pip install adidt[xsa]",
                fg="red",
            )
        )
        return

    try:
        profile = ProfileManager().load(name)
    except ProfileError as ex:
        click.echo(click.style(f"Error: {ex}", fg="red"))
        return

    click.echo(json.dumps(profile, indent=2))


@cli.command("kuiper-boards")
@click.option(
    "--status",
    "-s",
    type=click.Choice(["all", "full", "profile_only", "unsupported"]),
    default="all",
    help="Filter by support status",
)
@click.option("--json-output", is_flag=True, help="Output raw JSON")
def kuiper_boards(status, json_output):
    """List Kuiper 2023-R2 supported boards and their status."""
    manifest_path = Path(__file__).parent.parent / "xsa" / "kuiper_boards.json"
    if not manifest_path.exists():
        click.echo(click.style("Error: kuiper_boards.json not found", fg="red"))
        return

    with open(manifest_path) as f:
        manifest = json.load(f)

    boards = manifest.get("boards", {})
    if status != "all":
        boards = {k: v for k, v in boards.items() if v.get("status") == status}

    if json_output:
        click.echo(json.dumps(boards, indent=2))
        return

    click.echo(
        click.style(
            f"Kuiper {manifest.get('release', '?')} — {len(boards)} boards",
            fg="cyan",
            bold=True,
        )
    )
    click.echo()

    status_colors = {
        "full": "green",
        "profile_only": "yellow",
        "unsupported": "red",
    }

    for name, info in sorted(boards.items()):
        st = info.get("status", "unknown")
        color = status_colors.get(st, "white")
        platform = info.get("platform", "?")
        converter = info.get("converter", "?")
        board_cls = info.get("board_class") or "-"
        label = click.style(f"{st.upper():>14s}", fg=color)
        click.echo(
            f"  {label}  {name:<50s}  {converter:<12s}  {platform:<8s}  {board_cls}"
        )
