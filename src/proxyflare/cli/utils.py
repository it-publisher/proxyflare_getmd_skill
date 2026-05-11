from pydantic import ValidationError

from proxyflare.cli.console import err_console

__all__ = ["handle_validation_error"]


def handle_validation_error(e: ValidationError) -> None:
    err_console.print("[bold red]Configuration Error:[/bold red]")
    for error in e.errors():
        field_name = ".".join(str(loc) for loc in error["loc"]) or "Global Config"
        message = error["msg"]
        input_value = error.get("input")
        err_console.print(
            f"  Field [bold]{field_name}[/bold]: {message} "
            f"(Invalid Value: [red]{input_value!r}[/red])"
        )
