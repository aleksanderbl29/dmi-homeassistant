"""Config flow for DMI Weather integration."""

from __future__ import annotations

import hashlib
import json
import logging
import math
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .api import CannotConnect, DMIApiClient
from .const import (
    CONF_BACKUP_PARAMETERS,
    CONF_BACKUP_STATION_NAME_SUFFIX,
    CONF_BACKUP_STATIONS,
    CONF_INCLUDE_FORECAST,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_LOW_ASTRONOMICAL_TIDE,
    CONF_MEAN_LOW_WATER_SPRING,
    CONF_SETUP_TYPE,
    CONF_STATION_ID,
    CONF_STATION_NAME,
    CONF_TIDEWATER_LATITUDE,
    CONF_TIDEWATER_LONGITUDE,
    CONF_TIDEWATER_STATION_ID,
    CONF_TIDEWATER_STATION_NAME,
    CONF_UPDATE_INTERVAL,
    CONF_USE_COORDINATES,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    SEA_SENSOR_TYPES_BY_KEY,
    SENSOR_TYPES_BY_KEY,
    SETUP_TYPE_ADVANCED,
    SETUP_TYPE_NORMAL,
    SETUP_TYPE_SEA,
)

_LOGGER = logging.getLogger(__name__)


class DMIConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for DMI Weather."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._stations: list[dict[str, Any]] = []
        self._sea_stations: list[dict[str, Any]] = []
        self._tidewater_stations: list[dict[str, Any]] = []
        self._sea_primary: dict[str, Any] | None = None
        self._advanced_primary: dict[str, Any] | None = None
        self._advanced_backup_count = 1
        self._advanced_backups: list[dict[str, Any]] = []
        self._advanced_current_backup_index = 0
        self._advanced_pending_backup: dict[str, Any] | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the initial step."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["station", "advanced_primary", "sea"],
        )

    async def async_step_sea(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle tide-gauge station selection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            station = self._get_station_by_id(
                str(user_input.get(CONF_STATION_ID, "")),
                stations=self._sea_stations,
            )
            if station is None:
                errors["base"] = "invalid_station"
            else:
                station_id = str(station.get("stationId") or "")
                station_name = str(station.get("name") or "DMI Sea Level")
                self._sea_primary = {
                    CONF_SETUP_TYPE: SETUP_TYPE_SEA,
                    CONF_STATION_ID: station_id,
                    CONF_STATION_NAME: station_name,
                    CONF_LATITUDE: station.get("latitude"),
                    CONF_LONGITUDE: station.get("longitude"),
                    CONF_USE_COORDINATES: False,
                }
                return await self.async_step_tidewater_station()

        if not await self._async_load_sea_stations():
            return self.async_show_form(
                step_id="sea",
                data_schema=vol.Schema({}),
                errors={"base": "cannot_connect"},
            )

        return self.async_show_form(
            step_id="sea",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STATION_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=self._build_station_options(self._sea_stations),
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_tidewater_station(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose the separate DMI station used for astronomical predictions."""
        if self._sea_primary is None:
            return await self.async_step_sea()

        errors: dict[str, str] = {}
        if not await self._async_load_tidewater_stations():
            return self.async_show_form(
                step_id="tidewater_station",
                data_schema=vol.Schema({}),
                errors={"base": "cannot_connect"},
            )

        if user_input is not None:
            prediction_station = self._get_station_by_id(
                str(user_input.get(CONF_TIDEWATER_STATION_ID, "")),
                stations=self._tidewater_stations,
            )
            if prediction_station is None:
                errors["base"] = "invalid_station"
            else:
                station_id = str(self._sea_primary[CONF_STATION_ID])
                station_name = str(self._sea_primary[CONF_STATION_NAME])
                data = {
                    **self._sea_primary,
                    CONF_TIDEWATER_STATION_ID: str(prediction_station["stationId"]),
                    CONF_TIDEWATER_STATION_NAME: str(
                        prediction_station.get("name") or prediction_station["stationId"]
                    ),
                    CONF_TIDEWATER_LATITUDE: prediction_station.get("latitude"),
                    CONF_TIDEWATER_LONGITUDE: prediction_station.get("longitude"),
                    CONF_LOW_ASTRONOMICAL_TIDE: prediction_station.get("lowAstronomicalTide"),
                    CONF_MEAN_LOW_WATER_SPRING: prediction_station.get("meanLowWaterSpring"),
                }
                await self.async_set_unique_id(f"dmi_sea_{station_id}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=station_name, data=data)

        nearest_station_id = self._nearest_tidewater_station_id()
        return self.async_show_form(
            step_id="tidewater_station",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_TIDEWATER_STATION_ID,
                        default=nearest_station_id,
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=self._build_tidewater_station_options(),
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_station(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle normal station selection step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            station = self._get_station_by_id(str(user_input.get(CONF_STATION_ID, "")))
            if station is None:
                errors["base"] = "invalid_station"
            else:
                data = self._build_primary_entry_data(station, user_input, SETUP_TYPE_NORMAL)
                await self.async_set_unique_id(f"dmi_{data[CONF_STATION_ID]}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=data[CONF_STATION_NAME], data=data)

        if not await self._async_load_stations():
            return self.async_show_form(
                step_id="station",
                data_schema=vol.Schema({}),
                errors={"base": "cannot_connect"},
            )

        return self.async_show_form(
            step_id="station",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STATION_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=self._build_station_options(),
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                    vol.Optional(CONF_USE_COORDINATES, default=False): BooleanSelector(),
                }
            ),
            errors=errors,
        )

    async def async_step_advanced_primary(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select the primary station for the advanced flow."""
        errors: dict[str, str] = {}

        if user_input is not None:
            station = self._get_station_by_id(str(user_input.get(CONF_STATION_ID, "")))
            if station is None:
                errors["base"] = "invalid_station"
            else:
                self._advanced_primary = self._build_primary_entry_data(
                    station,
                    user_input,
                    SETUP_TYPE_ADVANCED,
                )
                self._advanced_backups = []
                self._advanced_backup_count = 1
                self._advanced_current_backup_index = 0
                return await self.async_step_advanced_backup_count()

        if not await self._async_load_stations():
            return self.async_show_form(
                step_id="advanced_primary",
                data_schema=vol.Schema({}),
                errors={"base": "cannot_connect"},
            )

        return self.async_show_form(
            step_id="advanced_primary",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STATION_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=self._build_station_options(),
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                    vol.Optional(CONF_USE_COORDINATES, default=False): BooleanSelector(),
                }
            ),
            errors=errors,
        )

    async def async_step_advanced_backup_count(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose how many backup stations to configure."""
        available_backup_count = len(self._get_available_backup_stations())

        if user_input is not None:
            self._advanced_backup_count = int(user_input["backup_station_count"])
            self._advanced_backups = []
            self._advanced_current_backup_index = 0
            return await self.async_step_advanced_backup_station()

        if available_backup_count == 0:
            return self.async_show_form(
                step_id="advanced_backup_count",
                data_schema=vol.Schema({}),
                errors={"base": "no_backup_parameters"},
            )

        count_options = [
            {"value": str(count), "label": str(count)}
            for count in range(1, min(3, available_backup_count) + 1)
        ]

        return self.async_show_form(
            step_id="advanced_backup_count",
            data_schema=vol.Schema(
                {
                    vol.Required("backup_station_count", default="1"): SelectSelector(
                        SelectSelectorConfig(
                            options=count_options,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_advanced_backup_station(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose a backup station."""
        errors: dict[str, str] = {}

        if user_input is not None:
            station_id = str(user_input.get(CONF_STATION_ID, ""))
            station = self._get_station_by_id(station_id)
            primary_station_id = str(self._advanced_primary[CONF_STATION_ID])
            selected_backup_ids = {
                str(backup[CONF_STATION_ID]) for backup in self._advanced_backups
            }

            if station is None:
                errors["base"] = "invalid_station"
            elif station_id == primary_station_id:
                errors["base"] = "backup_matches_primary"
            elif station_id in selected_backup_ids:
                errors["base"] = "duplicate_backup_station"
            else:
                backup_parameters = self._get_backup_parameter_ids(station)
                if not backup_parameters:
                    errors["base"] = "no_backup_parameters"
                else:
                    self._advanced_pending_backup = {
                        CONF_STATION_ID: station_id,
                        CONF_STATION_NAME: station.get(CONF_STATION_NAME) or station.get("name"),
                        CONF_LATITUDE: station.get(CONF_LATITUDE) or station.get("latitude"),
                        CONF_LONGITUDE: station.get(CONF_LONGITUDE) or station.get("longitude"),
                        CONF_BACKUP_STATION_NAME_SUFFIX: bool(
                            user_input.get(CONF_BACKUP_STATION_NAME_SUFFIX, False)
                        ),
                    }
                    return await self.async_step_advanced_backup_parameters()

        backup_station_options = self._build_backup_station_options()
        if not backup_station_options:
            if self._advanced_backups:
                return await self.async_step_advanced_no_more_backups()
            return self.async_show_form(
                step_id="advanced_backup_station",
                data_schema=vol.Schema({}),
                errors={"base": "no_backup_parameters"},
                description_placeholders={
                    "backup_index": str(self._advanced_current_backup_index + 1)
                },
            )

        return self.async_show_form(
            step_id="advanced_backup_station",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_STATION_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=backup_station_options,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                    vol.Optional(
                        CONF_BACKUP_STATION_NAME_SUFFIX,
                        default=True,
                    ): BooleanSelector(),
                }
            ),
            errors=errors,
            description_placeholders={"backup_index": str(self._advanced_current_backup_index + 1)},
        )

    async def async_step_advanced_backup_parameters(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Choose which backup parameters to import from the pending backup station."""
        errors: dict[str, str] = {}

        if self._advanced_pending_backup is None:
            return await self.async_step_advanced_backup_station()

        pending_station = self._get_station_by_id(
            str(self._advanced_pending_backup[CONF_STATION_ID])
        )
        if pending_station is None:
            self._advanced_pending_backup = None
            return await self.async_step_advanced_backup_station()

        available_parameters = self._get_backup_parameter_ids(pending_station)

        if user_input is not None:
            selected_parameter_set = {
                str(parameter_id)
                for parameter_id in user_input.get(CONF_BACKUP_PARAMETERS, [])
                if parameter_id
            }
            selected_parameters = [
                parameter_id
                for parameter_id in available_parameters
                if parameter_id in selected_parameter_set
            ]
            if not selected_parameters:
                errors["base"] = "no_backup_parameters"
            else:
                self._advanced_backups.append(
                    {
                        **self._advanced_pending_backup,
                        CONF_BACKUP_PARAMETERS: selected_parameters,
                    }
                )
                self._advanced_pending_backup = None
                self._advanced_current_backup_index += 1
                if self._advanced_current_backup_index >= self._advanced_backup_count:
                    return await self._async_create_advanced_entry()
                if not self._get_available_backup_stations():
                    return await self.async_step_advanced_no_more_backups()
                return await self.async_step_advanced_backup_station()

        return self.async_show_form(
            step_id="advanced_backup_parameters",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_BACKUP_PARAMETERS,
                        default=available_parameters,
                    ): SelectSelector(
                        SelectSelectorConfig(
                            options=self._build_backup_parameter_options(available_parameters),
                            multiple=True,
                            mode=SelectSelectorMode.LIST,
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders={
                "backup_index": str(self._advanced_current_backup_index + 1),
                "backup_station_name": str(
                    self._advanced_pending_backup.get(CONF_STATION_NAME) or ""
                ),
            },
        )

    async def async_step_advanced_no_more_backups(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Finish advanced setup when no remaining station can add new data."""
        if user_input is not None:
            return await self._async_create_advanced_entry()

        return self.async_show_form(
            step_id="advanced_no_more_backups",
            data_schema=vol.Schema({}),
        )

    async def _async_create_advanced_entry(self) -> ConfigFlowResult:
        """Create an advanced composite entry."""
        if self._advanced_primary is None:
            return await self.async_step_user()

        entry_data = {
            **self._advanced_primary,
            CONF_BACKUP_STATIONS: self._advanced_backups,
        }

        hash_payload = {
            CONF_STATION_ID: entry_data[CONF_STATION_ID],
            CONF_USE_COORDINATES: entry_data[CONF_USE_COORDINATES],
            CONF_BACKUP_STATIONS: [
                {
                    CONF_STATION_ID: backup[CONF_STATION_ID],
                    CONF_BACKUP_PARAMETERS: sorted(backup[CONF_BACKUP_PARAMETERS]),
                    CONF_BACKUP_STATION_NAME_SUFFIX: backup[CONF_BACKUP_STATION_NAME_SUFFIX],
                }
                for backup in self._advanced_backups
            ],
        }
        hash_digest = hashlib.sha1(
            json.dumps(hash_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:12]

        await self.async_set_unique_id(f"dmi_advanced_{entry_data[CONF_STATION_ID]}_{hash_digest}")
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=f"{entry_data[CONF_STATION_NAME]} + backups",
            data=entry_data,
        )

    def _build_primary_entry_data(
        self,
        station: Mapping[str, Any],
        user_input: Mapping[str, Any],
        setup_type: str,
    ) -> dict[str, Any]:
        """Build the stored entry data for a primary station."""
        latitude = station.get("latitude")
        longitude = station.get("longitude")
        use_coordinates = bool(user_input.get(CONF_USE_COORDINATES, False))
        if use_coordinates:
            latitude = self.hass.config.latitude
            longitude = self.hass.config.longitude

        return {
            CONF_SETUP_TYPE: setup_type,
            CONF_STATION_ID: str(station.get("stationId") or ""),
            CONF_STATION_NAME: str(station.get("name") or "DMI Weather"),
            CONF_LATITUDE: latitude,
            CONF_LONGITUDE: longitude,
            CONF_USE_COORDINATES: use_coordinates,
        }

    def _get_station_by_id(
        self,
        station_id: str,
        *,
        stations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Return a station by id."""
        for station in self._stations if stations is None else stations:
            if str(station.get("stationId", "")) == station_id:
                return station
        return None

    def _build_station_options(
        self,
        stations: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, str]]:
        """Build selector options for stations."""
        station_options_by_id: dict[str, dict[str, str]] = {}
        for station in self._stations if stations is None else stations:
            station_id = station.get("stationId")
            if not station_id:
                continue
            name = station.get("name") or f"Station {station_id}"
            station_options_by_id[str(station_id)] = {
                "value": str(station_id),
                "label": f"{name} ({station_id})",
            }

        station_options = list(station_options_by_id.values())
        station_options.sort(key=lambda option: option["label"])
        return station_options

    def _get_available_backup_stations(self) -> list[dict[str, Any]]:
        """Return backup stations that can add at least one new supported parameter."""
        if self._advanced_primary is None:
            return []

        primary_station_id = str(self._advanced_primary[CONF_STATION_ID])
        selected_backup_ids = {str(backup[CONF_STATION_ID]) for backup in self._advanced_backups}

        available_stations: list[dict[str, Any]] = []
        for station in self._stations:
            station_id = str(station.get("stationId") or "")
            if (
                not station_id
                or station_id == primary_station_id
                or station_id in selected_backup_ids
            ):
                continue
            if self._get_backup_parameter_ids(station):
                available_stations.append(station)
        return available_stations

    def _build_backup_station_options(self) -> list[dict[str, str]]:
        """Build selector options for useful backup stations only."""
        station_options_by_id: dict[str, dict[str, str]] = {}
        for station in self._get_available_backup_stations():
            station_id = station.get("stationId")
            if not station_id:
                continue
            name = station.get("name") or f"Station {station_id}"
            station_options_by_id[str(station_id)] = {
                "value": str(station_id),
                "label": f"{name} ({station_id})",
            }

        station_options = list(station_options_by_id.values())
        station_options.sort(key=lambda option: option["label"])
        return station_options

    def _build_backup_parameter_options(self, parameter_ids: list[str]) -> list[dict[str, str]]:
        """Build selector options for backup parameters."""
        return [
            {
                "value": parameter_id,
                "label": SENSOR_TYPES_BY_KEY[parameter_id].name or parameter_id,
            }
            for parameter_id in parameter_ids
        ]

    def _get_backup_parameter_ids(self, backup_station: Mapping[str, Any]) -> list[str]:
        """Return supported backup parameters not already owned by the composite entry."""
        primary_station = self._get_station_by_id(str(self._advanced_primary[CONF_STATION_ID]))
        primary_parameters = {
            parameter_id
            for parameter_id in primary_station.get("parameterId", [])
            if parameter_id in SENSOR_TYPES_BY_KEY
        }
        claimed_backup_parameters = {
            parameter_id
            for backup in self._advanced_backups
            for parameter_id in backup.get(CONF_BACKUP_PARAMETERS, [])
        }
        unavailable_parameters = primary_parameters | claimed_backup_parameters
        backup_parameters = [
            parameter_id
            for parameter_id in backup_station.get("parameterId", [])
            if parameter_id in SENSOR_TYPES_BY_KEY and parameter_id not in unavailable_parameters
        ]

        return sorted(
            backup_parameters,
            key=lambda parameter_id: str(SENSOR_TYPES_BY_KEY[parameter_id].name or parameter_id),
        )

    async def _async_load_stations(self) -> bool:
        """Load station list from the DMI API."""
        if self._stations:
            return True

        try:
            session = async_get_clientsession(self.hass)
            api_client = DMIApiClient(session)
            self._stations = await api_client.get_stations(active_only=True)
            _LOGGER.debug("Fetched %d stations from DMI API", len(self._stations))
        except CannotConnect as err:
            _LOGGER.error("Cannot connect to DMI API: %s", err)
            return False
        except Exception as err:  # pragma: no cover - defensive path
            _LOGGER.exception("Unexpected error fetching stations: %s", err)
            return False

        return bool(self._stations)

    async def _async_load_sea_stations(self) -> bool:
        """Load supported tide-gauge stations from the DMI oceanObs API."""
        if self._sea_stations:
            return True

        try:
            session = async_get_clientsession(self.hass)
            api_client = DMIApiClient(session)
            stations = await api_client.get_sea_stations(active_only=True)
            self._sea_stations = [
                station
                for station in stations
                if station.get("validTo") is None
                and any(
                    parameter_id in SEA_SENSOR_TYPES_BY_KEY
                    for parameter_id in station.get("parameterId", [])
                )
            ]
            _LOGGER.debug("Fetched %d supported tide-gauge stations", len(self._sea_stations))
        except CannotConnect as err:
            _LOGGER.error("Cannot connect to DMI oceanObs API: %s", err)
            return False
        except Exception as err:  # pragma: no cover - defensive path
            _LOGGER.exception("Unexpected error fetching tide-gauge stations: %s", err)
            return False

        return bool(self._sea_stations)

    async def _async_load_tidewater_stations(self) -> bool:
        """Load astronomical prediction stations from DMI oceanObs."""
        if self._tidewater_stations:
            return True

        try:
            session = async_get_clientsession(self.hass)
            api_client = DMIApiClient(session)
            self._tidewater_stations = await api_client.get_tidewater_stations()
            _LOGGER.debug(
                "Fetched %d astronomical prediction stations",
                len(self._tidewater_stations),
            )
        except CannotConnect as err:
            _LOGGER.error("Cannot connect to DMI tidewater API: %s", err)
            return False
        except Exception as err:  # pragma: no cover - defensive path
            _LOGGER.exception("Unexpected error fetching prediction stations: %s", err)
            return False

        return bool(self._tidewater_stations)

    @staticmethod
    def _distance_km(
        latitude_a: float,
        longitude_a: float,
        latitude_b: float,
        longitude_b: float,
    ) -> float:
        """Return the great-circle distance between two coordinates."""
        lat_a = math.radians(latitude_a)
        lat_b = math.radians(latitude_b)
        lat_delta = lat_b - lat_a
        lon_delta = math.radians(longitude_b - longitude_a)
        haversine = (
            math.sin(lat_delta / 2) ** 2
            + math.cos(lat_a) * math.cos(lat_b) * math.sin(lon_delta / 2) ** 2
        )
        return 6371.0 * 2 * math.asin(math.sqrt(haversine))

    def _tidewater_station_distance(self, station: Mapping[str, Any]) -> float:
        """Return distance from the selected gauge, or infinity if unknown."""
        if self._sea_primary is None:
            return math.inf
        try:
            return self._distance_km(
                float(self._sea_primary[CONF_LATITUDE]),
                float(self._sea_primary[CONF_LONGITUDE]),
                float(station["latitude"]),
                float(station["longitude"]),
            )
        except (KeyError, TypeError, ValueError):
            return math.inf

    def _nearest_tidewater_station_id(self) -> str:
        """Return the closest prediction station to the selected gauge."""
        nearest = min(
            self._tidewater_stations,
            key=self._tidewater_station_distance,
        )
        return str(nearest["stationId"])

    def _build_tidewater_station_options(self) -> list[dict[str, str]]:
        """Build prediction-station options ordered by proximity."""
        options: list[dict[str, str]] = []
        for station in sorted(
            self._tidewater_stations,
            key=lambda item: (
                self._tidewater_station_distance(item),
                str(item.get("name") or ""),
            ),
        ):
            station_id = str(station["stationId"])
            station_name = str(station.get("name") or station_id)
            distance = self._tidewater_station_distance(station)
            distance_label = f" — {distance:.1f} km" if math.isfinite(distance) else ""
            options.append(
                {
                    "value": station_id,
                    "label": f"{station_name} ({station_id}){distance_label}",
                }
            )
        return options

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return DMIOptionsFlowHandler()


class DMIOptionsFlowHandler(OptionsFlow):
    """Handle options flow for DMI Weather."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL // 60
        )
        current_include_forecast = self.config_entry.options.get(CONF_INCLUDE_FORECAST, True)

        schema: dict[vol.Marker, Any] = {
            vol.Optional(
                CONF_UPDATE_INTERVAL,
                default=current_interval,
            ): NumberSelector(
                NumberSelectorConfig(
                    min=10,
                    max=60,
                    step=1,
                    mode=NumberSelectorMode.SLIDER,
                    unit_of_measurement="minutes",
                )
            )
        }
        if self.config_entry.data.get(CONF_SETUP_TYPE) != SETUP_TYPE_SEA:
            schema[
                vol.Optional(
                    CONF_INCLUDE_FORECAST,
                    default=current_include_forecast,
                )
            ] = BooleanSelector()

        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))
