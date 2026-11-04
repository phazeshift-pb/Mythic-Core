"""Dice expressions (``4D10+12``, ``2D5``, ``1D100``) and rolling them."""

import random
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

_DICE_PATTERN = re.compile(
    r"^\s*(?:(?P<count>\d+)?\s*[dD]\s*(?P<sides>\d+))?\s*(?P<bonus>[+-]?\s*\d+)?\s*$"
)


class RollResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    sides: int
    dice: tuple[int, ...]
    bonus: int = 0

    @property
    def total(self) -> int:
        return sum(self.dice) + self.bonus

    @property
    def max_faces(self) -> int:
        """How many dice landed on their highest face (a 10 on a D10, a 5 on a D5).

        In Mythic, a damage die showing its highest face can cause Special Damage.
        """
        return sum(1 for value in self.dice if value == self.sides)


class DiceRoll(BaseModel):
    """``count`` dice with ``sides`` faces plus a flat ``bonus``.

    Validates from a string as well as a dict, so JSON can say ``"damage": "4D10+12"``.
    A plain number such as ``"12"`` is a flat value with no dice.
    """

    model_config = ConfigDict(frozen=True)

    count: int = Field(default=0, ge=0)
    sides: int = Field(default=10, ge=1)
    bonus: int = 0

    @model_validator(mode="before")
    @classmethod
    def _from_text(cls, value: Any) -> Any:
        if isinstance(value, str):
            return cls._parse_fields(value)
        if isinstance(value, int) and not isinstance(value, bool):
            return {"count": 0, "bonus": value}
        return value

    @staticmethod
    def _parse_fields(text: str) -> dict[str, int]:
        match = _DICE_PATTERN.match(text)
        if match is None or not text.strip():
            raise ValueError(f"Not a dice expression: {text!r}")
        fields: dict[str, int] = {}
        if match["sides"] is not None:
            fields["count"] = int(match["count"]) if match["count"] else 1
            fields["sides"] = int(match["sides"])
        if match["bonus"] is not None:
            fields["bonus"] = int(match["bonus"].replace(" ", ""))
        return fields

    @classmethod
    def parse(cls, text: str) -> DiceRoll:
        return cls.model_validate(text)

    @property
    def minimum(self) -> int:
        return self.count + self.bonus

    @property
    def maximum(self) -> int:
        return self.count * self.sides + self.bonus

    def plus(self, bonus: int) -> DiceRoll:
        return self.model_copy(update={"bonus": self.bonus + bonus})

    def roll(self, rng: random.Random | None = None) -> RollResult:
        rng = rng or random.Random()
        dice = tuple(rng.randint(1, self.sides) for _ in range(self.count))
        return RollResult(sides=self.sides, dice=dice, bonus=self.bonus)

    def __str__(self) -> str:
        dice = f"{self.count}D{self.sides}" if self.count else ""
        if not self.bonus:
            return dice or "0"
        if not dice:
            return str(self.bonus)
        return f"{dice}{self.bonus:+d}"
