import secrets
import string
import time
from importlib import resources
from typing import Any

from cloudflare import AsyncCloudflare
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from proxyflare.constants import (
    COMPATIBILITY_DATE,
    CONTENT_TYPES,
    WORKER_META,
    WorkerMeta,
    WorkerType,
)
from proxyflare.cors import CORS_HEADERS
from proxyflare.exceptions import SubdomainMissingError
from proxyflare.models.deployment import DeploymentConfig

__all__ = ["WorkerService"]

RUST_BUILD_HINT = (
    "Install rustup (https://rustup.rs), run `rustup target add wasm32-unknown-unknown`, "
    "then reinstall from the repository root: `uv tool install --force .`\n"
    "Or use a worker that needs no build: `--type js`."
)


class WorkerService:
    """Service for managing Cloudflare Workers deployments."""

    def __init__(
        self, client: AsyncCloudflare, account_id: str, worker_prefix: str = "proxyflare"
    ) -> None:
        """
        Initialize the WorkerService.

        Args:
            client: AsyncCloudflare client instance.
            account_id: Cloudflare account ID.
            worker_prefix: Prefix for worker names to isolate resources.
        """
        self.client = client
        self.account_id = account_id
        self.worker_prefix = worker_prefix
        self._subdomain: str | None = None

    async def ensure_subdomain(self) -> str:
        """
        Check that a workers.dev subdomain exists for the account.
        Raises RuntimeError if not configured — never auto-provisions.
        """
        if self._subdomain:
            return self._subdomain

        try:
            subdomain_info = await self.client.workers.subdomains.get(account_id=self.account_id)
            if subdomain_info and subdomain_info.subdomain:
                self._subdomain = subdomain_info.subdomain
                return self._subdomain
        except Exception as e:
            logger.debug(f"Could not get subdomain: {e}")

        raise SubdomainMissingError(
            "Workers.dev subdomain is not configured for this account.\n"
            "Please set it up manually in the Cloudflare dashboard:\n"
            "  Workers & Pages → Overview → Change subdomain"
        )

    def generate_worker_name(self) -> str:
        """
        Generate a unique name for a new worker using the configured prefix.

        Returns:
            A string containing the worker name.
        """
        timestamp = str(int(time.time()))
        random_suffix = "".join(secrets.choice(string.ascii_lowercase) for _ in range(6))
        return f"{self.worker_prefix}-{timestamp}-{random_suffix}"

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
    async def deploy_worker(
        self,
        config: DeploymentConfig,
    ) -> str:
        """
        Deploy a worker script and its metadata to Cloudflare.

        Args:
            config: The deployment configuration (name, script, type, wasm).

        Returns:
            The public URL of the deployed worker.

        Raises:
            RuntimeError: If deployment fails.
        """
        meta = WORKER_META[config.worker_type]

        # Prepare Bindings (CORS)
        # We transform headers into environment variables for the worker
        bindings = [
            {
                "type": "plain_text",
                "name": "CORS_ORIGIN",
                "text": CORS_HEADERS["Access-Control-Allow-Origin"],
            },
            {
                "type": "plain_text",
                "name": "CORS_METHODS",
                "text": CORS_HEADERS["Access-Control-Allow-Methods"],
            },
            {
                "type": "plain_text",
                "name": "CORS_ALLOWED_HEADERS",
                "text": CORS_HEADERS["Access-Control-Allow-Headers"],
            },
        ]

        metadata: dict[str, Any] = {
            "main_module": meta.main_module,
            "bindings": bindings,
            "compatibility_date": COMPATIBILITY_DATE,
            "compatibility_flags": list(meta.compatibility_flags),
        }

        files: dict[str, tuple[str, bytes, str]] = {}

        # Determine content type based on worker type
        content_type = CONTENT_TYPES.get(config.worker_type, "application/javascript")

        files[meta.main_module] = (
            meta.main_module,
            config.script_content.encode("utf-8"),
            content_type,
        )

        if config.wasm_content and meta.wasm_file:
            files[meta.wasm_file] = (
                meta.wasm_file,
                config.wasm_content,
                CONTENT_TYPES.get("wasm", "application/wasm"),
            )

        try:
            await self.client.workers.scripts.update(
                account_id=self.account_id,
                script_name=config.name,
                metadata=metadata,  # ty: ignore[invalid-argument-type]
                files=files,  # ty: ignore[invalid-argument-type]
            )

            await self.client.workers.scripts.subdomain.create(
                account_id=self.account_id, script_name=config.name, enabled=True
            )

            subdomain = await self.ensure_subdomain()
            return f"https://{config.name}.{subdomain}.workers.dev"

        except Exception as e:
            logger.error(f"Deployment failed: {e}")
            raise RuntimeError(f"Deployment failed: {e}") from e

    async def list_workers(self) -> list[dict[str, Any]]:
        """
        List all Cloudflare Workers belonging to the current prefix.

        Returns:
            A list of dictionaries containing worker metadata (id, created_on, etc.).

        Raises:
            RuntimeError: If the Cloudflare API call fails.
        """
        try:
            response = await self.client.workers.scripts.list(account_id=self.account_id)
            workers = []
            for script in response.result:
                if not script.id or not script.id.startswith(f"{self.worker_prefix}-"):
                    continue
                workers.append(
                    {
                        "id": script.id,
                        "created_on": getattr(script, "created_on", None),
                        "modified_on": getattr(script, "modified_on", None),
                        "usage_model": getattr(script, "usage_model", None),
                    }
                )
            return workers
        except Exception as e:
            logger.error(f"Failed to list workers: {e}")
            raise RuntimeError(f"Failed to list workers: {e}") from e

    async def delete_worker(self, name: str) -> None:
        """
        Delete a specific worker by name.

        Args:
            name: The name of the worker to delete.

        Raises:
            ValueError: If the worker name does not match the configured prefix.
            RuntimeError: If the Cloudflare API call fails.
        """
        if not name.startswith(f"{self.worker_prefix}-"):
            raise ValueError(
                f"Worker '{name}' does not belong to this proxyflare instance "
                f"(prefix: '{self.worker_prefix}-'). Deletion denied."
            )
        try:
            await self.client.workers.scripts.delete(
                script_name=name, account_id=self.account_id, force=True
            )
        except Exception as e:
            logger.error(f"Failed to delete worker {name}: {e}")
            raise RuntimeError(f"Failed to delete worker {name}: {e}") from e

    def _get_resource_source(
        self, worker_type: WorkerType, meta: WorkerMeta
    ) -> tuple[bytes | None, bytes | None]:
        """
        Attempt to load worker source code from the package's bundled resources.

        Args:
            worker_type: The type of worker.
            meta: Metadata for the worker type.

        Returns:
            A tuple of (script_content, wasm_content) in bytes, or None if not found.
        """
        pkg_name = f"proxyflare.workers.{worker_type}"
        if worker_type == "rust":
            pkg_name = "proxyflare.workers.rust.build"

        try:
            pkg = resources.files(pkg_name)
            # Rust uses index.js in build folder, others use meta.source_file
            filename = "index.js" if worker_type == "rust" else meta.source_file
            script_content = pkg.joinpath(filename).read_bytes()
        except (KeyError, ModuleNotFoundError, FileNotFoundError):
            return None, None

        wasm_content = None
        if worker_type == "rust" and meta.wasm_file:
            try:
                wasm_content = pkg.joinpath(meta.wasm_file).read_bytes()
            except FileNotFoundError:
                pass

        return script_content, wasm_content

    def get_worker_source(self, worker_type: WorkerType) -> tuple[str, bytes | None]:
        """
        Retrieve the source code and optional WASM content for a worker.

        Checks the package resources for the built artifacts.

        Args:
            worker_type: The type of worker to retrieve.

        Returns:
            A tuple of (script_content_str, wasm_content_bytes).

        Raises:
            ValueError: If the worker type is unknown.
            FileNotFoundError: If the worker source cannot be found.
        """
        if worker_type not in WORKER_META:
            raise ValueError(f"Unknown worker type: {worker_type}")

        meta = WORKER_META[worker_type]

        script_bytes, wasm_bytes = self._get_resource_source(worker_type, meta)

        if script_bytes is None:
            hint = (
                RUST_BUILD_HINT
                if worker_type == "rust"
                else "Please assure the package was correctly built and installed."
            )
            raise FileNotFoundError(
                f"Worker source for '{worker_type}' not found in package resources.\n{hint}"
            )

        if worker_type == "rust" and wasm_bytes is None:
            raise FileNotFoundError(
                f"Rust worker WASM artifact not found in package resources.\n{RUST_BUILD_HINT}"
            )

        return script_bytes.decode("utf-8"), wasm_bytes
