from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from cloudflare import AuthenticationError, NotFoundError
from tenacity import wait_none

from proxyflare.exceptions import SubdomainMissingError
from proxyflare.models.deployment import DeploymentConfig
from proxyflare.services.worker import WorkerService


def make_api_error(error_class, status):
    response = httpx.Response(status, request=httpx.Request("GET", "https://api.test"))
    return error_class("API error", response=response, body=None)


@pytest.fixture
def mock_client():
    client = AsyncMock()
    return client


@pytest.fixture
def service(mock_client):
    return WorkerService(mock_client, "test-account", "proxyflare")


# --- ensure_subdomain ---


async def test_ensure_subdomain_cached(service):
    service._subdomain = "cached-subdomain"
    assert await service.ensure_subdomain() == "cached-subdomain"
    service.client.workers.subdomains.get.assert_not_called()


async def test_ensure_subdomain_success(service, mock_client):
    mock_client.workers.subdomains.get.return_value.subdomain = "existing-subdomain"
    assert await service.ensure_subdomain() == "existing-subdomain"
    mock_client.workers.subdomains.get.assert_called_once_with(account_id="test-account")


async def test_ensure_subdomain_not_configured(service, mock_client):
    """Should raise SubdomainMissingError instead of auto-provisioning."""
    mock_client.workers.subdomains.get.side_effect = make_api_error(NotFoundError, 404)

    with pytest.raises(SubdomainMissingError, match="subdomain is not configured"):
        await service.ensure_subdomain()

    # Must NOT attempt to create/update a subdomain
    mock_client.workers.subdomains.update.assert_not_called()


async def test_ensure_subdomain_does_not_hide_other_api_errors(service, mock_client):
    """A rejected token must not be reported as a missing subdomain."""
    mock_client.workers.subdomains.get.side_effect = make_api_error(AuthenticationError, 401)

    with pytest.raises(AuthenticationError):
        await service.ensure_subdomain()


async def test_ensure_subdomain_empty_result(service, mock_client):
    """Should raise SubdomainMissingError when API returns empty subdomain."""
    mock_client.workers.subdomains.get.return_value.subdomain = None

    with pytest.raises(SubdomainMissingError, match="subdomain is not configured"):
        await service.ensure_subdomain()

    mock_client.workers.subdomains.update.assert_not_called()


# --- generate_worker_name ---


def test_generate_worker_name_uses_prefix(service):
    name = service.generate_worker_name()
    assert name.startswith("proxyflare-")


def test_generate_worker_name_custom_prefix(mock_client):
    svc = WorkerService(mock_client, "test-account", "myprefix")
    name = svc.generate_worker_name()
    assert name.startswith("myprefix-")


# --- deploy_worker ---


async def test_deploy_worker_rust(service, mock_client):
    service.ensure_subdomain = AsyncMock(return_value="test-sub")

    config = DeploymentConfig(
        name="rust-worker",
        script_content="shim",
        worker_type="rust",
        key="test-key",
        wasm_content=b"wasmbytes",
    )
    await service.deploy_worker(config)

    _, kwargs = mock_client.workers.scripts.update.call_args
    assert kwargs["metadata"]["main_module"] == "worker.js"
    assert kwargs["files"]["worker.js"] == (
        "worker.js",
        b"shim",
        "application/javascript+module",
    )
    assert kwargs["files"]["index_bg.wasm"] == (
        "index_bg.wasm",
        b"wasmbytes",
        "application/wasm",
    )


async def test_deploy_worker_failure(service, mock_client, monkeypatch):
    monkeypatch.setattr(WorkerService.deploy_worker.retry, "wait", wait_none())
    service.ensure_subdomain = AsyncMock(return_value="test-sub")
    mock_client.workers.scripts.update.side_effect = Exception("Deploy Error")

    config = DeploymentConfig(
        name="test",
        script_content="content",
        worker_type="js",
        key="test-key",
    )
    with pytest.raises(RuntimeError, match="Deployment failed: Deploy Error"):
        await service.deploy_worker(config)
    assert mock_client.workers.scripts.update.call_count == 3


# --- list_workers ---


async def test_list_workers_filters_by_prefix(service, mock_client):
    """Only workers matching the prefix should be returned."""
    pf_worker = MagicMock()
    pf_worker.id = "proxyflare-123-abc"
    pf_worker.created_on = "2024-01-01"
    pf_worker.modified_on = "2024-01-02"
    pf_worker.usage_model = "bundled"

    other_worker = MagicMock()
    other_worker.id = "my-other-worker"
    other_worker.created_on = "2024-01-03"
    other_worker.modified_on = "2024-01-04"
    other_worker.usage_model = "standard"

    response = MagicMock()
    response.result = [pf_worker, other_worker]
    mock_client.workers.scripts.list.return_value = response

    result = await service.list_workers()

    assert len(result) == 1
    assert result[0]["id"] == "proxyflare-123-abc"
    mock_client.workers.scripts.list.assert_called_once_with(account_id="test-account")


async def test_list_workers_custom_prefix(mock_client):
    svc = WorkerService(mock_client, "test-account", "custom")

    w1 = MagicMock()
    w1.id = "custom-worker1"
    w2 = MagicMock()
    w2.id = "proxyflare-worker2"

    response = MagicMock()
    response.result = [w1, w2]
    mock_client.workers.scripts.list.return_value = response

    result = await svc.list_workers()
    assert len(result) == 1
    assert result[0]["id"] == "custom-worker1"


async def test_list_workers_empty_after_filter(service, mock_client):
    other = MagicMock()
    other.id = "unrelated-worker"
    response = MagicMock()
    response.result = [other]
    mock_client.workers.scripts.list.return_value = response

    assert await service.list_workers() == []


async def test_list_workers_failure(service, mock_client):
    mock_client.workers.scripts.list.side_effect = Exception("List Error")

    with pytest.raises(RuntimeError, match="Failed to list workers"):
        await service.list_workers()


# --- delete_worker ---


async def test_delete_worker_success(service, mock_client):
    await service.delete_worker("proxyflare-test-worker")
    mock_client.workers.scripts.delete.assert_called_once_with(
        script_name="proxyflare-test-worker", account_id="test-account", force=True
    )


async def test_delete_worker_rejects_foreign(service):
    """Must refuse to delete workers that don't match the prefix."""
    with pytest.raises(ValueError, match="does not belong"):
        await service.delete_worker("some-other-worker")


async def test_delete_worker_rejects_foreign_custom_prefix(mock_client):
    svc = WorkerService(mock_client, "test-account", "myapp")
    with pytest.raises(ValueError, match="does not belong"):
        await svc.delete_worker("proxyflare-old-worker")


async def test_delete_worker_already_gone(service, mock_client):
    mock_client.workers.scripts.delete.side_effect = make_api_error(NotFoundError, 404)
    await service.delete_worker("proxyflare-test")


async def test_delete_worker_failure(service, mock_client):
    mock_client.workers.scripts.delete.side_effect = Exception("Delete Error")

    with pytest.raises(RuntimeError, match="Failed to delete worker"):
        await service.delete_worker("proxyflare-test")


# --- deploy_worker (JS) ---


async def test_deploy_worker_js(service, mock_client):
    service.ensure_subdomain = AsyncMock(return_value="test-sub")

    config = DeploymentConfig(
        name="js-worker",
        script_content="addEventListener('fetch'...)",
        worker_type="js",
        key="secret-key",
    )
    url = await service.deploy_worker(config)

    assert url == "https://js-worker.test-sub.workers.dev"

    _, kwargs = mock_client.workers.scripts.update.call_args
    assert kwargs["account_id"] == "test-account"
    assert kwargs["script_name"] == "js-worker"
    assert kwargs["metadata"]["main_module"] == "worker.js"
    assert kwargs["files"]["worker.js"] == (
        "worker.js",
        b"addEventListener('fetch'...)",
        "application/javascript+module",
    )
    assert kwargs["metadata"]["bindings"] == [
        {"type": "secret_text", "name": "PROXYFLARE_KEY", "text": "secret-key"}
    ]
    mock_client.workers.scripts.subdomain.create.assert_called_once_with(
        account_id="test-account", script_name="js-worker", enabled=True
    )
