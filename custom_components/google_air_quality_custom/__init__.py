"""Google Air Quality (Custom) integration.

homeassistant imports are kept inside function bodies (not at module top
level) so this package's api/models/const/cli submodules stay importable in
an environment without homeassistant installed (e.g. the standalone CLI).
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

    from .coordinator import AirQualityCoordinator

    type GoogleAirQualityConfigEntry = ConfigEntry[dict[str, AirQualityCoordinator]]


async def async_setup_entry(hass: "HomeAssistant", entry: "GoogleAirQualityConfigEntry") -> bool:
    """Set up one client and one coordinator per location subentry."""
    from homeassistant.const import Platform
    from homeassistant.helpers.aiohttp_client import async_get_clientsession

    from .api import GoogleAirQualityClient
    from .coordinator import AirQualityCoordinator

    session = async_get_clientsession(hass)
    client = GoogleAirQualityClient(session, entry.data["api_key"])

    coordinators: dict[str, AirQualityCoordinator] = {}
    for subentry_id, subentry in entry.subentries.items():
        if subentry.subentry_type != "location":
            continue
        coordinator = AirQualityCoordinator(hass, entry, subentry, client)
        await coordinator.async_config_entry_first_refresh()
        coordinators[subentry_id] = coordinator

    entry.runtime_data = coordinators
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.SENSOR])
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: "HomeAssistant", entry: "GoogleAirQualityConfigEntry") -> bool:
    """Unload the sensor platform for this entry."""
    from homeassistant.const import Platform

    return await hass.config_entries.async_unload_platforms(entry, [Platform.SENSOR])


async def _async_reload(hass: "HomeAssistant", entry: "GoogleAirQualityConfigEntry") -> None:
    """Reload the entry when a subentry is added, removed, or reconfigured."""
    await hass.config_entries.async_reload(entry.entry_id)
