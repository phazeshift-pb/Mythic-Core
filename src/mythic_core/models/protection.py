"""Armor ratings and energy shields."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ArmorLocation(StrEnum):
    HEAD = "head"
    ARMS = "arms"
    CHEST = "chest"
    LEGS = "legs"


class ArmorRating(BaseModel):
    """Armor per body location (damage ignored before Pierce)."""

    model_config = ConfigDict(frozen=True)

    head: int = Field(default=0, ge=0)
    arms: int = Field(default=0, ge=0)
    chest: int = Field(default=0, ge=0)
    legs: int = Field(default=0, ge=0)

    def at(self, location: ArmorLocation) -> int:
        value: int = getattr(self, location.value)
        return value


class EnergyShield(BaseModel):
    """An energy shield: Shield Integrity, Delay (turns before recharging), Recharge Rate."""

    model_config = ConfigDict(frozen=True)

    integrity: int = Field(ge=0)
    delay: int = Field(default=0, ge=0)
    recharge: int = Field(default=0, ge=0)
