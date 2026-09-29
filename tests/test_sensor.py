"""Tests for sensor.py: entity creation, states, and health-text truncation."""

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.google_air_quality_custom.const import API_URL, DOMAIN
from custom_components.google_air_quality_custom.sensor import (
    _HEALTH_STATE_MAX_LEN,
    _HEALTH_TRUNCATED_LEN,
)


async def _setup_entry_with_subentry(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    response: dict,
    sensors: list[str],
    *,
    aqi_source: str = "universal",
) -> tuple[MockConfigEntry, ConfigSubentry]:
    aioclient_mock.post(API_URL, json=response)
    entry = MockConfigEntry(domain=DOMAIN, data={"api_key": "key", "language": "en"})
    entry.add_to_hass(hass)
    subentry = ConfigSubentry(
        data={
            "name": "Torino",
            "latitude": 45.0,
            "longitude": 7.0,
            "aqi_source": aqi_source,
            "region_code": None,
            "local_aqi": None,
            "sensors": sensors,
        },
        subentry_type="location",
        title="Torino",
        unique_id=f"45.0000_7.0000_{aqi_source}",
    )
    hass.config_entries.async_add_subentry(entry, subentry)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, subentry


async def test_only_selected_sensors_are_created(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, universal_response: dict
) -> None:
    entry, subentry = await _setup_entry_with_subentry(
        hass, aioclient_mock, universal_response, ["aqi", "pm25"]
    )
    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    keys = {e.unique_id.split("_")[-1] for e in entities}
    assert keys == {"aqi", "pm25"}


async def test_entities_belong_to_correct_device(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, universal_response: dict
) -> None:
    entry, subentry = await _setup_entry_with_subentry(
        hass, aioclient_mock, universal_response, ["aqi"]
    )
    registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(registry, entry.entry_id)
    assert len(entities) == 1
    assert entities[0].unique_id == f"{subentry.subentry_id}_aqi"


async def test_aqi_state_and_attributes(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, universal_response: dict
) -> None:
    entry, subentry = await _setup_entry_with_subentry(
        hass, aioclient_mock, universal_response, ["aqi"]
    )
    state = hass.states.get("sensor.torino_air_quality_index")
    assert state is not None
    assert state.state == "45"
    assert state.attributes["index_code"] == "uaqi"
    assert state.attributes["dominant_pollutant"] == "pm25"
    assert state.attributes["aqi_source"] == "universal"
    assert state.attributes["region_code"] is None
    assert state.attributes["local_aqi"] is None


async def test_aqi_attributes_expose_regional_custom_source(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, regional_response: dict
) -> None:
    aioclient_mock.post(API_URL, json=regional_response)
    entry = MockConfigEntry(domain=DOMAIN, data={"api_key": "key", "language": "en"})
    entry.add_to_hass(hass)
    subentry = ConfigSubentry(
        data={
            "name": "Torino",
            "latitude": 45.0,
            "longitude": 7.0,
            "aqi_source": "regional",
            "region_code": "IT",
            "local_aqi": "ita_moniqa",
            "sensors": ["aqi"],
        },
        subentry_type="location",
        title="Torino",
        unique_id="45.0000_7.0000_regional",
    )
    hass.config_entries.async_add_subentry(entry, subentry)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    state = hass.states.get("sensor.torino_air_quality_index")
    assert state is not None
    assert state.attributes["aqi_source"] == "regional"
    assert state.attributes["region_code"] == "IT"
    assert state.attributes["local_aqi"] == "ita_moniqa"


async def test_pollutant_state_and_unit(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, universal_response: dict
) -> None:
    entry, subentry = await _setup_entry_with_subentry(
        hass, aioclient_mock, universal_response, ["pm25"]
    )
    states = [s for s in hass.states.async_all() if s.entity_id.startswith("sensor.torino")]
    assert len(states) == 1
    state = states[0]
    assert state.state == "8.6"
    from homeassistant.const import CONCENTRATION_MICROGRAMS_PER_CUBIC_METER

    assert state.attributes["unit_of_measurement"] == CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
    assert state.attributes["device_class"] == "pm25"


async def test_health_recommendations_truncation(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, regional_response: dict
) -> None:
    long_text = "x" * 300
    regional_response = dict(regional_response)
    regional_response["healthRecommendations"] = dict(regional_response["healthRecommendations"])
    regional_response["healthRecommendations"]["generalPopulation"] = long_text

    entry, subentry = await _setup_entry_with_subentry(
        hass,
        aioclient_mock,
        regional_response,
        ["health_recommendations"],
        aqi_source="regional",
    )
    states = [s for s in hass.states.async_all() if s.entity_id.startswith("sensor.torino")]
    assert len(states) == 1
    state = states[0]
    assert len(state.state) <= _HEALTH_STATE_MAX_LEN
    assert state.state == long_text[:_HEALTH_TRUNCATED_LEN] + "…"
    assert state.attributes["general_population"] == long_text


async def test_health_recommendations_short_text_not_truncated(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, regional_response: dict
) -> None:
    entry, subentry = await _setup_entry_with_subentry(
        hass,
        aioclient_mock,
        regional_response,
        ["health_recommendations"],
        aqi_source="regional",
    )
    states = [s for s in hass.states.async_all() if s.entity_id.startswith("sensor.torino")]
    state = states[0]
    assert state.state == regional_response["healthRecommendations"]["generalPopulation"]


async def test_data_timestamp_sensor(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, universal_response: dict
) -> None:
    entry, subentry = await _setup_entry_with_subentry(
        hass, aioclient_mock, universal_response, ["data_timestamp"]
    )
    states = [s for s in hass.states.async_all() if s.entity_id.startswith("sensor.torino")]
    assert len(states) == 1
    assert states[0].state == "2026-09-28T10:00:00+00:00"


async def test_update_failed_marks_entity_unavailable(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker
) -> None:
    aioclient_mock.post(API_URL, status=500, json={"error": {"message": "server error"}})
    entry = MockConfigEntry(domain=DOMAIN, data={"api_key": "key", "language": "en"})
    entry.add_to_hass(hass)
    subentry = ConfigSubentry(
        data={
            "name": "Torino",
            "latitude": 45.0,
            "longitude": 7.0,
            "aqi_source": "universal",
            "region_code": None,
            "local_aqi": None,
            "sensors": ["aqi"],
        },
        subentry_type="location",
        title="Torino",
        unique_id="45.0000_7.0000_universal",
    )
    hass.config_entries.async_add_subentry(entry, subentry)
    # First refresh fails -> setup itself fails (ConfigEntryNotReady), entry stays in setup_retry.
    result = await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert result is False
