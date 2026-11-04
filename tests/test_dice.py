import random

import pytest
from pydantic import BaseModel, ValidationError

from mythic_core.dice import DiceRoll, RollResult


@pytest.mark.parametrize(
    ("text", "count", "sides", "bonus"),
    [
        ("4D10", 4, 10, 0),
        ("4d10+12", 4, 10, 12),
        ("3D5 + 2", 3, 5, 2),
        ("1D100", 1, 100, 0),
        ("D10", 1, 10, 0),
        ("2D10-3", 2, 10, -3),
        ("12", 0, 10, 12),
    ],
)
def test_parse(text: str, count: int, sides: int, bonus: int) -> None:
    roll = DiceRoll.parse(text)
    assert (roll.count, roll.sides, roll.bonus) == (count, sides, bonus)


@pytest.mark.parametrize("text", ["", "banana", "4D", "4D10+", "4x10"])
def test_parse_rejects_garbage(text: str) -> None:
    with pytest.raises(ValidationError):
        DiceRoll.parse(text)


def test_validates_inside_other_models_from_json() -> None:
    class Weapon(BaseModel):
        damage: DiceRoll

    weapon = Weapon.model_validate_json('{"damage": "4D10+12"}')
    assert weapon.damage == DiceRoll(count=4, sides=10, bonus=12)


@pytest.mark.parametrize("text", ["4D10+12", "2D5", "1D100", "12", "2D10-3"])
def test_str_round_trips(text: str) -> None:
    assert str(DiceRoll.parse(text)) == text


def test_min_max_and_plus() -> None:
    roll = DiceRoll.parse("3D10").plus(8)
    assert str(roll) == "3D10+8"
    assert (roll.minimum, roll.maximum) == (11, 38)


def test_roll_is_within_range_and_reproducible() -> None:
    roll = DiceRoll.parse("4D10+12")
    first = roll.roll(random.Random(42))
    second = roll.roll(random.Random(42))
    assert first == second
    assert len(first.dice) == 4
    assert roll.minimum <= first.total <= roll.maximum


def test_max_faces_counts_special_damage_triggers() -> None:
    result = RollResult(sides=10, dice=(10, 3, 10, 7), bonus=5)
    assert result.max_faces == 2
    assert result.total == 35
