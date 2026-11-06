"""Pydantic models for worker result JSON files."""

from pathlib import Path

from pydantic import BaseModel, Field, RootModel

from proxyflare.constants import WorkerType

__all__ = ["WorkerRecord", "WorkerResultFile"]

OWNER_ONLY_MODE = 0o600


class WorkerRecord(BaseModel):
    """A single worker deployment record."""

    name: str
    url: str
    type: WorkerType
    created_at: float
    key: str = Field(repr=False)


class WorkerResultFile(RootModel[list[WorkerRecord]]):
    """Typed model for proxyflare-workers.json — a list of WorkerRecord entries."""

    def save(self, path: Path) -> None:
        """Write the file readable only by its owner, because it holds worker keys."""
        path.touch(mode=OWNER_ONLY_MODE, exist_ok=True)
        path.chmod(OWNER_ONLY_MODE)
        path.write_text(self.model_dump_json(indent=2), encoding="utf-8")
