"""Thin async HTTP client for the Google Air Quality API.

Pure stdlib + aiohttp only — no homeassistant imports, so this module can be
imported by the CLI without homeassistant installed. The caller supplies the
aiohttp.ClientSession (Home Assistant's shared session, or a short-lived one
created by the CLI); this module doesn't know or care which.
"""

from typing import Any

import aiohttp

from .const import API_URL, REQUEST_TIMEOUT


class GoogleAirQualityError(Exception):
    """Base error for all Google Air Quality API failures."""


class GoogleAirQualityAuthError(GoogleAirQualityError):
    """Raised on 401/403 responses (invalid or unauthorized API key)."""


class GoogleAirQualityRequestError(GoogleAirQualityError):
    """Raised on 400 responses (malformed request, e.g. bad location)."""


def _error_message(status: int, body: dict[str, Any]) -> str:
    message = body.get("error", {}).get("message")
    if message:
        return f"Google Air Quality API error {status}: {message}"
    return f"Google Air Quality API error {status}"


class GoogleAirQualityClient:
    """Calls the currentConditions:lookup endpoint."""

    def __init__(self, session: aiohttp.ClientSession, api_key: str) -> None:
        self._session = session
        self._api_key = api_key

    async def current_conditions(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST payload to the API and return the parsed JSON body."""
        try:
            async with self._session.post(
                API_URL,
                json=payload,
                headers={"X-Goog-Api-Key": self._api_key},
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as response:
                body: dict[str, Any] = await response.json()
                if response.status in (401, 403):
                    raise GoogleAirQualityAuthError(_error_message(response.status, body))
                if response.status == 400:
                    raise GoogleAirQualityRequestError(_error_message(response.status, body))
                if response.status >= 300:
                    raise GoogleAirQualityError(_error_message(response.status, body))
                return body
        except TimeoutError as err:
            raise GoogleAirQualityError("Google Air Quality API request timed out") from err
        except aiohttp.ClientError as err:
            raise GoogleAirQualityError(f"Google Air Quality API connection error: {err}") from err
