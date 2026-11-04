"""Derived-stat rules shared by every Mythic tool.

Moved from the character manager's ``src/models/derived_stats.py`` with the same names and
signatures, so the character manager can switch its imports over unchanged.
"""

from typing import Any

WOUNDS_BASE = 40
WOUNDS_PER_TOUGHNESS_MODIFIER = 2
WOUNDS_PER_MYTHIC_TOUGHNESS = 2
ROBUST_WOUNDS = 18  # per Robust outlier taken (max 2)

FATIGUE_PENALTY_PER_LEVEL = -5


def characteristic_modifier(value: int) -> int:
    """Characteristic modifier: the tens digit, floor(value / 10)."""
    return int(value) // 10


def mythic_value(raw: Any) -> int:
    """Mythic scores may be stored as ints or strings such as ``'+3'``; anything else is 0."""
    if isinstance(raw, str):
        try:
            return int(raw.strip())
        except ValueError:
            return 0
    if isinstance(raw, bool):
        return 0
    return int(raw) if isinstance(raw, (int, float)) else 0


def max_wounds(
    toughness: int,
    mythic_toughness: Any = 0,
    robust_count: int = 0,
    *,
    base: int = WOUNDS_BASE,
    toughness_multiplier: int = WOUNDS_PER_TOUGHNESS_MODIFIER,
    mythic_multiplier: int = WOUNDS_PER_MYTHIC_TOUGHNESS,
    robust_bonus: int = ROBUST_WOUNDS,
    flat_bonus: int = 0,
) -> int:
    """Wounds = 40 + (TOU modifier x 2) + (Mythic TOU x 2) + 18 per Robust + flat bonus.

    This is the character-creation formula. Bestiary NPCs list their Wounds per Bestiary
    Rank instead.
    """
    return (
        base
        + characteristic_modifier(toughness) * toughness_multiplier
        + mythic_value(mythic_toughness) * mythic_multiplier
        + max(0, int(robust_count)) * robust_bonus
        + int(flat_bonus)
    )


def fatigue_coma_threshold(toughness: int) -> int:
    """Fatigue above which a character falls into a coma: TOU modifier x 2."""
    return characteristic_modifier(toughness) * 2


def fatigue_penalty(levels: int) -> int:
    """Penalty to all Tests from Fatigue: -5 per level."""
    return max(0, int(levels)) * FATIGUE_PENALTY_PER_LEVEL


def initiative_bonus(agility: int, mythic_agility: Any = 0) -> int:
    """Added to the D10 Initiative roll: AGI modifier + half of Mythic AGI (rounded down)."""
    return characteristic_modifier(agility) + mythic_value(mythic_agility) // 2
