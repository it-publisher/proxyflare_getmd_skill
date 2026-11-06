import tomllib
from pathlib import Path

import proxyflare


def test_package_version_matches_pyproject():
    pyproject = Path(__file__).parents[2] / "pyproject.toml"
    assert proxyflare.__version__ == tomllib.loads(pyproject.read_text())["project"]["version"]
