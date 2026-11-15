"""Command line interface: `openrole fetch`, `openrole list`, `openrole run`."""

import typer

from openrole import __version__

app = typer.Typer(help="Watch company career pages and get notified about new matching roles.")


@app.callback()
def main() -> None:
    """Keeps `openrole` a command group, so subcommands like `fetch` can be added."""


@app.command()
def version() -> None:
    """Show the installed version."""
    typer.echo(__version__)
