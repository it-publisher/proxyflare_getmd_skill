import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from hatchling.builders.hooks.plugin.interface import (  # ty:ignore[unresolved-import]
    BuildHookInterface,
)

RUST_DIR = Path("src/proxyflare/workers/rust")
BUILD_SCRIPT = Path("src/proxyflare/scripts/build_rust.py")


def is_rust_build_current(rust_dir: Path) -> bool:
    """Tell whether the WASM artifact exists and is newer than every Rust source."""
    wasm_artifact = rust_dir / "build" / "index_bg.wasm"
    if not wasm_artifact.exists():
        return False

    sources = [*(rust_dir / "src").rglob("*.rs"), rust_dir / "Cargo.toml", rust_dir / "Cargo.lock"]
    newest_source_mtime = max(source.stat().st_mtime for source in sources)
    return wasm_artifact.stat().st_mtime >= newest_source_mtime


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if os.environ.get("SKIP_RUST_BUILD"):
            print("SKIP_RUST_BUILD set — skipping Rust worker build.")
            return

        project_root = Path(self.root)
        if is_rust_build_current(project_root / RUST_DIR):
            print("Rust worker artifacts are up to date — skipping build.")
            return

        print("Building Rust worker...")
        result = subprocess.run(
            [sys.executable, str(project_root / BUILD_SCRIPT)],
            cwd=project_root,
            check=False,
        )
        if result.returncode == 0:
            return

        if os.environ.get("REQUIRE_RUST_BUILD"):
            raise RuntimeError("Rust worker build failed and REQUIRE_RUST_BUILD is set")

        # JS workers need no toolchain, so a missing one must not block the whole install
        print("WARNING: Rust worker build failed. `pf create --type rust` will not work.")
