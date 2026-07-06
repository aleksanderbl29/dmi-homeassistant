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
    CONF_BACKUP_PARAMETERS,
    CONF_BACKUP_STATION_NAME_SUFFIX,
    CONF_BACKUP_STATIONS,
    CONF_INCLUDE_FORECAST,
    CONF_SETUP_TYPE,
    CONF_STATION_ID,
    CONF_UPDATE_INTERVAL,
    CONF_USE_COORDINATES,
    DOMAIN,
)


@pytest.fixture
def mock_stations() -> list[dict[str, Any]]:
    """Return mock station list matching the parsed API response."""
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


def _flow_menu_select(result: dict[str, Any], next_step_id: str) -> dict[str, str]:
    """Return a menu selection payload."""
    assert result["type"] == FlowResultType.MENU
    return {"next_step_id": next_step_id}


def _select_all_backup_parameters(result: dict[str, Any]) -> dict[str, list[str]]:
    """Select every available backup parameter in the current form."""
    options = _selector_options(result, CONF_BACKUP_PARAMETERS)
    return {CONF_BACKUP_PARAMETERS: [option["value"] for option in options]}


def _selector_options(result: dict[str, Any], field_name: str) -> list[dict[str, str]]:
    """Return selector options for a schema field."""
    parameter_field = next(
        field for field in result["data_schema"].schema if field.schema == field_name
    )
    selector = result["data_schema"].schema[parameter_field]
    return list(selector.config["options"])


def _field_default(result: dict[str, Any], field_name: str) -> Any:
    """Return a schema field default."""
    field = next(field for field in result["data_schema"].schema if field.schema == field_name)
    return field.default()


def _select_backup_parameters(parameter_ids: list[str]) -> dict[str, list[str]]:
    """Return a backup parameter selection payload."""
    return {CONF_BACKUP_PARAMETERS: parameter_ids}


class TestDMIConfigFlow:
    """Test cases for DMIConfigFlow."""

    async def test_user_flow_shows_setup_menu(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test user step shows a menu with normal and advanced setup."""
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )

        assert result["type"] == FlowResultType.MENU
        assert set(result["menu_options"]) == {"station", "advanced_primary"}

    async def test_normal_flow_creates_entry(
        self,
        hass: HomeAssistant,
        mock_stations: list[dict[str, Any]],
    ) -> None:
        """Test the normal setup path still creates a config entry."""
        with patch("custom_components.dmi.config_flow.DMIApiClient") as mock_api_class:
            mock_api = MagicMock()
            mock_api.get_stations = AsyncMock(return_value=mock_stations)
            mock_api_class.return_value = mock_api

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], _flow_menu_select(result, "station")
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    CONF_STATION_ID: "06180",
                    CONF_USE_COORDINATES: False,
                },
            )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["title"] == "Københavns Lufthavn"
        assert result["data"][CONF_SETUP_TYPE] == "normal"
        assert result["data"][CONF_STATION_ID] == "06180"

    async def test_advanced_flow_creates_composite_entry(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test the advanced flow creates a composite entry."""
        advanced_stations = [
            {
                "stationId": "06186",
                "name": "Landbohojskolen",
                "latitude": 55.68,
                "longitude": 12.53,
                "parameterId": ["temp_dry", "humidity"],
            },
            {
                "stationId": "06187",
                "name": "Kobenhavns Toldbod",
                "latitude": 55.69,
                "longitude": 12.60,
                "parameterId": ["radia_glob", "sun_last1h_glob", "temp_dry"],
            },
        ]
        with patch("custom_components.dmi.config_flow.DMIApiClient") as mock_api_class:
            mock_api = MagicMock()
            mock_api.get_stations = AsyncMock(return_value=advanced_stations)
            mock_api_class.return_value = mock_api

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], _flow_menu_select(result, "advanced_primary")
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    CONF_STATION_ID: "06186",
                    CONF_USE_COORDINATES: False,
                },
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {"backup_station_count": "1"},
            )
            backup_options = _selector_options(result, CONF_STATION_ID)
            assert {option["value"] for option in backup_options} == {"06187"}
            suffix_field = next(
                field
                for field in result["data_schema"].schema
                if field.schema == CONF_BACKUP_STATION_NAME_SUFFIX
            )
            assert suffix_field.default() is True

            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {
                    CONF_STATION_ID: "06187",
                    CONF_BACKUP_STATION_NAME_SUFFIX: True,
                },
            )
            assert _field_default(result, CONF_BACKUP_PARAMETERS) == [
                "radia_glob",
                "sun_last1h_glob",
            ]
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {},
            )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_SETUP_TYPE] == "advanced"
        assert result["data"][CONF_STATION_ID] == "06186"
        assert result["data"][CONF_BACKUP_STATIONS][0][CONF_STATION_ID] == "06187"
        assert result["data"][CONF_BACKUP_STATIONS][0][CONF_BACKUP_PARAMETERS] == [
            "radia_glob",
            "sun_last1h_glob",
        ]
        assert result["data"][CONF_BACKUP_STATIONS][0][CONF_BACKUP_STATION_NAME_SUFFIX] is True

    async def test_advanced_flow_stores_selected_backup_parameter_subset(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test advanced flow stores exactly the backup parameters the user selects."""
        stations = [
            {
                "stationId": "06186",
                "name": "Landbohojskolen",
                "latitude": 55.68,
                "longitude": 12.53,
                "parameterId": ["temp_dry"],
            },
            {
                "stationId": "06187",
                "name": "Kobenhavns Toldbod",
                "latitude": 55.69,
                "longitude": 12.60,
                "parameterId": ["radia_glob", "sun_last1h_glob", "temp_dry"],
            },
        ]
        with patch("custom_components.dmi.config_flow.DMIApiClient") as mock_api_class:
            mock_api = MagicMock()
            mock_api.get_stations = AsyncMock(return_value=stations)
            mock_api_class.return_value = mock_api

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], _flow_menu_select(result, "advanced_primary")
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_STATION_ID: "06186", CONF_USE_COORDINATES: False},
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {"backup_station_count": "1"}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_STATION_ID: "06187", CONF_BACKUP_STATION_NAME_SUFFIX: False},
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                _select_backup_parameters(["radia_glob"]),
            )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        assert result["data"][CONF_BACKUP_STATIONS][0][CONF_BACKUP_PARAMETERS] == ["radia_glob"]

    async def test_advanced_flow_filters_backup_station_options_to_new_parameters(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test backup station options only include stations with new parameters."""
        stations = [
            {
                "stationId": "06186",
                "name": "Landbohojskolen",
                "latitude": 55.68,
                "longitude": 12.53,
                "parameterId": ["temp_dry", "humidity"],
            },
            {
                "stationId": "06070",
                "name": "Duplicate Parameters",
                "latitude": 56.30,
                "longitude": 10.61,
                "parameterId": ["temp_dry"],
            },
            {
                "stationId": "06187",
                "name": "Solar Backup",
                "latitude": 55.69,
                "longitude": 12.60,
                "parameterId": ["radia_glob"],
            },
            {
                "stationId": "06188",
                "name": "Sun Backup",
                "latitude": 55.70,
                "longitude": 12.61,
                "parameterId": ["sun_last1h_glob", "temp_dry"],
            },
        ]
        with patch("custom_components.dmi.config_flow.DMIApiClient") as mock_api_class:
            mock_api = MagicMock()
            mock_api.get_stations = AsyncMock(return_value=stations)
            mock_api_class.return_value = mock_api

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], _flow_menu_select(result, "advanced_primary")
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_STATION_ID: "06186", CONF_USE_COORDINATES: False},
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {"backup_station_count": "1"}
            )

        backup_options = _selector_options(result, CONF_STATION_ID)
        assert {option["value"] for option in backup_options} == {"06187", "06188"}

    async def test_advanced_backup_count_is_capped_by_useful_station_count(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test backup count only offers useful backup station counts."""
        stations = [
            {
                "stationId": "06186",
                "name": "Landbohojskolen",
                "latitude": 55.68,
                "longitude": 12.53,
                "parameterId": ["temp_dry"],
            },
            {
                "stationId": "06187",
                "name": "Kobenhavns Toldbod",
                "latitude": 55.69,
                "longitude": 12.60,
                "parameterId": ["radia_glob"],
            },
            {
                "stationId": "06070",
                "name": "Aarhus Lufthavn",
                "latitude": 56.30,
                "longitude": 10.61,
                "parameterId": ["temp_dry"],
            },
        ]
        with patch("custom_components.dmi.config_flow.DMIApiClient") as mock_api_class:
            mock_api = MagicMock()
            mock_api.get_stations = AsyncMock(return_value=stations)
            mock_api_class.return_value = mock_api

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], _flow_menu_select(result, "advanced_primary")
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_STATION_ID: "06186", CONF_USE_COORDINATES: False},
            )

        count_options = _selector_options(result, "backup_station_count")
        assert [option["value"] for option in count_options] == ["1"]

    async def test_advanced_flow_rejects_empty_backup_parameter_selection(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test advanced flow rejects an empty backup parameter selection."""
        stations = [
            {
                "stationId": "06186",
                "name": "Landbohojskolen",
                "latitude": 55.68,
                "longitude": 12.53,
                "parameterId": ["temp_dry"],
            },
            {
                "stationId": "06187",
                "name": "Kobenhavns Toldbod",
                "latitude": 55.69,
                "longitude": 12.60,
                "parameterId": ["radia_glob", "sun_last1h_glob"],
            },
        ]
        with patch("custom_components.dmi.config_flow.DMIApiClient") as mock_api_class:
            mock_api = MagicMock()
            mock_api.get_stations = AsyncMock(return_value=stations)
            mock_api_class.return_value = mock_api

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], _flow_menu_select(result, "advanced_primary")
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_STATION_ID: "06186", CONF_USE_COORDINATES: False},
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {"backup_station_count": "1"}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_STATION_ID: "06187", CONF_BACKUP_STATION_NAME_SUFFIX: False},
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_BACKUP_PARAMETERS: []},
            )

        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"] == "no_backup_parameters"

    async def test_advanced_flow_rejects_duplicate_or_primary_backup_station(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test backup station validation."""
        stations = [
            {
                "stationId": "06186",
                "name": "Landbohojskolen",
                "latitude": 55.68,
                "longitude": 12.53,
                "parameterId": ["temp_dry", "humidity"],
            },
            {
                "stationId": "06187",
                "name": "Kobenhavns Toldbod",
                "latitude": 55.69,
                "longitude": 12.60,
                "parameterId": ["radia_glob", "sun_last1h_glob"],
            },
            {
                "stationId": "06070",
                "name": "Aarhus Lufthavn",
                "latitude": 56.30,
                "longitude": 10.61,
                "parameterId": ["pressure_at_sea"],
            },
        ]
        with patch("custom_components.dmi.config_flow.DMIApiClient") as mock_api_class:
            mock_api = MagicMock()
            mock_api.get_stations = AsyncMock(return_value=stations)
            mock_api_class.return_value = mock_api

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], _flow_menu_select(result, "advanced_primary")
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_STATION_ID: "06186", CONF_USE_COORDINATES: False},
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {"backup_station_count": "2"}
            )
            backup_options = _selector_options(result, CONF_STATION_ID)
            assert {option["value"] for option in backup_options} == {"06070", "06187"}

            flow = hass.config_entries.flow._progress[result["flow_id"]]
            result = await flow.async_step_advanced_backup_station(
                {CONF_STATION_ID: "06186", CONF_BACKUP_STATION_NAME_SUFFIX: False}
            )
            assert result["errors"]["base"] == "backup_matches_primary"

            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_STATION_ID: "06187", CONF_BACKUP_STATION_NAME_SUFFIX: False},
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                _select_all_backup_parameters(result),
            )
            result = await flow.async_step_advanced_backup_station(
                {CONF_STATION_ID: "06187", CONF_BACKUP_STATION_NAME_SUFFIX: False}
            )

        assert result["errors"]["base"] == "duplicate_backup_station"

    async def test_advanced_flow_rejects_backup_without_missing_parameters(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test flow stops early when no backup stations add new parameters."""
        stations = [
            {
                "stationId": "06186",
                "name": "Landbohojskolen",
                "latitude": 55.68,
                "longitude": 12.53,
                "parameterId": ["temp_dry"],
            },
            {
                "stationId": "06187",
                "name": "Kobenhavns Toldbod",
                "latitude": 55.69,
                "longitude": 12.60,
                "parameterId": ["temp_dry"],
            },
        ]
        with patch("custom_components.dmi.config_flow.DMIApiClient") as mock_api_class:
            mock_api = MagicMock()
            mock_api.get_stations = AsyncMock(return_value=stations)
            mock_api_class.return_value = mock_api

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], _flow_menu_select(result, "advanced_primary")
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_STATION_ID: "06186", CONF_USE_COORDINATES: False},
            )

        assert result["errors"]["base"] == "no_backup_parameters"

    async def test_advanced_flow_excludes_parameters_claimed_by_previous_backups(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test later backup stations only own still-unclaimed parameters."""
        stations = [
            {
                "stationId": "06186",
                "name": "Landbohojskolen",
                "latitude": 55.68,
                "longitude": 12.53,
                "parameterId": ["temp_dry"],
            },
            {
                "stationId": "06187",
                "name": "Kobenhavns Toldbod",
                "latitude": 55.69,
                "longitude": 12.60,
                "parameterId": ["radia_glob", "sun_last1h_glob"],
            },
            {
                "stationId": "06070",
                "name": "Aarhus Lufthavn",
                "latitude": 56.30,
                "longitude": 10.61,
                "parameterId": ["radia_glob", "pressure_at_sea"],
            },
        ]
        with patch("custom_components.dmi.config_flow.DMIApiClient") as mock_api_class:
            mock_api = MagicMock()
            mock_api.get_stations = AsyncMock(return_value=stations)
            mock_api_class.return_value = mock_api

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], _flow_menu_select(result, "advanced_primary")
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_STATION_ID: "06186", CONF_USE_COORDINATES: False},
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {"backup_station_count": "2"}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_STATION_ID: "06187", CONF_BACKUP_STATION_NAME_SUFFIX: False},
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                _select_all_backup_parameters(result),
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_STATION_ID: "06070", CONF_BACKUP_STATION_NAME_SUFFIX: False},
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                _select_all_backup_parameters(result),
            )

        assert result["type"] == FlowResultType.CREATE_ENTRY
        backups = result["data"][CONF_BACKUP_STATIONS]
        assert backups[0][CONF_BACKUP_PARAMETERS] == ["radia_glob", "sun_last1h_glob"]
        assert backups[1][CONF_BACKUP_PARAMETERS] == ["pressure_at_sea"]

    async def test_advanced_flow_rejects_backup_with_only_claimed_parameters(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test later backup step stops when earlier backups claim all parameters."""
        stations = [
            {
                "stationId": "06186",
                "name": "Landbohojskolen",
                "latitude": 55.68,
                "longitude": 12.53,
                "parameterId": ["temp_dry"],
            },
            {
                "stationId": "06187",
                "name": "Kobenhavns Toldbod",
                "latitude": 55.69,
                "longitude": 12.60,
                "parameterId": ["radia_glob"],
            },
            {
                "stationId": "06070",
                "name": "Aarhus Lufthavn",
                "latitude": 56.30,
                "longitude": 10.61,
                "parameterId": ["radia_glob", "temp_dry"],
            },
        ]
        with patch("custom_components.dmi.config_flow.DMIApiClient") as mock_api_class:
            mock_api = MagicMock()
            mock_api.get_stations = AsyncMock(return_value=stations)
            mock_api_class.return_value = mock_api

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], _flow_menu_select(result, "advanced_primary")
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_STATION_ID: "06186", CONF_USE_COORDINATES: False},
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], {"backup_station_count": "2"}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_STATION_ID: "06187", CONF_BACKUP_STATION_NAME_SUFFIX: False},
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                _select_all_backup_parameters(result),
            )

        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "advanced_backup_station"
        assert result["errors"]["base"] == "no_backup_parameters"

    async def test_normal_flow_duplicate_entry(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
        mock_stations: list[dict[str, Any]],
    ) -> None:
        """Test duplicate normal entry is prevented."""
        mock_config_entry.add_to_hass(hass)

        with patch("custom_components.dmi.config_flow.DMIApiClient") as mock_api_class:
            mock_api = MagicMock()
            mock_api.get_stations = AsyncMock(return_value=mock_stations)
            mock_api_class.return_value = mock_api

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], _flow_menu_select(result, "station")
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"],
                {CONF_STATION_ID: "06180", CONF_USE_COORDINATES: False},
            )

        assert result["type"] == FlowResultType.ABORT
        assert result["reason"] == "already_configured"

    async def test_flow_connection_error(
        self,
        hass: HomeAssistant,
    ) -> None:
        """Test connection error shows form with error."""
        with patch("custom_components.dmi.config_flow.DMIApiClient") as mock_api_class:
            mock_api = MagicMock()
            mock_api.get_stations = AsyncMock(side_effect=CannotConnect("Failed"))
            mock_api_class.return_value = mock_api

            result = await hass.config_entries.flow.async_init(
                DOMAIN, context={"source": config_entries.SOURCE_USER}
            )
            result = await hass.config_entries.flow.async_configure(
                result["flow_id"], _flow_menu_select(result, "station")
            )

        assert result["type"] == FlowResultType.FORM
        assert result["errors"]["base"] == "cannot_connect"


class TestDMIOptionsFlow:
    """Test cases for DMI options flow."""

    async def test_options_flow_updates_options(
        self,
        hass: HomeAssistant,
        mock_config_entry: MockConfigEntry,
    ) -> None:
        """Test submitting options updates the entry."""
        mock_config_entry.add_to_hass(hass)

        result = await hass.config_entries.options.async_init(mock_config_entry.entry_id)
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
