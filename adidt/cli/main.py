import adidt
import click
from .helpers import list_node_props, list_node_prop


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
@click.pass_context
def cli(ctx, no_color, context, ip, username, password):
    """ADI device tree utility"""
    ctx.ensure_object(dict)

    ctx.obj["no_color"] = no_color
    ctx.obj["context"] = context
    ctx.obj["ip"] = ip
    ctx.obj["username"] = username
    ctx.obj["password"] = password


@cli.command()
@click.argument("compatible_id", required=False)
@click.argument("prop", required=False)
@click.argument("value", required=False)
@click.option(
    "--reboot",
    "-r",
    is_flag=True,
    help="Reboot boards after successful write",
)
@click.pass_context
def prop(ctx, compatible_id, prop, value, reboot):
    """Get and set device tree properties

    \b
    COMPATIBLE_ID  - Value of compatible field of desired node
    PROP           - Name property to get/set
    VALUE          - Value to write to property of node
    """
    d = adidt.dt(
        dt_source=ctx.obj["context"],
        ip=ctx.obj["ip"],
        username=ctx.obj["username"],
        password=ctx.obj["password"],
    )
    # List all compatible ids
    if not compatible_id:
        nodes = d._dt.search("compatible")
        for node in nodes:
            print(node.value)
        return

    nodes = d.get_node_by_compatible(compatible_id)
    if len(nodes) == 0:
        click.echo(f"No nodes found with compatible_id {compatible_id}")
        return

    # List all properties of node with compatible id
    if not value:
        for node in nodes:
            if not prop:
                list_node_props(node, ctx.obj["no_color"])
            else:
                list_node_prop(node, prop, ctx.obj["no_color"])
        return

    # Set property to value of node with compatible id
    for node in nodes:
        for p in node.props:
            if p.name == prop:
                node.set_property(prop, value)
                d.update_current_dt(reboot=reboot)
                return
    click.echo(f"ERROR: No property found {prop}")
