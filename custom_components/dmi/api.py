"""DMI API Client for fetching weather data."""

from __future__ import annotations

import asyncio
import logging
import math
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any

import aiohttp

from .const import FORECAST_URL, METOBS_URL, OCEANOBS_URL

_LOGGER = logging.getLogger(__name__)
AUTH_PARAM_NAMES = frozenset({"api-key", "apikey", "token"})
PAGE_SIZE = 1000
OBSERVATION_PAGE_SIZE = 100


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class UpstreamError(CannotConnect):
    """Error to indicate the upstream API returned a non-rate-limit failure."""


class RequestTimeout(CannotConnect):
    """Error to indicate an API request timed out."""


class RateLimitExceeded(Exception):
    """Error to indicate rate limit exceeded."""

    def __init__(self, message: str, *, retry_at: datetime | None = None) -> None:
        """Preserve the server's earliest permitted retry time, when supplied."""
        super().__init__(message)
        self.retry_at = retry_at


def _retry_after_deadline(headers: Mapping[str, str] | None) -> datetime | None:
    """Parse Retry-After seconds or an HTTP date at the response boundary."""
    if not isinstance(headers, Mapping):
        return None
    value = headers.get("Retry-After")
    if not isinstance(value, str):
        return None
    value = value.strip()
    now = datetime.now(UTC)
    try:
        if value.isascii() and value.isdecimal():
            return now + timedelta(seconds=int(value))
        deadline = parsedate_to_datetime(value)
        if deadline.tzinfo is not None and deadline >= now:
            return deadline.astimezone(UTC)
    except (ValueError, TypeError, OverflowError):
        pass
    return None


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

    @staticmethod
    def _truncate_error_text(text: str, limit: int = 200) -> str:
        """Return a compact error payload snippet for logs and exceptions."""
        compact = " ".join(str(text).split())
        if len(compact) <= limit:
            return compact
        return f"{compact[: limit - 3]}..."

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
                    response_text = await response.text()
                    detail = self._truncate_error_text(response_text)
                    raise RateLimitExceeded(
                        "DMI API returned HTTP 429"
                        + (f": {detail}" if detail else " (too many requests or server busy)"),
                        retry_at=_retry_after_deadline(response.headers),
                    )
                if response.status >= 400:
                    response_text = await response.text()
                    truncated_text = self._truncate_error_text(response_text)
                    _LOGGER.error(
                        "DMI API returned HTTP %s for %s with params %s: %s",
                        response.status,
                        url,
                        params,
                        truncated_text or "<empty body>",
                    )
                    raise UpstreamError(
                        f"HTTP {response.status} error from DMI API"
                        + (f": {truncated_text}" if truncated_text else "")
                    )
                response.raise_for_status()
                data = await response.json()
                headers = response.headers
                content_length = (
                    headers.get("Content-Length") if isinstance(headers, Mapping) else None
                )
                if content_length is not None:
                    _LOGGER.debug("Received response with Content-Length %s", content_length)
                return data
        except RateLimitExceeded:
            raise
        except asyncio.CancelledError:
            # Cancellation is how Home Assistant stops in-flight work during
            # reload and shutdown. It must not be converted into a retryable
            # request failure, otherwise the task keeps the shutdown waiting.
            raise
        except aiohttp.ContentTypeError as err:
            _LOGGER.error("Invalid JSON response from DMI API: %s", err)
            raise UpstreamError(f"Invalid JSON response from DMI API: {err}") from err
        except aiohttp.ClientResponseError as err:
            if err.status == 429:
                raise RateLimitExceeded(
                    "DMI API rate limit exceeded",
                    retry_at=_retry_after_deadline(err.headers),
                ) from err
            _LOGGER.error("DMI API response error (HTTP %s): %s", err.status, err)
            raise UpstreamError(f"HTTP {err.status} error from DMI API: {err}") from err
        except aiohttp.ClientError as err:
            _LOGGER.error("API connection error: %s", err)
            raise CannotConnect(f"Connection error: {err}") from err
        except UpstreamError:
            raise
        except RequestTimeout:
            raise
        except TimeoutError as err:
            _LOGGER.error("DMI API request exceeded the 30-second timeout")
            raise RequestTimeout("DMI API request exceeded the 30-second timeout") from err

    def _merge_station_feature(
        self,
        stations_by_id: dict[str, dict[str, Any]],
        feature: dict[str, Any],
    ) -> None:
        """Merge a station feature into the deduplicated station catalog."""
        props = feature.get("properties", {})
        geometry = feature.get("geometry", {})
        coordinates = geometry.get("coordinates", [None, None])
        station_id = props.get("stationId")

        if not station_id:
            return

        station = {
            "stationId": station_id,
            "name": props.get("name"),
            "longitude": coordinates[0] if len(coordinates) > 0 else None,
            "latitude": coordinates[1] if len(coordinates) > 1 else None,
            "type": props.get("type"),
            "parameterId": self._normalize_parameter_ids(props.get("parameterId")),
            "validTo": props.get("validTo"),
        }

        existing = stations_by_id.get(str(station_id))
        if existing is None:
            stations_by_id[str(station_id)] = {
                **station,
                "_sort_key": self._station_sort_key(props),
            }
            return

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

    async def _get_stations(
        self,
        api_url: str,
        *,
        active_only: bool,
    ) -> list[dict[str, Any]]:
        """Fetch and normalize a station catalog."""
        url = f"{api_url}/collections/station/items"
        offset = 0
        stations_by_id: dict[str, dict[str, Any]] = {}

        while True:
            params: dict[str, Any] = {"limit": PAGE_SIZE, "offset": offset}
            if active_only:
                params["status"] = "Active"

            data = await self._request(url, params)
            features = data.get("features", [])
            for feature in features:
                self._merge_station_feature(stations_by_id, feature)

            if len(features) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

        return [
            {key: value for key, value in station.items() if key != "_sort_key"}
            for station in stations_by_id.values()
        ]

    async def get_stations(self, active_only: bool = True) -> list[dict[str, Any]]:
        """Fetch list of weather stations.

        Args:
            active_only: If True, only return active stations.

        Returns:
            List of station dictionaries with stationId, name, coordinates, etc.
        """
        # DMI metObs items supports limit/offset pagination:
        # https://www.dmi.dk/friedata/dokumentation/meteorological-observation-api
        return await self._get_stations(METOBS_URL, active_only=active_only)

    async def get_sea_stations(self, active_only: bool = True) -> list[dict[str, Any]]:
        """Fetch the list of oceanographic tide-gauge stations."""
        # DMI oceanObs uses the same OGC station schema as metObs:
        # https://www.dmi.dk/friedata/dokumentation/apis/oceanographic-observation-and-tidewater-api
        return await self._get_stations(OCEANOBS_URL, active_only=active_only)

    async def get_tidewater_stations(self) -> list[dict[str, Any]]:
        """Fetch DMI's separate catalog of astronomical prediction stations."""
        url = f"{OCEANOBS_URL}/collections/tidewaterstation/items"
        offset = 0
        stations: list[dict[str, Any]] = []

        while True:
            data = await self._request(url, {"limit": PAGE_SIZE, "offset": offset})
            features = data.get("features", [])
            for feature in features:
                props = feature.get("properties", {})
                geometry = feature.get("geometry", {})
                coordinates = geometry.get("coordinates", [None, None])
                station_id = props.get("stationId")
                if not station_id:
                    continue
                stations.append(
                    {
                        "stationId": str(station_id),
                        "name": props.get("name"),
                        "country": props.get("country"),
                        "longitude": coordinates[0] if len(coordinates) > 0 else None,
                        "latitude": coordinates[1] if len(coordinates) > 1 else None,
                        "lowAstronomicalTide": props.get("lowAstronomicalTide"),
                        "meanLowWaterSpring": props.get("meanLowWaterSpring"),
                    }
                )

            if len(features) < PAGE_SIZE:
                break
            offset += PAGE_SIZE

        return stations

    @staticmethod
    def _parse_observations(data: dict[str, Any]) -> dict[str, Any]:
        """Return the newest reading for every parameter in a response."""
        observations: dict[str, Any] = {}
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            param_id = props.get("parameterId")
            observed = props.get("observed")

            if param_id and (
                param_id not in observations
                or str(observed or "") > str(observations[param_id].get("observed") or "")
            ):
                observation = {
                    "value": props.get("value"),
                    "observed": observed,
                }
                if props.get("created") is not None:
                    observation["created"] = props["created"]
                if props.get("qcStatus") is not None:
                    observation["qc_status"] = props["qcStatus"]
                observations[param_id] = observation

        return observations

    async def get_observations(self, station_id: str) -> dict[str, Any]:
        """Fetch latest observations for a station.

        Args:
            station_id: The station ID to fetch observations for.

        Returns:
            Dictionary keyed by parameterId with value and observed timestamp.
        """
        url = f"{METOBS_URL}/collections/observation/items"
        # DMI metObs observation items documents stationId, limit and offset.
        # Do not add sortorder here; the live metObs API returns "Unknown sortorder".
        # Do not paginate observations during HA setup; the endpoint can expose
        # large historical result sets and first refresh must stay bounded.
        # https://www.dmi.dk/friedata/dokumentation/meteorological-observation-api
        params = {
            "stationId": station_id,
            "limit": OBSERVATION_PAGE_SIZE,
            "offset": 0,
        }

        data = await self._request(url, params)

        return self._parse_observations(data)

    async def get_sea_observations(self, station_id: str) -> dict[str, Any]:
        """Fetch the latest sea-level and water-temperature observations."""
        url = f"{OCEANOBS_URL}/collections/observation/items"
        # oceanObs explicitly supports sorting observations. A descending page
        # ensures all currently reported parameters are found in one bounded request.
        params = {
            "stationId": station_id,
            "limit": OBSERVATION_PAGE_SIZE,
            "offset": 0,
            "sortorder": "observed,DESC",
        }

        data = await self._request(url, params)
        return self._parse_observations(data)

    @staticmethod
    def _rfc3339(value: datetime) -> str:
        """Format a datetime for DMI's inclusive datetime-range filter."""
        if value.tzinfo is None:
            value = value.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    async def get_tidewater_forecast(
        self,
        station_id: str,
        start: datetime,
        end: datetime,
    ) -> list[dict[str, Any]]:
        """Fetch astronomical tide predictions for a prediction station."""
        url = f"{OCEANOBS_URL}/collections/tidewater/items"
        params = {
            "stationId": station_id,
            "datetime": f"{self._rfc3339(start)}/{self._rfc3339(end)}",
            # A 24-hour response contains about 144 ten-minute predictions
            # plus minima and maxima, so this remains a bounded request.
            "limit": 500,
            "offset": 0,
        }
        data = await self._request(url, params)

        predictions: list[dict[str, Any]] = []
        for feature in data.get("features", []):
            props = feature.get("properties", {})
            prediction_time = props.get("predictionTime")
            prediction_type = props.get("predictionType")
            if prediction_time is None or prediction_type is None:
                continue
            predictions.append(
                {
                    "value": props.get("value"),
                    "prediction_time": prediction_time,
                    "prediction_type": prediction_type,
                    "created": props.get("created"),
                    "station_id": str(props.get("stationId") or station_id),
                }
            )

        return sorted(predictions, key=lambda prediction: prediction["prediction_time"])

    @staticmethod
    def _dkss_collection_for_position(latitude: float, longitude: float) -> str:
        """Choose DMI's most detailed DKSS model covering a position."""
        model_areas = (
            ("dkss_if", 11.6, 12.1, 55.6, 56.0),
            ("dkss_lb", 9.5, 10.1, 55.2, 55.7),
            ("dkss_lf", 8.2, 10.3, 56.5, 57.1),
            ("dkss_ws", 6.2, 10.5, 53.2, 55.7),
            ("dkss_idw", 9.3, 14.8, 53.6, 57.6),
            ("dkss_nsbs", 4.1, 30.3, 48.0, 65.9),
        )
        for collection_id, west, east, south, north in model_areas:
            if west <= longitude <= east and south <= latitude <= north:
                return collection_id
        return "dkss_nsbs"

    @staticmethod
    def _axis_values(axis: dict[str, Any]) -> list[float]:
        """Expand a CoverageJSON numeric axis into explicit values."""
        if isinstance(axis.get("values"), list):
            return [float(value) for value in axis["values"]]
        count = int(axis.get("num") or 0)
        if count <= 0:
            return []
        start = float(axis["start"])
        if count == 1:
            return [start]
        stop = float(axis["stop"])
        step = (stop - start) / (count - 1)
        return [start + step * index for index in range(count)]

    @classmethod
    def _parse_dkss_coverage(
        cls,
        data: dict[str, Any],
        *,
        latitude: float,
        longitude: float,
        collection_id: str,
    ) -> dict[str, Any] | None:
        """Extract the closest wet grid cell from a DKSS coverage."""
        axes = data.get("domain", {}).get("axes", {})
        time_values = axes.get("t", {}).get("values", [])
        x_values = cls._axis_values(axes.get("x", {}))
        y_values = cls._axis_values(axes.get("y", {}))
        values = data.get("ranges", {}).get("sea-mean-deviation", {}).get("values", [])
        if not time_values or not x_values or not y_values or not values:
            return None

        cell_count = len(x_values) * len(y_values)
        wet_cells: list[tuple[float, int, int]] = []
        longitude_scale = math.cos(math.radians(latitude))
        for y_index, model_latitude in enumerate(y_values):
            for x_index, model_longitude in enumerate(x_values):
                cell_index = y_index * len(x_values) + x_index
                if not any(
                    time_index * cell_count + cell_index < len(values)
                    and values[time_index * cell_count + cell_index] is not None
                    for time_index in range(len(time_values))
                ):
                    continue
                distance_squared = (model_latitude - latitude) ** 2 + (
                    (model_longitude - longitude) * longitude_scale
                ) ** 2
                wet_cells.append((distance_squared, y_index, x_index))

        if not wet_cells:
            return None

        _, y_index, x_index = min(wet_cells)
        cell_index = y_index * len(x_values) + x_index
        forecast: list[dict[str, Any]] = []
        for time_index, forecast_time in enumerate(time_values):
            value_index = time_index * cell_count + cell_index
            if value_index >= len(values) or values[value_index] is None:
                continue
            forecast.append(
                {
                    "datetime": forecast_time,
                    # DKSS sea-mean-deviation is metres; sea sensors use centimetres.
                    "value": round(float(values[value_index]) * 100, 2),
                }
            )

        if not forecast:
            return None
        return {
            "collection_id": collection_id,
            "model_latitude": y_values[y_index],
            "model_longitude": x_values[x_index],
            "forecast": forecast,
        }

    async def get_dkss_forecast(
        self,
        latitude: float,
        longitude: float,
        start: datetime,
        end: datetime,
    ) -> dict[str, Any] | None:
        """Fetch the DKSS sea-level forecast nearest a tide gauge."""
        preferred_collection = self._dkss_collection_for_position(latitude, longitude)
        collection_ids = [preferred_collection]
        if preferred_collection != "dkss_nsbs":
            collection_ids.append("dkss_nsbs")
        params = {
            "coords": f"POINT({longitude} {latitude})",
            "crs": "crs84",
            "parameter-name": "sea-mean-deviation",
            "datetime": f"{self._rfc3339(start)}/{self._rfc3339(end)}",
            "f": "CoverageJSON",
        }
        for collection_id in collection_ids:
            url = f"{FORECAST_URL}/collections/{collection_id}/position"
            data = await self._request(url, params)
            parsed = self._parse_dkss_coverage(
                data,
                latitude=latitude,
                longitude=longitude,
                collection_id=collection_id,
            )
            if parsed is not None:
                return parsed
        return None

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
            # DMI Forecast EDR position queries document coords, crs, parameter-name and f:
            # https://www.dmi.dk/friedata/dokumentation/forecast-data-edr-api
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

        previous_precipitation: float | None = None
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
                precipitation = float(precipitation_data[i])
                if previous_precipitation is None:
                    forecast_entry["precipitation"] = precipitation
                else:
                    forecast_entry["precipitation"] = max(
                        precipitation - previous_precipitation,
                        0,
                    )
                previous_precipitation = precipitation

            if i < len(cloud_cover_data) and cloud_cover_data[i] is not None:
                cloud_cover = float(cloud_cover_data[i])
                forecast_entry["cloud_cover"] = (
                    cloud_cover * 100 if 0 <= cloud_cover <= 1 else cloud_cover
                )

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
