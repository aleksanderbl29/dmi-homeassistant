"""DMI API Client for fetching weather data."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import FORECAST_URL, METOBS_URL

_LOGGER = logging.getLogger(__name__)
AUTH_PARAM_NAMES = frozenset({"api-key", "apikey", "token"})


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class RateLimitExceeded(Exception):
    """Error to indicate rate limit exceeded."""


class DMIApiClient:
    """Client for interacting with DMI Open Data API."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        """Initialize the API client.

        Args:
            session: aiohttp client session for making requests.
        """
        self._session = session

    @staticmethod
    def _ensure_no_auth_params(params: dict[str, Any] | None) -> None:
        """Reject authenticated query params on the open-data client."""
        if params is None:
            return

        forbidden_params = AUTH_PARAM_NAMES & set(params)
        if forbidden_params:
            raise CannotConnect(
                "Authenticated DMI query parameters are not supported on the open-data client: "
                + ", ".join(sorted(forbidden_params))
            )

    @staticmethod
    def _normalize_parameter_ids(parameter_ids: Any) -> list[str]:
        """Return a stable list of parameter ids."""
        if isinstance(parameter_ids, list):
            values = parameter_ids
        elif parameter_ids is None:
            values = []
        else:
            values = [parameter_ids]

        normalized: list[str] = []
        for value in values:
            if value is None:
                continue
            parameter_id = str(value)
            if parameter_id not in normalized:
                normalized.append(parameter_id)
        return normalized

    @staticmethod
    def _station_sort_key(props: dict[str, Any]) -> tuple[int, str, str]:
        """Build a sort key that prefers the current station record."""
        return (
            1 if props.get("validTo") is None else 0,
            str(props.get("validFrom") or ""),
            str(props.get("updated") or props.get("created") or ""),
        )

    async def _request(self, url: str, params: dict[str, Any] | None = None) -> dict:
        """Make an API request.

        Args:
            url: The URL to request.
            params: Optional query parameters.

        Returns:
            JSON response as dictionary.

        Raises:
            RateLimitExceeded: If rate limit is hit (429).
            CannotConnect: If connection fails.
        """
        try:
            self._ensure_no_auth_params(params)
            _LOGGER.debug("Making request to %s with params %s", url, params)
            async with self._session.get(
                url, params=params, timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 429:
                    raise RateLimitExceeded("DMI API rate limit exceeded")
                response.raise_for_status()
                data = await response.json()
                _LOGGER.debug("Received response with %d bytes", len(str(data)))
                return data
        except RateLimitExceeded:
            raise
        except aiohttp.ClientResponseError as err:
            if err.status == 429:
                raise RateLimitExceeded("DMI API rate limit exceeded") from err
            _LOGGER.error("API response error: %s", err)
            raise CannotConnect(f"API error: {err}") from err
        except aiohttp.ClientError as err:
            _LOGGER.error("API connection error: %s", err)
            raise CannotConnect(f"Connection error: {err}") from err
        except TimeoutError as err:
            _LOGGER.error("API timeout: %s", err)
            raise CannotConnect(f"Request timeout: {err}") from err
        except Exception as err:
            _LOGGER.error("Unexpected API error: %s", err)
            raise CannotConnect(f"Unexpected error: {err}") from err

    async def get_stations(self, active_only: bool = True) -> list[dict[str, Any]]:
        """Fetch list of weather stations.

        Args:
            active_only: If True, only return active stations.

        Returns:
            List of station dictionaries with stationId, name, coordinates, etc.
        """
        url = f"{METOBS_URL}/collections/station/items"
        params: dict[str, Any] = {"limit": 1000}
        if active_only:
            params["status"] = "Active"

        data = await self._request(url, params)

        stations_by_id: dict[str, dict[str, Any]] = {}
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            geometry = feature.get("geometry", {})
            coordinates = geometry.get("coordinates", [None, None])
            station_id = props.get("stationId")

            if not station_id:
                continue

            station = {
                "stationId": station_id,
                "name": props.get("name"),
                "longitude": coordinates[0] if len(coordinates) > 0 else None,
                "latitude": coordinates[1] if len(coordinates) > 1 else None,
                "type": props.get("type"),
                "parameterId": self._normalize_parameter_ids(props.get("parameterId")),
            }

            existing = stations_by_id.get(str(station_id))
            if existing is None:
                stations_by_id[str(station_id)] = {
                    **station,
                    "_sort_key": self._station_sort_key(props),
                }
                continue

            merged_parameter_ids = existing["parameterId"][:]
            for parameter_id in station["parameterId"]:
                if parameter_id not in merged_parameter_ids:
                    merged_parameter_ids.append(parameter_id)

            if self._station_sort_key(props) >= existing["_sort_key"]:
                stations_by_id[str(station_id)] = {
                    **station,
                    "parameterId": merged_parameter_ids,
                    "_sort_key": self._station_sort_key(props),
                }
            else:
                existing["parameterId"] = merged_parameter_ids

        return [
            {key: value for key, value in station.items() if key != "_sort_key"}
            for station in stations_by_id.values()
        ]

    async def get_observations(self, station_id: str) -> dict[str, Any]:
        """Fetch latest observations for a station.

        Args:
            station_id: The station ID to fetch observations for.

        Returns:
            Dictionary keyed by parameterId with value and observed timestamp.
        """
        url = f"{METOBS_URL}/collections/observation/items"
        params = {
            "stationId": station_id,
            "limit": 100,
        }

        data = await self._request(url, params)

        # Extract the latest observation per parameter
        observations: dict[str, Any] = {}
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            param_id = props.get("parameterId")
            observed = props.get("observed")

            if param_id:
                # Only keep if this is newer than what we have
                if param_id not in observations or observed > observations[param_id]["observed"]:
                    observations[param_id] = {
                        "value": props.get("value"),
                        "observed": observed,
                    }

        return observations

    async def get_forecast(self, latitude: float, longitude: float) -> dict[str, Any]:
        """Fetch forecast data for coordinates.

        Uses the HARMONIE model for forecast data.

        Args:
            latitude: Latitude coordinate.
            longitude: Longitude coordinate.

        Returns:
            Dictionary with hourly forecast data.
        """
        url = f"{FORECAST_URL}/collections/harmonie_dini_sf/position"

        # Build the coords parameter (POINT format with lon lat)
        coords = f"POINT({longitude} {latitude})"

        params = {
            "coords": coords,
            "crs": "crs84",
            "parameter-name": "temperature-2m,wind-speed-10m,wind-dir-10m,relative-humidity-2m,total-precipitation,fraction-of-cloud-cover",
            "f": "CoverageJSON",
        }

        data = await self._request(url, params)

        # Parse the forecast data into hourly format
        hourly_forecast: list[dict[str, Any]] = []

        # The response contains ranges with time steps
        ranges = data.get("ranges", {})

        # Get time steps from the domain
        domain = data.get("domain", {})
        axes = domain.get("axes", {})
        time_axis = axes.get("t", {})
        time_values = time_axis.get("values", [])

        # Extract parameter values
        temperature_data = ranges.get("temperature-2m", {}).get("values", [])
        wind_speed_data = ranges.get("wind-speed-10m", {}).get("values", [])
        wind_dir_data = ranges.get("wind-dir-10m", {}).get("values", [])
        humidity_data = ranges.get("relative-humidity-2m", {}).get("values", [])
        precipitation_data = ranges.get("total-precipitation", {}).get("values", [])
        cloud_cover_data = ranges.get("fraction-of-cloud-cover", {}).get("values", [])

        for i, time_value in enumerate(time_values):
            forecast_entry: dict[str, Any] = {
                "datetime": time_value,
            }

            # Add values if available at this index
            if i < len(temperature_data) and temperature_data[i] is not None:
                # Convert from Kelvin to Celsius
                forecast_entry["temperature"] = temperature_data[i] - 273.15

            if i < len(wind_speed_data) and wind_speed_data[i] is not None:
                forecast_entry["wind_speed"] = wind_speed_data[i]

            if i < len(wind_dir_data) and wind_dir_data[i] is not None:
                forecast_entry["wind_dir"] = wind_dir_data[i]

            if i < len(humidity_data) and humidity_data[i] is not None:
                forecast_entry["humidity"] = humidity_data[i]

            if i < len(precipitation_data) and precipitation_data[i] is not None:
                forecast_entry["precipitation"] = precipitation_data[i]

            if i < len(cloud_cover_data) and cloud_cover_data[i] is not None:
                forecast_entry["cloud_cover"] = cloud_cover_data[i]

            hourly_forecast.append(forecast_entry)

        return {"hourly": hourly_forecast}

    async def test_connection(self) -> bool:
        """Test API connectivity.

        Returns:
            True if connection is successful.

        Raises:
            CannotConnect: If connection fails.
        """
        url = f"{METOBS_URL}/collections/station/items"
        params = {"limit": 1}

        try:
            await self._request(url, params)
            return True
        except Exception as err:
            _LOGGER.error("Connection test failed: %s", err)
            raise CannotConnect(f"Connection test failed: {err}") from err
