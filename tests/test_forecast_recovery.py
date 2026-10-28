"""Regressions for https://github.com/aleksanderbl29/dmi-homeassistant/issues/26."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from homeassistant.core import Event, HomeAssistant, callback

from custom_components.dmi.api import (
    CannotConnect,
    RateLimitExceeded,
    RequestTimeout,
    UpstreamError,
)
from custom_components.dmi.coordinator import DMIDataUpdateCoordinator
from custom_components.dmi.weather import DMIWeather
from tests.ha_test_compat import MockConfigEntry, async_fire_time_changed


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


async def test_failed_forecast_retries_automatically_after_one_minute(
    hass: HomeAssistant,
    freezer,
    mock_config_entry: MockConfigEntry,
    mock_api_client: MagicMock,
) -> None:
    """Retry a failed forecast at its deadline without waiting for the poll interval."""
    mock_config_entry.add_to_hass(hass)
    coordinator = DMIDataUpdateCoordinator(hass, mock_config_entry, mock_api_client)
    now = datetime(2026, 10, 26, 12, tzinfo=UTC)
    recovered = {"hourly": [{"datetime": "2026-10-26T14:00:00Z", "temperature": 12}]}
    mock_api_client.get_forecast = AsyncMock(
        side_effect=[UpstreamError("temporary failure"), recovered]
    )

    freezer.move_to(now)
    try:
        with patch("custom_components.dmi.coordinator.asyncio.sleep", new_callable=AsyncMock):
            await coordinator.async_refresh()
            assert mock_api_client.get_forecast.await_count == 1

            freezer.move_to(now + timedelta(seconds=59))
            async_fire_time_changed(hass, now + timedelta(seconds=59))
            await hass.async_block_till_done()
            assert mock_api_client.get_forecast.await_count == 1

            freezer.move_to(now + timedelta(minutes=1))
            async_fire_time_changed(hass, now + timedelta(minutes=1))
            await hass.async_block_till_done()

        assert mock_api_client.get_forecast.await_count == 2
        assert mock_api_client.get_observations.await_count == 1
        assert coordinator.data["forecast"] == recovered
    finally:
        await coordinator.async_shutdown()


async def test_rate_limited_forecast_retry_backs_off_without_refetching_observations(
    hass: HomeAssistant,
    freezer,
    mock_config_entry: MockConfigEntry,
    mock_api_client: MagicMock,
) -> None:
    """Back off repeated forecast 429s and keep observation requests on their cadence."""
    mock_config_entry.add_to_hass(hass)
    coordinator = DMIDataUpdateCoordinator(hass, mock_config_entry, mock_api_client)
    now = datetime(2026, 10, 26, 12, tzinfo=UTC)
    recovered = {"hourly": [{"datetime": "2026-10-26T14:00:00Z", "temperature": 12}]}
    mock_api_client.get_forecast = AsyncMock(
        side_effect=[RateLimitExceeded("busy"), RateLimitExceeded("busy"), recovered]
    )

    freezer.move_to(now)
    try:
        with patch("custom_components.dmi.coordinator.asyncio.sleep", new_callable=AsyncMock):
            await coordinator.async_refresh()
            assert mock_api_client.get_forecast.await_count == 1
            assert mock_api_client.get_observations.await_count == 1

            freezer.move_to(now + timedelta(minutes=1))
            async_fire_time_changed(hass, now + timedelta(minutes=1))
            await hass.async_block_till_done()
            assert mock_api_client.get_forecast.await_count == 2
            assert mock_api_client.get_observations.await_count == 1

            freezer.move_to(now + timedelta(minutes=2))
            async_fire_time_changed(hass, now + timedelta(minutes=2))
            await hass.async_block_till_done()
            assert mock_api_client.get_forecast.await_count == 2
            assert mock_api_client.get_observations.await_count == 1

            freezer.move_to(now + timedelta(minutes=3))
            async_fire_time_changed(hass, now + timedelta(minutes=3))
            await hass.async_block_till_done()

        assert mock_api_client.get_forecast.await_count == 3
        assert mock_api_client.get_observations.await_count == 1
        assert coordinator.data["forecast"] == recovered
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("cache_state", ["missing", "empty", "expired", "available"])
async def test_forecast_backoff_cap_depends_on_usable_cache(
    hass: HomeAssistant,
    freezer,
    mock_config_entry: MockConfigEntry,
    mock_api_client: MagicMock,
    cache_state: str,
) -> None:
    """Issue #26 recovery stays responsive when no unexpired forecast is available."""
    mock_config_entry.add_to_hass(hass)
    coordinator = DMIDataUpdateCoordinator(hass, mock_config_entry, mock_api_client)
    now = datetime(2026, 10, 26, 12, tzinfo=UTC)
    freezer.move_to(now)
    try:
        with patch("custom_components.dmi.coordinator.asyncio.sleep", new_callable=AsyncMock):
            if cache_state != "missing":
                forecast_time = now + timedelta(hours=1 if cache_state == "expired" else 48)
                mock_api_client.get_forecast.return_value = {
                    "hourly": []
                    if cache_state == "empty"
                    else [{"datetime": forecast_time.isoformat(), "temperature": 12}]
                }
                await coordinator.async_refresh()
                now += timedelta(hours=3)
                freezer.move_to(now)
                mock_api_client.get_forecast.reset_mock()

            mock_api_client.get_forecast.side_effect = RateLimitExceeded("busy")
            await coordinator.async_refresh()
        observation_requests = mock_api_client.get_observations.await_count
        cap = 60 if cache_state == "available" else 5

        for attempt in range(10):
            retry_at = now + timedelta(minutes=min(2**attempt, cap))
            assert coordinator.weather_forecast_retry_at == retry_at
            freezer.move_to(retry_at - timedelta(seconds=1))
            async_fire_time_changed(hass, retry_at - timedelta(seconds=1))
            await hass.async_block_till_done()
            assert mock_api_client.get_forecast.await_count == attempt + 1

            freezer.move_to(retry_at)
            async_fire_time_changed(hass, retry_at)
            await hass.async_block_till_done()
            assert mock_api_client.get_forecast.await_count == attempt + 2
            assert mock_api_client.get_observations.await_count == observation_requests
            now = retry_at

        recovered = {"hourly": [{"datetime": "2026-10-28T12:00:00Z", "temperature": 12}]}
        mock_api_client.get_forecast.side_effect = None
        mock_api_client.get_forecast.return_value = recovered
        retry_at = coordinator.weather_forecast_retry_at
        freezer.move_to(retry_at)
        async_fire_time_changed(hass, retry_at)
        await hass.async_block_till_done()
        assert coordinator.data["forecast"] == recovered
        assert coordinator.weather_forecast_retry_at is None

        now = retry_at + timedelta(hours=3)
        freezer.move_to(now)
        mock_api_client.get_forecast.side_effect = RateLimitExceeded("busy")
        with patch("custom_components.dmi.coordinator.asyncio.sleep", new_callable=AsyncMock):
            await coordinator.async_refresh()
        assert coordinator.weather_forecast_retry_at == now + timedelta(minutes=1)
    finally:
        await coordinator.async_shutdown()


@pytest.mark.parametrize("retry_seconds", [30, 600, 7200])
async def test_forecast_respects_server_retry_deadline(
    hass: HomeAssistant,
    freezer,
    mock_config_entry: MockConfigEntry,
    mock_api_client: MagicMock,
    retry_seconds: int,
) -> None:
    """Never retry earlier than Retry-After, even beyond our fallback backoff cap."""
    mock_config_entry.add_to_hass(hass)
    coordinator = DMIDataUpdateCoordinator(hass, mock_config_entry, mock_api_client)
    now = datetime(2026, 10, 26, 12, tzinfo=UTC)
    recovered = {"hourly": [{"datetime": "2026-10-27T14:00:00Z", "temperature": 12}]}
    mock_api_client.get_forecast = AsyncMock(
        side_effect=[
            RateLimitExceeded("busy", retry_at=now + timedelta(seconds=retry_seconds)),
            recovered,
        ]
    )
    retry_at = now + timedelta(seconds=max(60, retry_seconds))

    freezer.move_to(now)
    try:
        with patch("custom_components.dmi.coordinator.asyncio.sleep", new_callable=AsyncMock):
            await coordinator.async_refresh()
            freezer.move_to(retry_at - timedelta(seconds=1))
            async_fire_time_changed(hass, retry_at - timedelta(seconds=1))
            await hass.async_block_till_done()
            assert mock_api_client.get_forecast.await_count == 1

            freezer.move_to(retry_at)
            async_fire_time_changed(hass, retry_at)
            await hass.async_block_till_done()

        assert mock_api_client.get_forecast.await_count == 2
        assert mock_api_client.get_observations.await_count == 1
        assert coordinator.data["forecast"] == recovered
    finally:
        await coordinator.async_shutdown()


async def test_observations_respect_server_retry_deadline(
    hass: HomeAssistant,
    freezer,
    mock_config_entry: MockConfigEntry,
    mock_api_client: MagicMock,
) -> None:
    """Honor the same server deadline when observations receive HTTP 429."""
    mock_config_entry.add_to_hass(hass)
    coordinator = DMIDataUpdateCoordinator(hass, mock_config_entry, mock_api_client)
    now = datetime(2026, 10, 26, 12, tzinfo=UTC)
    mock_api_client.get_observations.side_effect = RateLimitExceeded(
        "busy", retry_at=now + timedelta(hours=2)
    )
    freezer.move_to(now)
    try:
        await coordinator.async_refresh()
        freezer.move_to(now + timedelta(hours=1))
        await coordinator.async_refresh()
        assert mock_api_client.get_observations.await_count == 1
        freezer.move_to(now + timedelta(hours=2))
        await coordinator.async_refresh()
        assert mock_api_client.get_observations.await_count == 2
    finally:
        await coordinator.async_shutdown()


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


async def test_forecast_status_entity_shows_retry_progress_and_recovery(
    hass: HomeAssistant,
    freezer,
    mock_config_entry: MockConfigEntry,
    mock_dmi_api: MagicMock,
) -> None:
    """Expose issue #26 retry progress through a real Home Assistant entity."""
    now = datetime(2026, 10, 26, 12, tzinfo=UTC)
    retry_at = now + timedelta(minutes=5)
    recovered = {"hourly": [{"datetime": "2026-10-26T14:00:00Z", "temperature": 12}]}
    mock_dmi_api.get_forecast = AsyncMock(
        side_effect=[RateLimitExceeded("busy", retry_at=retry_at), recovered]
    )
    entity_id = "sensor.kobenhavns_lufthavn_forecast_status"
    states: list[str] = []

    @callback
    def record_status(event: Event) -> None:
        if event.data["entity_id"] == entity_id and (state := event.data["new_state"]):
            states.append(state.state)

    unsubscribe = hass.bus.async_listen("state_changed", record_status)
    freezer.move_to(now)
    mock_config_entry.add_to_hass(hass)
    try:
        with patch("custom_components.dmi.coordinator.asyncio.sleep", new_callable=AsyncMock):
            assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
            await hass.async_block_till_done()
            status = hass.states.get(entity_id)
            assert status is not None
            assert status.state == "retry_scheduled"
            assert status.attributes["retry_at"] == retry_at.isoformat()
            assert hass.states.get("weather.kobenhavns_lufthavn").state == "partlycloudy"

            freezer.move_to(retry_at)
            async_fire_time_changed(hass, retry_at)
            await hass.async_block_till_done()

        status = hass.states.get(entity_id)
        assert status.state == "available"
        assert status.attributes["retry_at"] is None
        assert states == ["retry_scheduled", "fetching", "available"]
    finally:
        unsubscribe()
        await hass.config_entries.async_unload(mock_config_entry.entry_id)


async def test_forecast_retry_waits_for_shared_observation_cooldown(
    hass: HomeAssistant,
    freezer,
    mock_config_entry: MockConfigEntry,
    mock_api_client: MagicMock,
) -> None:
    """Issue #26 retries must honor a later 429 received by another DMI entry."""
    mock_config_entry.add_to_hass(hass)
    coordinator = DMIDataUpdateCoordinator(hass, mock_config_entry, mock_api_client)
    other_entry = DMIDataUpdateCoordinator(hass, mock_config_entry, mock_api_client)
    now = datetime(2026, 10, 26, 12, tzinfo=UTC)
    recovered = {"hourly": [{"datetime": "2026-10-26T14:00:00Z", "temperature": 12}]}
    mock_api_client.get_forecast.side_effect = [UpstreamError("busy"), recovered]
    freezer.move_to(now)
    try:
        with patch("custom_components.dmi.coordinator.asyncio.sleep", new_callable=AsyncMock):
            await coordinator.async_refresh()
        freezer.move_to(now + timedelta(seconds=30))
        mock_api_client.get_observations.side_effect = RateLimitExceeded(
            "busy", retry_at=now + timedelta(minutes=5)
        )
        await other_entry.async_refresh()

        freezer.move_to(now + timedelta(minutes=1))
        async_fire_time_changed(hass, now + timedelta(minutes=1))
        await hass.async_block_till_done()
        assert mock_api_client.get_forecast.await_count == 1
        assert coordinator.weather_forecast_retry_at == now + timedelta(minutes=5)

        freezer.move_to(now + timedelta(minutes=5))
        async_fire_time_changed(hass, now + timedelta(minutes=5))
        await hass.async_block_till_done()
        assert mock_api_client.get_forecast.await_count == 2
        assert coordinator.data["forecast"] == recovered
    finally:
        await coordinator.async_shutdown()
        await other_entry.async_shutdown()
