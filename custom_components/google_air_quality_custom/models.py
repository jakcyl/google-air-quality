"""Payload building and response parsing — pure functions, no I/O.

No homeassistant imports here either, so the CLI can use this module standalone.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

POLLUTANT_KEYS = frozenset({"pm25", "pm10", "co", "no2", "o3", "so2"})
ALL_SENSOR_KEYS = POLLUTANT_KEYS | {"aqi", "health_recommendations", "data_timestamp"}

_HEALTH_GROUP_MAP = {
    "generalPopulation": "general_population",
    "elderly": "elderly",
    "lungDiseasePopulation": "lung_disease_population",
    "heartDiseasePopulation": "heart_disease_population",
    "athletes": "athletes",
    "pregnantWomen": "pregnant_women",
    "children": "children",
}


class AqiSource(StrEnum):
    """Which AQI index to request/select from the response."""

    UNIVERSAL = "universal"
    REGIONAL = "regional"


@dataclass(frozen=True, slots=True)
class CustomAqi:
    """A custom local AQI request (regionCode + local index id)."""

    region_code: str
    aqi: str


@dataclass(frozen=True, slots=True)
class AqiIndex:
    code: str
    display_name: str
    value: int
    category: str
    dominant_pollutant: str | None


@dataclass(frozen=True, slots=True)
class AirQualityData:
    timestamp: datetime
    index: AqiIndex
    pollutants: dict[str, float]  # key -> value in target unit
    health: dict[str, str] | None  # snake_case group -> text


def validate_custom_aqi(
    aqi_source: AqiSource, region_code: str | None, local_aqi: str | None
) -> None:
    """Raise ValueError if the custom-AQI fields are inconsistent.

    Shared by the HA subentry flow and the CLI so both apply the same rules:
    - region_code and local_aqi must be both set or both empty.
    - custom AQI fields only make sense when aqi_source is REGIONAL.
    """
    if bool(region_code) != bool(local_aqi):
        raise ValueError("custom_aqi_incomplete")
    if (region_code or local_aqi) and aqi_source is not AqiSource.REGIONAL:
        raise ValueError("custom_aqi_requires_regional")


def build_payload(
    latitude: float,
    longitude: float,
    aqi_source: AqiSource,
    sensors: frozenset[str],
    language: str,
    custom_aqi: CustomAqi | None,
) -> dict[str, Any]:
    """Build the currentConditions:lookup request body."""
    computations: list[str] = []
    if sensors & POLLUTANT_KEYS:
        computations.append("POLLUTANT_CONCENTRATION")
    if "health_recommendations" in sensors:
        computations.append("HEALTH_RECOMMENDATIONS")
    if aqi_source is AqiSource.REGIONAL:
        computations.append("LOCAL_AQI")
    payload: dict[str, Any] = {
        "location": {"latitude": latitude, "longitude": longitude},
        "universalAqi": aqi_source is AqiSource.UNIVERSAL,
        "languageCode": language,
        "extraComputations": computations,
    }
    if custom_aqi is not None:
        payload["customLocalAqis"] = [{"regionCode": custom_aqi.region_code, "aqi": custom_aqi.aqi}]
    return payload


def _parse_timestamp(raw: str) -> datetime:
    text = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
    return datetime.fromisoformat(text)


def _select_index(raw: dict[str, Any], aqi_source: AqiSource) -> dict[str, Any]:
    indexes: list[dict[str, Any]] = raw.get("indexes", [])
    if aqi_source is AqiSource.UNIVERSAL:
        for index in indexes:
            if index.get("code") == "uaqi":
                return index
        raise ValueError("no universal AQI index (code 'uaqi') in response")
    for index in indexes:
        if index.get("code") != "uaqi":
            return index
    raise ValueError("no regional AQI index in response")


def _index_value(raw_index: dict[str, Any]) -> int:
    if "aqi" in raw_index:
        return int(raw_index["aqi"])
    if "aqiDisplay" in raw_index:
        return int(float(raw_index["aqiDisplay"]))
    raise ValueError("AQI index has neither 'aqi' nor 'aqiDisplay'")


def _convert_pollutant(code: str, value: float, unit: str) -> float:
    if code in ("pm25", "pm10"):
        if unit != "MICROGRAMS_PER_CUBIC_METER":
            raise ValueError(f"unexpected unit {unit!r} for {code}")
        return round(value, 2)
    if unit != "PARTS_PER_BILLION":
        raise ValueError(f"unexpected unit {unit!r} for {code}")
    if code == "co":
        return round(value / 1000, 2)
    molar_mass = {"no2": 46.0055, "o3": 47.9982, "so2": 64.066}.get(code)
    if molar_mass is None:
        raise ValueError(f"no unit conversion defined for pollutant {code!r}")
    return round(value * molar_mass / 24.45, 2)


def _find_pollutant(raw: dict[str, Any], key: str) -> dict[str, Any]:
    pollutants: list[dict[str, Any]] = raw.get("pollutants", [])
    for pollutant in pollutants:
        if pollutant.get("code") == key:
            return pollutant
    raise ValueError(f"pollutant {key} not returned for this location")


def parse_response(
    raw: dict[str, Any], aqi_source: AqiSource, sensors: frozenset[str]
) -> AirQualityData:
    """Parse a currentConditions:lookup response into AirQualityData."""
    raw_timestamp = raw.get("dateTime")
    if not raw_timestamp:
        raise ValueError("response is missing 'dateTime'")
    timestamp = _parse_timestamp(raw_timestamp)

    raw_index = _select_index(raw, aqi_source)
    index = AqiIndex(
        code=raw_index["code"],
        display_name=raw_index["displayName"],
        value=_index_value(raw_index),
        category=raw_index["category"],
        dominant_pollutant=raw_index.get("dominantPollutant"),
    )

    pollutants: dict[str, float] = {}
    for key in sensors & POLLUTANT_KEYS:
        raw_pollutant = _find_pollutant(raw, key)
        concentration = raw_pollutant["concentration"]
        pollutants[key] = _convert_pollutant(key, concentration["value"], concentration["units"])

    health: dict[str, str] | None = None
    if "health_recommendations" in sensors:
        raw_health = raw.get("healthRecommendations")
        if not raw_health:
            raise ValueError("health_recommendations requested but not returned")
        health = {
            _HEALTH_GROUP_MAP[camel]: text
            for camel, text in raw_health.items()
            if camel in _HEALTH_GROUP_MAP
        }

    return AirQualityData(timestamp=timestamp, index=index, pollutants=pollutants, health=health)
