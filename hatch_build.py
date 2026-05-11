import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import (  # ty:ignore[unresolved-import]
    BuildHookInterface,
)


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        project_root = Path.cwd()

        # Explicit opt-out
        if os.environ.get("SKIP_RUST_BUILD"):
            print("SKIP_RUST_BUILD set — skipping Rust worker build.")  # noqa: T201
            return

        # Pre-built artifacts are committed to the repo; no need to rebuild.
        wasm_artifact = (
            project_root / "src" / "proxyflare" / "workers" / "rust" / "build" / "index_bg.wasm"
        )
        if wasm_artifact.exists():
            print("Pre-built Rust artifacts found — skipping Rust worker build.")  # noqa: T201
            return

        print("Running CustomBuildHook to build Rust worker...")  # noqa: T201
        script_path = project_root / "src" / "proxyflare" / "scripts" / "build_rust.py"

        if not script_path.exists():
            print(f"Warning: Rust build script not found at {script_path}. Skipping.")  # noqa: T201
            return

        try:
            print(f"Executing: {sys.executable} {script_path}")  # noqa: T201
            subprocess.run([sys.executable, str(script_path)], check=True, cwd=str(project_root))  # noqa: S603
            print("Build hook complete.")  # noqa: T201
        except subprocess.CalledProcessError as e:
            print(f"Error in build hook (Rust compilation failed): {e}")  # noqa: T201
            print("Please check the output above for Rust/Cargo errors.")  # noqa: T201
            print("Ensure Rust is installed (https://rustup.rs/) and you have network access.")  # noqa: T201
            raise RuntimeError("Rust worker build failed") from e
        except Exception as e:
            print(f"Unexpected error in build hook: {e}")  # noqa: T201
            raise RuntimeError("Unexpected build hook error") from e
