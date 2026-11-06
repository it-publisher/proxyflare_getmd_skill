import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import hatch_build
from hatch_build import CustomBuildHook, is_rust_build_current


def make_rust_sources(rust_dir: Path) -> None:
    (rust_dir / "src").mkdir(parents=True)
    for name in ("src/lib.rs", "Cargo.toml", "Cargo.lock"):
        (rust_dir / name).touch()
        os.utime(rust_dir / name, (100, 100))


def make_wasm(rust_dir: Path, mtime: int) -> None:
    (rust_dir / "build").mkdir(exist_ok=True)
    wasm = rust_dir / "build" / "index_bg.wasm"
    wasm.touch()
    os.utime(wasm, (mtime, mtime))


@pytest.fixture
def rust_dir(tmp_path):
    path = tmp_path / hatch_build.RUST_DIR
    make_rust_sources(path)
    return path


@pytest.fixture
def hook(tmp_path, monkeypatch):
    monkeypatch.delenv("SKIP_RUST_BUILD", raising=False)
    monkeypatch.delenv("REQUIRE_RUST_BUILD", raising=False)
    return CustomBuildHook(str(tmp_path), {}, MagicMock(), MagicMock(), "", "wheel")


def run_hook(hook, returncode=0):
    with patch.object(hatch_build.subprocess, "run") as mock_run:
        mock_run.return_value = MagicMock(returncode=returncode)
        hook.initialize("standard", {})
    return mock_run


def test_build_is_not_current_without_artifact(rust_dir):
    assert is_rust_build_current(rust_dir) is False


def test_build_is_current_when_artifact_is_newer(rust_dir):
    make_wasm(rust_dir, mtime=200)
    assert is_rust_build_current(rust_dir) is True


def test_build_is_stale_when_source_is_newer(rust_dir):
    make_wasm(rust_dir, mtime=50)
    assert is_rust_build_current(rust_dir) is False


def test_skip_env_avoids_build(hook, rust_dir, monkeypatch):
    monkeypatch.setenv("SKIP_RUST_BUILD", "1")
    assert run_hook(hook).call_count == 0


def test_current_artifact_avoids_build(hook, rust_dir):
    make_wasm(rust_dir, mtime=200)
    assert run_hook(hook).call_count == 0


def test_missing_artifact_triggers_build(hook, rust_dir, tmp_path):
    mock_run = run_hook(hook)
    assert mock_run.call_args.args[0][-1] == str(tmp_path / hatch_build.BUILD_SCRIPT)


def test_failed_build_only_warns_by_default(hook, rust_dir, capsys):
    run_hook(hook, returncode=1)
    assert "WARNING" in capsys.readouterr().out


def test_failed_build_raises_when_required(hook, rust_dir, monkeypatch):
    monkeypatch.setenv("REQUIRE_RUST_BUILD", "1")
    with pytest.raises(RuntimeError, match="REQUIRE_RUST_BUILD"):
        run_hook(hook, returncode=1)
