# Mythic Core

> **This repository has moved.** Since 2026-11-05 it lives in the private Mythic Suite monorepo,
> [phazeshift-pb/Mythic-Suite](https://github.com/phazeshift-pb/Mythic-Suite), in `packages/mythic-core/`,
> with its full history. This repository is archived (read-only); don't make changes here.

Shared rules data, types and pure rule functions for Mythic TTRPG tools: the
[character manager](https://github.com/phazeshift-pb/Mythic-TTRPG-Character-Gen) and
Mythic DM Tools. No Qt dependency, so every app and its tests can use it.

| Module | What's in it |
|--------|--------------|
| `mythic_core.characteristics` | `Characteristic` enum (STR … LDR), full names, `Characteristic.parse("Agility")` |
| `mythic_core.dice` | `DiceRoll` (`"4D10+12"` ↔ model, validates straight from JSON), rolling, Special Damage max-face count |
| `mythic_core.models` | Shared Pydantic models: `ArmorRating`, `EnergyShield`, `Weapon` (+ `FiringMode`, `RangeBand`, `Capacity`, `SpecialRule`), `EquipmentItem`, `Vehicle` (+ `Breakpoints`, `VehicleArmor`, `Movement`, `Crew`, `ArmamentVariant`, `WalkerStats`) |
| `mythic_core.catalog` | The catalogs: `weapons()`, `weapon(id)`, `find_weapons("plasma pistol", faction="Covenant")`, `match_weapons(text)`; `vehicles()`, `vehicle(id)`, `find_vehicles("scorpion", kind=VehicleKind.WALKER)` |
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

## Weapon catalog

`src/mythic_core/data/catalog/core_weapons.json` is generated from the rulebook text, not
hand-written. To rebuild it (e.g. after a rulebook update or an importer fix):

```powershell
uv run python tools/import_weapons.py "path\to\Mythic 7.0 CU1.txt"
```

The importer validates every record against `Weapon` and writes what it couldn't handle to
`tools/import_weapons_report.txt` (currently 14 weapons with two firing profiles in one table,
e.g. the Boltshot, plus a few sentences of rules text it left in the description).

Known limitations:

- The text export runs the **Name** and **Nickname** columns together, so `name` holds both
  ("MA5B Individual Combat Weapon System Assault Rifle"). Search still matches either.
- Weapons printed inside bestiary entries are not in the catalog; they belong to those entries.
- Conditional or prose rules (e.g. "+5 Base Damage per Half Action charged") stay in
  `description`; only plain Special Rules are structured.

## Vehicle catalog

`src/mythic_core/data/catalog/core_vehicles.json` and `light_and_sky_vehicles.json` are
generated the same way, by `tools/import_vehicles.py`:

```powershell
uv run python tools/import_vehicles.py "path\to\Mythic 7.0 CU1.txt" "path\to\Light and Sky.txt"
```

205 records (core: 142 vehicles, 22 walkers, 29 automated turrets and gun pods; Light and
Sky: 9 vehicles, 3 walkers), each validated against `Vehicle`. A record holds cost and Defeat
Experience, movement (MpT), dimensions, Size/Weapon points, crew and passengers, Breakpoints
per component, directional armor (or Head/Arms/Chest/Legs for walkers), energy shield,
walker characteristics and melee, special rules (checked against the book's Vehicle Special
Rules), mobility systems ("4 Wheel Vehicle" -> 4 wheels), named rules sections, and every
armament variant with its weapons (position tags `[O]`/`[G]`/`[C]`, count, linked, and the
matching catalog weapon when there is exactly one). `tools/import_vehicles_report.txt` lists
anything it couldn't read (currently nothing).

Known limitations:

- Variant descriptions (e.g. the Warthog GT's "250 MpT Top Speed, 18 Armor") stay as text in
  the variant's `notes`; the vehicle's base numbers aren't changed.
- About 50 armament weapon lines have no catalog weapon yet (Light and Sky's own vehicle
  weapons, and the weapons the weapon importer skips).
- Vehicle *weapons* printed in Light and Sky's "unique vehicle weapons" tables aren't
  imported yet.

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
