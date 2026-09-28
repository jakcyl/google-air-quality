"""Tests for api.py: HTTP header/URL handling and status-code error mapping."""

import asyncio

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from custom_components.google_air_quality_custom.api import (
    GoogleAirQualityAuthError,
    GoogleAirQualityClient,
    GoogleAirQualityError,
    GoogleAirQualityRequestError,
)
from custom_components.google_air_quality_custom.const import API_URL


async def test_header_contains_key_and_url_has_no_key(
    aioclient_mock: AiohttpClientMocker,
) -> None:
    aioclient_mock.post(
        API_URL, json={"dateTime": "2026-01-01T00:00:00Z", "indexes": [], "pollutants": []}
    )
    session = aioclient_mock.create_session(asyncio.get_running_loop())
    try:
        client = GoogleAirQualityClient(session, "secret-key")
        await client.current_conditions({"foo": "bar"})
    finally:
        await session.close()

    method, url, _data, headers = aioclient_mock.mock_calls[0]
    assert headers["X-Goog-Api-Key"] == "secret-key"
    assert "secret-key" not in str(url)


@pytest.mark.parametrize(
    ("status", "expected_exc"),
    [
        (401, GoogleAirQualityAuthError),
        (403, GoogleAirQualityAuthError),
        (400, GoogleAirQualityRequestError),
        (500, GoogleAirQualityError),
    ],
)
async def test_status_code_mapping(
    aioclient_mock: AiohttpClientMocker, status: int, expected_exc: type[Exception]
) -> None:
    aioclient_mock.post(API_URL, status=status, json={"error": {"message": "boom"}})
    session = aioclient_mock.create_session(asyncio.get_running_loop())
    try:
        client = GoogleAirQualityClient(session, "key")
        with pytest.raises(expected_exc, match="boom"):
            await client.current_conditions({})
    finally:
        await session.close()


async def test_timeout_raises_generic_error(aioclient_mock: AiohttpClientMocker) -> None:
    aioclient_mock.post(API_URL, exc=TimeoutError())
    session = aioclient_mock.create_session(asyncio.get_running_loop())
    try:
        client = GoogleAirQualityClient(session, "key")
        with pytest.raises(GoogleAirQualityError, match="timed out"):
            await client.current_conditions({})
    finally:
        await session.close()


async def test_connection_error_raises_generic_error(aioclient_mock: AiohttpClientMocker) -> None:
    import aiohttp

    aioclient_mock.post(API_URL, exc=aiohttp.ClientConnectionError("boom"))
    session = aioclient_mock.create_session(asyncio.get_running_loop())
    try:
        client = GoogleAirQualityClient(session, "key")
        with pytest.raises(GoogleAirQualityError, match="connection error"):
            await client.current_conditions({})
    finally:
        await session.close()


def test_api_url_constant_unchanged() -> None:
    assert API_URL == "https://airquality.googleapis.com/v1/currentConditions:lookup"
