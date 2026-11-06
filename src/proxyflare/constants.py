from dataclasses import dataclass
from typing import Literal

__all__ = [
    "COMPATIBILITY_DATE",
    "CONTENT_TYPES",
    "DEFAULT_DEPLOY_CONCURRENCY",
    "DEFAULT_WORKER_TYPE",
    "WORKER_ERROR_HEADER",
    "WORKER_KEY_BINDING",
    "WORKER_KEY_BYTES",
    "WORKER_KEY_HEADER",
    "WORKER_META",
    "WORKER_PROPAGATION_SECONDS",
    "WORKER_TYPES",
    "WorkerMeta",
    "WorkerType",
]

# Cloudflare
# The Rust worker imports WorkerEntrypoint, which needs a date newer than early 2024
COMPATIBILITY_DATE = "2025-05-11"

# Worker Types
WorkerType = Literal["rust", "js"]
WORKER_TYPES: set[WorkerType] = {"rust", "js"}
DEFAULT_WORKER_TYPE: WorkerType = "js"

# Worker authentication, see docs/worker-contract.md
WORKER_KEY_HEADER = "X-Proxyflare-Key"
WORKER_KEY_BINDING = "PROXYFLARE_KEY"
WORKER_KEY_BYTES = 32
WORKER_ERROR_HEADER = "X-Proxyflare-Error"

# Defaults
DEFAULT_DEPLOY_CONCURRENCY = 5
# Measured: locations mixed 404 and 500 with normal answers for up to about 15 seconds
WORKER_PROPAGATION_SECONDS = 30


@dataclass(frozen=True)
class WorkerMeta:
    """Metadata describing how a worker type is deployed to Cloudflare."""

    main_module: str
    source_file: str
    wasm_file: str | None = None


WORKER_META: dict[WorkerType, WorkerMeta] = {
    "js": WorkerMeta(
        main_module="worker.js",
        source_file="worker.js",
    ),
    "rust": WorkerMeta(
        main_module="worker.js",
        source_file="index.js",
        wasm_file="index_bg.wasm",
    ),
}

CONTENT_TYPES: dict[str, str] = {
    "js": "application/javascript+module",
    "rust": "application/javascript+module",
    "wasm": "application/wasm",
}
