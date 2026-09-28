"""Sensor entities: one per selected sensor key, per location subentry."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
    CONCENTRATION_PARTS_PER_MILLION,
    EntityCategory,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AirQualityCoordinator
from .models import AirQualityData

if TYPE_CHECKING:
    from . import GoogleAirQualityConfigEntry

_HEALTH_STATE_MAX_LEN = 255
_HEALTH_TRUNCATED_LEN = 254


@dataclass(frozen=True, kw_only=True)
class GoogleAirQualitySensorDescription(SensorEntityDescription):
    """Sensor description with data extraction functions."""

    value_fn: Callable[[AirQualityData], StateType | datetime]
    attrs_fn: Callable[[AirQualityData], dict[str, Any]] | None = None


def _aqi_attrs(data: AirQualityData) -> dict[str, Any]:
    return {
        "index_code": data.index.code,
        "index_name": data.index.display_name,
        "category": data.index.category,
        "dominant_pollutant": data.index.dominant_pollutant,
    }


def _health_value(data: AirQualityData) -> str:
    assert data.health is not None
    text = data.health["general_population"]
    if len(text) > _HEALTH_STATE_MAX_LEN:
        return text[:_HEALTH_TRUNCATED_LEN] + "…"
    return text


def _health_attrs(data: AirQualityData) -> dict[str, Any]:
    assert data.health is not None
    return dict(data.health)


SENSOR_DESCRIPTIONS: tuple[GoogleAirQualitySensorDescription, ...] = (
    GoogleAirQualitySensorDescription(
        key="aqi",
        translation_key="aqi",
        device_class=SensorDeviceClass.AQI,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.index.value,
        attrs_fn=_aqi_attrs,
    ),
    GoogleAirQualitySensorDescription(
        key="pm25",
        device_class=SensorDeviceClass.PM25,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.pollutants["pm25"],
    ),
    GoogleAirQualitySensorDescription(
        key="pm10",
        device_class=SensorDeviceClass.PM10,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.pollutants["pm10"],
    ),
    GoogleAirQualitySensorDescription(
        key="co",
        device_class=SensorDeviceClass.CO,
        native_unit_of_measurement=CONCENTRATION_PARTS_PER_MILLION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.pollutants["co"],
    ),
    GoogleAirQualitySensorDescription(
        key="no2",
        device_class=SensorDeviceClass.NITROGEN_DIOXIDE,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.pollutants["no2"],
    ),
    GoogleAirQualitySensorDescription(
        key="o3",
        device_class=SensorDeviceClass.OZONE,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.pollutants["o3"],
    ),
    GoogleAirQualitySensorDescription(
        key="so2",
        device_class=SensorDeviceClass.SULPHUR_DIOXIDE,
        native_unit_of_measurement=CONCENTRATION_MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.pollutants["so2"],
    ),
    GoogleAirQualitySensorDescription(
        key="health_recommendations",
        translation_key="health_recommendations",
        value_fn=_health_value,
        attrs_fn=_health_attrs,
    ),
    GoogleAirQualitySensorDescription(
        key="data_timestamp",
        translation_key="data_timestamp",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda data: data.timestamp,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: "GoogleAirQualityConfigEntry",
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Create sensors for each location subentry, limited to its selected sensors."""
    for subentry_id, coordinator in entry.runtime_data.items():
        subentry = entry.subentries[subentry_id]
        selected = set(subentry.data["sensors"])
        entities = [
            GoogleAirQualitySensor(coordinator, description, subentry_id, subentry.title)
            for description in SENSOR_DESCRIPTIONS
            if description.key in selected
        ]
        async_add_entities(entities, config_subentry_id=subentry_id)


class GoogleAirQualitySensor(CoordinatorEntity[AirQualityCoordinator], SensorEntity):
    """A single air-quality sensor entity."""

    _attr_has_entity_name = True
    _attr_attribution = "Data provided by Google Air Quality API"
    entity_description: GoogleAirQualitySensorDescription

    def __init__(
        self,
        coordinator: AirQualityCoordinator,
        description: GoogleAirQualitySensorDescription,
        subentry_id: str,
        device_name: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{subentry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, subentry_id)},
            name=device_name,
            manufacturer="Google",
            model="Air Quality API",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url="https://developers.google.com/maps/documentation/air-quality",
        )

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator.data)
