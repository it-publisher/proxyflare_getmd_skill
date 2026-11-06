from pydantic import BaseModel, Field

from proxyflare.constants import WorkerType

__all__ = ["DeploymentConfig"]


class DeploymentConfig(BaseModel):
    """Configuration for deploying a worker."""

    name: str
    script_content: str
    worker_type: WorkerType
    key: str = Field(repr=False)
    wasm_content: bytes | None = None
