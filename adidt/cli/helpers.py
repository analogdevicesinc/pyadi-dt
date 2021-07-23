from rich.console import Console
from rich.table import Column, Table
from rich import box
from rich.text import Text

console = Console()


def list_node_props(node, no_color):
    if no_color:
        for prop in node.props:
            try:
                print(prop.name, prop.value)
            except:
                print(prop.name)
        return

    table = Table(title=node.name)
    table.add_column("Name", justify="left", style="cyan", no_wrap=True)
    table.add_column("Value", justify="left", style="magenta")
    for prop in node.props:
        try:
            table.add_row(prop.name, str(prop.value))
        except:
            table.add_row(prop.name, "")
    console.print(table)


def list_node_prop(node, prop, no_color):
    p = node.get_property(prop)
    if no_color:
        print(prop, p.value)
        return

    text = Text()
    text.append(prop, style="bold red")
    text.append(f" {p.value}", style="green")
    console.print(text)
