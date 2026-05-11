"""CLI application using Typer."""

import sys

import typer

from proxyflare.cli.commands.config import config_app
from proxyflare.cli.commands.create import create
from proxyflare.cli.commands.delete import delete_worker
from proxyflare.cli.commands.list import list_workers
from proxyflare.cli.commands.test import test_workers
from proxyflare.cli.console import print_error
from proxyflare.exceptions import ProxyflareError

__all__ = ["app", "main"]

app = typer.Typer(
    name="proxyflare",
    help="CLI Utility for managing Cloudflare Proxy Workers.",
    add_completion=True,
    no_args_is_help=True,
)


@app.callback()
def main_callback(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
) -> None:
    """
    Proxyflare CLI entry point.
    """
    from proxyflare.logging import configure_logging

    configure_logging("DEBUG" if verbose else "INFO")


# config has subcommands (show, verify) — stays as sub-app
app.add_typer(config_app, name="config")

# Single-action commands registered directly
app.command(name="create")(create)
app.command(name="list")(list_workers)
app.command(name="delete")(delete_worker)
app.command(name="test")(test_workers)


def main() -> None:
    """Main entry point for CLI."""
    try:
        app()
    except ProxyflareError as e:
        print_error(e.message)
        sys.exit(e.exit_code)
    except Exception as e:
        # Unexpected error
        print_error(f"An unexpected error occurred: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
