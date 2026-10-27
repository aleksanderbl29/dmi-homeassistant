"""Run pytest after initializing Home Assistant's HTTP client compatibility."""

import os
import sys

import pytest

if os.environ.get("HA_MODE") == "development":
    import homeassistant  # noqa: F401

if __name__ == "__main__":
    raise SystemExit(pytest.main(sys.argv[1:]))
