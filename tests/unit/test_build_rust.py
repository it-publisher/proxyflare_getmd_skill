import subprocess
import tomllib
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from proxyflare.scripts import build_rust


def make_tool(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


def fake_version(version: str) -> MagicMock:
    return MagicMock(returncode=0, stdout=f"{version}\n")


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    """Point the script at empty directories so the real toolchain is never seen."""
    monkeypatch.setattr(build_rust.Path, "home", lambda: tmp_path / "home")
    monkeypatch.setattr(build_rust, "LOCAL_TOOL_ROOT", tmp_path / "tools")
    monkeypatch.setattr(build_rust, "RUST_DIR", tmp_path / "rust")
    monkeypatch.setattr(build_rust.shutil, "which", lambda _: None)
    return tmp_path


def test_uses_existing_tool_with_pinned_version(isolated_paths):
    tool = make_tool(isolated_paths / "home" / ".cargo" / "bin" / "worker-build")

    with patch.object(build_rust.subprocess, "run") as mock_run:
        mock_run.return_value = fake_version(build_rust.WORKER_BUILD_VERSION)
        assert build_rust.ensure_worker_build() == tool

    assert mock_run.call_count == 1  # only the version check, no cargo install


def test_installs_pinned_version_locally_when_existing_tool_differs(isolated_paths):
    make_tool(isolated_paths / "home" / ".cargo" / "bin" / "worker-build")

    with patch.object(build_rust.subprocess, "run") as mock_run:
        mock_run.return_value = fake_version("0.0.1")
        tool = build_rust.ensure_worker_build()

    assert tool == isolated_paths / "tools" / "bin" / "worker-build"
    install_command = mock_run.call_args.args[0]
    assert install_command[:2] == ["cargo", "install"]
    assert build_rust.WORKER_BUILD_VERSION in install_command
    assert "--locked" in install_command
    assert str(isolated_paths / "tools") in install_command


def test_main_returns_error_when_cargo_is_missing(isolated_paths, capsys):
    with patch.object(build_rust.subprocess, "run", side_effect=FileNotFoundError("cargo")):
        assert build_rust.main() == 1
    assert "rustup target add wasm32-unknown-unknown" in capsys.readouterr().err


def test_main_returns_error_when_build_fails(isolated_paths):
    make_tool(isolated_paths / "tools" / "bin" / "worker-build")

    def run(command, **_kwargs):
        if "--release" in command:
            raise subprocess.CalledProcessError(1, command)
        return fake_version(build_rust.WORKER_BUILD_VERSION)

    with patch.object(build_rust.subprocess, "run", side_effect=run):
        assert build_rust.main() == 1


def test_main_builds_in_rust_dir(isolated_paths):
    make_tool(isolated_paths / "tools" / "bin" / "worker-build")

    with patch.object(build_rust.subprocess, "run") as mock_run:
        mock_run.return_value = fake_version(build_rust.WORKER_BUILD_VERSION)
        assert build_rust.main() == 0

    assert mock_run.call_args.kwargs["cwd"] == isolated_paths / "rust"
    assert mock_run.call_args.args[0][-1] == "--release"


def test_wrangler_config_pins_the_same_version():
    wrangler_config = tomllib.loads((build_rust.RUST_DIR / "wrangler.toml").read_text())
    assert f"--version {build_rust.WORKER_BUILD_VERSION} " in wrangler_config["build"]["command"]
