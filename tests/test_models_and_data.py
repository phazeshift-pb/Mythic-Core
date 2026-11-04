import json

import pytest
from pydantic import ValidationError

from mythic_core.data import data_root, iter_documents, load_json
from mythic_core.models import ArmorLocation, ArmorRating, EnergyShield


def test_armor_rating_by_location() -> None:
    armor = ArmorRating(head=17, arms=18, chest=19, legs=18)
    assert armor.at(ArmorLocation.CHEST) == 19


def test_armor_cannot_be_negative() -> None:
    with pytest.raises(ValidationError):
        ArmorRating(head=-1)


def test_energy_shield() -> None:
    shield = EnergyShield(integrity=125, delay=3, recharge=50)
    assert shield.model_dump() == {"integrity": 125, "delay": 3, "recharge": 50}


def test_data_folder_is_bundled() -> None:
    assert data_root().is_dir()
    assert len(iter_documents()) > 100


def test_every_rules_document_is_valid_json_with_an_object_root() -> None:
    for path in iter_documents():
        document = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(document, dict), path


def test_load_json() -> None:
    hit_locations = load_json("wounds_medical", "hit_locations.json")
    assert "hit_locations" in hit_locations
