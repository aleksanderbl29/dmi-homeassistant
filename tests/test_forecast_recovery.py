"""Regressions for https://github.com/aleksanderbl29/dmi-homeassistant/issues/26."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dmi.api import (
    CannotConnect,
    RateLimitExceeded,
    RequestTimeout,
    UpstreamError,
)
from custom_components.dmi.coordinator import DMIDataUpdateCoordinator
from custom_components.dmi.weather import DMIWeather


@pytest.mark.parametrize(
    "error",
    [CannotConnect, RateLimitExceeded, RequestTimeout, UpstreamError, TimeoutError],
)
async def test_failed_forecast_recovers_on_next_observation_update(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: MagicMock,
    error: type[Exception],
) -> None:
    """Successful observations must not hide a stuck forecast after a transient failure."""
    mock_config_entry.add_to_hass(hass)
    coordinator = DMIDataUpdateCoordinator(hass, mock_config_entry, mock_api_client)
    now = datetime(2026, 10, 26, 12, tzinfo=UTC)
    recovered = {"hourly": [{"datetime": "2026-10-26T14:00:00Z", "temperature": 12}]}
    mock_api_client.get_forecast = AsyncMock(side_effect=[error("temporary failure"), recovered])

    with (
        patch("custom_components.dmi.coordinator.asyncio.sleep", new_callable=AsyncMock),
        patch("custom_components.dmi.coordinator.dt_util.utcnow", return_value=now) as clock,
    ):
        first = await coordinator._async_update_data()
        immediate = await coordinator._async_update_data()
        assert mock_api_client.get_forecast.await_count == 1

        clock.return_value = now + timedelta(minutes=10)
        second = await coordinator._async_update_data()
        clock.return_value = now + timedelta(minutes=20)
        cached = await coordinator._async_update_data()

    assert first["observations"]["temp_dry"]["value"] == 15.5
    assert first["last_updated"] == now
    assert first["forecast"] is None
    assert immediate["forecast"] is None
    assert second["forecast"] == recovered
    assert cached["forecast"] == recovered
    assert mock_api_client.get_observations.await_count == 4
    assert mock_api_client.get_forecast.await_count == 2


async def test_recovered_forecast_is_delivered_to_existing_subscriber(
    hass: HomeAssistant,
    mock_config_entry: MockConfigEntry,
    mock_api_client: MagicMock,
) -> None:
    """Push recovery to the same forecast subscription used by the weather card."""
    mock_config_entry.add_to_hass(hass)
    coordinator = DMIDataUpdateCoordinator(hass, mock_config_entry, mock_api_client)
    coordinator.async_set_updated_data({"observations": {}, "forecast": None})
    entity = DMIWeather(coordinator, mock_config_entry)
    entity.hass = hass
    entity.entity_id = "weather.forecast_recovery"
    await entity.async_added_to_hass()
    listener = Mock()
    unsubscribe = entity.async_subscribe_forecast("hourly", listener)
    try:
        coordinator.async_set_updated_data(
            {
                "observations": {},
                "forecast": {"hourly": [{"datetime": "2026-10-26T14:00:00Z", "temperature": 12}]},
            }
        )
        await hass.async_block_till_done()

        listener.assert_called_once()
        forecast = listener.call_args.args[0]
        assert forecast[0]["datetime"] == "2026-10-26T14:00:00Z"
        assert forecast[0]["temperature"] == 12
    finally:
        unsubscribe()
        await entity.async_remove()
