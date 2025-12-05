"""Tests for the DMI integration setup and teardown."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dmi import PLATFORMS
from custom_components.dmi.const import DOMAIN


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
