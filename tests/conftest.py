"""Shared test fixtures."""

import json
from pathlib import Path
from typing import Any

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Make custom_components/ discoverable by Home Assistant in every test."""


def load_fixture_json(name: str) -> dict[str, Any]:
    """Load a JSON fixture file from tests/fixtures/ by filename."""
    return json.loads((FIXTURES_DIR / name).read_text())


@pytest.fixture
def universal_response() -> dict[str, Any]:
    return load_fixture_json("current_conditions_universal.json")


@pytest.fixture
def regional_response() -> dict[str, Any]:
    return load_fixture_json("current_conditions_regional.json")
