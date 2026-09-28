"""Shared constants. No homeassistant imports here — the CLI must import this module standalone."""

import logging
from datetime import timedelta

DOMAIN = "google_air_quality_custom"
UPDATE_INTERVAL = timedelta(minutes=30)
LOGGER = logging.getLogger(__package__)

API_URL = "https://airquality.googleapis.com/v1/currentConditions:lookup"
REQUEST_TIMEOUT = 20

SENSOR_KEYS = frozenset(
    {"aqi", "pm25", "pm10", "co", "no2", "o3", "so2", "health_recommendations", "data_timestamp"}
)
