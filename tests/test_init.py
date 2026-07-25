"""Tests for the DMI integration setup and teardown."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dmi import PLATFORMS
from custom_components.dmi.api import RateLimitExceeded
from custom_components.dmi.const import (
    CONF_SETUP_TYPE,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    DOMAIN,
    SETUP_TYPE_SEA,
)


class TestIntegrationSetup:
    """Test cases for integration setup."""

    def test_platforms_defined(self) -> None:
        """Test that correct platforms are defined."""
        assert Platform.WEATHER in PLATFORMS
        assert Platform.SENSOR in PLATFORMS
        assert len(PLATFORMS) == 2

    async def test_setup_entry_success(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_dmi_api: MagicMock,
    ) -> None:
        """Test successful setup of config entry."""
        mock_config_entry.add_to_hass(hass)

        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert mock_config_entry.state is ConfigEntryState.LOADED
        assert DOMAIN in hass.data
        assert mock_config_entry.entry_id in hass.data[DOMAIN]

    async def test_setup_entry_creates_coordinator(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_dmi_api: MagicMock,
    ) -> None:
        """Test setup creates coordinator and stores it."""
        mock_config_entry.add_to_hass(hass)

        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]
        assert coordinator is not None
        assert coordinator.data is not None

    async def test_setup_entry_creates_entities(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_dmi_api: MagicMock,
    ) -> None:
        """Test setup creates weather and sensor entities."""
        mock_config_entry.add_to_hass(hass)

        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        # Check weather entity exists
        weather_entity = hass.states.get("weather.kobenhavns_lufthavn")
        assert weather_entity is not None

        last_fetch_entity = hass.states.get("sensor.kobenhavns_lufthavn_last_successful_update")
        assert last_fetch_entity is not None

    async def test_setup_entry_api_called(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_dmi_api: MagicMock,
    ) -> None:
        """Test setup fetches data from API."""
        mock_config_entry.add_to_hass(hass)

        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        # Verify API was called
        mock_dmi_api.get_observations.assert_called()
        mock_dmi_api.get_forecast.assert_called()

    async def test_sea_setup_entry_loads_during_rate_limit(
        self,
        hass: HomeAssistant,
        mock_dmi_api: MagicMock,
    ) -> None:
        """Test a sea entry loads even when its initial request is throttled."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Korsør",
            data={
                CONF_SETUP_TYPE: SETUP_TYPE_SEA,
                CONF_STATION_ID: "30017",
                CONF_STATION_NAME: "Korsør",
            },
            unique_id="dmi_sea_30017",
        )
        entry.add_to_hass(hass)
        mock_dmi_api.get_sea_observations = AsyncMock(side_effect=RateLimitExceeded("Rate limit"))

        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.state is ConfigEntryState.LOADED
        coordinator = hass.data[DOMAIN][entry.entry_id]
        assert coordinator.data["observations"] == {}
        assert coordinator.data["last_updated"] is None

    async def test_weather_setup_entry_loads_during_rate_limit(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_dmi_api: MagicMock,
    ) -> None:
        """Test a weather entry loads when its initial request is throttled."""
        mock_config_entry.add_to_hass(hass)
        mock_dmi_api.get_observations = AsyncMock(side_effect=RateLimitExceeded("Rate limit"))

        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert mock_config_entry.state is ConfigEntryState.LOADED
        coordinator = hass.data[DOMAIN][mock_config_entry.entry_id]
        assert coordinator.data["observations"] == {}
        assert coordinator.data["last_updated"] is None


class TestIntegrationUnload:
    """Test cases for integration unload."""

    async def test_unload_entry_success(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_dmi_api: MagicMock,
    ) -> None:
        """Test successful unload of config entry."""
        mock_config_entry.add_to_hass(hass)

        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert mock_config_entry.state is ConfigEntryState.LOADED

        # Now unload
        await hass.config_entries.async_unload(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert mock_config_entry.state is ConfigEntryState.NOT_LOADED
        assert mock_config_entry.entry_id not in hass.data[DOMAIN]

    async def test_unload_removes_coordinator(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_dmi_api: MagicMock,
    ) -> None:
        """Test unload removes coordinator from hass.data."""
        mock_config_entry.add_to_hass(hass)

        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert mock_config_entry.entry_id in hass.data[DOMAIN]

        await hass.config_entries.async_unload(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert mock_config_entry.entry_id not in hass.data[DOMAIN]


class TestIntegrationReload:
    """Test cases for integration reload on options change."""

    async def test_reload_on_options_update(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_dmi_api: MagicMock,
    ) -> None:
        """Test integration reloads when options change."""
        mock_config_entry.add_to_hass(hass)

        await hass.config_entries.async_setup(mock_config_entry.entry_id)
        await hass.async_block_till_done()

        assert mock_config_entry.state is ConfigEntryState.LOADED

        # Update options (this should trigger reload)
        hass.config_entries.async_update_entry(
            mock_config_entry,
            options={"update_interval": 30, "include_forecast": False},
        )
        await hass.async_block_till_done()

        # Entry should still be loaded after reload
        assert mock_config_entry.state is ConfigEntryState.LOADED
