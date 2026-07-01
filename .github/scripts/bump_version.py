import json
import sys
from pathlib import Path


def update_manifest(version: str) -> None:
    manifest_path = Path("custom_components/dmi/manifest.json")
    manifest = json.loads(manifest_path.read_text())
    manifest["version"] = version
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")


def update_pyproject(version: str) -> None:
    pyproject_path = Path("pyproject.toml")
    lines = pyproject_path.read_text().splitlines()
    updated_lines: list[str] = []
    in_project_section = False
    version_updated = False

    for line in lines:
        stripped = line.strip()
        if stripped == "[project]":
            in_project_section = True
        elif stripped.startswith("[") and stripped.endswith("]"):
            in_project_section = False

        if in_project_section and stripped.startswith('version = "'):
            updated_lines.append(f'version = "{version}"')
            version_updated = True
            continue

        updated_lines.append(line)

    if not version_updated:
        raise RuntimeError("Could not find [project].version in pyproject.toml")

    pyproject_path.write_text("\n".join(updated_lines) + "\n")


def main() -> None:
    version = sys.argv[1]
    update_manifest(version)
    update_pyproject(version)
    print(f"Updated project files to version {version}")


if __name__ == "__main__":
    main()
