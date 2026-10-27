"""Imports shared test helpers from the matching Home Assistant test package."""

try:
    from pytest_homeassistant.common import (
        MockConfigEntry as MockConfigEntry,
    )
    from pytest_homeassistant.common import (
        async_fire_time_changed as async_fire_time_changed,
    )
except ModuleNotFoundError as err:
    if err.name != "pytest_homeassistant":
        raise
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry as MockConfigEntry,
    )
    from pytest_homeassistant_custom_component.common import (
        async_fire_time_changed as async_fire_time_changed,
    )
