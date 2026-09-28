"""Tests for models.py: payload building, response parsing, unit conversion."""

from datetime import UTC, datetime

import pytest

from custom_components.google_air_quality_custom.models import (
    AqiSource,
    CustomAqi,
    build_payload,
    parse_response,
    validate_custom_aqi,
)


def test_build_payload_pollutants_trigger_pollutant_computation() -> None:
    payload = build_payload(1.0, 2.0, AqiSource.UNIVERSAL, frozenset({"pm25"}), "en", None)
    assert payload["extraComputations"] == ["POLLUTANT_CONCENTRATION"]
    assert payload["universalAqi"] is True


def test_build_payload_health_recommendations_computation() -> None:
    payload = build_payload(
        1.0, 2.0, AqiSource.UNIVERSAL, frozenset({"health_recommendations"}), "en", None
    )
    assert payload["extraComputations"] == ["HEALTH_RECOMMENDATIONS"]


def test_build_payload_regional_adds_local_aqi_computation() -> None:
    payload = build_payload(1.0, 2.0, AqiSource.REGIONAL, frozenset(), "en", None)
    assert payload["extraComputations"] == ["LOCAL_AQI"]
    assert payload["universalAqi"] is False


def test_build_payload_all_sensors_all_computations() -> None:
    sensors = frozenset({"pm25", "health_recommendations"})
    payload = build_payload(1.0, 2.0, AqiSource.REGIONAL, sensors, "en", None)
    assert set(payload["extraComputations"]) == {
        "POLLUTANT_CONCENTRATION",
        "HEALTH_RECOMMENDATIONS",
        "LOCAL_AQI",
    }


def test_build_payload_custom_aqi() -> None:
    custom = CustomAqi(region_code="IT", aqi="ita_moniqa")
    payload = build_payload(1.0, 2.0, AqiSource.REGIONAL, frozenset(), "en", custom)
    assert payload["customLocalAqis"] == [{"regionCode": "IT", "aqi": "ita_moniqa"}]


def test_build_payload_no_custom_aqi_omits_key() -> None:
    payload = build_payload(1.0, 2.0, AqiSource.UNIVERSAL, frozenset(), "en", None)
    assert "customLocalAqis" not in payload


def test_parse_response_universal_index_selected_by_code(universal_response: dict) -> None:
    data = parse_response(universal_response, AqiSource.UNIVERSAL, frozenset({"aqi"}))
    assert data.index.code == "uaqi"
    assert data.index.value == 45
    assert data.timestamp == datetime(2026, 9, 28, 10, 0, tzinfo=UTC)


def test_parse_response_regional_index_selected_by_code_not_position(
    regional_response: dict,
) -> None:
    # ita_moniqa is first in the fixture's "indexes" list; selection must be by code.
    data = parse_response(regional_response, AqiSource.REGIONAL, frozenset())
    assert data.index.code == "ita_moniqa"
    assert data.index.value == 3  # parsed from aqiDisplay, no "aqi" key present


def test_parse_response_reordered_indexes_still_selects_uaqi() -> None:
    raw = {
        "dateTime": "2026-01-01T00:00:00Z",
        "indexes": [
            {"code": "other", "displayName": "Other", "aqi": 10, "category": "x"},
            {"code": "uaqi", "displayName": "Universal AQI", "aqi": 20, "category": "y"},
        ],
        "pollutants": [],
    }
    data = parse_response(raw, AqiSource.UNIVERSAL, frozenset())
    assert data.index.code == "uaqi"
    assert data.index.value == 20


def test_parse_response_missing_universal_index_raises() -> None:
    raw = {"dateTime": "2026-01-01T00:00:00Z", "indexes": [], "pollutants": []}
    with pytest.raises(ValueError, match="uaqi"):
        parse_response(raw, AqiSource.UNIVERSAL, frozenset())


def test_parse_response_missing_regional_index_raises() -> None:
    raw = {
        "dateTime": "2026-01-01T00:00:00Z",
        "indexes": [{"code": "uaqi", "displayName": "x", "aqi": 1, "category": "y"}],
        "pollutants": [],
    }
    with pytest.raises(ValueError, match="regional"):
        parse_response(raw, AqiSource.REGIONAL, frozenset())


def test_parse_response_pollutant_units_and_rounding(universal_response: dict) -> None:
    sensors = frozenset({"pm25", "pm10", "co", "no2", "o3", "so2"})
    data = parse_response(universal_response, AqiSource.UNIVERSAL, sensors)
    assert data.pollutants["pm25"] == 8.6
    assert data.pollutants["pm10"] == 14.2
    assert data.pollutants["co"] == round(324.3 / 1000, 2)
    assert data.pollutants["no2"] == round(10.2 * 46.0055 / 24.45, 2)
    assert data.pollutants["o3"] == round(27.4 * 47.9982 / 24.45, 2)
    assert data.pollutants["so2"] == round(1.8 * 64.066 / 24.45, 2)


def test_parse_response_unknown_unit_raises() -> None:
    raw = {
        "dateTime": "2026-01-01T00:00:00Z",
        "indexes": [{"code": "uaqi", "displayName": "x", "aqi": 1, "category": "y"}],
        "pollutants": [
            {"code": "pm25", "concentration": {"value": 1.0, "units": "SOMETHING_ELSE"}}
        ],
    }
    with pytest.raises(ValueError):
        parse_response(raw, AqiSource.UNIVERSAL, frozenset({"pm25"}))


def test_parse_response_missing_requested_pollutant_raises(universal_response: dict) -> None:
    # so2 is present in the fixture; ask for a pollutant not in the response instead.
    raw = dict(universal_response)
    raw["pollutants"] = [p for p in raw["pollutants"] if p["code"] != "so2"]
    with pytest.raises(ValueError, match="so2"):
        parse_response(raw, AqiSource.UNIVERSAL, frozenset({"so2"}))


def test_parse_response_health_recommendations_mapped_to_snake_case(
    regional_response: dict,
) -> None:
    data = parse_response(
        regional_response, AqiSource.REGIONAL, frozenset({"health_recommendations"})
    )
    assert data.health is not None
    assert set(data.health) == {
        "general_population",
        "elderly",
        "lung_disease_population",
        "heart_disease_population",
        "athletes",
        "pregnant_women",
        "children",
    }


def test_parse_response_health_recommendations_missing_raises(universal_response: dict) -> None:
    with pytest.raises(ValueError):
        parse_response(
            universal_response, AqiSource.UNIVERSAL, frozenset({"health_recommendations"})
        )


@pytest.mark.parametrize(
    ("source", "region_code", "local_aqi"),
    [
        (AqiSource.UNIVERSAL, "IT", None),
        (AqiSource.UNIVERSAL, None, "ita_moniqa"),
        (AqiSource.REGIONAL, "IT", None),
        (AqiSource.REGIONAL, None, "ita_moniqa"),
    ],
)
def test_validate_custom_aqi_incomplete_or_wrong_source_raises(
    source: AqiSource, region_code: str | None, local_aqi: str | None
) -> None:
    with pytest.raises(ValueError):
        validate_custom_aqi(source, region_code, local_aqi)


def test_validate_custom_aqi_both_empty_ok() -> None:
    validate_custom_aqi(AqiSource.UNIVERSAL, None, None)
    validate_custom_aqi(AqiSource.REGIONAL, None, None)


def test_validate_custom_aqi_regional_with_both_set_ok() -> None:
    validate_custom_aqi(AqiSource.REGIONAL, "IT", "ita_moniqa")


def test_validate_custom_aqi_universal_with_both_set_raises() -> None:
    with pytest.raises(ValueError, match="custom_aqi_requires_regional"):
        validate_custom_aqi(AqiSource.UNIVERSAL, "IT", "ita_moniqa")
