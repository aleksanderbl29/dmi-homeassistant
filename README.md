# DMI Weather for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/release/aleksanderbl29/dmi-homeassistant.svg)](https://github.com/aleksanderbl29/dmi-homeassistant/releases)
[![License](https://img.shields.io/github/license/aleksanderbl29/dmi-homeassistant.svg)](LICENSE)

A Home Assistant custom integration for weather data from the Danish Meteorological Institute (DMI).

## Features

- **No API key required** - DMI's open data API is freely available
- Weather entity with current conditions
- Hourly forecast support
- Multiple sensor entities:
  - Temperature
  - Dew Point
  - Humidity
  - Atmospheric Pressure
  - Wind Speed & Gusts
  - Wind Direction
  - Precipitation
  - Visibility
  - Cloud Cover
  - Solar Radiation
- Support for all active DMI weather stations in Denmark, Greenland, and the Faroe Islands
- Danish and English translations

## Installation

### HACS (Recommended)

1. Open HACS in your Home Assistant instance
2. Click on "Integrations"
3. Click the three dots in the top right corner and select "Custom repositories"
4. Add `https://github.com/aleksanderbl29/dmi-homeassistant` as a custom repository with category "Integration"
5. Click "Install"
6. Restart Home Assistant

### Manual Installation

1. Download the latest release from the [releases page](https://github.com/aleksanderbl29/dmi-homeassistant/releases)
2. Extract the `custom_components/dmi` folder to your Home Assistant `custom_components` directory
3. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **+ Add Integration**
3. Search for "DMI Weather"
4. Select a weather station from the dropdown list
5. Optionally enable "Use Home Assistant coordinates for forecasts"

### Options

After setup, you can configure:
- **Update interval**: How often to fetch new data (10-60 minutes)
- **Include forecast**: Enable/disable hourly forecast data

## Entities

### Weather Entity

The main weather entity provides:
- Current condition (sunny, cloudy, rainy, etc.)
- Temperature
- Humidity
- Pressure
- Wind speed and direction
- Visibility
- Hourly forecast (if enabled)

### Sensors

Depending on what the selected station reports, you may get sensors for:

| Sensor | Unit | Description |
|--------|------|-------------|
| Temperature | °C | Current air temperature |
| Dew Point | °C | Dew point temperature |
| Humidity | % | Relative humidity |
| Pressure | hPa | Atmospheric pressure at sea level |
| Wind Speed | m/s | Current wind speed |
| Wind Gust | m/s | Maximum wind gust |
| Wind Direction | ° | Wind direction in degrees |
| Precipitation | mm | Precipitation in the last hour |
| Visibility | m | Horizontal visibility |
| Cloud Cover | % | Cloud coverage percentage |
| Solar Radiation | W/m² | Global solar radiation |

> **Note**: Not all stations report all parameters. The integration only creates sensors for parameters the selected station actually provides.

## API Information

This integration uses DMI's Open Data API at `opendataapi.dmi.dk`. The API is completely open and requires no authentication.

### Data Sources

- **Observations**: Real-time data from DMI weather stations
- **Forecasts**: HARMONIE-DINI model forecasts

### Rate Limiting

The API has rate limits. The default update interval of 10 minutes should be well within limits for normal use.

## Troubleshooting

### No sensors appearing

Some stations (like Pluvio rain gauges) only report specific parameters. Try selecting a different station with more sensors.

### Forecast not available

Forecast requires coordinates. Enable "Use Home Assistant coordinates for forecasts" or ensure the selected station has valid coordinates.

### Connection errors

Check your internet connection. The integration will automatically retry when connectivity is restored.

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This integration is not affiliated with or endorsed by DMI. Weather data is provided by DMI's open data initiative.

## Links

- [DMI Open Data](https://opendataapi.dmi.dk/)
- [Home Assistant](https://www.home-assistant.io/)
- [HACS](https://hacs.xyz/)
