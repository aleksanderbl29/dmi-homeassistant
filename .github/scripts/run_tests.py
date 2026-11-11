"""Run pytest after initializing Home Assistant's HTTP client compatibility."""

import sys

import homeassistant  # noqa: F401
import pytest

if __name__ == "__main__":
    raise SystemExit(pytest.main(sys.argv[1:]))
