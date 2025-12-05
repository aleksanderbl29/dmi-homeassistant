"""Tests for the DMI data update coordinator."""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dmi.api import CannotConnect, DMIApiClient, RateLimitExceeded
from custom_components.dmi.const import (
    CONF_INCLUDE_FORECAST,
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
        """Create a coordinator instance."""
        mock_config_entry.add_to_hass(hass)
        return DMIDataUpdateCoordinator(
            hass,
            mock_config_entry,
            mock_api_client,
        )

    def test_coordinator_initialization(
        self,
        coordinator: DMIDataUpdateCoordinator,
    ) -> None:
        """Test coordinator initializes with correct values."""
        assert coordinator.station_id == "06180"
        assert coordinator.station_name == "Københavns Lufthavn"
        assert coordinator.latitude == 55.614
        assert coordinator.longitude == 12.6455
        assert coordinator.include_forecast is True
        assert coordinator.update_interval == timedelta(minutes=10)

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
            options={
                CONF_UPDATE_INTERVAL: 30,  # 30 minutes
                CONF_INCLUDE_FORECAST: True,
            },
        )
        entry.add_to_hass(hass)

        coordinator = DMIDataUpdateCoordinator(hass, entry, mock_api_client)

        assert coordinator.update_interval == timedelta(minutes=30)

    def test_coordinator_forecast_disabled(
        self,
        hass: HomeAssistant,
        mock_api_client: MagicMock,
        mock_config_entry_data: dict[str, Any],
    ) -> None:
        """Test coordinator with forecast disabled."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test",
            data=mock_config_entry_data,
            options={
                CONF_UPDATE_INTERVAL: 10,
                CONF_INCLUDE_FORECAST: False,
            },
        )
        entry.add_to_hass(hass)

        coordinator = DMIDataUpdateCoordinator(hass, entry, mock_api_client)

        assert coordinator.include_forecast is False

    def test_coordinator_missing_coordinates(
        self,
        hass: HomeAssistant,
        mock_api_client: MagicMock,
    ) -> None:
        """Test coordinator handles missing coordinates."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test",
            data={
                CONF_STATION_ID: "06180",
                CONF_STATION_NAME: "Test",
                # No latitude/longitude
            },
            options={},
        )
        entry.add_to_hass(hass)

        coordinator = DMIDataUpdateCoordinator(hass, entry, mock_api_client)

        assert coordinator.latitude is None
        assert coordinator.longitude is None

    async def test_async_update_data_success(
        self,
        coordinator: DMIDataUpdateCoordinator,
        mock_api_client: MagicMock,
    ) -> None:
        """Test successful data update."""
        data = await coordinator._async_update_data()

        assert "observations" in data
        assert "forecast" in data
        assert "last_updated" in data

        mock_api_client.get_observations.assert_called_once_with("06180")
        mock_api_client.get_forecast.assert_called_once_with(55.614, 12.6455)

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
            options={
                CONF_UPDATE_INTERVAL: 10,
                CONF_INCLUDE_FORECAST: False,
            },
        )
        entry.add_to_hass(hass)

        coordinator = DMIDataUpdateCoordinator(hass, entry, mock_api_client)
        data = await coordinator._async_update_data()

        assert "observations" in data
        assert data["forecast"] is None
        mock_api_client.get_forecast.assert_not_called()

    async def test_async_update_data_without_coordinates(
        self,
        hass: HomeAssistant,
        mock_api_client: MagicMock,
    ) -> None:
        """Test data update without coordinates (no forecast)."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test",
            data={
                CONF_STATION_ID: "06180",
                CONF_STATION_NAME: "Test",
                # No coordinates
            },
            options={
                CONF_UPDATE_INTERVAL: 10,
                CONF_INCLUDE_FORECAST: True,
            },
        )
        entry.add_to_hass(hass)

        coordinator = DMIDataUpdateCoordinator(hass, entry, mock_api_client)
        data = await coordinator._async_update_data()

        assert "observations" in data
        assert data["forecast"] is None
        mock_api_client.get_forecast.assert_not_called()

    async def test_async_update_data_forecast_error_continues(
        self,
        coordinator: DMIDataUpdateCoordinator,
        mock_api_client: MagicMock,
    ) -> None:
        """Test that forecast error doesn't fail the entire update."""
        mock_api_client.get_forecast.side_effect = Exception("Forecast error")

        data = await coordinator._async_update_data()

        assert "observations" in data
        assert data["forecast"] is None  # Forecast failed but update succeeded

    async def test_async_update_data_rate_limit(
        self,
        coordinator: DMIDataUpdateCoordinator,
        mock_api_client: MagicMock,
    ) -> None:
        """Test rate limit error raises UpdateFailed."""
        mock_api_client.get_observations.side_effect = RateLimitExceeded("Rate limit")

        with pytest.raises(UpdateFailed) as exc_info:
            await coordinator._async_update_data()

        assert "Rate limit exceeded" in str(exc_info.value)

    async def test_async_update_data_connection_error(
        self,
        coordinator: DMIDataUpdateCoordinator,
        mock_api_client: MagicMock,
    ) -> None:
        """Test connection error raises UpdateFailed."""
        mock_api_client.get_observations.side_effect = CannotConnect("Connection failed")

        with pytest.raises(UpdateFailed) as exc_info:
            await coordinator._async_update_data()

        assert "Connection error" in str(exc_info.value)

    async def test_async_update_data_timeout(
        self,
        coordinator: DMIDataUpdateCoordinator,
        mock_api_client: MagicMock,
    ) -> None:
        """Test timeout raises UpdateFailed."""
        mock_api_client.get_observations.side_effect = TimeoutError("Timeout")

        with pytest.raises(UpdateFailed) as exc_info:
            await coordinator._async_update_data()

        assert "Timeout" in str(exc_info.value)

    def test_coordinator_name(
        self,
        coordinator: DMIDataUpdateCoordinator,
    ) -> None:
        """Test coordinator name is set correctly."""
        assert coordinator.name == f"{DOMAIN} (Københavns Lufthavn)"
