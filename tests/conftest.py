"""
pytest configuration and hooks.
"""

from typing import Any, List
import pytest


def pytest_collection_modifyitems(config: Any, items: List[Any]) -> None:
    """
    Automatically marks tests based on their directory location under tests/.
    Tests under tests/unit/ are marked as 'unit'.
    Tests under tests/integration/ are marked as 'integration'.
    """
    for item in items:
        path = str(item.fspath).replace("\\", "/")
        if "tests/unit/" in path:
            item.add_marker(pytest.mark.unit)
        elif "tests/integration/" in path:
            item.add_marker(pytest.mark.integration)
