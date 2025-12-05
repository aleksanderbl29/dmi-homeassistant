"""Tests for the DMI API client."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.dmi.api import CannotConnect, DMIApiClient, RateLimitExceeded


class TestDMIApiClient:
    """Test cases for DMIApiClient."""

    @pytest.fixture
    def api_client(self) -> DMIApiClient:
        """Create an API client with a mock session."""
        session = MagicMock(spec=aiohttp.ClientSession)
        return DMIApiClient(session)

    # --- get_stations tests ---

    async def test_get_stations_success(
        self,
        api_client: DMIApiClient,
        mock_stations_data: dict[str, Any],
    ) -> None:
        """Test successful station fetch."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_stations_data)
        mock_response.raise_for_status = MagicMock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        api_client._session.get = MagicMock(return_value=mock_context)

        stations = await api_client.get_stations(active_only=True)

        assert len(stations) == 3
        assert stations[0]["stationId"] == "06180"
        assert stations[0]["name"] == "Københavns Lufthavn"
        assert stations[0]["latitude"] == 55.614
        assert stations[0]["longitude"] == 12.6455

    async def test_get_stations_empty_response(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test handling of empty stations response."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"features": []})
        mock_response.raise_for_status = MagicMock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        api_client._session.get = MagicMock(return_value=mock_context)

        stations = await api_client.get_stations()

        assert stations == []

    async def test_get_stations_filters_invalid(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test that stations without stationId are filtered out."""
        mock_data = {
            "features": [
                {
                    "properties": {"name": "Test Station"},
                    "geometry": {"coordinates": [10.0, 55.0]},
                },
                {
                    "properties": {"stationId": "12345", "name": "Valid Station"},
                    "geometry": {"coordinates": [11.0, 56.0]},
                },
            ],
        }
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_data)
        mock_response.raise_for_status = MagicMock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        api_client._session.get = MagicMock(return_value=mock_context)

        stations = await api_client.get_stations()

        assert len(stations) == 1
        assert stations[0]["stationId"] == "12345"

    # --- get_observations tests ---

    async def test_get_observations_success(
        self,
        api_client: DMIApiClient,
        mock_observations_data: dict[str, Any],
    ) -> None:
        """Test successful observations fetch."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_observations_data)
        mock_response.raise_for_status = MagicMock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        api_client._session.get = MagicMock(return_value=mock_context)

        observations = await api_client.get_observations("06180")

        assert "temp_dry" in observations
        assert observations["temp_dry"]["value"] == 15.5
        assert observations["humidity"]["value"] == 75.0
        assert observations["wind_speed"]["value"] == 5.2

    async def test_get_observations_keeps_latest(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test that only the latest observation per parameter is kept."""
        mock_data = {
            "features": [
                {
                    "properties": {
                        "parameterId": "temp_dry",
                        "value": 14.0,
                        "observed": "2024-01-15T11:00:00Z",
                    },
                },
                {
                    "properties": {
                        "parameterId": "temp_dry",
                        "value": 15.5,
                        "observed": "2024-01-15T12:00:00Z",
                    },
                },
            ],
        }
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_data)
        mock_response.raise_for_status = MagicMock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        api_client._session.get = MagicMock(return_value=mock_context)

        observations = await api_client.get_observations("06180")

        assert observations["temp_dry"]["value"] == 15.5
        assert observations["temp_dry"]["observed"] == "2024-01-15T12:00:00Z"

    # --- get_forecast tests ---

    async def test_get_forecast_success(
        self,
        api_client: DMIApiClient,
        mock_forecast_data: dict[str, Any],
    ) -> None:
        """Test successful forecast fetch."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_forecast_data)
        mock_response.raise_for_status = MagicMock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        api_client._session.get = MagicMock(return_value=mock_context)

        forecast = await api_client.get_forecast(55.6761, 12.5683)

        assert "hourly" in forecast
        assert len(forecast["hourly"]) == 4

        # Check Kelvin to Celsius conversion (288.65K = 15.5°C)
        first_hour = forecast["hourly"][0]
        assert abs(first_hour["temperature"] - 15.5) < 0.1
        assert first_hour["wind_speed"] == 5.0
        assert first_hour["wind_dir"] == 180

    async def test_get_forecast_handles_missing_data(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test forecast handles missing parameter data gracefully."""
        mock_data = {
            "domain": {
                "axes": {
                    "t": {"values": ["2024-01-15T12:00:00Z"]},
                },
            },
            "ranges": {
                "temperature-2m": {"values": [288.65]},
                # Other parameters missing
            },
        }
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_data)
        mock_response.raise_for_status = MagicMock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        api_client._session.get = MagicMock(return_value=mock_context)

        forecast = await api_client.get_forecast(55.6761, 12.5683)

        assert len(forecast["hourly"]) == 1
        assert "temperature" in forecast["hourly"][0]
        assert "wind_speed" not in forecast["hourly"][0]

    # --- test_connection tests ---

    async def test_test_connection_success(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test successful connection test."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={"features": []})
        mock_response.raise_for_status = MagicMock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        api_client._session.get = MagicMock(return_value=mock_context)

        result = await api_client.test_connection()

        assert result is True

    async def test_test_connection_failure(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test connection test failure."""
        mock_context = AsyncMock()
        mock_context.__aenter__.side_effect = aiohttp.ClientError("Connection failed")
        api_client._session.get = MagicMock(return_value=mock_context)

        with pytest.raises(CannotConnect):
            await api_client.test_connection()

    # --- Error handling tests ---

    async def test_rate_limit_error(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test rate limit error handling."""
        mock_response = AsyncMock()
        mock_response.status = 429

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        api_client._session.get = MagicMock(return_value=mock_context)

        with pytest.raises(RateLimitExceeded):
            await api_client.get_stations()

    async def test_client_response_error_429(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test 429 error via ClientResponseError."""
        mock_response = AsyncMock()
        mock_response.status = 429
        mock_response.raise_for_status = MagicMock(
            side_effect=aiohttp.ClientResponseError(
                request_info=MagicMock(),
                history=(),
                status=429,
            )
        )

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        api_client._session.get = MagicMock(return_value=mock_context)

        with pytest.raises(RateLimitExceeded):
            await api_client.get_stations()

    async def test_client_error(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test general client error handling."""
        mock_context = AsyncMock()
        mock_context.__aenter__.side_effect = aiohttp.ClientError("Connection refused")
        api_client._session.get = MagicMock(return_value=mock_context)

        with pytest.raises(CannotConnect):
            await api_client.get_stations()

    async def test_timeout_error(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test timeout error handling."""
        mock_context = AsyncMock()
        mock_context.__aenter__.side_effect = TimeoutError("Request timed out")
        api_client._session.get = MagicMock(return_value=mock_context)

        with pytest.raises(CannotConnect):
            await api_client.get_stations()

    async def test_unexpected_error(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test unexpected error handling."""
        mock_context = AsyncMock()
        mock_context.__aenter__.side_effect = Exception("Unexpected error")
        api_client._session.get = MagicMock(return_value=mock_context)

        with pytest.raises(CannotConnect):
            await api_client.get_stations()

    async def test_client_response_error_other_status(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test non-429 ClientResponseError."""
        mock_response = AsyncMock()
        mock_response.status = 500
        mock_response.raise_for_status = MagicMock(
            side_effect=aiohttp.ClientResponseError(
                request_info=MagicMock(),
                history=(),
                status=500,
            )
        )

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        api_client._session.get = MagicMock(return_value=mock_context)

        with pytest.raises(CannotConnect):
            await api_client.get_stations()

