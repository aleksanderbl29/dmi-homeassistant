"""Tests for the DMI config flow."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dmi.api import CannotConnect
from custom_components.dmi.const import (
    CONF_INCLUDE_FORECAST,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    CONF_UPDATE_INTERVAL,
    CONF_USE_COORDINATES,
    DOMAIN,
)


@pytest.fixture
def mock_stations() -> list[dict[str, Any]]:
    """Return mock station list matching actual API response format."""
    return [
        {
            "stationId": "06180",
            "name": "Københavns Lufthavn",
            "latitude": 55.614,
            "longitude": 12.6455,
            "type": "Synop",
            "parameterId": ["temp_dry", "humidity", "wind_speed", "pressure_at_sea"],
        },
        {
            "stationId": "06070",
            "name": "Aarhus Lufthavn",
            "latitude": 56.3031,
            "longitude": 10.6195,
            "type": "Synop",
            "parameterId": ["temp_dry", "humidity"],
        },
    ]


class TestDMIConfigFlow:
    """Test cases for DMIConfigFlow."""

    async def test_user_flow_shows_station_form(
        self,
        hass: HomeAssistant,
        mock_stations: list[dict[str, Any]],
    ) -> None:
        """Test user step shows station selection form."""
        with patch(
            "custom_components.dmi.config_flow.DMIApiClient"
        ) as mock_api_class:
            mock_api = MagicMock()
            mock_api.get_stations = AsyncMock(return_value=mock_stations)
            mock_api_class.return_value = mock_api

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )

            assert result["type"] == FlowResultType.FORM
            assert result["step_id"] == "station"
            assert "data_schema" in result

    async def test_user_flow_creates_entry(
        self,
        hass: HomeAssistant,
        mock_stations: list[dict[str, Any]],
    ) -> None:
        """Test successful config entry creation."""
        with patch(
            "custom_components.dmi.config_flow.DMIApiClient"
        ) as mock_api_class:
            mock_api = MagicMock()
            mock_api.get_stations = AsyncMock(return_value=mock_stations)
            mock_api_class.return_value = mock_api

            # First step: show form
            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )

            assert result["type"] == FlowResultType.FORM

            # Second step: submit station selection
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    CONF_STATION_ID: "06180",
                    CONF_USE_COORDINATES: False,
                },
            )

            assert result["type"] == FlowResultType.CREATE_ENTRY
            assert result["title"] == "Københavns Lufthavn"
            assert result["data"][CONF_STATION_ID] == "06180"
            assert result["data"][CONF_STATION_NAME] == "Københavns Lufthavn"
            assert result["data"]["latitude"] == 55.614
            assert result["data"]["longitude"] == 12.6455

    async def test_user_flow_with_ha_coordinates(
        self,
        hass: HomeAssistant,
        mock_stations: list[dict[str, Any]],
    ) -> None:
        """Test config entry uses HA coordinates when selected."""
        # Set Home Assistant coordinates
        hass.config.latitude = 56.0
        hass.config.longitude = 11.0

        with patch(
            "custom_components.dmi.config_flow.DMIApiClient"
        ) as mock_api_class:
            mock_api = MagicMock()
            mock_api.get_stations = AsyncMock(return_value=mock_stations)
            mock_api_class.return_value = mock_api

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )

            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    CONF_STATION_ID: "06180",
                    CONF_USE_COORDINATES: True,
                },
            )

            assert result["type"] == FlowResultType.CREATE_ENTRY
            assert result["data"]["latitude"] == 56.0
            assert result["data"]["longitude"] == 11.0

    async def test_user_flow_connection_error(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test connection error shows form with error."""
        with patch(
            "custom_components.dmi.config_flow.DMIApiClient"
        ) as mock_api_class:
            mock_api = MagicMock()
            mock_api.get_stations = AsyncMock(side_effect=CannotConnect("Failed"))
            mock_api_class.return_value = mock_api

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )

            assert result["type"] == FlowResultType.FORM
            assert result["errors"]["base"] == "cannot_connect"

    async def test_user_flow_unknown_error(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test unknown error shows form with error."""
        with patch(
            "custom_components.dmi.config_flow.DMIApiClient"
        ) as mock_api_class:
            mock_api = MagicMock()
            mock_api.get_stations = AsyncMock(side_effect=Exception("Unknown"))
            mock_api_class.return_value = mock_api

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )

            assert result["type"] == FlowResultType.FORM
            assert result["errors"]["base"] == "unknown"

    async def test_user_flow_no_stations(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test empty station list shows error."""
        with patch(
            "custom_components.dmi.config_flow.DMIApiClient"
        ) as mock_api_class:
            mock_api = MagicMock()
            mock_api.get_stations = AsyncMock(return_value=[])
            mock_api_class.return_value = mock_api

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )

            assert result["type"] == FlowResultType.FORM
            assert result["errors"]["base"] == "cannot_connect"

    async def test_user_flow_duplicate_entry(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_stations: list[dict[str, Any]],
    ) -> None:
        """Test duplicate entry is prevented."""
        # Add existing entry
        mock_config_entry.add_to_hass(hass)

        with patch(
            "custom_components.dmi.config_flow.DMIApiClient"
        ) as mock_api_class:
            mock_api = MagicMock()
            mock_api.get_stations = AsyncMock(return_value=mock_stations)
            mock_api_class.return_value = mock_api

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )

            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    CONF_STATION_ID: "06180",
                    CONF_USE_COORDINATES: False,
                },
            )

            assert result["type"] == FlowResultType.ABORT
            assert result["reason"] == "already_configured"

    async def test_user_flow_filters_invalid_stations(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test stations without stationId are filtered from options."""
        stations_with_invalid = [
            {
                "stationId": None,  # Invalid
                "name": "Invalid",
            },
            {
                "stationId": "06180",
                "name": "København",
                "latitude": 55.6761,
                "longitude": 12.5683,
            },
        ]

        with patch(
            "custom_components.dmi.config_flow.DMIApiClient"
        ) as mock_api_class:
            mock_api = MagicMock()
            mock_api.get_stations = AsyncMock(return_value=stations_with_invalid)
            mock_api_class.return_value = mock_api

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )

            assert result["type"] == FlowResultType.FORM
            # Form should be shown with valid stations only


class TestDMIOptionsFlow:
    """Test cases for DMI options flow."""

    async def test_options_flow_shows_form(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test options flow shows form with current values."""
        mock_config_entry.add_to_hass(hass)

        result = await hass.config_entries.options.async_init(
            mock_config_entry.entry_id
        )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "init"

    async def test_options_flow_updates_options(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test submitting options updates the entry."""
        mock_config_entry.add_to_hass(hass)

        result = await hass.config_entries.options.async_init(
            mock_config_entry.entry_id
        )

        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_UPDATE_INTERVAL: 20,
                CONF_INCLUDE_FORECAST: False,
            },
        )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_UPDATE_INTERVAL] == 20
        assert result["data"][CONF_INCLUDE_FORECAST] is False

    async def test_options_flow_default_values(
        self,
        hass: HomeAssistant,
        mock_config_entry_data: dict[str, Any],
    ) -> None:
        """Test options flow uses defaults when no options set."""
        entry = MockConfigEntry(
            domain=DOMAIN,
            title="Test Station",
            data=mock_config_entry_data,
            options={},  # No options set
            unique_id="dmi_test",
        )
        entry.add_to_hass(hass)

        result = await hass.config_entries.options.async_init(entry.entry_id)

        assert result["type"] == FlowResultType.FORM
        # Form should use defaults from const.py
