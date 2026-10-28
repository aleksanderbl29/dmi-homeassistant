"""Retry lifecycle regressions for https://github.com/aleksanderbl29/dmi-homeassistant/issues/26."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.core import HomeAssistant

from custom_components.dmi.api import UpstreamError
from custom_components.dmi.coordinator import DMIDataUpdateCoordinator
from tests.ha_test_compat import MockConfigEntry, async_fire_time_changed


async def test_shutdown_cancels_inflight_forecast_retry(
    hass: HomeAssistant,
    freezer,
    mock_config_entry: MockConfigEntry,
    mock_api_client: MagicMock,
) -> None:
    """Issue #26 retries must not survive an unload and reschedule old requests."""
    mock_config_entry.add_to_hass(hass)
    coordinator = DMIDataUpdateCoordinator(hass, mock_config_entry, mock_api_client)
    now = datetime(2026, 10, 26, 12, tzinfo=UTC)
    started = asyncio.Event()
    release = asyncio.Event()
    cancelled = asyncio.Event()

    async def forecast_request(*_) -> None:
        if mock_api_client.get_forecast.await_count > 1:
            started.set()
            try:
                await release.wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise
        raise UpstreamError("busy")

    mock_api_client.get_forecast.side_effect = forecast_request
    freezer.move_to(now)
    try:
        with patch("custom_components.dmi.coordinator.asyncio.sleep", new_callable=AsyncMock):
            await coordinator.async_refresh()
        freezer.move_to(now + timedelta(minutes=1))
        async_fire_time_changed(hass, now + timedelta(minutes=1))
        async with asyncio.timeout(5):
            await started.wait()
        await coordinator.async_shutdown()
        release.set()
        await hass.async_block_till_done()
        freezer.move_to(now + timedelta(minutes=2))
        async_fire_time_changed(hass, now + timedelta(minutes=2))
        await hass.async_block_till_done()

        assert cancelled.is_set()
        assert mock_api_client.get_forecast.await_count == 2
    finally:
        release.set()
        await hass.async_block_till_done()
        await coordinator.async_shutdown()
