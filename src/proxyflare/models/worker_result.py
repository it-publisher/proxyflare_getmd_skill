"""Pydantic models for worker result JSON files."""

from pathlib import Path
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, RootModel

from proxyflare.constants import WorkerType

__all__ = ["WorkerRecord", "WorkerResultFile"]

OWNER_ONLY_FILE_MODE = 0o600
OWNER_ONLY_DIR_MODE = 0o700


class WorkerRecord(BaseModel):
    """A single worker deployment record."""

    name: str
    url: str
    type: WorkerType
    created_at: float
    key: str = Field(repr=False)


class WorkerResultFile(RootModel[list[WorkerRecord]]):
    """Typed model for the workers file — a list of WorkerRecord entries."""

    # Validation errors would otherwise quote the records, printing their keys to the terminal
    model_config = ConfigDict(hide_input_in_errors=True)

    @classmethod
    def load_or_empty(cls, path: Path) -> Self:
        """Read the file, treating a missing one as empty. Raises ValueError if it is invalid."""
        if not path.exists():
            return cls(root=[])
        return cls.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, path: Path) -> None:
        """Replace the file atomically, readable only by its owner, because it holds worker keys."""
        path.parent.mkdir(parents=True, exist_ok=True, mode=OWNER_ONLY_DIR_MODE)

        temp_path = path.with_name(f"{path.name}.tmp")
        temp_path.touch(mode=OWNER_ONLY_FILE_MODE)
        temp_path.chmod(OWNER_ONLY_FILE_MODE)
        temp_path.write_text(self.model_dump_json(indent=2), encoding="utf-8")
        temp_path.replace(path)
