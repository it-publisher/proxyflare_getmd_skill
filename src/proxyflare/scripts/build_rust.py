#!/usr/bin/env python3
"""Build the Rust worker with a pinned worker-build version."""

import shutil
import subprocess
import sys
from pathlib import Path

# worker-build rejects crate versions it doesn't support, so an unpinned install breaks the build
# as soon as a new release appears. Keep in sync with workers/rust/wrangler.toml.
WORKER_BUILD_VERSION = "0.8.1"

RUST_DIR = Path(__file__).parent.parent / "workers" / "rust"
LOCAL_TOOL_ROOT = RUST_DIR / "target" / "tools"


def has_pinned_version(command: Path) -> bool:
    result = subprocess.run(
        [str(command), "--version"], capture_output=True, text=True, check=False
    )
    return result.returncode == 0 and WORKER_BUILD_VERSION in result.stdout.split()


def find_worker_build() -> Path | None:
    """Return an installed worker-build of the pinned version, if there is one."""
    on_path = shutil.which("worker-build")
    candidates = [
        Path(on_path) if on_path else None,
        Path.home() / ".cargo" / "bin" / "worker-build",
        LOCAL_TOOL_ROOT / "bin" / "worker-build",
    ]
    for candidate in candidates:
        if candidate and candidate.exists() and has_pinned_version(candidate):
            return candidate
    return None


def ensure_worker_build() -> Path:
    """Find worker-build or install it next to the build, leaving the user's copy untouched."""
    installed = find_worker_build()
    if installed:
        return installed

    print(f"Installing worker-build {WORKER_BUILD_VERSION}...")
    subprocess.run(
        [
            "cargo",
            "install",
            "--quiet",
            "--locked",
            "--version",
            WORKER_BUILD_VERSION,
            "--root",
            str(LOCAL_TOOL_ROOT),
            "worker-build",
        ],
        check=True,
    )
    return LOCAL_TOOL_ROOT / "bin" / "worker-build"


def main() -> int:
    try:
        worker_build = ensure_worker_build()
        print(f"Running {worker_build}...")
        subprocess.run([str(worker_build), "--release"], cwd=RUST_DIR, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(f"\nError building Rust worker: {e}", file=sys.stderr)
        print(
            "Requirements: rustup (https://rustup.rs) and "
            "`rustup target add wasm32-unknown-unknown`.",
            file=sys.stderr,
        )
        return 1

    print("Build successful!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
