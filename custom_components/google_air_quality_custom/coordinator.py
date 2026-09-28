"""DataUpdateCoordinator for a single location subentry."""

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import GoogleAirQualityAuthError, GoogleAirQualityClient, GoogleAirQualityError
from .const import DOMAIN, LOGGER, UPDATE_INTERVAL
from .models import AqiSource, CustomAqi, build_payload, parse_response

if TYPE_CHECKING:
    from . import GoogleAirQualityConfigEntry
    from .models import AirQualityData


class AirQualityCoordinator(DataUpdateCoordinator["AirQualityData"]):
    """Fetches and parses air quality data for one location."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: "GoogleAirQualityConfigEntry",
        subentry: ConfigSubentry,
        client: GoogleAirQualityClient,
    ) -> None:
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{subentry.subentry_id}",
            update_interval=UPDATE_INTERVAL,
        )
        self._client = client
        data = subentry.data
        self._aqi_source = AqiSource(data["aqi_source"])
        self._sensors = frozenset(data["sensors"])
        region_code = data.get("region_code")
        local_aqi = data.get("local_aqi")
        custom_aqi = None
        if region_code:
            assert local_aqi is not None  # config flow guarantees both-or-neither
            custom_aqi = CustomAqi(region_code=region_code, aqi=local_aqi)
        self._payload = build_payload(
            latitude=data["latitude"],
            longitude=data["longitude"],
            aqi_source=self._aqi_source,
            sensors=self._sensors,
            language=entry.data["language"],
            custom_aqi=custom_aqi,
        )

    async def _async_update_data(self) -> "AirQualityData":
        try:
            raw = await self._client.current_conditions(self._payload)
        except GoogleAirQualityAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except GoogleAirQualityError as err:
            raise UpdateFailed(str(err)) from err
        try:
            return parse_response(raw, self._aqi_source, self._sensors)
        except ValueError as err:
            raise UpdateFailed(str(err)) from err
