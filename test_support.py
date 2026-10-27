"""Repository-wide policy: live services are explicitly opt-in."""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="Run tests requiring provider credentials, live services or ML models",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: requires live services, credentials or ML models",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-integration"):
        return
    skip = pytest.mark.skip(
        reason="Requires --run-integration and configured services"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
