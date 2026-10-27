"""Tests for the DMI data update coordinator."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util

from custom_components.dmi.api import (
    CannotConnect,
    RateLimitExceeded,
    RequestTimeout,
    UpstreamError,
)
from custom_components.dmi.const import (
    CONF_BACKUP_ALLOW_OVERRIDE,
    CONF_BACKUP_PARAMETERS,
    CONF_BACKUP_STATIONS,
    CONF_HAS_SEA_OBSERVATIONS,
    CONF_INCLUDE_FORECAST,
    CONF_SEA_OBSERVATION_STATION_ID,
    CONF_SEA_OBSERVATION_STATION_NAME,
    CONF_SOURCE_STATION_ID,
    CONF_SOURCE_STATION_NAME,
    CONF_SOURCE_TYPE,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    CONF_TIDEWATER_STATION_ID,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
)
from custom_components.dmi.coordinator import (
    RATE_LIMIT_COOLDOWN,
    REQUEST_STAGGER_SECONDS,
    DMIDataUpdateCoordinator,
)
from tests.ha_test_compat import MockConfigEntry


class TestDMIDataUpdateCoordinator:
    """Test cases for DMIDataUpdateCoordinator."""

    @pytest.fixture
    def coordinator(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_api_client: MagicMock,
    ) -> DMIDataUpdateCoordinator:
        """Create a normal coordinator instance."""
        mock_config_entry.add_to_hass(hass)
        return DMIDataUpdateCoordinator(hass, mock_config_entry, mock_api_client)

    @pytest.fixture
    def advanced_coordinator(
        self,
        hass: HomeAssistant,
        advanced_config_entry: MockConfigEntry,
        mock_api_client: MagicMock,
    ) -> DMIDataUpdateCoordinator:
        """Create an advanced coordinator instance."""
        advanced_config_entry.add_to_hass(hass)
        return DMIDataUpdateCoordinator(hass, advanced_config_entry, mock_api_client)

    def test_coordinator_initialization(
        self,
        coordinator: DMIDataUpdateCoordinator,
    ) -> None:
        """Test coordinator initializes with correct values."""
        assert coordinator.station_id == "06180"
        assert coordinator.station_name == "Københavns Lufthavn"
        assert coordinator.update_interval == timedelta(minutes=10)
        assert coordinator.include_forecast is True

    def test_coordinator_with_custom_update_interval(
        self,
        hass: HomeAssistant,
        mock_api_client: MagicMock,
        mock_config_entry_data: dict[str, Any],
    ) -> None:
        """Test coordinator respects custom update interval."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test",
            data=mock_config_entry_data,
            options={CONF_UPDATE_INTERVAL: 30, CONF_INCLUDE_FORECAST: True},
        )
        entry.add_to_hass(hass)

        coordinator = DMIDataUpdateCoordinator(hass, entry, mock_api_client)

        assert coordinator.update_interval == timedelta(minutes=30)

    async def test_async_update_data_success(
        self,
        coordinator: DMIDataUpdateCoordinator,
        mock_api_client: MagicMock,
    ) -> None:
        """Test successful normal data update."""
        data = await coordinator._async_update_data()

        assert "observations" in data
        assert "forecast" in data
        assert data["observations"]["temp_dry"][CONF_SOURCE_STATION_ID] == "06180"
        mock_api_client.get_observations.assert_called_once_with("06180")
        mock_api_client.get_forecast.assert_called_once()

    async def test_weather_forecast_is_cached_between_observation_updates(
        self,
        coordinator: DMIDataUpdateCoordinator,
        mock_api_client: MagicMock,
    ) -> None:
        """Test frequent observations reuse the slower-moving weather forecast."""
        now = datetime(2026, 7, 26, 5, 0, tzinfo=UTC)
        forecast = {
            "hourly": [
                {
                    "datetime": "2026-07-26T06:00:00Z",
                    "temperature": 18.0,
                }
            ]
        }
        mock_api_client.get_forecast = AsyncMock(return_value=forecast)

        with (
            patch(
                "custom_components.dmi.coordinator.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.dmi.coordinator.dt_util.utcnow",
                return_value=now,
            ),
        ):
            first_data = await coordinator._async_update_data()
            second_data = await coordinator._async_update_data()

        assert first_data["forecast"] == forecast
        assert second_data["forecast"] == forecast
        assert mock_api_client.get_observations.await_count == 2
        mock_api_client.get_forecast.assert_awaited_once()

    async def test_weather_forecast_rate_limit_keeps_fresh_observations(
        self,
        coordinator: DMIDataUpdateCoordinator,
        mock_api_client: MagicMock,
    ) -> None:
        """Test Forecast EDR throttling does not throttle metObs updates."""
        mock_api_client.get_forecast = AsyncMock(side_effect=RateLimitExceeded("Server is busy"))

        with patch(
            "custom_components.dmi.coordinator.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            first_data = await coordinator._async_update_data()
            second_data = await coordinator._async_update_data()

        assert first_data["observations"]["temp_dry"]["value"] == 15.5
        assert second_data["observations"]["temp_dry"]["value"] == 15.5
        assert first_data["forecast"] is None
        assert coordinator._rate_limited_until is None
        assert mock_api_client.get_observations.await_count == 2
        mock_api_client.get_forecast.assert_awaited_once()
        await coordinator.async_shutdown()

    async def test_sea_update_fetches_tidewater_forecast(
        self,
        hass: HomeAssistant,
        mock_api_client: MagicMock,
    ) -> None:
        """Test sea entries fetch observations and astronomical predictions."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Korsør",
            data={
                "setup_type": "sea",
                CONF_STATION_ID: "30017",
                CONF_STATION_NAME: "Korsør",
                CONF_TIDEWATER_STATION_ID: "29393",
                "latitude": 55.33,
                "longitude": 11.14,
            },
            options={CONF_UPDATE_INTERVAL: 10},
        )
        entry.add_to_hass(hass)
        mock_api_client.get_sea_observations = AsyncMock(
            return_value={
                "sealev_dvr": {
                    "value": 26.0,
                    "observed": "2026-07-25T09:30:00Z",
                }
            }
        )
        predictions = [
            {
                "value": 16.1,
                "prediction_time": "2026-07-25T09:40:00Z",
                "prediction_type": "10minutes",
                "created": "2026-03-23T10:18:26Z",
                "station_id": "29393",
            }
        ]
        mock_api_client.get_tidewater_forecast = AsyncMock(return_value=predictions)
        dkss_forecast = {
            "collection_id": "dkss_idw",
            "model_latitude": 55.329,
            "model_longitude": 11.146,
            "forecast": [{"datetime": "2026-07-25T10:00:00Z", "value": 12.3}],
        }
        mock_api_client.get_dkss_forecast = AsyncMock(return_value=dkss_forecast)
        coordinator = DMIDataUpdateCoordinator(hass, entry, mock_api_client)
        now = datetime(2026, 7, 25, 9, 35, tzinfo=UTC)

        with (
            patch(
                "custom_components.dmi.coordinator.asyncio.sleep",
                new_callable=AsyncMock,
            ) as mock_sleep,
            patch(
                "custom_components.dmi.coordinator.dt_util.utcnow",
                return_value=now,
            ),
        ):
            data = await coordinator._async_update_data()
            cached_data = await coordinator._async_update_data()

        assert data["tidewater_forecast"] == predictions
        assert data["dkss_forecast"] == dkss_forecast
        assert cached_data["tidewater_forecast"] == predictions
        assert cached_data["dkss_forecast"] == dkss_forecast
        assert coordinator.tidewater_station_id == "29393"
        assert mock_api_client.get_sea_observations.await_count == 2
        mock_api_client.get_tidewater_forecast.assert_awaited_once()
        forecast_args = mock_api_client.get_tidewater_forecast.await_args.args
        assert forecast_args[0] == "29393"
        assert forecast_args[2] - forecast_args[1] == timedelta(hours=24)
        mock_api_client.get_dkss_forecast.assert_awaited_once()
        dkss_args = mock_api_client.get_dkss_forecast.await_args.args
        assert dkss_args[:2] == (55.33, 11.14)
        assert dkss_args[3] - dkss_args[2] == timedelta(hours=120)
        assert mock_sleep.await_args_list == [
            call(REQUEST_STAGGER_SECONDS),
            call(REQUEST_STAGGER_SECONDS),
        ]
        mock_api_client.get_forecast.assert_not_called()

    async def test_prediction_only_sea_update_fetches_backup_observations(
        self,
        hass: HomeAssistant,
        mock_api_client: MagicMock,
    ) -> None:
        """Test prediction-only stations fetch and attribute backup observations."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Kyndbyværket Havn",
            data={
                "setup_type": "sea",
                CONF_STATION_ID: "30121",
                CONF_STATION_NAME: "Kyndbyværket Havn",
                CONF_TIDEWATER_STATION_ID: "30121",
                CONF_HAS_SEA_OBSERVATIONS: False,
                CONF_SEA_OBSERVATION_STATION_ID: "30119",
                CONF_SEA_OBSERVATION_STATION_NAME: "Jægerspris Kignæs Havn",
                "latitude": 55.8117,
                "longitude": 11.8773,
            },
            options={CONF_UPDATE_INTERVAL: 10},
        )
        entry.add_to_hass(hass)
        mock_api_client.get_sea_observations = AsyncMock(
            return_value={
                "sea_reg": {
                    "value": 18.0,
                    "observed": "2026-08-02T09:30:00Z",
                }
            }
        )
        mock_api_client.get_tidewater_forecast = AsyncMock(return_value=[])
        mock_api_client.get_dkss_forecast = AsyncMock(return_value=None)
        coordinator = DMIDataUpdateCoordinator(hass, entry, mock_api_client)

        with patch(
            "custom_components.dmi.coordinator.asyncio.sleep",
            new_callable=AsyncMock,
        ):
            data = await coordinator._async_update_data()

        sea_level = data["observations"]["sea_reg"]
        assert sea_level["value"] == 18.0
        assert sea_level[CONF_SOURCE_STATION_ID] == "30119"
        assert sea_level[CONF_SOURCE_STATION_NAME] == "Jægerspris Kignæs Havn"
        assert sea_level[CONF_SOURCE_TYPE] == "backup"
        assert coordinator.has_sea_observations is False
        mock_api_client.get_sea_observations.assert_awaited_once_with("30119")
        mock_api_client.get_tidewater_forecast.assert_awaited_once()
        mock_api_client.get_dkss_forecast.assert_awaited_once()

    async def test_legacy_prediction_only_entry_skips_observation_request(
        self,
        hass: HomeAssistant,
        mock_api_client: MagicMock,
    ) -> None:
        """Test old prediction-only entries without a source remain compatible."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Kyndbyværket Havn",
            data={
                "setup_type": "sea",
                CONF_STATION_ID: "30121",
                CONF_STATION_NAME: "Kyndbyværket Havn",
                CONF_HAS_SEA_OBSERVATIONS: False,
            },
            options={CONF_UPDATE_INTERVAL: 10},
        )
        entry.add_to_hass(hass)
        coordinator = DMIDataUpdateCoordinator(hass, entry, mock_api_client)

        data = await coordinator._async_update_data()

        assert data["observations"] == {}
        mock_api_client.get_sea_observations.assert_not_called()

    async def test_sea_forecast_rate_limit_keeps_cached_forecasts(
        self,
        hass: HomeAssistant,
        mock_api_client: MagicMock,
    ) -> None:
        """Test forecast rate limits do not discard live sea observations."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Korsør",
            data={
                "setup_type": "sea",
                CONF_STATION_ID: "30017",
                CONF_STATION_NAME: "Korsør",
                CONF_TIDEWATER_STATION_ID: "29393",
                "latitude": 55.33,
                "longitude": 11.14,
            },
            options={CONF_UPDATE_INTERVAL: 10},
        )
        entry.add_to_hass(hass)
        now = datetime(2026, 7, 25, 9, 35, tzinfo=UTC)
        predictions = [
            {
                "value": 16.1,
                "prediction_time": "2026-07-25T09:40:00Z",
            }
        ]
        dkss_forecast = {
            "collection_id": "dkss_idw",
            "forecast": [{"datetime": "2026-07-25T10:00:00Z", "value": 12.3}],
        }
        mock_api_client.get_sea_observations = AsyncMock(
            return_value={"sealev_dvr": {"value": 26.0}}
        )
        mock_api_client.get_tidewater_forecast = AsyncMock(
            side_effect=[predictions, RateLimitExceeded("Rate limit")]
        )
        mock_api_client.get_dkss_forecast = AsyncMock(
            side_effect=[dkss_forecast, RateLimitExceeded("Rate limit")]
        )
        coordinator = DMIDataUpdateCoordinator(hass, entry, mock_api_client)

        with (
            patch(
                "custom_components.dmi.coordinator.asyncio.sleep",
                new_callable=AsyncMock,
            ),
            patch(
                "custom_components.dmi.coordinator.dt_util.utcnow",
                return_value=now,
            ),
        ):
            await coordinator._async_update_data()
            coordinator._tidewater_forecast_attempted_at = None
            coordinator._dkss_forecast_attempted_at = None
            data = await coordinator._async_update_data()

        assert data["observations"]["sealev_dvr"]["value"] == 26.0
        assert data["tidewater_forecast"] == predictions
        assert data["dkss_forecast"] == dkss_forecast
        assert mock_api_client.get_tidewater_forecast.await_count == 2
        assert mock_api_client.get_dkss_forecast.await_count == 2

    async def test_advanced_update_merges_backup_observations(
        self,
        advanced_coordinator: DMIDataUpdateCoordinator,
        mock_api_client: MagicMock,
    ) -> None:
        """Test advanced entries merge selected backup parameters."""
        data = await advanced_coordinator._async_update_data()

        assert data["observations"]["temp_dry"][CONF_SOURCE_STATION_ID] == "06186"
        assert data["observations"]["radia_glob"][CONF_SOURCE_STATION_ID] == "06187"
        assert data["observations"]["radia_glob"][CONF_SOURCE_TYPE] == "backup"
        assert data["observations"]["sun_last1h_glob"][CONF_SOURCE_STATION_ID] == "06187"
        mock_api_client.get_observations.assert_any_call("06186")
        mock_api_client.get_observations.assert_any_call("06187")
        mock_api_client.get_forecast.assert_called_once()

    async def test_advanced_update_ignores_legacy_override(
        self,
        hass: HomeAssistant,
        mock_api_client: MagicMock,
        mock_config_entry_options: dict[str, Any],
    ) -> None:
        """Test legacy override config does not replace primary observations."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Landbohojskolen + backups",
            data={
                "setup_type": "advanced",
                CONF_STATION_ID: "06186",
                CONF_STATION_NAME: "Landbohojskolen",
                "latitude": 55.68,
                "longitude": 12.53,
                "use_coordinates": False,
                CONF_BACKUP_STATIONS: [
                    {
                        CONF_STATION_ID: "06187",
                        CONF_STATION_NAME: "Kobenhavns Toldbod",
                        CONF_BACKUP_PARAMETERS: ["temp_dry"],
                        CONF_BACKUP_ALLOW_OVERRIDE: True,
                    }
                ],
            },
            options=mock_config_entry_options,
        )
        entry.add_to_hass(hass)

        coordinator = DMIDataUpdateCoordinator(hass, entry, mock_api_client)
        data = await coordinator._async_update_data()

        assert data["observations"]["temp_dry"]["value"] == 16.0
        assert data["observations"]["temp_dry"][CONF_SOURCE_STATION_ID] == "06186"

    async def test_advanced_update_without_override_keeps_primary(
        self,
        advanced_coordinator: DMIDataUpdateCoordinator,
        mock_api_client: MagicMock,
    ) -> None:
        """Test backup overlap does not replace the primary without override."""
        advanced_coordinator.backup_stations[0][CONF_BACKUP_PARAMETERS] = ["temp_dry"]

        data = await advanced_coordinator._async_update_data()

        assert data["observations"]["temp_dry"]["value"] == 16.0
        assert data["observations"]["temp_dry"][CONF_SOURCE_STATION_ID] == "06186"

    @pytest.mark.parametrize(
        "backup_error",
        [
            CannotConnect("Connection failed"),
            RequestTimeout("Timeout"),
            UpstreamError("HTTP 503"),
        ],
    )
    async def test_advanced_update_skips_failed_backup(
        self,
        advanced_coordinator: DMIDataUpdateCoordinator,
        mock_api_client: MagicMock,
        backup_error: Exception,
    ) -> None:
        """Test backup failures do not discard freshly fetched primary data."""

        async def get_observations(station_id: str) -> dict[str, Any]:
            if station_id == "06186":
                return {
                    "temp_dry": {"value": 16.0, "observed": "2024-01-15T12:00:00Z"},
                    "humidity": {"value": 70.0, "observed": "2024-01-15T12:00:00Z"},
                }
            raise backup_error

        mock_api_client.get_observations = AsyncMock(side_effect=get_observations)

        data = await advanced_coordinator._async_update_data()

        assert data["observations"]["temp_dry"]["value"] == 16.0
        assert data["observations"]["temp_dry"][CONF_SOURCE_STATION_ID] == "06186"
        assert "radia_glob" not in data["observations"]
        mock_api_client.get_observations.assert_has_awaits([call("06186"), call("06187")])

    async def test_advanced_update_continues_after_failed_backup(
        self,
        hass: HomeAssistant,
        mock_api_client: MagicMock,
        mock_config_entry_options: dict[str, Any],
    ) -> None:
        """Test one failed backup does not stop later backups from being merged."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Landbohojskolen + backups",
            data={
                "setup_type": "advanced",
                CONF_STATION_ID: "06186",
                CONF_STATION_NAME: "Landbohojskolen",
                "latitude": 55.68,
                "longitude": 12.53,
                "use_coordinates": False,
                CONF_BACKUP_STATIONS: [
                    {
                        CONF_STATION_ID: "06187",
                        CONF_STATION_NAME: "Kobenhavns Toldbod",
                        CONF_BACKUP_PARAMETERS: ["radia_glob"],
                    },
                    {
                        CONF_STATION_ID: "06070",
                        CONF_STATION_NAME: "Aarhus Lufthavn",
                        CONF_BACKUP_PARAMETERS: ["pressure_at_sea"],
                    },
                ],
            },
            options=mock_config_entry_options,
        )
        entry.add_to_hass(hass)

        async def get_observations(station_id: str) -> dict[str, Any]:
            if station_id == "06186":
                return {
                    "temp_dry": {"value": 16.0, "observed": "2024-01-15T12:00:00Z"},
                }
            if station_id == "06187":
                raise CannotConnect("Connection failed")
            return {
                "pressure_at_sea": {
                    "value": 1012.0,
                    "observed": "2024-01-15T12:00:00Z",
                },
            }

        mock_api_client.get_observations = AsyncMock(side_effect=get_observations)
        coordinator = DMIDataUpdateCoordinator(hass, entry, mock_api_client)

        data = await coordinator._async_update_data()

        assert "radia_glob" not in data["observations"]
        assert data["observations"]["pressure_at_sea"]["value"] == 1012.0
        assert data["observations"]["pressure_at_sea"][CONF_SOURCE_STATION_ID] == "06070"
        mock_api_client.get_observations.assert_has_awaits(
            [call("06186"), call("06187"), call("06070")]
        )

    async def test_advanced_backup_rate_limit_uses_global_cooldown(
        self,
        advanced_coordinator: DMIDataUpdateCoordinator,
        mock_api_client: MagicMock,
    ) -> None:
        """Test backup rate limits still trigger the coordinator cooldown."""

        async def get_observations(station_id: str) -> dict[str, Any]:
            if station_id == "06186":
                return {
                    "temp_dry": {"value": 16.0, "observed": "2024-01-15T12:00:00Z"},
                }
            raise RateLimitExceeded("Rate limit")

        mock_api_client.get_observations = AsyncMock(side_effect=get_observations)

        data = await advanced_coordinator._async_update_data()

        assert advanced_coordinator._rate_limited_until is not None
        assert data["observations"] == {}

        advanced_coordinator.data = data
        calls_before_cooldown = mock_api_client.get_observations.await_count

        cached_data = await advanced_coordinator._async_update_data()

        assert cached_data is data
        assert mock_api_client.get_observations.await_count == calls_before_cooldown

    async def test_rate_limit_cooldown_serves_cached_data(
        self,
        coordinator: DMIDataUpdateCoordinator,
        mock_api_client: MagicMock,
    ) -> None:
        """Test active cooldown skips API calls and serves cached data."""
        cached_data = {
            "observations": {"temp_dry": {"value": 15.5, "observed": "2024-01-15T12:00:00Z"}},
            "forecast": None,
            "last_updated": "cached",
        }
        coordinator.data = cached_data
        coordinator._rate_limited_until = dt_util.utcnow() + timedelta(minutes=1)

        data = await coordinator._async_update_data()

        assert data is cached_data
        mock_api_client.get_observations.assert_not_called()
        mock_api_client.get_forecast.assert_not_called()

    async def test_rate_limit_state_is_shared_between_entries(
        self,
        hass: HomeAssistant,
        mock_api_client: MagicMock,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test a new coordinator honors a previous coordinator's cooldown."""
        mock_config_entry.add_to_hass(hass)
        first = DMIDataUpdateCoordinator(hass, mock_config_entry, mock_api_client)
        first._rate_limited_until = dt_util.utcnow() + RATE_LIMIT_COOLDOWN

        second = DMIDataUpdateCoordinator(hass, mock_config_entry, mock_api_client)

        data = await second._async_update_data()

        assert data == second._empty_data()
        mock_api_client.get_observations.assert_not_called()

    async def test_repeated_rate_limits_increase_shared_cooldown(
        self,
        coordinator: DMIDataUpdateCoordinator,
        mock_api_client: MagicMock,
    ) -> None:
        """Test repeated 429 responses progressively increase the cooldown."""
        mock_api_client.get_observations.side_effect = RateLimitExceeded("Rate limit")

        first_data = await coordinator._async_update_data()
        first_deadline = coordinator._rate_limited_until
        assert first_deadline is not None
        assert first_data == coordinator._empty_data()

        coordinator._rate_limited_until = None
        second_data = await coordinator._async_update_data()
        second_deadline = coordinator._rate_limited_until
        assert second_deadline is not None
        assert second_data == coordinator._empty_data()

        assert second_deadline - dt_util.utcnow() > RATE_LIMIT_COOLDOWN

    async def test_advanced_update_staggers_backup_fetches(
        self,
        advanced_coordinator: DMIDataUpdateCoordinator,
        mock_api_client: MagicMock,
    ) -> None:
        """Test backup observation fetches are staggered to avoid request bursts."""
        with patch(
            "custom_components.dmi.coordinator.asyncio.sleep",
            new_callable=AsyncMock,
        ) as mock_sleep:
            await advanced_coordinator._async_update_data()

        assert mock_sleep.await_count == 2
        assert mock_sleep.await_args_list == [
            call(REQUEST_STAGGER_SECONDS),
            call(REQUEST_STAGGER_SECONDS),
        ]

    async def test_async_update_data_without_forecast(
        self,
        hass: HomeAssistant,
        mock_api_client: MagicMock,
        mock_config_entry_data: dict[str, Any],
    ) -> None:
        """Test data update with forecast disabled."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test",
            data=mock_config_entry_data,
            options={CONF_UPDATE_INTERVAL: 10, CONF_INCLUDE_FORECAST: False},
        )
        entry.add_to_hass(hass)

        coordinator = DMIDataUpdateCoordinator(hass, entry, mock_api_client)
        data = await coordinator._async_update_data()

        assert data["forecast"] is None
        mock_api_client.get_forecast.assert_not_called()

    async def test_initial_rate_limit_returns_unavailable_data(
        self,
        coordinator: DMIDataUpdateCoordinator,
        mock_api_client: MagicMock,
    ) -> None:
        """Test a rate limit does not prevent initial entry setup."""
        mock_api_client.get_observations.side_effect = RateLimitExceeded("Rate limit")

        data = await coordinator._async_update_data()

        assert data == {
            "observations": {},
            "forecast": None,
            "tidewater_forecast": None,
            "dkss_forecast": None,
            "last_updated": None,
        }

    async def test_sea_initial_rate_limit_returns_unavailable_data(
        self,
        hass: HomeAssistant,
        mock_api_client: MagicMock,
    ) -> None:
        """Test a rate limit does not prevent initial sea entry setup."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Korsør",
            data={
                "setup_type": "sea",
                CONF_STATION_ID: "30017",
                CONF_STATION_NAME: "Korsør",
            },
            options={CONF_UPDATE_INTERVAL: 10},
        )
        entry.add_to_hass(hass)
        mock_api_client.get_sea_observations = AsyncMock(
            side_effect=RateLimitExceeded("Rate limit")
        )
        coordinator = DMIDataUpdateCoordinator(hass, entry, mock_api_client)

        data = await coordinator._async_update_data()

        assert data == {
            "observations": {},
            "forecast": None,
            "tidewater_forecast": None,
            "dkss_forecast": None,
            "last_updated": None,
        }

    async def test_async_update_data_connection_error_uses_cached_data(
        self,
        coordinator: DMIDataUpdateCoordinator,
        mock_api_client: MagicMock,
    ) -> None:
        """Test cached data is kept on connection error after initial success."""
        cached_data = {
            "observations": {"temp_dry": {"value": 15.5, "observed": "2024-01-15T12:00:00Z"}},
            "forecast": None,
            "last_updated": "cached",
        }
        coordinator.data = cached_data
        mock_api_client.get_observations.side_effect = CannotConnect("Connection failed")

        data = await coordinator._async_update_data()

        assert data is cached_data

    async def test_async_update_data_upstream_error_uses_cached_data(
        self,
        coordinator: DMIDataUpdateCoordinator,
        mock_api_client: MagicMock,
    ) -> None:
        """Test cached data is kept on upstream error after initial success."""
        cached_data = {
            "observations": {"temp_dry": {"value": 15.5, "observed": "2024-01-15T12:00:00Z"}},
            "forecast": None,
            "last_updated": "cached",
        }
        coordinator.data = cached_data
        mock_api_client.get_observations.side_effect = UpstreamError("HTTP 503")

        data = await coordinator._async_update_data()

        assert data is cached_data

    async def test_async_update_data_timeout_uses_cached_data(
        self,
        coordinator: DMIDataUpdateCoordinator,
        mock_api_client: MagicMock,
    ) -> None:
        """Test cached data is kept on timeout after initial success."""
        cached_data = {
            "observations": {"temp_dry": {"value": 15.5, "observed": "2024-01-15T12:00:00Z"}},
            "forecast": None,
            "last_updated": "cached",
        }
        coordinator.data = cached_data
        mock_api_client.get_observations.side_effect = RequestTimeout("Timeout")

        data = await coordinator._async_update_data()

        assert data is cached_data

    async def test_advanced_primary_failure_uses_cached_data(
        self,
        advanced_coordinator: DMIDataUpdateCoordinator,
        mock_api_client: MagicMock,
    ) -> None:
        """Test advanced entries keep cached data when the primary station fails."""
        cached_data = {
            "observations": {"temp_dry": {"value": 15.5, "observed": "2024-01-15T12:00:00Z"}},
            "forecast": None,
            "last_updated": "cached",
        }
        advanced_coordinator.data = cached_data
        mock_api_client.get_observations.side_effect = CannotConnect("Connection failed")

        data = await advanced_coordinator._async_update_data()

        assert data is cached_data
