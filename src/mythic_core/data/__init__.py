"""The bundled rules JSON (moved from the character manager's ``data/`` folder).

The folder layout and document shapes are described in ``docs/data_schema.md``.
"""

import json
from importlib.resources import files
from pathlib import Path
from typing import Any


def data_root() -> Path:
    """Folder holding the rules JSON. Works from source, an installed wheel, or PyInstaller
    (DM Tools' spec collects these files)."""
    return Path(str(files("mythic_core") / "data"))


def data_path(*parts: str) -> Path:
    return data_root().joinpath(*parts)


def load_json(*parts: str) -> Any:
    """Load one rules document, e.g. ``load_json("wounds_medical", "hit_locations.json")``."""
    return json.loads(data_path(*parts).read_text(encoding="utf-8"))


def iter_documents() -> list[Path]:
    """Every rules JSON file, sorted by path."""
    return sorted(data_root().rglob("*.json"))
