"""Tests for the DMI data update coordinator."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
    CONF_INCLUDE_FORECAST,
    CONF_SOURCE_STATION_ID,
    CONF_SOURCE_TYPE,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
)
from custom_components.dmi.coordinator import DMIDataUpdateCoordinator


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

    async def test_async_update_data_rate_limit(
        self,
        coordinator: DMIDataUpdateCoordinator,
        mock_api_client: MagicMock,
    ) -> None:
        """Test rate limit error raises UpdateFailed."""
        mock_api_client.get_observations.side_effect = RateLimitExceeded("Rate limit")

        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

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
