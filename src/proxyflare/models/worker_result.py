"""Pydantic models for worker result JSON files."""

from pydantic import BaseModel, RootModel

from proxyflare.constants import WorkerType

__all__ = ["WorkerRecord", "WorkerResultFile"]


class WorkerRecord(BaseModel):
    """A single worker deployment record."""

    name: str
    url: str
    type: WorkerType
    created_at: float


class WorkerResultFile(RootModel[list[WorkerRecord]]):
    """Typed model for proxyflare-workers.json — a list of WorkerRecord entries."""
