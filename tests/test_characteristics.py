import pytest

from mythic_core.characteristics import MYTHIC_CHARACTERISTICS, Characteristic


def test_ten_characteristics_in_book_order() -> None:
    assert [c.value for c in Characteristic] == [
        "STR", "TOU", "AGI", "WFR", "WFM", "INT", "PER", "CRG", "CHA", "LDR",
    ]  # fmt: skip


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("AGI", Characteristic.AGI),
        ("agi", Characteristic.AGI),
        ("Agility", Characteristic.AGI),
        (" warfare range ", Characteristic.WFR),
    ],
)
def test_parse_accepts_codes_and_names(text: str, expected: Characteristic) -> None:
    assert Characteristic.parse(text) is expected


def test_parse_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        Characteristic.parse("Luck")


def test_full_name() -> None:
    assert Characteristic.WFM.full_name == "Warfare Melee"


def test_mythic_characteristics() -> None:
    assert MYTHIC_CHARACTERISTICS == (Characteristic.STR, Characteristic.TOU, Characteristic.AGI)
