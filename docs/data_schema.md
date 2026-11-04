# Mythic TTRPG Data Schema

This document is the source-of-truth contract for JSON data in `data/`. The repository contains rule documents, lookup tables, catalogs, character-creation profiles, and polymorphic records; they do not share one single record shape. Every file follows the common document rules below and one family contract.

## Common Rules

- Files are UTF-8 JSON documents, formatted with two-space indentation.
- The root is an object. Its top-level keys identify the document type.
- Property names use `snake_case`; game-facing names and characteristic codes preserve their source spelling.
- Unknown fields are allowed in rule records so new source material can be added without destroying data.
- `null` means the source explicitly has no value. An omitted field means the field is not applicable or is not supplied.
- A value may be a number, string, boolean, object, array, or `null` when the source uses mixed representations. Rules that need arithmetic should normalize numeric strings at runtime.
- Repeated records use objects with a required `name` where the source provides a name. Unnamed table rows may use the source's table fields directly.
- Optional source citations use `citation`, `reference_page`, or `source`.

## Shared Definitions

```text
CharacteristicCode = STR | TOU | AGI | WFR | WFM | INT | PER | CRG | CHA | LDR
CharacteristicMap = object keyed by CharacteristicCode with number|string|null values
Range = [number|string|null, number|string|null]
NamedRecord = { name: string, ...additional source fields }
Trait = { name: string, effect: string, ...optional fields }
Cost = number|string|object
RuleText = string|number|boolean|object|array|null
```

## Soldier Type

Files: `core/unsc_soldier_types/*.json`, `light_and_sky/character_creation/human_soldier_types/*.json`, and `light_and_sky/character_creation/guardian_classes_subclasses/*.json`.

```json
{
  "name": "string",
  "experience_cost": "number",
  "training": ["string"],
  "upbringing": "string or [string]",
  "base_characteristics": "CharacteristicMap",
  "mythic_characteristics": "CharacteristicMap",
  "advancements": "CharacteristicMap",
  "physical_attributes": {
    "height_cm": "Range",
    "weight_kg": "Range",
    "size": "string"
  },
  "traits": ["Trait"],
  "optional_rules": "object",
  "insurrectionist_rules": "object",
  "special_rules": "object",
  "subclasses": {
    "subclass_name": {
      "characteristic_modifiers": "CharacteristicMap",
      "...additional subclass fields": "RuleText"
    }
  },
  "equipment_sets": { "set_name": ["string"] }
}
```

`physical_attributes`, `insurrectionist_rules`, and `equipment_sets` may be empty objects when the source table does not define them. `special_rules` is intentionally open-ended because soldier types contain named rules with different shapes. `mythic_characteristics` and `advancements` may be empty or partial maps.

## Character Creation

- `upbringing`: `{ "upbringing": [NamedRecord] }`, with `bonuses`, `penalties`, and `environment_available` arrays where supplied.
- `environment`: `{ "environment": [NamedRecord] }`, with `bonuses` and `penalties` arrays.
- In `upbringing` and `environment` records, each `bonuses`/`penalties` entry is either a modifier string that always applies (`"+5 Charisma"`, `"+2 Wounds"`) or a choice group `{ "choose_one": [option, ...] }`, where the player picks one option. An option is a modifier string or an array of modifiers taken together (Laborer: `["+2 Strength", "+1 Toughness"]`). This mirrors the rulebook's "X or Y" wording.
- `lifestyle`: `{ "lifestyle": [{ "name": string, "outcomes": [{ "roll": string, "bonuses": [string], "penalties": [string] }] }] }`.
- `experience_tiers`: `{ "experience_tiers": { "tiers": [record], "luck": number, "credits": number, "notes": string } }`.
- `creation_points`: `{ "creation_points": object }`.
- `languages`: `{ "languages": { "rules": object, "notes": string } }`.
- `weapon_training`, `wounds_formula`, and `outliers`: named rule documents whose nested fields remain source-defined.
- `light_and_sky/character_creation/connections.json`: `{ "connections": { "rules": object, "light": [record], "darkness": [record], "specialized": [record], ... } }`.

## Core Catalogs and Lookup Tables

These documents use a named top-level collection whose value is an array of records, unless noted otherwise:

```text
characteristics, size_categories, low_characteristics, zero_characteristics,
skills, actions, action_subtypes, action_types, equipment_packs, rank_credit_multipliers,
weapon_training, weapon_tags, special_rules, hit_locations, medical_effects,
environmental_effects, wounds, damage, defense, training, terrain, weather, lighting,
ground_type, background_noise, movement_stealth_modifiers, passive_perception, radar,
visr, iff, smartlink, camouflage, active_camouflage, listening, cover, pierce,
scatter, initiative, speed_combat, time, turn_structure, attack_limits, attack_sequence
```

Catalog records may contain `name`, `description`, `effect`, `rules`, `modifiers`, `requirements`, `cost`, `citation`, and additional source fields. Lookup maps use the source's key names and may contain scalar values, arrays, or nested objects.

## Skills and Education

```json
{
  "skills": [{
    "name": "string",
    "difficulty": "string",
    "characteristics": ["string"],
    "type": ["string"],
    "cost": { "trained": "number", "+10": "number", "+20": "number" },
    "description": "string",
    "opposed_by": ["string"],
    "modifiers": [{ "value": "string", "example": "string" }],
    "subsections": [{ "name": "string", "text": "string" }]
  }],
  "difficulty_modifiers": [{ "difficulty": "string", "modifier": "number" }]
}
```

`opposed_by`, `modifiers`, and `subsections` may be omitted when the source has no entries.

```json
{
  "general_education": ["EducationRecord"],
  "street_smarts": ["EducationRecord"]
}
```

An `EducationRecord` contains `name`, `difficulty`, `characteristics_or_skills`, `cost`, and optional `description`.

## Combat, Movement, Actions, and Cyber Warfare

These families use open record documents because the source varies by rule:

- Action records: `name`, `length`, `subtype`, `description`, optional `effects`, and optional `citation`.
- Combat and movement rules: named top-level object containing tables, formulas, modifiers, thresholds, and narrative rule text.
- Melee and ranged combat: named arrays or maps of attacks, stances, ranges, firing modes, weapon tables, and action results.
- Cyber warfare: named arrays/maps of protocols, software, AI, firewalls, upgrades, encryption, hacking, and defenses. `effect` may be text or a structured object.
- Luck: named rule documents for spending, burning, and encounter/medical/narrative outcomes.
- Wounds and medical: named tables for locations, wounds, special damage, medical effects, and environmental effects.

All records in these families may use `citation`, `reference_page`, `requirements`, `modifiers`, `effects`, `outcomes`, `roll`, `threshold`, and `notes` when provided by the source.

## Equipment

- `combat/armor.json`: armor catalog/table document. It may contain armor tables, `armor_subtype`, `armor_variant`, `armor_perks`, and `exotic_armor_perks`.
- `light_and_sky/equipment/armor.json`: armor catalog with timeline, material tables, modules, perks, and variants.
- `light_and_sky/equipment/weapons.json`: grouped weapon arrays such as `scout_rifles`, `pulse_rifles`, and `sidearms`; weapon records contain source-defined combat fields including `rate_of_fire`, `damage`, `bonus_damage`, `pierce`, `range`, `magazine`, `reload`, `tags`, `ammo_type`, and `weapon_type`.
- Equipment records may use numeric strings for dice, ranges, Pierce, ammunition, and other values because these values can contain formulas or units.

## Light and Sky

- `light_aspect_rules.json`: `{ "light_aspects": { "rules": object } }`.
- `light_aspects.json`: `{ "light_aspects": { "arc": [record], "solar": [record], "void": [record], "terraform": [record], "resurrection": [record], "strand": [record], "stasis": [record] } }`; each record has `name`, `experience_cost`, and `description`.
- `light_ability_rules.json`: `{ "light_abilities": { "rules": object, "supers": { ..., "experience_cost_multiplier": number, "energy_cost_multiplier": number }, "grenade_supers": object, "energy": object, "double_jump": object } }`.
- `light_abilities_and_grenades.json`: `{ "abilities": [record], "grenades": [record] }`; abilities use `connection`, `category`, `experience_cost`, `light_cost`, `description`, and optional `super_description`; grenades also use `pierce` (number or null), `base_damage`, `damage_roll`, `range`, and `special_rules`, plus an optional `second_detonation` object with the same four stat fields for grenades that detonate twice with different stats.
- `light_weapon_abilities.json`: `{ "light_weapon_abilities": { "base_ability": object, "effects": { "connection": [record] } } }`; effect records use `description`, `additional_light_energy`, and optional `cost_modifier`.
- `character_creation/guardian_classes_subclasses/*.json`: soldier profiles with required `subclasses` and class-specific characteristic modifiers.

## Validation and Compatibility

Validation must be performed in two layers:

1. **Document validation:** valid UTF-8 JSON, object root, known top-level document family, and correct primitive/container types for that family.
2. **Game validation:** required rules, allowed characteristic codes, non-negative costs, valid ranges, unique names within a catalog, and references to existing skills, abilities, equipment, and Connections.

The schema is intentionally permissive for rule payloads and polymorphic `effects`; the validator must report unknown fields rather than delete them. Files are named in `snake_case` with standard spelling (for example `encumbrance.json`, `camouflage.json`, `multi_targeting.json`). Run `python tools/validate_all.py` to check both layers; it exits non-zero when any error is found.
