from unittest.mock import MagicMock, patch

import pytest

from proxyflare.services.worker import WorkerService


@pytest.fixture
def service():
    client = MagicMock()
    return WorkerService(client, "test-account")


def test_get_worker_source_resources(service):
    """Test that it loads from resources correctly."""

    with patch("proxyflare.services.worker.resources") as MockResources:
        # Resource simulation
        mock_pkg = MagicMock()
        MockResources.files.return_value = mock_pkg
        mock_resource_file = mock_pkg.joinpath.return_value
        mock_resource_file.read_bytes.return_value = b"resource_content"

        # Execute
        content, wasm = service.get_worker_source("js")

        # Verify
        assert content == "resource_content"
        assert wasm is None
        MockResources.files.assert_called_with("proxyflare.workers.js")
        mock_pkg.joinpath.assert_called_with("worker.js")


def test_get_worker_source_rust_resources(service):
    """Test Rust worker retrieval (shim + wasm) from resources."""
    with patch("proxyflare.services.worker.resources") as MockResources:
        mock_pkg = MagicMock()
        MockResources.files.return_value = mock_pkg

        mock_shim = MagicMock()
        mock_shim.read_bytes.return_value = b"rust_shim"

        mock_wasm = MagicMock()
        mock_wasm.read_bytes.return_value = b"rust_wasm_bytes"

        def safe_joinpath(other):
            if other == "index.js":
                return mock_shim
            if other == "index_bg.wasm":
                return mock_wasm
            return MagicMock()

        mock_pkg.joinpath.side_effect = safe_joinpath

        # Exec
        content, wasm = service.get_worker_source("rust")

        # Verify
        assert content == "rust_shim"
        assert wasm == b"rust_wasm_bytes"
        MockResources.files.assert_called_with("proxyflare.workers.rust.build")


def test_get_worker_source_not_found(service):
    """Test that it raises FileNotFoundError if resources are missing."""
    with patch("proxyflare.services.worker.resources") as MockResources:
        MockResources.files.side_effect = FileNotFoundError

        with pytest.raises(FileNotFoundError, match="not found in package resources"):
            service.get_worker_source("js")


def test_get_worker_source_rust_missing_wasm(service):
    """Test that it raises FileNotFoundError if Rust wasm is missing."""
    with patch("proxyflare.services.worker.resources") as MockResources:
        mock_pkg = MagicMock()
        MockResources.files.return_value = mock_pkg

        mock_shim = MagicMock()
        mock_shim.read_bytes.return_value = b"rust_shim"

        def safe_joinpath(other):
            if other == "index.js":
                return mock_shim
            if other == "index_bg.wasm":
                mock_wasm = MagicMock()
                mock_wasm.read_bytes.side_effect = FileNotFoundError("Missing file")
                return mock_wasm
            return MagicMock()

        mock_pkg.joinpath.side_effect = safe_joinpath

        with pytest.raises(FileNotFoundError) as exc_info:
            service.get_worker_source("rust")

        assert "Rust worker WASM artifact not found in package resources" in str(exc_info.value)
