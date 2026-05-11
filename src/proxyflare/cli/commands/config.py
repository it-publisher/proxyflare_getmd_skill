import asyncio
import shutil
import sys

import typer
from pydantic import ValidationError

from proxyflare.cli.console import console
from proxyflare.cli.context import get_app_context
from proxyflare.cli.exceptions import ConfigError
from proxyflare.cli.utils import handle_validation_error
from proxyflare.exceptions import SubdomainMissingError
from proxyflare.models.config import Config

config_app = typer.Typer(
    no_args_is_help=True, help="Manage Proxyflare configuration (show, verify)."
)


@config_app.command()
def verify() -> None:
    """Validate Cloudflare API token and environment setup."""

    from cloudflare import Client

    from proxyflare.cli.exceptions import ConfigError
    from proxyflare.validation import WORKER_PERMISSIONS, check_token_permissions, verify_token

    async def _verify_async() -> None:
        console.print(f"Python Version: [green]{sys.version.split()[0]}[/green]")

        wrangler_path = shutil.which("wrangler") or shutil.which("npx")
        if wrangler_path:
            console.print(f"Wrangler/Npx found: [green]{wrangler_path}[/green]")
        else:
            console.print("Wrangler/Npx: [red]NOT FOUND[/red]")
            console.print("[yellow]Some features will not work without it.[/yellow]")
            console.print(
                "[dim]  Hint: Install Node.js and Wrangler (npm install -g wrangler)[/dim]"
            )

        async with get_app_context() as ctx:
            console.print(f"Account ID: [green]{ctx.config.account_id}[/green]")

            # 1. Verify Token (Sync via validation.py)
            console.print("Checking API Token...", end=" ")
            token_valid = False

            # Create a Sync Client just for validation reuse
            sync_client = Client(api_token=ctx.config.api_token.get_secret_value())

            try:
                token_id = verify_token(sync_client.user.tokens)
                console.print(f"[green]VALID[/green] (id: {token_id})")
                token_valid = True
            except Exception as e:
                console.print(f"[yellow]WARN[/yellow] (Verify failed: {e})")
                console.print("  [dim]Falling back to functional check...[/dim]", end=" ")

            # 2. Check Permissions (Sync via validation.py)
            if token_valid and token_id:
                try:
                    check_token_permissions(sync_client.user.tokens, token_id)
                    console.print("Token has all required permissions.", style="green")
                except ValueError as e:
                    console.print(f"[yellow]WARN: {e}[/yellow]")
                    console.print("  [dim]Some functionality may be restricted.[/dim]")
                    console.print("  [dim]Required permissions:[/dim]")
                    for perm in WORKER_PERMISSIONS:
                        console.print(f"  [dim]  - {perm}[/dim]")
                except Exception as e:
                    if "403" in str(e) or "9109" in str(e):
                        console.print(
                            "[yellow]WARN: Could not fetch permissions[/yellow] "
                            "[dim](requires 'User -> API Tokens -> Read')[/dim]"
                        )
                    else:
                        console.print(f"[yellow]WARN: Check failed: {e}[/yellow]")

            # 3. Functional Check (Async via WorkerService)
            console.print("Checking Workers Subdomain...", end=" ")
            try:
                sub = await ctx.service.ensure_subdomain()
                console.print(f"[green]FOUND[/green] ({sub}.workers.dev)")
                if not token_valid:
                    console.print(
                        "  [green]Functional check passed (Token works for Workers)[/green]"
                    )
            except SubdomainMissingError:
                console.print("[red]MISSING[/red]")
                console.print(
                    "[yellow]Please configure a subdomain in Cloudflare Dashboard.[/yellow]"
                )
            except Exception as e:
                console.print(f"[red]ERROR[/red] ({e})")
                if not token_valid:
                    # If both verify and functional check failed, it's likely invalid
                    raise ConfigError(f"Token verification failed: {e}") from e

    try:
        asyncio.run(_verify_async())
    except ConfigError:
        raise
    except Exception as e:
        raise ConfigError(f"Verification failed: {e}") from e


@config_app.command()
def show() -> None:
    """Display the current Proxyflare configuration."""
    try:
        config = Config()  # type: ignore[call-arg]
        console.print(config)
    except ValidationError as e:
        handle_validation_error(e)
        raise ConfigError("Configuration validation failed.") from e
    except Exception as e:
        raise ConfigError(f"Configuration error: {e}") from e
