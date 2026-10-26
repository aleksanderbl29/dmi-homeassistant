"""Select Home Assistant compatibility targets and their test dependencies."""

import argparse
import json
import re
import tomllib
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[2]
DEV_URL = "https://github.com/home-assistant/core/archive/refs/heads/dev.zip"


def fetch_json(url: str) -> dict:
    with urlopen(url, timeout=60) as response:
        return json.load(response)


def python_version(requirement: str) -> str:
    """Use the latest patch of the minimum Python minor required by HA."""
    match = re.search(r">=\s*(3\.\d+)", requirement)
    if match is None:
        raise ValueError(f"Unsupported Python requirement: {requirement}")
    return match[1]


def stable_targets(releases: dict, minimum: str) -> list[str]:
    """Keep the exact support floor and sample two intervening release months."""
    floor = tuple(map(int, minimum.split(".")))
    monthly = {}
    for version, files in releases.items():
        if not re.fullmatch(r"\d{4}\.\d+\.\d+", version):
            continue
        parts = tuple(map(int, version.split(".")))
        if parts < floor or not any(not file["yanked"] for file in files):
            continue
        month = parts[:2]
        monthly[month] = max(parts, monthly.get(month, parts))
    if not monthly:
        raise ValueError(f"No stable Home Assistant releases at or above {minimum}")
    versions = [".".join(map(str, monthly[month])) for month in sorted(monthly)]
    indices = [len(versions) // 3, 2 * len(versions) // 3, len(versions) - 1]
    return list(dict.fromkeys([minimum, *(versions[index] for index in indices)]))


def matrix() -> dict:
    minimum = json.loads((ROOT / "hacs.json").read_text())["homeassistant"]
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    locked = next(p["version"] for p in lock["package"] if p["name"] == "homeassistant")
    releases = fetch_json("https://pypi.org/pypi/homeassistant/json")["releases"]
    rows = []
    targets = stable_targets(releases, minimum)
    for version in targets:
        release = fetch_json(f"https://pypi.org/pypi/homeassistant/{version}/json")
        info = release["info"]
        # Keep historical dependency graphs near their release date. The extra
        # week allows the separately published HA fixture package to catch up.
        uploaded = max(file["upload_time_iso_8601"] for file in release["urls"])
        cutoff = datetime.fromisoformat(uploaded) + timedelta(days=7)
        rows.append(
            {
                "version": version,
                "python": python_version(info["requires_python"]),
                "mode": "stable",
                "experimental": False,
                "cutoff": cutoff.isoformat() if version != targets[-1] else "",
            }
        )
    info = fetch_json(f"https://pypi.org/pypi/homeassistant/{locked}/json")["info"]
    rows.append(
        {
            "version": f"locked ({locked})",
            "python": python_version(info["requires_python"]),
            "mode": "locked",
            "experimental": False,
            "cutoff": "",
        }
    )
    with urlopen(
        "https://raw.githubusercontent.com/home-assistant/core/dev/pyproject.toml", timeout=60
    ) as response:
        development = tomllib.loads(response.read().decode())
    rows.append(
        {
            "version": "dev",
            "python": python_version(development["project"]["requires-python"]),
            "mode": "development",
            "experimental": True,
            "cutoff": "",
        }
    )
    return {"include": rows}


def requirements(version: str) -> str:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    dependencies = list(project["dependencies"])
    for dependency in project["optional-dependencies"]["test"]:
        name = re.split(r"[<>=!~\[; ]", dependency, maxsplit=1)[0]
        if name == "homeassistant":
            continue
        # Historical HA fixtures pin their own pytest stack. Resolve matching
        # tooling rather than applying today's test-tool minimums to old HA.
        dependencies.append(name if name.startswith("pytest") else dependency)
    dependencies.append(
        f"homeassistant @ {DEV_URL}" if version == "dev" else f"homeassistant=={version}"
    )
    return "\n".join(dependencies) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("matrix")
    subparsers.add_parser("overrides")
    requirements_parser = subparsers.add_parser("requirements")
    requirements_parser.add_argument("version")
    args = parser.parse_args()
    if args.command == "matrix":
        print(json.dumps(matrix()))
    elif args.command == "overrides":
        # The released fixture package pins stable HA. Only the experimental
        # job overrides that pin, so it can exercise upstream's actual dev code.
        print(f"homeassistant @ {DEV_URL}")
    else:
        print(requirements(args.version), end="")
