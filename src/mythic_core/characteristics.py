"""The ten Mythic characteristics and helpers for naming them."""

from enum import StrEnum


class Characteristic(StrEnum):
    STR = "STR"
    TOU = "TOU"
    AGI = "AGI"
    WFR = "WFR"
    WFM = "WFM"
    INT = "INT"
    PER = "PER"
    CRG = "CRG"
    CHA = "CHA"
    LDR = "LDR"

    @property
    def full_name(self) -> str:
        return FULL_NAMES[self]

    @classmethod
    def parse(cls, text: str) -> Characteristic:
        """Accept a code (``"agi"``) or a full name (``"Agility"``), any case."""
        key = text.strip().casefold()
        for member in cls:
            if key in (member.value.casefold(), FULL_NAMES[member].casefold()):
                return member
        raise ValueError(f"Unknown characteristic: {text!r}")


FULL_NAMES: dict[Characteristic, str] = {
    Characteristic.STR: "Strength",
    Characteristic.TOU: "Toughness",
    Characteristic.AGI: "Agility",
    Characteristic.WFR: "Warfare Range",
    Characteristic.WFM: "Warfare Melee",
    Characteristic.INT: "Intellect",
    Characteristic.PER: "Perception",
    Characteristic.CRG: "Courage",
    Characteristic.CHA: "Charisma",
    Characteristic.LDR: "Leadership",
}

#: Characteristics that can have a Mythic score.
MYTHIC_CHARACTERISTICS: tuple[Characteristic, ...] = (
    Characteristic.STR,
    Characteristic.TOU,
    Characteristic.AGI,
)

#: A score for each characteristic, e.g. ``{Characteristic.AGI: 45, ...}``.
type CharacteristicScores = dict[Characteristic, int]
