"""Tests for config_flow.py: the API-key entry flow and the location subentry flow."""

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.google_air_quality_custom.const import API_URL, DOMAIN


def _mock_universal_ok(aioclient_mock: AiohttpClientMocker, universal_response: dict) -> None:
    aioclient_mock.post(API_URL, json=universal_response)


def _mock_regional_ok(aioclient_mock: AiohttpClientMocker, regional_response: dict) -> None:
    aioclient_mock.post(API_URL, json=regional_response)


async def test_user_flow_happy_path(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, universal_response: dict
) -> None:
    _mock_universal_ok(aioclient_mock, universal_response)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": "the-key", "language": "en"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Google Air Quality"
    assert result["data"]["api_key"] == "the-key"


async def test_user_flow_invalid_auth(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(API_URL, status=401, json={"error": {"message": "bad key"}})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": "bad-key", "language": "en"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_auth"


async def test_user_flow_duplicate_key_aborts(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, universal_response: dict
) -> None:
    _mock_universal_ok(aioclient_mock, universal_response)
    from custom_components.google_air_quality_custom.config_flow import _api_key_unique_id

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"api_key": "dup-key", "language": "en"},
        unique_id=_api_key_unique_id("dup-key"),
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": "dup-key", "language": "en"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_flow_updates_key(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, universal_response: dict
) -> None:
    _mock_universal_ok(aioclient_mock, universal_response)
    entry = MockConfigEntry(domain=DOMAIN, data={"api_key": "old-key", "language": "en"})
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"api_key": "new-key"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["api_key"] == "new-key"


@pytest.fixture
def parent_entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data={"api_key": "the-key", "language": "en"})
    entry.add_to_hass(hass)
    return entry


async def test_subentry_create_universal(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    universal_response: dict,
    parent_entry: MockConfigEntry,
) -> None:
    _mock_universal_ok(aioclient_mock, universal_response)
    result = await hass.config_entries.subentries.async_init(
        (parent_entry.entry_id, "location"),
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Home",
            "location": {"latitude": 45.0, "longitude": 7.0},
            "aqi_source": "universal",
            "region_code": "",
            "local_aqi": "",
            "sensors": ["aqi"],
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Home"
    subentries = list(parent_entry.subentries.values())
    assert len(subentries) == 1
    assert subentries[0].unique_id == "45.0000_7.0000_universal"


async def test_subentry_same_location_different_source_gets_distinct_titles(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    regional_response: dict,
    parent_entry: MockConfigEntry,
) -> None:
    """Two subentries at the same location must not end up with the same title."""
    from homeassistant.config_entries import ConfigSubentry

    hass.config_entries.async_add_subentry(
        parent_entry,
        ConfigSubentry(
            data={
                "name": "Home",
                "latitude": 45.0,
                "longitude": 7.0,
                "aqi_source": "universal",
                "region_code": None,
                "local_aqi": None,
                "sensors": ["aqi"],
            },
            subentry_type="location",
            title="Home",
            unique_id="45.0000_7.0000_universal",
        ),
    )

    _mock_regional_ok(aioclient_mock, regional_response)
    result = await hass.config_entries.subentries.async_init(
        (parent_entry.entry_id, "location"),
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Home",
            "location": {"latitude": 45.0, "longitude": 7.0},
            "aqi_source": "regional",
            "region_code": "",
            "local_aqi": "",
            "sensors": ["aqi"],
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Home (Regional AQI)"
    titles = {subentry.title for subentry in parent_entry.subentries.values()}
    assert titles == {"Home", "Home (Regional AQI)"}


async def test_subentry_custom_aqi_incomplete_error(
    hass: HomeAssistant, parent_entry: MockConfigEntry
) -> None:
    result = await hass.config_entries.subentries.async_init(
        (parent_entry.entry_id, "location"),
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Home",
            "location": {"latitude": 45.0, "longitude": 7.0},
            "aqi_source": "regional",
            "region_code": "IT",
            "local_aqi": "",
            "sensors": ["aqi"],
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "custom_aqi_incomplete"


async def test_subentry_custom_aqi_requires_regional_error(
    hass: HomeAssistant, parent_entry: MockConfigEntry
) -> None:
    result = await hass.config_entries.subentries.async_init(
        (parent_entry.entry_id, "location"),
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Home",
            "location": {"latitude": 45.0, "longitude": 7.0},
            "aqi_source": "universal",
            "region_code": "IT",
            "local_aqi": "ita_moniqa",
            "sensors": ["aqi"],
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "custom_aqi_requires_regional"


async def test_subentry_regional_unavailable_error(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    universal_response: dict,
    parent_entry: MockConfigEntry,
) -> None:
    # universal_response has only a "uaqi" index, so a regional request finds no local index.
    _mock_universal_ok(aioclient_mock, universal_response)
    result = await hass.config_entries.subentries.async_init(
        (parent_entry.entry_id, "location"),
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Home",
            "location": {"latitude": 45.0, "longitude": 7.0},
            "aqi_source": "regional",
            "region_code": "",
            "local_aqi": "",
            "sensors": ["aqi"],
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "regional_unavailable"


async def test_subentry_invalid_location_error(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, parent_entry: MockConfigEntry
) -> None:
    aioclient_mock.post(API_URL, status=400, json={"error": {"message": "bad location"}})
    result = await hass.config_entries.subentries.async_init(
        (parent_entry.entry_id, "location"),
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Home",
            "location": {"latitude": 45.0, "longitude": 7.0},
            "aqi_source": "universal",
            "region_code": "",
            "local_aqi": "",
            "sensors": ["aqi"],
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "invalid_location"


async def test_subentry_duplicate_aborts(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    universal_response: dict,
    parent_entry: MockConfigEntry,
) -> None:
    _mock_universal_ok(aioclient_mock, universal_response)
    from homeassistant.config_entries import ConfigSubentry

    hass.config_entries.async_add_subentry(
        parent_entry,
        ConfigSubentry(
            data={
                "name": "Home",
                "latitude": 45.0,
                "longitude": 7.0,
                "aqi_source": "universal",
                "region_code": None,
                "local_aqi": None,
                "sensors": ["aqi"],
            },
            subentry_type="location",
            title="Home",
            unique_id="45.0000_7.0000_universal",
        ),
    )

    result = await hass.config_entries.subentries.async_init(
        (parent_entry.entry_id, "location"),
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Home 2",
            "location": {"latitude": 45.0, "longitude": 7.0},
            "aqi_source": "universal",
            "region_code": "",
            "local_aqi": "",
            "sensors": ["aqi"],
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_subentry_reconfigure(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    universal_response: dict,
    parent_entry: MockConfigEntry,
) -> None:
    _mock_universal_ok(aioclient_mock, universal_response)
    from homeassistant.config_entries import ConfigSubentry

    subentry = ConfigSubentry(
        data={
            "name": "Home",
            "latitude": 45.0,
            "longitude": 7.0,
            "aqi_source": "universal",
            "region_code": None,
            "local_aqi": None,
            "sensors": ["aqi"],
        },
        subentry_type="location",
        title="Home",
        unique_id="45.0000_7.0000_universal",
    )
    hass.config_entries.async_add_subentry(parent_entry, subentry)

    result = await hass.config_entries.subentries.async_init(
        (parent_entry.entry_id, "location"),
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "subentry_id": subentry.subentry_id,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Home renamed",
            "location": {"latitude": 45.0, "longitude": 7.0},
            "aqi_source": "universal",
            "region_code": "",
            "local_aqi": "",
            "sensors": ["aqi", "pm25"],
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    updated = parent_entry.subentries[subentry.subentry_id]
    assert updated.title == "Home renamed"
    assert updated.data["sensors"] == ["aqi", "pm25"]
