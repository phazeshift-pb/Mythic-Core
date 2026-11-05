"""The vehicle catalog built by tools/import_vehicles.py, checked against the rulebooks."""

import pytest

from mythic_core import catalog
from mythic_core.models import (
    ArmorFacing,
    Breakpoints,
    Component,
    Vehicle,
    VehicleKind,
    WeaponPosition,
)


def test_catalog_loads_both_books() -> None:
    vehicles = catalog.vehicles()
    assert len(vehicles) >= 200
    kinds = {v.kind for v in vehicles.values()}
    assert kinds == {VehicleKind.VEHICLE, VehicleKind.WALKER, VehicleKind.TURRET}
    assert {v.source for v in vehicles.values()} == {
        "Mythic 7.0 CU1",
        "Light and Sky Vehicle Update",
    }
    with pytest.raises(KeyError, match="no_such_vehicle"):
        catalog.vehicle("no_such_vehicle")


def test_mongoose_matches_the_book() -> None:
    mongoose = catalog.vehicle("m274_ultra_light_all_terrain_vehicle_mongoose")
    assert mongoose.page == 243 and mongoose.faction == "UNSC"
    assert (mongoose.cost, mongoose.defeat_experience) == (175, 35)
    assert mongoose.movement is not None
    assert (mongoose.movement.accelerate, mongoose.movement.top_speed) == (40, 160)
    assert (mongoose.size_points, mongoose.weapon_points) == (1, 4)
    assert mongoose.crew.operators == 1 and mongoose.crew.passengers == 1
    assert mongoose.breakpoints == Breakpoints(weapon=30, mobility=40, engine=50, hull=65)
    assert mongoose.breakpoints.of(Component.OPTICS) is None
    assert mongoose.armor is not None and mongoose.armor.at(ArmorFacing.FRONT) == 17
    assert mongoose.open_top and mongoose.has_rule("All-Terrain") and not mongoose.heavy_plating
    assert [(m.kind.value, m.count) for m in mongoose.mobility_systems] == [("wheel", 4)]
    names = [a.name for a in mongoose.armaments]
    assert names == ["Standard", "M274-M Light Gungoose", "M274-M Heavy Gungoose"]
    light = mongoose.armament("M274-M Light Gungoose")
    assert light is not None and light.cost == 315
    [smg] = light.weapons
    assert smg.positions == [WeaponPosition.OPERATOR] and smg.linked and smg.quantity == 2
    assert smg.weapon_id is not None and "m7" in smg.weapon_id


def test_scorpion_variants_and_rules() -> None:
    scorpion = catalog.vehicle("m808b_scorpion_main_battle_tank")
    assert scorpion.heavy_plating and scorpion.has_rule("Continuous Track")
    assert [(m.kind.value, m.count) for m in scorpion.mobility_systems] == [("tread", 4)]
    default = scorpion.armament()
    assert default is not None and default.name == "M808B Scorpion"
    cannon, gun = default.weapons
    assert cannon.positions == [WeaponPosition.OPERATOR] and cannon.weapon_id is not None
    assert catalog.weapon(cannon.weapon_id).vehicle_weapon
    assert gun.positions == [WeaponPosition.GUNNER]
    with pytest.raises(KeyError):
        scorpion.armament("Nope")


def test_walker() -> None:
    mantis = catalog.vehicle("hrunting_yggdrasil_mark_ix_mantis")
    assert mantis.kind is VehicleKind.WALKER and mantis.movement is None
    assert mantis.walker is not None
    assert (mantis.walker.strength, mantis.walker.mythic_strength) == (35, 12)
    assert mantis.walker.size_category == "Immense"
    assert mantis.walker_armor is not None and mantis.walker_armor.chest == 40
    assert mantis.shield is not None and mantis.shield.integrity == 150
    platform = catalog.vehicle("hrunting_yggdrasil_mark_viii_battle_platform")
    assert platform.walker_armor is not None and platform.walker_armor.arms == 0  # '--'


def test_turrets() -> None:
    talos = catalog.vehicle("m5_talos_weapon_station")
    assert talos.kind is VehicleKind.TURRET and talos.breakpoints.hull == 80
    assert talos.characteristics == {"WFR": 65, "INT": 30, "PER": 45}
    first = talos.armament()
    assert first is not None and (first.defeat_experience, first.cost) == (50, 240)
    assert talos.experience_payout() == 50
    assert talos.experience_payout("Two Linked M66 Light Railgun") == 90
    artillery = catalog.vehicle("z_8250_heavy_artillery")
    assert artillery.shield is not None and artillery.heavy_plating


def test_light_and_sky() -> None:
    sparrow = catalog.vehicle("guardian_sparrow")
    assert sparrow.faction == "Guardian" and sparrow.has_rule("Boost")
    assert "Boost (5)" in sparrow.special_rules
    assert any(
        v.faction == "Fallen" and v.kind is VehicleKind.WALKER for v in catalog.vehicles().values()
    )


def test_experience_payout_fallback() -> None:
    base = catalog.vehicle("m274_ultra_light_all_terrain_vehicle_mongoose")
    assert base.experience_payout() == 35
    unpriced = base.model_copy(update={"defeat_experience": None, "cost": 15_000})
    assert unpriced.experience_payout("Standard") == 35  # Standard costs 175 -> 175 / 5
    no_variants = unpriced.model_copy(update={"armaments": []})
    assert no_variants.experience_payout() == 2000  # capped


def test_find_vehicles() -> None:
    scorpions = catalog.find_vehicles("scorpion")
    assert len(scorpions) >= 4 and all("Scorpion" in v.name for v in scorpions)
    walkers = catalog.find_vehicles(kind=VehicleKind.WALKER, faction="covenant")
    assert walkers and all(v.faction == "Covenant" for v in walkers)


def test_every_vehicle_round_trips() -> None:
    for item in catalog.vehicles().values():
        assert Vehicle.model_validate_json(item.model_dump_json()) == item
        assert item.breakpoints.hull >= 0
