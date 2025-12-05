"""DMI API Client for fetching weather data."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from .const import FORECAST_URL, METOBS_URL

_LOGGER = logging.getLogger(__name__)


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
            async with self._session.get(url, params=params) as response:
                if response.status == 429:
                    raise RateLimitExceeded("DMI API rate limit exceeded")
                response.raise_for_status()
                return await response.json()
        except aiohttp.ClientResponseError as err:
            if err.status == 429:
                raise RateLimitExceeded("DMI API rate limit exceeded") from err
            _LOGGER.error("API response error: %s", err)
            raise CannotConnect(f"API error: {err}") from err
        except aiohttp.ClientError as err:
            _LOGGER.error("API connection error: %s", err)
            raise CannotConnect(f"Connection error: {err}") from err

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

        stations = []
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            geometry = feature.get("geometry", {})
            coordinates = geometry.get("coordinates", [None, None])

            station = {
                "stationId": props.get("stationId"),
                "name": props.get("name"),
                "longitude": coordinates[0] if len(coordinates) > 0 else None,
                "latitude": coordinates[1] if len(coordinates) > 1 else None,
                "type": props.get("type"),
                "parameterId": props.get("parameterId", []),
            }
            if station["stationId"]:
                stations.append(station)

        return stations

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
            "period": "latest",
        }

        data = await self._request(url, params)

        observations: dict[str, Any] = {}
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            param_id = props.get("parameterId")
            if param_id:
                observations[param_id] = {
                    "value": props.get("value"),
                    "observed": props.get("observed"),
                }

        return observations

    async def get_forecast(
        self, latitude: float, longitude: float
    ) -> dict[str, Any]:
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
            "parameter-name": "temperature-2m,wind-speed-10m,wind-dir-10m,relative-humidity,total-precipitation,cloud-cover",
            "f": "GeoJSON",
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
        humidity_data = ranges.get("relative-humidity", {}).get("values", [])
        precipitation_data = ranges.get("total-precipitation", {}).get("values", [])
        cloud_cover_data = ranges.get("cloud-cover", {}).get("values", [])

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

