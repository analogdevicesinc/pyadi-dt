from rich.console import Console
from rich.table import Column, Table
from rich import box
from rich.text import Text

console = Console()


def list_node_props(node):
    table = Table(title=node.name)
    table.add_column("Name", justify="left", style="cyan", no_wrap=True)
    table.add_column("Value", justify="left", style="magenta")
    for prop in node.props:
        try:
            table.add_row(prop.name, str(prop.value))
            # print(prop.name, prop.value)
        except:
            table.add_row(prop.name, "")
            # print(prop.name)
    # console = Console()
    console.print(table)

def list_node_prop(node,prop):
    p = node.get_property(prop)
    text = Text()
    text.append(prop, style="bold red")
    text.append(f" {p.value}", style='green')
    console.print(text)

