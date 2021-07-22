import adidt
import click
from .helpers import list_node_props, list_node_prop


@click.group()
@click.option(
    "--context",
    "-c",
    default="local",
    help="Set context (default is local)",
    type=click.Choice(["local", "remote_fs", "remote_sd"]),
)
@click.option(
    "--ip",
    "-i",
    default="192.168.2.1",
    help="Set ip used by remote contexts (default is 192.168.2.1)",
)
@click.option(
    "--username",
    "-u",
    default="root",
    help="Set username used by remote SSH sessions (default is root)",
)
@click.option(
    "--password",
    "-w",
    default="analog",
    help="Set password used by remote SSH sessions (default is analog)",
)
@click.pass_context
def cli(ctx, context, ip, username, password):
    """ADI device tree utility"""
    ctx.ensure_object(dict)

    ctx.obj["context"] = context
    ctx.obj["ip"] = ip
    ctx.obj["username"] = username
    ctx.obj["password"] = password


@cli.command()
@click.pass_context
def get_cmp(ctx):
    """Get all node compatible ids"""
    d = adidt.dt(
        dt_source=ctx.obj["context"],
        ip=ctx.obj["ip"],
        username=ctx.obj["username"],
        password=ctx.obj["password"],
    )

    nodes = d._dt.search("compatible")
    for node in nodes:
        print(node.value)


@cli.command()
@click.argument("compatible_id")
@click.argument("props", nargs=-1)
@click.pass_context
def cmp(ctx, compatible_id, props):
    """Get node information through compatible id

    COMPATIBLE_ID: Value of compatible field of node
    """
    d = adidt.dt(
        dt_source=ctx.obj["context"],
        ip=ctx.obj["ip"],
        username=ctx.obj["username"],
        password=ctx.obj["password"],
    )

    if not props:
        props = [""]

    nodes = d.get_node_by_compatible(compatible_id)
    if len(nodes) == 0:
        click.echo(f"No nodes found with compatible_id {compatible_id}")
        return
    for prop in props:
        for node in nodes:
            if prop == "":
                list_node_props(node)
            else:
                list_node_prop(node, prop)

@cli.command()
@click.argument("compatible_id")
@click.argument("prop")
@click.argument("value")
@click.pass_context
def scmp(ctx, compatible_id, prop, value):
    """Set node property through compatible id reference

    COMPATIBLE_ID: Value of compatible field of node
    PROP: Property field name of node
    VALUE: Value field of node
    """
    d = adidt.dt(
        dt_source=ctx.obj["context"],
        ip=ctx.obj["ip"],
        username=ctx.obj["username"],
        password=ctx.obj["password"],
    )

    nodes = d.get_node_by_compatible(compatible_id)
    if len(nodes) == 0:
        click.echo(f"No nodes found with compatible_id {compatible_id}")
        return
    for node in nodes:
        for p in node.props:
            if p.name == prop:
                 node.set_property(prop,value)
                 return
    click.echo(f"ERROR: No property found {prop}")

cli.add_command(cmp)
cli.add_command(get_cmp)
cli.add_command(scmp)
