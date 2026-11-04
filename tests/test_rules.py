import re
from typing import Any

import pytest

from mythic_core import rules
from mythic_core.data import load_json
from mythic_core.rules import derived


def test_characteristic_modifier() -> None:
    assert rules.characteristic_modifier(25) == 2
    assert rules.characteristic_modifier(50) == 5
    assert rules.characteristic_modifier(9) == 0


@pytest.mark.parametrize(
    ("raw", "expected"), [("+3", 3), (2, 2), ("0", 0), (None, 0), ("x", 0), (True, 0)]
)
def test_mythic_value(raw: Any, expected: int) -> None:
    assert rules.mythic_value(raw) == expected


def test_max_wounds_matches_data_examples() -> None:
    doc = load_json("character_creation", "wounds_formula.json")["wounds_formula"]
    for example in doc["examples"]:
        expected = int(example["calculated_wounds"].rsplit("=", 1)[1])
        assert rules.max_wounds(example["toughness"], example["mythic_toughness"]) == expected


def test_wounds_constants_match_data_files() -> None:
    formula = load_json("character_creation", "wounds_formula.json")["wounds_formula"]["formula"]
    assert formula["base"] == derived.WOUNDS_BASE
    assert int(re.findall(r"\d+", formula["toughness_modifier"])[-1]) == (
        derived.WOUNDS_PER_TOUGHNESS_MODIFIER
    )
    assert int(re.findall(r"\d+", formula["mythic_toughness"])[-1]) == (
        derived.WOUNDS_PER_MYTHIC_TOUGHNESS
    )


def test_robust_adds_wounds() -> None:
    assert rules.max_wounds(50, 0, 1) == rules.max_wounds(50, 0) + derived.ROBUST_WOUNDS


def test_fatigue() -> None:
    assert rules.fatigue_coma_threshold(50) == 10
    assert rules.fatigue_penalty(3) == -15
    assert rules.fatigue_penalty(0) == 0


@pytest.mark.parametrize(
    ("agility", "mythic", "expected"), [(45, 0, 4), (55, "+3", 6), (40, 4, 6), (9, 1, 0)]
)
def test_initiative_bonus(agility: int, mythic: Any, expected: int) -> None:
    # Initiative = D10 + AGI modifier + half of Mythic AGI (Mythic 7.0, Combat chapter).
    assert rules.initiative_bonus(agility, mythic) == expected
