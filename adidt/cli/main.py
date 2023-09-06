import adidt
import fdt
import click
from .helpers import list_node_props, list_node_prop, list_node_subnodes


@click.group()
@click.option(
    "--no-color",
    "-nc",
    is_flag=True,
    help="Disable formatting",
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
    help="Set target architecture which will set the target DT. auto with determine from running system",
    show_default=True,
)
@click.pass_context
def cli(ctx, no_color, context, ip, username, password, arch, filepath):
    """ADI device tree utility"""
    ctx.ensure_object(dict)

    ctx.obj["no_color"] = no_color
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
        d._runr(f"reboot", warn=True)
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
        d._runr(f"reboot", warn=True)
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
        local_dt_filepath=ctx.obj["filepath"]
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
