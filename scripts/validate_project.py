"""Validate local packaging, JSON translations, and Python documentation contracts."""

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "natural_shutter"


def read_json(path: Path) -> dict:
    """Read one UTF-8 JSON object, rejecting duplicate keys and nonfinite constants."""

    def unique_object(pairs: list[tuple[str, object]]) -> dict:
        """Build an object while rejecting duplicate JSON field names."""
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate key {key} in {path}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        """Reject JSON constants that would produce nonfinite numeric values."""
        raise ValueError(f"Invalid JSON constant {value} in {path}")

    return json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=unique_object,
        parse_constant=reject_constant,
    )


def leaf_keys(data: dict, prefix: str = "") -> set[str]:
    """Return every translation leaf path and require nonempty string values."""
    result = set()
    for key, value in data.items():
        path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(leaf_keys(value, path))
        else:
            assert isinstance(value, str) and value.strip(), path
            result.add(path)
    return result


def validate() -> None:
    """Check the local contracts and report intentionally incomplete publication metadata."""
    directories = [
        path.name
        for path in (ROOT / "custom_components").iterdir()
        if path.is_dir() and path.name != "__pycache__"
    ]
    assert directories == ["natural_shutter"], directories
    manifest = read_json(INTEGRATION / "manifest.json")
    hacs = read_json(ROOT / "hacs.json")
    constants = ast.parse((INTEGRATION / "const.py").read_text(encoding="utf-8"))
    names = {
        node.targets[0].id: node.value.value
        for node in constants.body
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant)
    }
    assert manifest["domain"] == names["DOMAIN"] == INTEGRATION.name
    assert manifest["name"] == hacs["name"] == names["NAME"]
    assert manifest["config_flow"] is True
    assert manifest["dependencies"] == ["cover"]
    assert manifest["after_dependencies"] == ["logbook", "notify"]
    assert manifest["integration_type"] == "device"
    assert manifest["iot_class"] == "calculated"
    assert manifest["requirements"] == []
    assert isinstance(manifest["codeowners"], list)
    assert re.fullmatch(r"\d+\.\d+\.\d+", manifest["version"])
    assert f"## {manifest['version']}" in (ROOT / "CHANGELOG.md").read_text(
        encoding="utf-8"
    )
    assert hacs["render_readme"] is True
    assert hacs["homeassistant"] == names["MIN_HA_VERSION"]
    assert re.fullmatch(r"\d{4}\.\d+\.\d+", hacs["homeassistant"])
    for document in ("README.md", "README.de.md", "ARCHITECTURE.md"):
        content = (ROOT / document).read_text(encoding="utf-8")
        assert content.strip() and hacs["homeassistant"] in content

    strings = read_json(INTEGRATION / "strings.json")
    english = read_json(INTEGRATION / "translations" / "en.json")
    german = read_json(INTEGRATION / "translations" / "de.json")
    assert english == strings
    assert leaf_keys(german) == leaf_keys(english)
    for key in leaf_keys(english):
        en_value = english
        de_value = german
        for part in key.split("."):
            en_value, de_value = en_value[part], de_value[part]
        assert set(re.findall(r"\{([^{}]+)\}", en_value)) == set(
            re.findall(r"\{([^{}]+)\}", de_value)
        ), key
    assert german["entity"]["number"]["target_position"]["name"] == "Ziel-Position"
    assert german["entity"]["number"]["buffer"]["name"] == "Puffer"

    for directory in (INTEGRATION, ROOT / "tests", ROOT / "scripts"):
        for path in directory.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            assert ast.get_docstring(tree), f"Module docstring missing: {path}"
            for node in ast.walk(tree):
                if isinstance(
                    node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
                ):
                    assert ast.get_docstring(node), (
                        f"Docstring missing: {path}:{node.lineno}"
                    )
    print(
        "Local validation passed: packaging, JSON, translations, placeholders, and docstrings."
    )
    for field in ("documentation", "issue_tracker"):
        if "example.invalid" in manifest[field]:
            print(f"Publication pending: replace manifest {field} placeholder.")
    if not manifest["codeowners"]:
        print("Publication pending: set actual codeowners.")
    if not (ROOT / "LICENSE").read_text(encoding="utf-8").strip():
        print("Publication pending: choose and complete the license.")
    if not (INTEGRATION / "brand" / "icon.png").exists():
        print("Publication pending: provide brand imagery; see docs/PUBLISHING.md.")


if __name__ == "__main__":
    validate()
