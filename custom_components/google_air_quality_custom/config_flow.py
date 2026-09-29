"""Config flow: one entry per API key, one 'location' subentry per device."""

import hashlib
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_API_KEY
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    LanguageSelector,
    LanguageSelectorConfig,
    LocationSelector,
    LocationSelectorConfig,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import GoogleAirQualityAuthError, GoogleAirQualityClient, GoogleAirQualityError
from .const import DOMAIN, SENSOR_KEYS
from .models import AqiSource, CustomAqi, build_payload, parse_response, validate_custom_aqi

CONF_LANGUAGE = "language"
CONF_NAME = "name"
CONF_LOCATION = "location"
CONF_AQI_SOURCE = "aqi_source"
CONF_REGION_CODE = "region_code"
CONF_LOCAL_AQI = "local_aqi"
CONF_SENSORS = "sensors"


def _dedupe_title(base_name: str, aqi_source: AqiSource, existing_titles: set[str]) -> str:
    """Avoid two devices at the same location sharing an identical name."""
    if base_name not in existing_titles:
        return base_name
    suffix = "Universal AQI" if aqi_source is AqiSource.UNIVERSAL else "Regional AQI"
    return f"{base_name} ({suffix})"


def _api_key_unique_id(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()[:16]


async def _validate_api_key(hass: Any, api_key: str) -> None:
    """Call the API once to validate the key. Raises on failure."""
    session = async_get_clientsession(hass)
    client = GoogleAirQualityClient(session, api_key)
    payload = build_payload(
        latitude=hass.config.latitude,
        longitude=hass.config.longitude,
        aqi_source=AqiSource.UNIVERSAL,
        sensors=frozenset(),
        language=hass.config.language,
        custom_aqi=None,
    )
    await client.current_conditions(payload)


class GoogleAirQualityConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the API-key config entry."""

    VERSION = 1

    @classmethod
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        return {"location": LocationSubentryFlow}

    async def _validate(self, user_input: dict[str, Any]) -> dict[str, str]:
        errors: dict[str, str] = {}
        try:
            await _validate_api_key(self.hass, user_input[CONF_API_KEY])
        except GoogleAirQualityAuthError:
            errors["base"] = "invalid_auth"
        except GoogleAirQualityError:
            errors["base"] = "cannot_connect"
        except Exception:  # noqa: BLE001 - fail closed into "unknown" per spec
            errors["base"] = "unknown"
        return errors

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(_api_key_unique_id(user_input[CONF_API_KEY]))
            self._abort_if_unique_id_configured()
            errors = await self._validate(user_input)
            if not errors:
                return self.async_create_entry(
                    title="Google Air Quality",
                    data={
                        CONF_API_KEY: user_input[CONF_API_KEY],
                        CONF_LANGUAGE: user_input[CONF_LANGUAGE],
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
                vol.Required(CONF_LANGUAGE, default=self.hass.config.language): LanguageSelector(
                    LanguageSelectorConfig()
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._validate(user_input)
            if not errors:
                reauth_entry = self._get_reauth_entry()
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data={
                        CONF_API_KEY: user_input[CONF_API_KEY],
                        CONF_LANGUAGE: reauth_entry.data[CONF_LANGUAGE],
                    },
                    reason="reauth_successful",
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): TextSelector(
                    TextSelectorConfig(type=TextSelectorType.PASSWORD)
                ),
            }
        )
        return self.async_show_form(step_id="reauth_confirm", data_schema=schema, errors=errors)


_AQI_SOURCE_OPTIONS = SelectSelectorConfig(
    options=["universal", "regional"],
    translation_key="aqi_source",
    mode=SelectSelectorMode.DROPDOWN,
)


def _sensors_selector() -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=sorted(SENSOR_KEYS),
            translation_key="sensors",
            mode=SelectSelectorMode.DROPDOWN,
            multiple=True,
        )
    )


class LocationSubentryFlow(ConfigSubentryFlow):
    """Handle a 'location' subentry (one per device)."""

    async def _build_schema(self, defaults: dict[str, Any]) -> vol.Schema:
        hass = self.hass
        return vol.Schema(
            {
                vol.Required(
                    CONF_NAME, default=defaults.get(CONF_NAME, hass.config.location_name)
                ): TextSelector(),
                vol.Required(
                    CONF_LOCATION,
                    default=defaults.get(
                        CONF_LOCATION,
                        {"latitude": hass.config.latitude, "longitude": hass.config.longitude},
                    ),
                ): LocationSelector(LocationSelectorConfig(radius=False)),
                vol.Required(
                    CONF_AQI_SOURCE, default=defaults.get(CONF_AQI_SOURCE, "universal")
                ): SelectSelector(_AQI_SOURCE_OPTIONS),
                vol.Optional(
                    CONF_REGION_CODE, default=defaults.get(CONF_REGION_CODE, "")
                ): TextSelector(),
                vol.Optional(
                    CONF_LOCAL_AQI, default=defaults.get(CONF_LOCAL_AQI, "")
                ): TextSelector(),
                vol.Required(
                    CONF_SENSORS, default=defaults.get(CONF_SENSORS, sorted(SENSOR_KEYS))
                ): _sensors_selector(),
            }
        )

    async def _validate_and_build(
        self, user_input: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, dict[str, str]]:
        errors: dict[str, str] = {}
        region_code = user_input.get(CONF_REGION_CODE) or None
        local_aqi = user_input.get(CONF_LOCAL_AQI) or None
        aqi_source = AqiSource(user_input[CONF_AQI_SOURCE])
        sensors = user_input[CONF_SENSORS]

        if not sensors:
            errors["sensors"] = "required"
            return None, errors

        try:
            validate_custom_aqi(aqi_source, region_code, local_aqi)
        except ValueError as err:
            errors["base"] = str(err)
            return None, errors

        custom_aqi = None
        if region_code:
            assert local_aqi is not None  # guaranteed by validate_custom_aqi above
            custom_aqi = CustomAqi(region_code=region_code, aqi=local_aqi)
        latitude = user_input[CONF_LOCATION]["latitude"]
        longitude = user_input[CONF_LOCATION]["longitude"]

        entry = self._get_entry()
        payload = build_payload(
            latitude=latitude,
            longitude=longitude,
            aqi_source=aqi_source,
            sensors=frozenset(sensors),
            language=entry.data[CONF_LANGUAGE],
            custom_aqi=custom_aqi,
        )
        session = async_get_clientsession(self.hass)
        client = GoogleAirQualityClient(session, entry.data[CONF_API_KEY])
        try:
            raw = await client.current_conditions(payload)
        except GoogleAirQualityAuthError:
            errors["base"] = "invalid_auth"
            return None, errors
        except GoogleAirQualityError as err:
            from .api import GoogleAirQualityRequestError

            if isinstance(err, GoogleAirQualityRequestError):
                errors["base"] = "invalid_location"
            else:
                errors["base"] = "cannot_connect"
            return None, errors
        except Exception:  # noqa: BLE001 - fail closed into "unknown" per spec
            errors["base"] = "unknown"
            return None, errors

        if aqi_source is AqiSource.REGIONAL:
            try:
                parse_response(raw, aqi_source, frozenset())
            except ValueError:
                errors["base"] = "regional_unavailable"
                return None, errors

        data = {
            CONF_NAME: user_input[CONF_NAME],
            "latitude": latitude,
            "longitude": longitude,
            CONF_AQI_SOURCE: aqi_source.value,
            CONF_REGION_CODE: region_code,
            CONF_LOCAL_AQI: local_aqi,
            CONF_SENSORS: sensors,
        }
        return data, errors

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            data, errors = await self._validate_and_build(user_input)
            if data is not None:
                latitude, longitude = data["latitude"], data["longitude"]
                unique_id = f"{latitude:.4f}_{longitude:.4f}_{data[CONF_AQI_SOURCE]}"
                existing_subentries = self._get_entry().subentries.values()
                for existing in existing_subentries:
                    if existing.unique_id == unique_id:
                        return self.async_abort(reason="already_configured")
                title = _dedupe_title(
                    data[CONF_NAME],
                    AqiSource(data[CONF_AQI_SOURCE]),
                    {existing.title for existing in existing_subentries},
                )
                return self.async_create_entry(title=title, data=data, unique_id=unique_id)

        schema = await self._build_schema(user_input or {})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data, errors = await self._validate_and_build(user_input)
            if data is not None:
                latitude, longitude = data["latitude"], data["longitude"]
                unique_id = f"{latitude:.4f}_{longitude:.4f}_{data[CONF_AQI_SOURCE]}"
                other_subentries = [
                    existing
                    for existing in self._get_entry().subentries.values()
                    if existing.subentry_id != subentry.subentry_id
                ]
                for existing in other_subentries:
                    if existing.unique_id == unique_id:
                        return self.async_abort(reason="already_configured")
                title = _dedupe_title(
                    data[CONF_NAME],
                    AqiSource(data[CONF_AQI_SOURCE]),
                    {existing.title for existing in other_subentries},
                )
                return self.async_update_and_abort(
                    self._get_entry(),
                    subentry,
                    title=title,
                    data=data,
                    unique_id=unique_id,
                )

        defaults = dict(subentry.data)
        defaults[CONF_LOCATION] = {
            "latitude": subentry.data["latitude"],
            "longitude": subentry.data["longitude"],
        }
        schema = await self._build_schema(user_input if user_input is not None else defaults)
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)
