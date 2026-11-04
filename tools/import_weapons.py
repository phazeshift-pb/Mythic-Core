"""Build the weapon catalog from the Mythic 7.0 rulebook text.

    uv run python tools/import_weapons.py "path/to/Mythic 7.0 CU1.txt"

Reads the plain-text export of the rulebook, finds every weapon table that follows the
book's 'How to Use Weapons' layout, and writes
``src/mythic_core/data/catalog/core_weapons.json``. Entries it can't parse are listed in
``tools/import_weapons_report.txt`` instead of being guessed at.

Known limitation: the text export runs the Name and Nickname columns together, so ``name``
holds both (e.g. "MA5B Individual Combat Weapon System Assault Rifle").
"""

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "src" / "mythic_core" / "data" / "catalog" / "core_weapons.json"
REPORT = ROOT / "tools" / "import_weapons_report.txt"
SOURCE = "Mythic 7.0 CU1"

HEADER_PREFIX = "TYPE DAMAGE ROLL BASE DAMAGE PIERCE "
CAPACITY_WORDS = {"MAGAZINE", "BATTERY", "BELT", "TUBE", "TANK", "LOADER"}
FIRING_KINDS = (
    "Semi-Auto",
    "Auto",
    "Burst",
    "Pump",
    "Sustained",
    "Pump Action",
    "Charge",
    "Drawback",
    "Flintlock",
    "Single Shot",
    "Bolt",
    "Bolt-Action",
    "Lever",
    "Lever-Action",
)

DICE = re.compile(r"(?<![\w\[])(?:(\d+)\s*[dD]\s*(10|5)!?|0|--)(?![\w\]])")
WEIGHT = re.compile(r"\s*Weight\s*\(([\d.]+)\s*KG\)\s*$", re.IGNORECASE)
VEHICLE = re.compile(r"\s*Vehicle Weapon\s*$", re.IGNORECASE)
FIRING = re.compile(
    r"(?:" + "|".join(re.escape(k) for k in sorted(FIRING_KINDS, key=len, reverse=True)) + r")"
    r"\s*\(\s*(?:\d+|X)\s*\)"
)
FIRING_TAIL = re.compile(
    r"^(?:" + FIRING.pattern + r")(?:\s*(?:,|with|and|or)?\s*(?:" + FIRING.pattern + r"))*\s*$"
)
RANGE = re.compile(r"(\d[\d,]*)\s*m\s*-\s*(\d[\d,]*)\s*m")
RELOAD = re.compile(
    r"^(\d+\s+(?:Half|Full)\s+Actions?|Single[ -]Loading|Autoloader\s*\(\d+\)|\d+\s+Rounds?|"
    r"\d+\s+Turns?|\d+\s+Minutes?)\s+(.*)$",
    re.IGNORECASE,
)
STRENGTH = re.compile(r"\+\s*(Full|Half)\s+Strength\s+Modifier", re.IGNORECASE)
TAG = re.compile(r"\[([A-Z]{1,3})\]")
ARMORY = re.compile(r"^([A-Z]+) ARMORY$")
FACTIONS = {
    "UNSC": "UNSC",
    "COVENANT": "Covenant",
    "BANISHED": "Banished",
    "FORERUNNER": "Forerunner",
    "VEHICLE": "Vehicle",
}


RULE_ALIASES = {
    "blast": "Blast",
    "kill": "Kill",
    "recharge": "Recharge",
    "tranq": "Tranquilize",
    "mortar": "Mortar",
    "smoke grenade": "Smoke",
}


def known_rule_names() -> dict[str, str]:
    """casefolded name -> canonical name, from the bundled special rules document."""
    path = ROOT / "src" / "mythic_core" / "data" / "weapon_and_armor_special_rules.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    names = {
        record["name"].casefold(): record["name"]
        for group in ("weapon_special_rules", "explosive_and_area_of_effect_rules")
        for record in document[group]
    }
    return {**names, **RULE_ALIASES}


@dataclass
class Problem:
    line: int
    name: str
    reason: str


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.casefold()).strip("_")[:60] or "weapon"


def _leading_int(text: str) -> int:
    """'+6' -> 6, '5+(X)' -> 5, '--' -> 0."""
    match = re.match(r"^\s*([+-]?)\s*(\d+)", text)
    if match is None:
        return 0
    return int(match[2]) * (-1 if match[1] == "-" else 1)


def split_top_level(text: str) -> list[str]:
    """Split on commas that are not inside parentheses."""
    parts, depth, current = [], 0, ""
    for char in text:
        depth += char == "("
        depth -= char == ")"
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    parts.append(current)
    return [p.strip() for p in parts if p.strip()]


def parse_name_line(line: str) -> tuple[str, list[str], float | None, bool]:
    text = line.strip()
    weight = None
    vehicle = False
    if match := WEIGHT.search(text):
        weight = float(match[1])
        text = text[: match.start()]
    if match := VEHICLE.search(text):
        vehicle = True
        text = text[: match.start()]
    modes: list[str] = []
    for start in (m.start() for m in FIRING.finditer(text)):
        if FIRING_TAIL.match(text[start:]):
            modes = [m.group(0) for m in FIRING.finditer(text[start:])]
            text = text[:start]
            break
    return text.strip(" ,"), [re.sub(r"\s+", " ", m) for m in modes], weight, vehicle


RULE_PART = re.compile(
    r"^([A-Z][A-Za-z'\u2019-]*(?: [A-Za-z'\u2019-]+){0,2})(?: \(([^()]*)\))?(?: [a-z].*)?$"
)


def parse_rules_text(text: str) -> list[str]:
    """Special Rules from sentences like 'Recharge (1), Kinetic, Kill (1) Special Rule.'

    Each part must look like a rule name (1-3 words, optional '(value)'); a trailing
    lower-case qualifier ('Recharge (1) after 10 Attacks') is dropped. Sentences with any
    other part - usually conditional rules text - are left to the description.
    """
    rules: list[str] = []
    for index, sentence in enumerate(re.split(r"(?<=\.)\s+", text)):
        sentence = sentence.strip().rstrip(".")
        # The sentence right after the tags may be a bare rule list: 'Flame (1D10), Kill (1).'
        bare_list = index == 1 and "(" in sentence
        if not re.search(r"Special Rules?$", sentence) and not bare_list:
            continue
        body = re.sub(r"\s*Special Rules?$", "", sentence)
        parts = [p for chunk in split_top_level(body) for p in re.split(r"\s+and\s+", chunk)]
        matches = [RULE_PART.match(p.strip()) for p in parts]
        if all(matches):
            rules += [m[1] + (f" ({m[2]})" if m[2] is not None else "") for m in matches if m]
    return rules


def parse_stats(header: str, stats: str) -> dict[str, Any]:
    """Parse the row under a TYPE header. Raises ValueError when the row doesn't fit."""
    columns = header[len(HEADER_PREFIX) :].split()
    dice = DICE.search(stats)
    if dice is None:
        raise ValueError("no damage dice")
    weapon_type = stats[: dice.start()]
    result: dict[str, Any] = {
        "weapon_type": TAG.sub("", weapon_type).strip(" \u2013-"),
        "type_tags": TAG.findall(weapon_type),
    }
    rest = stats[dice.end() :].strip()

    # Base Damage: '+6', '--', '5+(X)' or '+7 +Full Strength Modifier'
    number = r"(?:[+-]?\s*\d+(?:\s*\+\s*\(X\))?|--)"
    strength = r"(\+\s*(?:Full|Half)\s+Strength\s+Modifier)?"
    match = re.match(rf"^({number})\s*{strength}\s*", rest)
    if match is None:
        raise ValueError("no base damage")
    base = _leading_int(match[1])
    if match[2]:
        result["damage_strength_bonus"] = STRENGTH.search(match[2])[1].lower()  # type: ignore[index]
    if dice[1]:
        result["damage"] = f"{dice[1]}D{dice[2]}{base:+d}" if base else f"{dice[1]}D{dice[2]}"
        if "!" in dice.group(0):
            result["damage_note"] = f"Damage printed as {dice.group(0)}"
    else:
        result["damage"] = str(base)
    if "(X)" in match[1]:
        result["damage_note"] = f"Base Damage printed as {match[1].strip()}"
    rest = rest[match.end() :]

    # Pierce: '12', '+3 +Half Strength Modifier', '5+(X)' or '--'
    match = re.match(rf"^({number})\s*{strength}\s*", rest)
    if match is None:
        raise ValueError("no pierce")
    result["pierce"] = max(0, _leading_int(match[1]))
    if match[2]:
        result["pierce_strength_bonus"] = STRENGTH.search(match[2])[1].lower()  # type: ignore[index]
    rest = rest[match.end() :]

    if columns == ["REACH", "PRICE"]:
        match = re.match(r"^(.*?)\s*(\d+|--)$", rest)
        if match is None:
            raise ValueError("no reach/price")
        result["reach"] = match[1].strip() or "--"
        result["price"] = None if match[2] == "--" else int(match[2])
        return result

    if columns == ["RANGE", "PRICE"]:  # explosives: 'Blast (7), Kill (1) 11'
        match = re.match(r"^(.*?)\s*(\d+|--)$", rest)
        if match is None:
            raise ValueError("no range/price")
        area = match[1].strip()
        if r := RANGE.fullmatch(area):
            result["range"] = r.group(0)
        elif re.fullmatch(r"--|[+-]?\d+", area):
            # Melee weapons printed under a RANGE column: the value is their reach.
            result["reach"] = area
        else:
            result["area_rules"] = split_top_level(area)
        result["price"] = None if match[2] == "--" else int(match[2])
        return result

    if len(columns) == 5 and columns[0] == "RANGE" and columns[1] in CAPACITY_WORDS:
        match = re.match(r"^(\d[\d,]*\s*m\s*-\s*\d[\d,]*\s*m)\s+(\d+)\s+(.*)$", rest)
        if match is None:
            raise ValueError("no range/capacity")
        result["range"] = match[1]
        result["capacity"] = {"kind": columns[1].lower(), "size": int(match[2])}
        reload = RELOAD.match(match[3])
        if reload is None:
            raise ValueError(f"unrecognised reload in {match[3]!r}")
        result["reload"] = re.sub(r"\s+", " ", reload[1])
        ammo_price = re.match(r"^(.*?)\s*(\d+|--)$", reload[2])
        if ammo_price is None:
            raise ValueError("no ammunition/price")
        result["ammunition"] = ammo_price[1].strip() or None
        result["price"] = None if ammo_price[2] == "--" else int(ammo_price[2])
        return result

    raise ValueError(f"unsupported column layout: {' '.join(columns)}")


def import_weapons(text: str) -> tuple[list[dict[str, Any]], list[Problem]]:
    lines = text.splitlines()
    headers = [i for i, line in enumerate(lines) if line.startswith(HEADER_PREFIX)]
    header_set = set(headers)

    faction_at: list[tuple[int, str]] = []
    page_at: list[tuple[int, int]] = []
    for i, line in enumerate(lines):
        if match := ARMORY.match(line.strip()):
            faction_at.append((i, FACTIONS.get(match[1], match[1].title())))
        if line.strip().isdigit() and (i == 0 or not lines[i - 1].strip()):
            page_at.append((i, int(line.strip())))

    def latest(table: list[tuple[int, Any]], index: int) -> Any:
        found = None
        for at, value in table:
            if at > index:
                break
            found = value
        return found

    weapons: list[dict[str, Any]] = []
    problems: list[Problem] = []
    known_rules = known_rule_names()
    seen_ids: dict[str, int] = {}
    for h in headers:
        name_line, stats = lines[h - 1], lines[h + 1] if h + 1 < len(lines) else ""
        name, modes, weight, vehicle = parse_name_line(name_line)
        name = TAG.sub("", name).strip()
        faction = latest(faction_at, h)
        if faction is None or faction == "Vehicle":
            # Before the armories is the tutorial example; after the Vehicle Armory come
            # bestiary-specific weapons, which belong with their bestiary entries.
            continue
        description_start = h + 2
        try:
            parsed = parse_stats(lines[h], stats)
        except ValueError as error:
            # The stats row sometimes wraps onto a second line.
            try:
                parsed = parse_stats(lines[h], f"{stats} {lines[h + 2]}")
                description_start = h + 3
            except ValueError, IndexError:
                problems.append(Problem(h + 1, name, str(error)))
                continue
        tags_from_type = parsed.pop("type_tags", [])

        description_lines: list[str] = []
        for j in range(description_start, len(lines)):
            line = lines[j].strip()
            if not line or (j + 1) in header_set or line.isdigit() or line.isupper():
                break
            description_lines.append(line)
        description = " ".join(description_lines)
        tags = list(dict.fromkeys([*tags_from_type, *TAG.findall(description)]))

        rules = []
        for rule in parse_rules_text(description) + parsed.pop("area_rules", []):
            rule_name, _, value = rule.partition(" (")
            canonical = known_rules.get(rule_name.casefold())
            if canonical is None:
                problems.append(Problem(h + 1, name, f"unrecognised rule kept as text: {rule!r}"))
                continue
            rules.append(f"{canonical} ({value}" if value else canonical)
        rules = list(dict.fromkeys(rules))

        weapon_id = slug(name)
        if weapon_id in seen_ids:
            seen_ids[weapon_id] += 1
            weapon_id = f"{weapon_id}_{seen_ids[weapon_id]}"
        else:
            seen_ids[weapon_id] = 1

        weapons.append(
            {
                "id": weapon_id,
                "name": name,
                "faction": faction,
                **({"vehicle_weapon": True} if vehicle else {}),
                "firing_modes": modes,
                "weight_kg": weight,
                **parsed,
                "tags": tags,
                "special_rules": rules,
                "description": description,
                "source": SOURCE,
                "page": latest(page_at, h),
            }
        )
    return weapons, problems


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    text = Path(argv[1]).read_text(encoding="utf-8")
    weapons, problems = import_weapons(text)

    # Validate every record against the real model before writing anything.
    sys.path.insert(0, str(ROOT / "src"))
    from mythic_core.models.weapons import Weapon

    valid = []
    for record in weapons:
        try:
            Weapon.model_validate(record)
            valid.append(record)
        except ValueError as error:
            problems.append(Problem(0, record["name"], f"invalid: {error}"))

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    document = {"weapons": valid, "source": SOURCE}
    OUTPUT.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", "utf-8")
    skipped = sum(1 for p in problems if not p.reason.startswith("unrecognised rule"))
    report = [f"{len(valid)} weapons imported, {skipped} skipped", ""]
    report += [f"line {p.line}: {p.name!r}: {p.reason}" for p in problems]
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(report[0])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
