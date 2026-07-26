"""Tests for the DMI API client."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest

from custom_components.dmi.api import (
    AUTH_PARAM_NAMES,
    CannotConnect,
    DMIApiClient,
    RateLimitExceeded,
    RequestTimeout,
    UpstreamError,
)
from custom_components.dmi.const import BASE_URL, FORECAST_URL, METOBS_URL, OCEANOBS_URL


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
        assert stations[0]["validTo"] == "2019-01-15T13:34:48Z"

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

    async def test_get_sea_stations_uses_oceanobs_endpoint(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test tide-gauge discovery uses the oceanObs station collection."""
        api_client._request = AsyncMock(return_value={"features": []})

        stations = await api_client.get_sea_stations()

        assert stations == []
        api_client._request.assert_awaited_once_with(
            f"{OCEANOBS_URL}/collections/station/items",
            {"limit": 1000, "offset": 0, "status": "Active"},
        )

    async def test_get_sea_stations_exposes_validity_for_current_station_filtering(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test station validity is retained so ended gauges can be hidden."""
        api_client._request = AsyncMock(
            return_value={
                "features": [
                    {
                        "properties": {
                            "stationId": "20002",
                            "name": "Old Gauge",
                            "parameterId": ["sealev_dvr"],
                            "validTo": "2021-01-06T00:00:00Z",
                        },
                        "geometry": {"coordinates": [10.59, 57.71]},
                    }
                ]
            }
        )

        stations = await api_client.get_sea_stations()

        assert stations[0]["validTo"] == "2021-01-06T00:00:00Z"

    async def test_get_tidewater_stations_parses_prediction_metadata(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test astronomical prediction stations retain reference metadata."""
        api_client._request = AsyncMock(
            return_value={
                "features": [
                    {
                        "geometry": {"coordinates": [11.1422, 55.3306]},
                        "properties": {
                            "stationId": "29393",
                            "name": "Korsør",
                            "country": "DNK",
                            "lowAstronomicalTide": -23.8,
                            "meanLowWaterSpring": -15.0,
                        },
                    }
                ]
            }
        )

        stations = await api_client.get_tidewater_stations()

        assert stations == [
            {
                "stationId": "29393",
                "name": "Korsør",
                "country": "DNK",
                "longitude": 11.1422,
                "latitude": 55.3306,
                "lowAstronomicalTide": -23.8,
                "meanLowWaterSpring": -15.0,
            }
        ]
        api_client._request.assert_awaited_once_with(
            f"{OCEANOBS_URL}/collections/tidewaterstation/items",
            {"limit": 1000, "offset": 0},
        )

    async def test_get_tidewater_stations_skips_invalid_and_paginates(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test invalid prediction stations are skipped across catalog pages."""
        api_client._request = AsyncMock(
            side_effect=[
                {"features": [{"properties": {}, "geometry": {}}]},
                {
                    "features": [
                        {
                            "properties": {"stationId": "29393"},
                            "geometry": {"coordinates": []},
                        }
                    ]
                },
                {"features": []},
            ]
        )

        with patch("custom_components.dmi.api.PAGE_SIZE", 1):
            stations = await api_client.get_tidewater_stations()

        assert stations == [
            {
                "stationId": "29393",
                "name": None,
                "country": None,
                "longitude": None,
                "latitude": None,
                "lowAstronomicalTide": None,
                "meanLowWaterSpring": None,
            }
        ]
        assert api_client._request.await_count == 3

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

    async def test_get_stations_consolidates_duplicate_station_ids(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test duplicate station ids are consolidated to the current record."""
        mock_data = {
            "features": [
                {
                    "properties": {
                        "stationId": "06180",
                        "name": "Københavns Lufthavn",
                        "type": "Synop",
                        "parameterId": ["temp_dry"],
                        "validFrom": "1983-06-16T00:00:00Z",
                        "validTo": "2019-01-15T13:34:48Z",
                    },
                    "geometry": {"coordinates": [12.6000, 55.6000]},
                },
                {
                    "properties": {
                        "stationId": "06180",
                        "name": "Københavns Lufthavn",
                        "type": "Synop",
                        "parameterId": ["humidity", "wind_speed"],
                        "validFrom": "2019-01-15T13:34:48Z",
                        "validTo": None,
                    },
                    "geometry": {"coordinates": [12.6455, 55.614]},
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
        assert stations[0]["stationId"] == "06180"
        assert stations[0]["latitude"] == 55.614
        assert stations[0]["longitude"] == 12.6455
        assert stations[0]["parameterId"] == ["temp_dry", "humidity", "wind_speed"]

    async def test_get_stations_paginates_with_offset(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test station discovery paginates with offset until a partial page."""
        first_page_features = [
            {
                "properties": {
                    "stationId": f"{index:05d}",
                    "name": f"Station {index}",
                    "parameterId": ["temp_dry"],
                },
                "geometry": {"coordinates": [12.0, 55.0]},
            }
            for index in range(1000)
        ]
        second_page_features = [
            {
                "properties": {
                    "stationId": f"{index:05d}",
                    "name": f"Station {index}",
                    "parameterId": ["temp_dry"],
                },
                "geometry": {"coordinates": [12.1, 55.1]},
            }
            for index in range(1000, 1050)
        ]

        responses = [
            {"features": first_page_features},
            {"features": second_page_features},
        ]
        response_index = 0

        async def json_side_effect() -> dict[str, Any]:
            nonlocal response_index
            payload = responses[response_index]
            response_index += 1
            return payload

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json = AsyncMock(side_effect=json_side_effect)

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        api_client._session.get = MagicMock(return_value=mock_context)

        stations = await api_client.get_stations(active_only=True)

        assert len(stations) == 1050
        assert api_client._session.get.call_count == 2
        first_call_params = api_client._session.get.call_args_list[0].kwargs["params"]
        second_call_params = api_client._session.get.call_args_list[1].kwargs["params"]
        assert first_call_params["offset"] == 0
        assert second_call_params["offset"] == 1000

    async def test_get_stations_pagination_merges_duplicate_ids_across_pages(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test duplicate station ids spanning pages are still merged."""
        first_page = {
            "features": [
                {
                    "properties": {
                        "stationId": "06180",
                        "name": "Old Record",
                        "parameterId": ["temp_dry"],
                        "validFrom": "1983-06-16T00:00:00Z",
                        "validTo": "2019-01-15T13:34:48Z",
                    },
                    "geometry": {"coordinates": [12.6000, 55.6000]},
                },
                *[
                    {
                        "properties": {
                            "stationId": f"{index:05d}",
                            "name": f"Station {index}",
                            "parameterId": ["temp_dry"],
                            "validTo": None,
                        },
                        "geometry": {"coordinates": [12.0, 55.0]},
                    }
                    for index in range(999)
                ],
            ],
        }
        second_page = {
            "features": [
                {
                    "properties": {
                        "stationId": "06180",
                        "name": "Current Record",
                        "parameterId": ["humidity"],
                        "validFrom": "2019-01-15T13:34:48Z",
                        "validTo": None,
                    },
                    "geometry": {"coordinates": [12.6455, 55.614]},
                },
            ],
        }

        responses = [first_page, second_page]
        response_index = 0

        async def json_side_effect() -> dict[str, Any]:
            nonlocal response_index
            payload = responses[response_index]
            response_index += 1
            return payload

        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.raise_for_status = MagicMock()
        mock_response.json = AsyncMock(side_effect=json_side_effect)

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        api_client._session.get = MagicMock(return_value=mock_context)

        stations = await api_client.get_stations()

        station_06180 = next(station for station in stations if station["stationId"] == "06180")
        assert station_06180["name"] == "Current Record"
        assert station_06180["parameterId"] == ["temp_dry", "humidity"]

    # --- get_observations tests ---

    async def test_get_sea_observations_preserves_quality_metadata(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test sea observations include the newest values and QC metadata."""
        api_client._request = AsyncMock(
            return_value={
                "features": [
                    {
                        "properties": {
                            "parameterId": "sealev_dvr",
                            "value": 26.0,
                            "observed": "2026-07-24T15:40:00Z",
                            "created": "2026-07-24T15:41:44Z",
                            "qcStatus": "auto",
                        }
                    },
                    {
                        "properties": {
                            "parameterId": "sealev_dvr",
                            "value": 25.0,
                            "observed": "2026-07-24T15:30:00Z",
                            "qcStatus": "manual",
                        }
                    },
                    {
                        "properties": {
                            "parameterId": "tw",
                            "value": 18.2,
                            "observed": "2026-07-24T15:40:00Z",
                            "qcStatus": "auto",
                        }
                    },
                ]
            }
        )

        observations = await api_client.get_sea_observations("30017")

        assert observations == {
            "sealev_dvr": {
                "value": 26.0,
                "observed": "2026-07-24T15:40:00Z",
                "created": "2026-07-24T15:41:44Z",
                "qc_status": "auto",
            },
            "tw": {
                "value": 18.2,
                "observed": "2026-07-24T15:40:00Z",
                "qc_status": "auto",
            },
        }
        api_client._request.assert_awaited_once_with(
            f"{OCEANOBS_URL}/collections/observation/items",
            {
                "stationId": "30017",
                "limit": 100,
                "offset": 0,
                "sortorder": "observed,DESC",
            },
        )

    async def test_get_tidewater_forecast_returns_sorted_prediction_types(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test tide predictions are normalized and sorted by prediction time."""
        api_client._request = AsyncMock(
            return_value={
                "features": [
                    {
                        "properties": {
                            "predictionType": "maximum",
                            "predictionTime": "2026-07-25T09:47:00Z",
                            "created": "2026-03-23T09:30:10Z",
                            "value": 16.2,
                            "stationId": "29393",
                        }
                    },
                    {
                        "properties": {
                            "predictionType": "10minutes",
                            "predictionTime": "2026-07-25T09:40:00Z",
                            "created": "2026-03-23T10:18:26Z",
                            "value": 16.1,
                            "stationId": "29393",
                        }
                    },
                ]
            }
        )
        start = datetime(2026, 7, 25, 9, 30, tzinfo=UTC)
        end = datetime(2026, 7, 26, 9, 30, tzinfo=UTC)

        predictions = await api_client.get_tidewater_forecast("29393", start, end)

        assert [prediction["prediction_type"] for prediction in predictions] == [
            "10minutes",
            "maximum",
        ]
        assert predictions[0] == {
            "value": 16.1,
            "prediction_time": "2026-07-25T09:40:00Z",
            "prediction_type": "10minutes",
            "created": "2026-03-23T10:18:26Z",
            "station_id": "29393",
        }
        api_client._request.assert_awaited_once_with(
            f"{OCEANOBS_URL}/collections/tidewater/items",
            {
                "stationId": "29393",
                "datetime": "2026-07-25T09:30:00Z/2026-07-26T09:30:00Z",
                "limit": 500,
                "offset": 0,
            },
        )

    async def test_tidewater_forecast_skips_incomplete_predictions(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test incomplete tide predictions are ignored."""
        api_client._request = AsyncMock(
            return_value={
                "features": [
                    {"properties": {"predictionTime": "2026-07-25T09:40:00Z"}},
                ]
            }
        )
        start = datetime(2026, 7, 25, 9, 30)
        end = datetime(2026, 7, 26, 9, 30)

        predictions = await api_client.get_tidewater_forecast("29393", start, end)

        assert predictions == []
        assert api_client._request.await_args.args[1]["datetime"] == (
            "2026-07-25T09:30:00Z/2026-07-26T09:30:00Z"
        )

    @pytest.mark.parametrize(
        ("latitude", "longitude", "expected"),
        [
            (55.8, 11.9, "dkss_if"),
            (55.4, 9.8, "dkss_lb"),
            (56.8, 9.5, "dkss_lf"),
            (55.0, 8.5, "dkss_ws"),
            (55.33, 11.14, "dkss_idw"),
            (58.0, 10.0, "dkss_nsbs"),
        ],
    )
    def test_dkss_collection_selects_most_detailed_model(
        self,
        latitude: float,
        longitude: float,
        expected: str,
    ) -> None:
        """Test DKSS collection selection prefers nested high-resolution areas."""
        assert DMIApiClient._dkss_collection_for_position(latitude, longitude) == expected

    async def test_get_dkss_forecast_parses_returned_grid_cell(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test a nearby water cell is used when the gauge's closest cell is land."""
        api_client._request = AsyncMock(
            return_value={
                "domain": {
                    "axes": {
                        "t": {
                            "values": [
                                "2026-07-25T10:00:00Z",
                                "2026-07-25T11:00:00Z",
                            ]
                        },
                        "x": {"start": 11.1, "stop": 11.2, "num": 2},
                        "y": {"values": [55.3, 55.4]},
                    }
                },
                "ranges": {
                    "sea-mean-deviation": {
                        "values": [
                            None,
                            0.12,
                            0.2,
                            0.3,
                            None,
                            0.13,
                            0.21,
                            0.31,
                        ]
                    }
                },
            }
        )
        start = datetime(2026, 7, 25, 10, tzinfo=UTC)
        end = datetime(2026, 7, 30, 10, tzinfo=UTC)

        forecast = await api_client.get_dkss_forecast(55.31, 11.11, start, end)

        assert forecast == {
            "collection_id": "dkss_idw",
            "model_latitude": 55.3,
            "model_longitude": 11.2,
            "forecast": [
                {"datetime": "2026-07-25T10:00:00Z", "value": 12.0},
                {"datetime": "2026-07-25T11:00:00Z", "value": 13.0},
            ],
        }
        request_url, request_params = api_client._request.await_args.args
        assert request_url == f"{FORECAST_URL}/collections/dkss_idw/position"
        assert request_params["coords"] == "POINT(11.11 55.31)"
        assert "bbox" not in request_params
        assert request_params["parameter-name"] == "sea-mean-deviation"
        assert request_params["datetime"] == ("2026-07-25T10:00:00Z/2026-07-30T10:00:00Z")

    async def test_get_dkss_forecast_falls_back_to_broad_model(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test an all-land regional result falls back to dkss_nsbs."""
        empty_coverage = {
            "domain": {
                "axes": {
                    "t": {"values": ["2026-07-25T10:00:00Z"]},
                    "x": {"values": [11.1]},
                    "y": {"values": [55.3]},
                }
            },
            "ranges": {"sea-mean-deviation": {"values": [None]}},
        }
        wet_coverage = {
            "domain": {
                "axes": {
                    "t": {"values": ["2026-07-25T10:00:00Z"]},
                    "x": {"values": [11.1]},
                    "y": {"values": [55.3]},
                }
            },
            "ranges": {"sea-mean-deviation": {"values": [0.1]}},
        }
        api_client._request = AsyncMock(side_effect=[empty_coverage, wet_coverage])
        start = datetime(2026, 7, 25, 10, tzinfo=UTC)
        end = datetime(2026, 7, 30, 10, tzinfo=UTC)

        forecast = await api_client.get_dkss_forecast(55.31, 11.11, start, end)

        assert forecast is not None
        assert forecast["collection_id"] == "dkss_nsbs"
        assert [call.args[0] for call in api_client._request.await_args_list] == [
            f"{FORECAST_URL}/collections/dkss_idw/position",
            f"{FORECAST_URL}/collections/dkss_nsbs/position",
        ]

    def test_dkss_helpers_handle_sparse_axes_and_forecasts(self) -> None:
        """Test DKSS parsing handles missing axes and intermittent values."""
        assert DMIApiClient._axis_values({}) == []
        assert DMIApiClient._axis_values({"start": 11.1, "num": 1}) == [11.1]
        assert (
            DMIApiClient._parse_dkss_coverage(
                {},
                latitude=55.3,
                longitude=11.1,
                collection_id="dkss_idw",
            )
            is None
        )

        forecast = DMIApiClient._parse_dkss_coverage(
            {
                "domain": {
                    "axes": {
                        "t": {"values": ["2026-07-25T10:00:00Z", "2026-07-25T11:00:00Z"]},
                        "x": {"values": [11.1]},
                        "y": {"values": [55.3]},
                    }
                },
                "ranges": {"sea-mean-deviation": {"values": [0.1, None]}},
            },
            latitude=55.3,
            longitude=11.1,
            collection_id="dkss_idw",
        )

        assert forecast is not None
        assert forecast["forecast"] == [{"datetime": "2026-07-25T10:00:00Z", "value": 10.0}]

    async def test_get_dkss_forecast_outside_model_returns_none(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test positions outside regional models use one broad-model request."""
        api_client._request = AsyncMock(return_value={})
        start = datetime(2026, 7, 25, 10, tzinfo=UTC)
        end = datetime(2026, 7, 30, 10, tzinfo=UTC)

        forecast = await api_client.get_dkss_forecast(70.0, 35.0, start, end)

        assert forecast is None
        api_client._request.assert_awaited_once()
        assert api_client._request.await_args.args[0] == (
            f"{FORECAST_URL}/collections/dkss_nsbs/position"
        )

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

    async def test_get_observations_does_not_send_unsupported_sortorder(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test observations avoid unsupported DMI sortorder parameters."""
        mock_data = {
            "features": [
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

        await api_client.get_observations("06180")

        params = api_client._session.get.call_args.kwargs["params"]
        assert "sortorder" not in params
        assert params["offset"] == 0

    async def test_get_observations_keeps_newest_when_older_rows_arrive_first(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test merge logic keeps the newest temp_dry even if older rows appear first."""
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

    async def test_get_observations_does_not_paginate_full_pages(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test observation fetch stays bounded even when DMI returns a full page."""
        mock_data = {
            "features": [
                {
                    "properties": {
                        "parameterId": f"param_{index}",
                        "value": index,
                        "observed": "2024-01-15T12:00:00Z",
                    },
                }
                for index in range(100)
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

        assert len(observations) == 100
        assert api_client._session.get.call_count == 1

    async def test_get_observations_uses_no_key_opendata_endpoint(
        self,
        api_client: DMIApiClient,
        mock_observations_data: dict[str, Any],
    ) -> None:
        """Test observations use the no-key DMI Open Data endpoint."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_observations_data)
        mock_response.raise_for_status = MagicMock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        api_client._session.get = MagicMock(return_value=mock_context)

        await api_client.get_observations("06180")

        url = api_client._session.get.call_args.args[0]
        params = api_client._session.get.call_args.kwargs["params"]

        assert url == f"{METOBS_URL}/collections/observation/items"
        assert url.startswith(BASE_URL)
        assert "dmigw.govcloud.dk" not in url
        assert not (AUTH_PARAM_NAMES & set(params))

    async def test_get_stations_uses_no_key_opendata_endpoint(
        self,
        api_client: DMIApiClient,
        mock_stations_data: dict[str, Any],
    ) -> None:
        """Test station discovery uses the no-key DMI Open Data endpoint."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_stations_data)
        mock_response.raise_for_status = MagicMock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        api_client._session.get = MagicMock(return_value=mock_context)

        await api_client.get_stations()

        url = api_client._session.get.call_args.args[0]
        params = api_client._session.get.call_args.kwargs["params"]

        assert url == f"{METOBS_URL}/collections/station/items"
        assert url.startswith(BASE_URL)
        assert "dmigw.govcloud.dk" not in url
        assert not (AUTH_PARAM_NAMES & set(params))

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
        assert first_hour["cloud_cover"] == 50.0

    async def test_get_forecast_converts_cumulative_precipitation_to_hourly_amounts(
        self,
        api_client: DMIApiClient,
        mock_forecast_data: dict[str, Any],
    ) -> None:
        """Test cumulative DMI precipitation becomes per-hour forecast amounts."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_forecast_data)
        mock_response.raise_for_status = MagicMock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        api_client._session.get = MagicMock(return_value=mock_context)

        forecast = await api_client.get_forecast(55.6761, 12.5683)

        precipitation = [entry["precipitation"] for entry in forecast["hourly"]]
        assert precipitation == pytest.approx([0.0, 0.1, 0.1, 0])

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

    async def test_get_forecast_uses_no_key_opendata_endpoint(
        self,
        api_client: DMIApiClient,
        mock_forecast_data: dict[str, Any],
    ) -> None:
        """Test forecasts use the no-key DMI Open Data endpoint."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_forecast_data)
        mock_response.raise_for_status = MagicMock()

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        api_client._session.get = MagicMock(return_value=mock_context)

        await api_client.get_forecast(55.6761, 12.5683)

        url = api_client._session.get.call_args.args[0]
        params = api_client._session.get.call_args.kwargs["params"]

        assert url == f"{FORECAST_URL}/collections/harmonie_dini_sf/position"
        assert url.startswith(BASE_URL)
        assert "dmigw.govcloud.dk" not in url
        assert not (AUTH_PARAM_NAMES & set(params))

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
        url = api_client._session.get.call_args.args[0]
        params = api_client._session.get.call_args.kwargs["params"]

        assert url == f"{METOBS_URL}/collections/station/items"
        assert url.startswith(BASE_URL)
        assert "dmigw.govcloud.dk" not in url
        assert not (AUTH_PARAM_NAMES & set(params))

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
        mock_response.text = AsyncMock(return_value='{"message":"Server is busy"}')

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        api_client._session.get = MagicMock(return_value=mock_context)

        with pytest.raises(RateLimitExceeded, match="Server is busy"):
            await api_client.get_stations()

    async def test_http_error_status_includes_response_body(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test non-429 HTTP errors include status and body details."""
        mock_response = AsyncMock()
        mock_response.status = 503
        mock_response.text = AsyncMock(return_value="Service unavailable upstream")

        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_response
        api_client._session.get = MagicMock(return_value=mock_context)

        with pytest.raises(
            UpstreamError, match="HTTP 503 error from DMI API: Service unavailable upstream"
        ):
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

        with pytest.raises(RequestTimeout):
            await api_client.get_stations()

    async def test_cancelled_request_becomes_request_timeout(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test cancelled outbound requests surface as retryable request timeouts."""
        mock_context = AsyncMock()
        mock_context.__aenter__.side_effect = asyncio.CancelledError
        api_client._session.get = MagicMock(return_value=mock_context)

        with pytest.raises(RequestTimeout, match="Request cancelled"):
            await api_client.get_stations()

    async def test_unexpected_error(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test unexpected errors propagate instead of being wrapped."""
        mock_context = AsyncMock()
        mock_context.__aenter__.side_effect = ValueError("Unexpected error")
        api_client._session.get = MagicMock(return_value=mock_context)

        with pytest.raises(ValueError, match="Unexpected error"):
            await api_client.get_stations()

    async def test_request_rejects_auth_query_params(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test authenticated query params are rejected before any request is sent."""
        with pytest.raises(CannotConnect, match="Authenticated DMI query parameters"):
            await api_client._request(
                f"{METOBS_URL}/collections/station/items",
                {"limit": 1, "api-key": "secret"},
            )

        api_client._session.get.assert_not_called()

    async def test_client_response_error_other_status(
        self,
        api_client: DMIApiClient,
    ) -> None:
        """Test non-429 ClientResponseError."""
        mock_response = AsyncMock()
        mock_response.status = 200
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

        with pytest.raises(UpstreamError, match="HTTP 500 error from DMI API"):
            await api_client.get_stations()
