"""Weapons, following the rulebook's weapon table layout (Mythic 7.0, 'How to Use Weapons').

Ranged:          Name, Nickname, Firing Type, Weight
                 Type, Damage Roll, Base Damage, Pierce, Range, Capacity, Reload, Ammo, Price
Explosive/Melee: Name, Nickname, Weight
                 Type, Damage Roll, Base Damage, Pierce, Range (Blast/Kill) or Reach, Price
Then a description holding Weapon Tags (``[TH]``), Special Rules and other rules text.
"""

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from mythic_core.dice import DiceRoll


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# ------------------------------------------------------------------ pieces ---

_RANGE = re.compile(r"^\s*(\d[\d,]*)\s*m\s*-\s*(\d[\d,]*)\s*m\s*$", re.IGNORECASE)


class RangeBand(_Frozen):
    """Optimal range in metres, e.g. ``60m-375m``."""

    min_m: int = Field(ge=0)
    max_m: int = Field(ge=0)

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            match = _RANGE.match(value)
            if match is None:
                raise ValueError(f"Not a range: {value!r}")
            return {
                "min_m": int(match[1].replace(",", "")),
                "max_m": int(match[2].replace(",", "")),
            }
        return value

    def __str__(self) -> str:
        return f"{self.min_m:,}m-{self.max_m:,}m"


_RULE = re.compile(r"^\s*(?P<name>[^()]+?)\s*(?:\((?P<value>[^()]*)\))?\s*$")


class SpecialRule(_Frozen):
    """A Special Rule such as ``Headshot``, ``Blast (7)`` or ``Flame (1D10)``."""

    name: str
    value: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            match = _RULE.match(value)
            if match is None or not match["name"].strip():
                raise ValueError(f"Not a special rule: {value!r}")
            return {"name": match["name"].strip(), "value": match["value"]}
        return value

    @property
    def number(self) -> int | None:
        """The value as a whole number, when it is one (``Blast (7)`` -> 7)."""
        if self.value is not None and self.value.strip().isdigit():
            return int(self.value)
        return None

    def __str__(self) -> str:
        return self.name if self.value is None else f"{self.name} ({self.value})"


class FiringMode(_Frozen):
    """A Firing Type with its rate, e.g. ``Auto (9)``; ``Charge (1)`` etc."""

    kind: str
    rate: int | None = None

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            rule = SpecialRule.model_validate(value)
            return {"kind": rule.name, "rate": rule.number}
        return value

    def __str__(self) -> str:
        return self.kind if self.rate is None else f"{self.kind} ({self.rate})"


class CapacityKind(StrEnum):
    MAGAZINE = "magazine"
    BATTERY = "battery"
    BELT = "belt"
    TUBE = "tube"
    TANK = "tank"
    LOADER = "loader"


class Capacity(_Frozen):
    kind: CapacityKind = CapacityKind.MAGAZINE
    size: int = Field(ge=0)


class StrengthBonus(StrEnum):
    """Melee weapons add the wielder's Strength Modifier to Base Damage and/or Pierce."""

    NONE = "none"
    HALF = "half"
    FULL = "full"


# ------------------------------------------------------------------ weapon ---

WIELDING_TAGS = {"DW": "Dual Wield", "OH": "One-Handed", "TH": "Two-Handed", "HW": "Heavy Weapon"}
DAMAGE_TYPE_TAGS = {
    "UD": "Universal Damage",
    "PD": "Piercing Damage",
    "SD": "Slashing Damage",
    "BD": "Bludgeoning Damage",
}


class Weapon(_Frozen):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    #: Formal name. Imported entries may still include the nickname (see README).
    name: str
    nickname: str = ""
    faction: str = ""
    weapon_type: str
    vehicle_weapon: bool = False
    firing_modes: list[FiringMode] = Field(default_factory=list)
    weight_kg: float | None = None

    #: Damage Roll + Base Damage, e.g. ``3D10+6``.
    damage: DiceRoll
    damage_strength_bonus: StrengthBonus = StrengthBonus.NONE
    #: Anything about the damage the numbers can't hold (e.g. a printed '4D10!').
    damage_note: str = ""
    pierce: int = Field(default=0, ge=0)
    pierce_strength_bonus: StrengthBonus = StrengthBonus.NONE

    range: RangeBand | None = None
    #: Melee reach as printed (``--`` means normal reach).
    reach: str | None = None
    capacity: Capacity | None = None
    reload: str | None = None
    ammunition: str | None = None
    price: int | None = None

    tags: list[str] = Field(default_factory=list)
    special_rules: list[SpecialRule] = Field(default_factory=list)
    description: str = ""
    source: str = ""
    page: int | None = None

    @property
    def is_melee(self) -> bool:
        return self.reach is not None

    @property
    def wielding(self) -> list[str]:
        return [t for t in self.tags if t in WIELDING_TAGS]

    def special_rule(self, name: str) -> SpecialRule | None:
        key = name.casefold()
        return next((r for r in self.special_rules if r.name.casefold() == key), None)

    @property
    def blast_radius(self) -> int | None:
        rule = self.special_rule("Blast")
        return rule.number if rule else None

    @property
    def kill_radius(self) -> int | None:
        rule = self.special_rule("Kill")
        return rule.number if rule else None


class EquipmentItem(_Frozen):
    """General equipment (medical kits, scopes, packs, ...): name, benefits, weight, cost."""

    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str
    category: str = ""
    benefits: str = ""
    weight_kg: float | None = None
    price: int | None = None
    source: str = ""
    page: int | None = None
