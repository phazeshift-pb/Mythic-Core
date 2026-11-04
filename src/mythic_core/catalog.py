"""The weapon catalog: every weapon from ``data/catalog/*weapons*.json``, by ID.

Built from the rulebook by ``tools/import_weapons.py``. Loaded once and cached.
"""

import re
from functools import cache
from typing import NamedTuple

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


# ----------------------------------------------------------- loadout matching ---

_NUMBER_WORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "twelve": 12,
}  # fmt: skip
_QUANTITY = re.compile(r"^(?:(\d+)\s*x?|x\s*(\d+)|([a-z]+))\s+(.+)$", re.IGNORECASE)
#: Words that describe a weapon but rarely appear in its printed name.
_GENERIC = {"series", "variant", "pattern", "type", "model", "pistol", "rifle", "carbine"}


class WeaponMatch(NamedTuple):
    """An equipment line ('Two M9 Dual-Purpose Grenades') read against the weapon catalog."""

    text: str
    quantity: int
    #: Catalog weapons that fit, best first. Empty for non-weapon gear.
    candidates: list[Weapon]
    #: True for 'MA5 series' style lines, where the GM picks the exact model.
    is_series: bool

    @property
    def weapon(self) -> Weapon | None:
        """The weapon, when exactly one fits."""
        return self.candidates[0] if len(self.candidates) == 1 else None


def parse_quantity(text: str) -> tuple[int, str]:
    """Split a leading count off a line: ``'Two Flashbangs'`` -> ``(2, 'Flashbangs')``."""
    match = _QUANTITY.match(text.strip())
    if match:
        digits, x_digits, word = match.group(1), match.group(2), match.group(3)
        rest = match.group(4)
        if digits or x_digits:
            return int(digits or x_digits), rest
        if word and word.casefold() in _NUMBER_WORDS:
            return _NUMBER_WORDS[word.casefold()], rest
    return 1, text.strip()


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.casefold().replace("\u2019", ""))
    return [
        w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") and w != "series" else w
        for w in words
    ]


def match_weapons(text: str) -> WeaponMatch:
    """Find the catalog weapons an equipment line refers to.

    Every word of the line must appear in a weapon's name, nickname or type. For a 'series'
    line (``'MA5 series Assault Rifle'``) the model designation also matches longer ones
    (``MA5B``, ``MA5C``). If nothing fits, the generic words (carbine, variant, ...) are
    dropped and only the designations (words with digits) are matched.
    """
    quantity, name = parse_quantity(text)
    words = _tokens(name)
    is_series = "series" in words
    wanted = [w for w in words if w != "series"]

    def fits(weapon_tokens: list[str], needed: list[str]) -> bool:
        for word in needed:
            if word in weapon_tokens:
                continue
            designation = is_series and any(c.isdigit() for c in word)
            if designation and any(
                t.startswith(word) and len(t) - len(word) <= 2 for t in weapon_tokens
            ):
                continue
            return False
        return True

    def search(needed: list[str]) -> list[Weapon]:
        if not needed:
            return []
        found = [
            w for w in weapons().values()
            if fits(_tokens(f"{w.name} {w.nickname} {w.weapon_type}"), needed)
        ]  # fmt: skip
        # Fewest extra words first = the closest name.
        return sorted(found, key=lambda w: (len(_tokens(w.name)), w.name.casefold()))

    candidates = search(wanted)
    if not candidates:
        designations = [w for w in wanted if any(c.isdigit() for c in w)]
        if designations and len(designations) < len(wanted):
            candidates = search(designations)
    # A bare generic word ('Hard Case', 'Rifle') is not a weapon reference.
    if candidates and all(w in _GENERIC for w in wanted):
        candidates = []
    return WeaponMatch(text.strip(), quantity, candidates, is_series)
