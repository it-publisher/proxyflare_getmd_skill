import json

import pytest

from proxyflare.client import ProxyflareWorkersManager
from proxyflare.models.worker_result import WorkerRecord, WorkerResultFile


def make_record(url: str = "https://worker.dev", worker_type: str = "js") -> WorkerRecord:
    return WorkerRecord(name="w", url=url, type=worker_type, created_at=1.0, key="secret-key")


def write_workers_file(path, workers: list[dict]):
    file_path = path / "workers.json"
    file_path.write_text(json.dumps(workers), encoding="utf-8")
    return file_path


def test_manager_init_with_list():
    workers = [make_record("https://worker1.dev"), make_record("https://worker2.dev")]
    manager = ProxyflareWorkersManager(workers)
    assert manager.workers == workers
    assert manager.get_worker() in workers


def test_manager_init_with_file(tmp_path):
    file_path = write_workers_file(
        tmp_path,
        [
            {
                "name": "w1",
                "url": "https://worker1.dev",
                "type": "js",
                "created_at": 1.0,
                "key": "k1",
            },
            {
                "name": "w2",
                "url": "https://worker2.dev",
                "type": "rust",
                "created_at": 2.0,
                "key": "k2",
            },
        ],
    )

    manager = ProxyflareWorkersManager(file_path)
    assert [(w.url, w.key) for w in manager.workers] == [
        ("https://worker1.dev", "k1"),
        ("https://worker2.dev", "k2"),
    ]


def test_manager_invalid_file():
    with pytest.raises(FileNotFoundError):
        ProxyflareWorkersManager("non_existent_file.json")


def test_manager_empty_source():
    with pytest.raises(ValueError, match="No workers found"):
        ProxyflareWorkersManager([])


def test_manager_rejects_invalid_schema(tmp_path):
    """JSON that doesn't match WorkerResultFile schema should raise ValueError."""
    file_path = write_workers_file(tmp_path, [{"url": "https://valid.dev"}])
    with pytest.raises(ValueError, match="Failed to parse"):
        ProxyflareWorkersManager(file_path)


@pytest.mark.parametrize("removed_field", ["key", "type"])
def test_manager_rejects_record_without_required_field(tmp_path, removed_field):
    """A file from before keys were introduced must fail loudly, not send unauthorized requests."""
    record = {"name": "w", "url": "https://w.dev", "type": "js", "created_at": 1.0, "key": "k"}
    del record[removed_field]
    with pytest.raises(ValueError, match="Failed to parse"):
        ProxyflareWorkersManager(write_workers_file(tmp_path, [record]))


def test_manager_rejects_removed_python_worker_type(tmp_path):
    record = {"name": "w", "url": "https://w.dev", "type": "python", "created_at": 1.0, "key": "k"}
    with pytest.raises(ValueError, match="Failed to parse"):
        ProxyflareWorkersManager(write_workers_file(tmp_path, [record]))


def test_record_repr_hides_the_key():
    assert "secret-key" not in repr(make_record())


def test_saved_file_is_readable_only_by_owner(tmp_path):
    path = tmp_path / "workers.json"
    path.write_text("[]")
    path.chmod(0o644)

    WorkerResultFile(root=[make_record()]).save(path)

    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text())[0]["key"] == "secret-key"
