"""HTTP-to-weather regressions for https://github.com/aleksanderbl29/dmi-homeassistant/issues/26."""

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from yarl import URL

from custom_components.dmi.api import DMIApiClient
from custom_components.dmi.const import CONF_UPDATE_INTERVAL, FORECAST_URL, METOBS_URL
from custom_components.dmi.coordinator import DMIDataUpdateCoordinator
from custom_components.dmi.weather import DMIWeather
from tests.ha_test_compat import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
    MockConfigEntry,
    async_fire_time_changed,
)


@pytest.mark.parametrize(
    ("failures", "retry_after", "delays"),
    [
        (5, None, [1, 2, 4, 5, 5]),
        (1, "1200", [20]),
        (1, "Fri, 30 Oct 2026 12:20:00 GMT", [20]),
    ],
)
async def test_http_429_recovers_on_existing_weather_subscription(
    hass: HomeAssistant,
    freezer,
    aioclient_mock: AiohttpClientMocker,
    mock_config_entry: MockConfigEntry,
    mock_observations_data: dict[str, Any],
    mock_forecast_data: dict[str, Any],
    failures: int,
    retry_after: str | None,
    delays: list[int],
) -> None:
    """A real-shaped DMI 429 must recover through timers and notify the open weather card."""
    now = datetime(2026, 10, 30, 12, tzinfo=UTC)
    freezer.move_to(now)
    mock_config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        mock_config_entry, options={**mock_config_entry.options, CONF_UPDATE_INTERVAL: 60}
    )
    api = DMIApiClient(async_get_clientsession(hass))
    coordinator = DMIDataUpdateCoordinator(hass, mock_config_entry, api)
    weather = DMIWeather(coordinator, mock_config_entry)
    weather.hass = hass
    weather.entity_id = "weather.http_forecast_recovery"
    await weather.async_added_to_hass()
    listener = Mock()
    unsubscribe = weather.async_subscribe_forecast("hourly", listener)

    forecast_payload = deepcopy(mock_forecast_data)
    times = forecast_payload["domain"]["axes"]["t"]["values"]
    times[:] = [(now + timedelta(hours=i + 1)).isoformat() for i in range(len(times))]
    observation_url = f"{METOBS_URL}/collections/observation/items"
    forecast_url = f"{FORECAST_URL}/collections/harmonie_dini_sf/position"

    responses = iter(
        [
            AiohttpClientMockResponse(
                "get",
                URL(forecast_url),
                status=429,
                json={
                    "status": 429,
                    "error": "Too Many Requests",
                    "message": "Server is busy. Please try again later.",
                    "path": "/v1/forecastedr/collections/harmonie_dini_sf/position",
                },
                headers={"Retry-After": retry_after} if retry_after else {},
            )
            for _ in range(failures)
        ]
        + [AiohttpClientMockResponse("get", URL(forecast_url), json=forecast_payload)]
    )

    async def forecast_response(*_) -> AiohttpClientMockResponse:
        return next(responses)

    aioclient_mock.get(observation_url, json=mock_observations_data)
    aioclient_mock.get(forecast_url, side_effect=forecast_response)

    def request_count(endpoint: str) -> int:
        return sum(str(url).startswith(endpoint + "?") for _, url, *_ in aioclient_mock.mock_calls)

    try:
        with patch("custom_components.dmi.coordinator.asyncio.sleep", new_callable=AsyncMock):
            await coordinator.async_refresh()
        await hass.async_block_till_done()
        assert coordinator.weather_forecast_status == "retry_scheduled"
        assert weather.native_temperature == 15.5
        assert await weather.async_forecast_hourly() is None

        for attempt, minutes in enumerate(delays, start=1):
            retry_at = now + timedelta(minutes=minutes)
            freezer.move_to(retry_at - timedelta(seconds=1))
            async_fire_time_changed(hass, retry_at - timedelta(seconds=1))
            await hass.async_block_till_done()
            assert request_count(forecast_url) == attempt

            freezer.move_to(retry_at)
            async_fire_time_changed(hass, retry_at)
            await hass.async_block_till_done()
            assert request_count(forecast_url) == attempt + 1
            assert request_count(observation_url) == 1
            assert coordinator.data["last_updated"] == datetime(2026, 10, 30, 12, tzinfo=UTC)
            now = retry_at

        assert coordinator.weather_forecast_status == "available"
        assert coordinator.weather_forecast_retry_at is None
        listener.assert_called()
        delivered = listener.call_args.args[0]
        assert delivered is not None
        assert delivered[0]["datetime"] == times[0]
        assert delivered[0]["temperature"] == pytest.approx(15.5)
    finally:
        unsubscribe()
        await weather.async_remove()
        await coordinator.async_shutdown()
