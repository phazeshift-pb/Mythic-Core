# Mythic Core

Shared rules data, types and pure rule functions for Mythic TTRPG tools: the
[character manager](https://github.com/phazeshift-pb/Mythic-TTRPG-Character-Gen) and
Mythic DM Tools. No Qt dependency, so every app and its tests can use it.

| Module | What's in it |
|--------|--------------|
| `mythic_core.characteristics` | `Characteristic` enum (STR … LDR), full names, `Characteristic.parse("Agility")` |
| `mythic_core.dice` | `DiceRoll` (`"4D10+12"` ↔ model, validates straight from JSON), rolling, Special Damage max-face count |
| `mythic_core.models` | Shared Pydantic models: `ArmorRating`, `EnergyShield` |
| `mythic_core.rules` | Pure rule functions: characteristic modifier, max wounds, fatigue, initiative bonus |
| `mythic_core.data` | The rules JSON (`data_root()`, `load_json(...)`); layout in `docs/data_schema.md` |

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```powershell
uv sync
uv run pytest
uv run ruff check .
uv run mypy
```

## Using it from an app

During development, install it from the folder next to the app so edits show up immediately.
In the app's `pyproject.toml`:

```toml
[project]
dependencies = ["mythic-core"]

[tool.uv.sources]
mythic-core = { path = "../Mythic Core", editable = true }
```

Once it's on GitHub, the source can point there instead:

```toml
[tool.uv.sources]
mythic-core = { git = "https://github.com/phazeshift-pb/Mythic-Core", tag = "v0.1.0" }
```

PyInstaller apps must bundle the data files: in the `.spec`, add
`collect_data_files("mythic_core")` to `datas`.

## Character manager migration

The rules JSON and `derived_stats.py` were moved here from the character manager unchanged
(`derived` keeps the same function names and signatures). To switch it over:

- `DataLoader(data_root=mythic_core.data.data_root())` instead of the repo's `data/` folder
- `from mythic_core.rules import max_wounds, characteristic_modifier, ...` instead of
  `src.models.derived_stats`
- then delete its local `data/` copy so there is only one source of truth
