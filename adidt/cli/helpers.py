from rich.console import Console
from rich.table import Table
from rich.text import Text

console = Console()


def to_str(p):
    """Convert an fdt property object to a human-readable string."""
    try:
        data = p.data
    except (AttributeError, TypeError):
        try:
            return str(p.value)
        except (AttributeError, TypeError):
            return ""
    if len(data) == 0:
        try:
            return str(p.value)
        except (AttributeError, TypeError):
            return ""
    elif len(data) == 1:
        return str(data[0])
    else:
        return ",".join(list(map(str, data)))


def list_node_props(node, no_color):
    """Print or render a Rich table of all properties in a device tree node."""
    if no_color:
        for prop in node.props:
            print(prop.name, to_str(prop))
        return

    table = Table(title=node.name)
    table.add_column("Name", justify="left", style="cyan", no_wrap=True)
    table.add_column("Value", justify="left", style="magenta")
    for prop in node.props:
        table.add_row(prop.name, to_str(prop))
    console.print(table)


def list_node_subnodes(nodes, no_color):
    """Print or render a Rich table listing child node names."""
    if no_color:
        print("\n--Child nodes")
        for node in nodes:
            print(node.name)
        return

    table = Table(title="Child Nodes")
    table.add_column("Name", justify="left", style="cyan", no_wrap=True)
    for snode in nodes:
        table.add_row(snode.name)
    console.print(table)


def list_node_prop(node, prop, no_color):
    """Print or render a single property value from a device tree node."""
    p = node.get_property(prop)
    if no_color:
        print(prop, to_str(p))
        return

    text = Text()
    text.append(prop, style="bold red")
    text.append(f" {to_str(p)}", style="green")
    console.print(text)
