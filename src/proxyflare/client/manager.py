import secrets
from pathlib import Path

from proxyflare.models.worker_result import WorkerRecord, WorkerResultFile

__all__ = ["ProxyflareWorkersManager"]


class ProxyflareWorkersManager:
    """
    Manages a pool of Proxyflare workers.
    Can load workers from a JSON file (created by `proxyflare create`)
    or accept a direct list of records.
    """

    def __init__(self, source: str | Path | list[WorkerRecord]) -> None:
        """
        Initialize the manager with worker sources.

        Args:
            source: A list of worker records, or a path to a JSON file.

        Raises:
            ValueError: If no workers are found.
        """
        self.workers: list[WorkerRecord] = []

        if isinstance(source, list):
            self.workers = source
        else:
            self.load_from_file(source)

        if not self.workers:
            raise ValueError("No workers found in the provided source.")

    def load_from_file(self, path: str | Path) -> None:
        """Load workers from a JSON file validated by WorkerResultFile model."""
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Worker file not found: {file_path}")

        try:
            self.workers = WorkerResultFile.load_or_empty(file_path).root
        except Exception as e:
            raise ValueError(f"Failed to parse worker file: {e}") from e

    def get_worker(self) -> WorkerRecord:
        """Return a random worker."""
        if not self.workers:
            raise ValueError("No workers available.")
        return secrets.choice(self.workers)
