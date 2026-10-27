"""Imports shared test helpers from the matching Home Assistant test package."""

try:
    from pytest_homeassistant.common import MockConfigEntry as MockConfigEntry
except ModuleNotFoundError as err:
    if err.name != "pytest_homeassistant":
        raise
    from pytest_homeassistant_custom_component.common import MockConfigEntry as MockConfigEntry
