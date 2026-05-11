"""Utility functions for managing worker artifacts."""

import shutil
import subprocess
import sys
from pathlib import Path

__all__ = [
    "build_rust_worker",
]


def build_rust_worker(verbose: bool = True) -> bool:
    """
    Build the Rust worker using the project's build script.
    Returns True if successful.
    """
    if verbose:
        from proxyflare.cli.console import console

    if verbose:
        console.print("Building Rust worker...", style="dim")

    if not shutil.which("cargo"):
        if verbose:
            console.print("Cargo not found. Skipping Rust worker build.", style="yellow")
        return False

    package_root = Path(__file__).parent.parent
    script_path = package_root / "scripts" / "build_rust.py"

    if not script_path.exists():
        if verbose:
            console.print(f"Build script not found at {script_path}", style="yellow")
        return False

    try:
        subprocess.run([sys.executable, str(script_path)], check=True)
        return True
    except subprocess.CalledProcessError as e:
        if verbose:
            console.print(f"Failed to build Rust worker: {e}", style="red")
        return False
