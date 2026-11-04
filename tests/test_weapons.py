import pytest
from pydantic import ValidationError

from mythic_core import catalog
from mythic_core.dice import DiceRoll
from mythic_core.models.weapons import (
    Capacity,
    CapacityKind,
    FiringMode,
    RangeBand,
    SpecialRule,
    StrengthBonus,
    Weapon,
)

# ----------------------------------------------------------------- pieces ---


@pytest.mark.parametrize(
    ("text", "low", "high"), [("60m-375m", 60, 375), ("40m-1,550m", 40, 1550), ("5m - 40m", 5, 40)]
)
def test_range_band(text: str, low: int, high: int) -> None:
    band = RangeBand.model_validate(text)
    assert (band.min_m, band.max_m) == (low, high)


def test_range_band_rejects_garbage() -> None:
    with pytest.raises(ValidationError):
        RangeBand.model_validate("Blast (7)")


@pytest.mark.parametrize(
    ("text", "name", "value", "number"),
    [
        ("Headshot", "Headshot", None, None),
        ("Blast (7)", "Blast", "7", 7),
        ("Flame (1D10)", "Flame", "1D10", None),
        ("Dice minimum (6)", "Dice minimum", "6", 6),
    ],
)
def test_special_rule(text: str, name: str, value: str | None, number: int | None) -> None:
    rule = SpecialRule.model_validate(text)
    assert (rule.name, rule.value, rule.number) == (name, value, number)
    assert str(rule) == text


def test_firing_mode() -> None:
    assert FiringMode.model_validate("Auto (9)") == FiringMode(kind="Auto", rate=9)
    assert FiringMode.model_validate("Charge (X)").rate is None


def make_weapon(**changes: object) -> Weapon:
    record: dict[str, object] = {
        "id": "test_rifle",
        "name": "Test Rifle",
        "weapon_type": "Rifle",
        "damage": "3D10+6",
        "pierce": 12,
        "range": "60m-375m",
        "capacity": {"kind": "magazine", "size": 32},
        "special_rules": ["Headshot", "Blast (4)", "Kill (2)"],
        "tags": ["UD", "TH"],
    }
    record.update(changes)
    return Weapon.model_validate(record)


def test_weapon_from_book_strings() -> None:
    rifle = make_weapon()
    assert rifle.damage == DiceRoll(count=3, sides=10, bonus=6)
    assert rifle.capacity == Capacity(kind=CapacityKind.MAGAZINE, size=32)
    assert (rifle.blast_radius, rifle.kill_radius) == (4, 2)
    assert rifle.special_rule("headshot") is not None
    assert rifle.wielding == ["TH"]
    assert not rifle.is_melee


def test_weapon_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        make_weapon(magazine=32)


# ---------------------------------------------------------------- catalog ---


def test_catalog_loads_the_rulebook_weapons() -> None:
    weapons = catalog.weapons()
    assert len(weapons) >= 400
    assert {w.faction for w in weapons.values()} == {"UNSC", "Covenant", "Banished", "Forerunner"}


def test_ma5b_matches_the_book() -> None:
    # Mythic 7.0 CU1, p.120
    ma5b = catalog.weapon("ma5b_individual_combat_weapon_system_assault_rifle")
    assert [str(m) for m in ma5b.firing_modes] == ["Semi-Auto (3)", "Auto (9)", "Burst (3)"]
    assert ma5b.weight_kg == 4.2
    assert str(ma5b.damage) == "3D10+6"
    assert ma5b.pierce == 12
    assert ma5b.range == RangeBand(min_m=60, max_m=375)
    assert ma5b.capacity == Capacity(kind=CapacityKind.MAGAZINE, size=60)
    assert ma5b.reload == "6 Half Actions"
    assert ma5b.ammunition == "7.62x51mm"
    assert ma5b.price == 52
    assert ma5b.tags == ["I", "UD", "TH"]


def test_grenade_area_rules() -> None:
    napalm = catalog.weapon("napalm_grenade_flame_grenade")
    assert (napalm.blast_radius, napalm.kill_radius) == (7, 1)
    assert napalm.special_rule("Flame") == SpecialRule(name="Flame", value="1D10")
    assert napalm.range is None


def test_melee_strength_bonuses() -> None:
    knife = catalog.weapon("jiralhanae_combat_knife")
    assert knife.is_melee
    assert knife.damage_strength_bonus is StrengthBonus.FULL
    assert knife.pierce_strength_bonus is StrengthBonus.HALF


def test_battery_weapon() -> None:
    pistol = catalog.weapon("eos_mak_plasma_pistol_type_25_directed_energy_pistol")
    assert pistol.capacity == Capacity(kind=CapacityKind.BATTERY, size=100)
    assert pistol.special_rule("Cauterize") is not None


def test_find_weapons() -> None:
    found = catalog.find_weapons("ma5 assault rifle")
    assert "ma5b_individual_combat_weapon_system_assault_rifle" in {w.id for w in found}
    covenant = catalog.find_weapons("plasma pistol", faction="covenant")
    assert covenant
    assert all(w.faction == "Covenant" for w in covenant)


def test_unknown_weapon_id() -> None:
    with pytest.raises(KeyError):
        catalog.weapon("bfg_9000")


def test_melee_printed_under_a_range_column() -> None:
    # The M1 Combat Knife's table says RANGE but holds its melee reach ('--').
    knife = catalog.weapon("m1_combat_knife_combat_knife")
    assert knife.is_melee
    assert knife.range is None
    assert knife.special_rules == []


def test_catalog_ids_are_unique_and_valid() -> None:
    weapons = catalog.weapons()
    assert all(weapon_id == w.id for weapon_id, w in weapons.items())
