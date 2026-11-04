"""The weapon catalog: every weapon from ``data/catalog/*weapons*.json``, by ID.

Built from the rulebook by ``tools/import_weapons.py``. Loaded once and cached.
"""

from functools import cache

from mythic_core.data import data_path, load_json
from mythic_core.models.weapons import Weapon


@cache
def weapons() -> dict[str, Weapon]:
    catalog: dict[str, Weapon] = {}
    for path in sorted(data_path("catalog").glob("*weapons*.json")):
        for record in load_json("catalog", path.name)["weapons"]:
            weapon = Weapon.model_validate(record)
            if weapon.id in catalog:
                raise ValueError(f"Duplicate weapon id {weapon.id!r} in {path.name}")
            catalog[weapon.id] = weapon
    return catalog


def weapon(weapon_id: str) -> Weapon:
    try:
        return weapons()[weapon_id]
    except KeyError:
        raise KeyError(f"No weapon with id {weapon_id!r}") from None


def find_weapons(query: str = "", *, faction: str | None = None) -> list[Weapon]:
    """Weapons whose name, nickname or type contains every word of ``query`` (any case)."""
    words = query.casefold().split()
    found = []
    for item in weapons().values():
        if faction is not None and item.faction.casefold() != faction.casefold():
            continue
        haystack = f"{item.name} {item.nickname} {item.weapon_type}".casefold()
        if all(word in haystack for word in words):
            found.append(item)
    return sorted(found, key=lambda w: w.name.casefold())
