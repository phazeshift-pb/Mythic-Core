"""Build the vehicle catalog from the rulebook text.

Reads the plain-text exports of Mythic 7.0 CU1 and (optionally) Light and Sky, finds every
vehicle, walker and automated turret / gun pod, and writes
``src/mythic_core/data/catalog/{core,light_and_sky}_vehicles.json``. Every record is
validated as a :class:`~mythic_core.models.vehicles.Vehicle`; anything the importer can't
read is listed in ``tools/import_vehicles_report.txt`` instead of being guessed.

Three layouts:

* Vehicles: name, COST/DEFEAT EXPERIENCE, MOBILITY, PHYSICAL ATTRIBUTES + CUSTOMIZATION
  (Size/Weapon points), CREW AND COMPLEMENT, BREAKPOINTS, directional ARMOR, INFORMATION
  (special rules, mobility systems, rules sections) and the armament variants.
* Walkers: COST EXPERIENCE, CHARACTERISTICS (STR/AGI + Mythic), JUMP/LEAP, MELEE and
  HEAD/ARMS/CHEST/LEGS armor instead of directional armor.
* Turrets and gun pods (in each faction's armory): DIMENSIONS, HULL INTEGRITY, optional
  ENERGY SHIELD / ARMOR / CHARACTERISTICS, and a variant table.

Usage (from the repo root)::

    uv run python tools/import_vehicles.py <core.txt> [<light_and_sky.txt>]
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from mythic_core.catalog import match_weapons, parse_quantity
from mythic_core.models.vehicles import Vehicle

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "src" / "mythic_core" / "data" / "catalog"
REPORT = Path(__file__).with_name("import_vehicles_report.txt")

PAGE = re.compile(r"^\d{1,3}$")
NUMBER = r"[\d,]+(?:\.\d+)?"

#: Vehicle special rules (Vehicle Special Rules table, core p. 238) plus Light and Sky's.
KNOWN_RULES = {
    "all-terrain", "anti-gravitational", "autoloader", "boost", "continuous track",
    "enclosed-top", "flight", "heavy plating", "neural interface", "open-top",
    "slipspace travel", "slipspace drive",
}  # fmt: skip
NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "twelve": 12,
}  # fmt: skip
RULE_ALIASES = {
    "open top": "Open-Top",
    "antigravity": "Anti-Gravitational",
    "anti-gravity": "Anti-Gravitational",
    "fllight": "Flight",
    "slipspace": "Slipspace Travel",
    "slipspace drive": "Slipspace Travel",
}
_COUNT = r"(\d+|one|two|three|four|five|six|seven|eight|ten|twelve)"
_PART = r"(wheel|tread|leg|jet|propeller|thruster)"
MOBILITY_COUNT = re.compile(rf"\b{_COUNT}\s+{_PART}s?\b", re.IGNORECASE)
MOBILITY_PART = re.compile(
    rf"{_COUNT}\s+(?:{_PART}|arm)s?(?:\s+vehicle|\s+propulsion system)?", re.IGNORECASE
)
MOBILITY_SENTENCE = re.compile(
    rf"{MOBILITY_PART.pattern}(?:\s*,\s*{MOBILITY_PART.pattern})*", re.IGNORECASE
)


def canonical_rule(text: str) -> str | None:
    """'Boost (5)' -> 'Boost (5)', 'Open Top' -> 'Open-Top'; ``None`` if unknown."""
    m = re.fullmatch(r"(.+?)(\s*\(\w+\))?", text.strip())
    if not m:
        return None
    base, value = m.group(1).strip(), (m.group(2) or "").strip()
    key = base.lower()
    if key in RULE_ALIASES:
        name = RULE_ALIASES[key]
    elif key in KNOWN_RULES:
        name = "-".join(w[:1].upper() + w[1:] for w in base.split("-"))
        name = " ".join(w[:1].upper() + w[1:] for w in name.split())
    else:
        return None
    return f"{name} {value}" if value else name


MOBILITY_WORDS = {
    "wheel": "wheel", "tread": "tread", "leg": "leg", "jet": "jet",
    "propeller": "propeller", "thruster": "thruster",
}  # fmt: skip


@dataclass(frozen=True)
class Book:
    key: str
    source: str
    #: Where vehicle blocks (vehicles + walkers) are found: (start line text, end pattern).
    start: str
    end: re.Pattern[str]
    #: Headers that set the faction/category of the vehicles after them.
    category_pattern: re.Pattern[str]


CORE = Book(
    key="core",
    source="Mythic 7.0 CU1",
    start="VEHICLE ARMORY",
    end=re.compile(r"^GAME MASTER TOOLS$"),
    category_pattern=re.compile(
        r"^(UNSC|HUMAN CIVILIAN|COVENANT|BANISHED|FORERUNNER) ?"
        r"(GROUND|WALKER|AERIAL|FLYING)? ?VEHICLES$"
    ),
)
LIGHT_AND_SKY = Book(
    key="light_and_sky",
    source="Light and Sky Vehicle Update",
    start="VEHICLES",
    end=re.compile(r"^ENEMY FACTION BESTIARY$"),
    # No category headers; the faction comes from the vehicle's name.
    category_pattern=re.compile(r"^(\x00)$"),
)

FACTIONS = {"UNSC": "UNSC", "HUMAN CIVILIAN": "Human", "COVENANT": "Covenant",
            "BANISHED": "Banished", "FORERUNNER": "Forerunner"}  # fmt: skip
LAS_FACTIONS = {"GUARDIAN": "Guardian", "FALLEN": "Fallen", "CABAL": "Cabal",
                "HIVE": "Hive", "VEX": "Vex", "TAKEN": "Taken", "SCORN": "Scorn"}  # fmt: skip


@dataclass
class Problem:
    book: str
    line: int
    name: str
    message: str

    def __str__(self) -> str:
        return f"{self.book} line {self.line}: {self.name!r}: {self.message}"


@dataclass
class Block:
    name: str
    line: int  # 1-based line of the name
    page: int | None
    faction: str
    category: str
    lines: list[tuple[int, str]] = field(default_factory=list)


# ------------------------------------------------------------------- helpers ---


def slug(text: str) -> str:
    text = re.sub("[\u2018\u2019']", "", text)  # typographic and plain apostrophes
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def num(text: str) -> float:
    return float(text.replace(",", ""))


def int_or_none(text: str) -> int | None:
    return None if text in ("--", "-", "N/A") else int(num(text))


def count_word(text: str) -> int:
    text = text.lower()
    return NUMBER_WORDS.get(text) or int(text)


def is_heading(line: str) -> bool:
    """An all-caps section heading ('ORBITAL DEPLOYMENT')."""
    letters = re.sub(r"[^A-Za-z]", "", line)
    return bool(letters) and letters.isupper() and len(letters) >= 4 and not line.startswith("[")


def title_case(text: str) -> str:
    def word(w: str) -> str:
        if any(c.isdigit() for c in w) or w in ("UNSC", "ONI", "AI", "ADS", "VTOL"):
            return w
        return re.sub(
            "(^|[-\u2019'/(])([a-z])", lambda m: m.group(1) + m.group(2).upper(), w.lower()
        )

    return " ".join(word(w) for w in text.split())


def page_at(text: list[str], k: int) -> int | None:
    for j in range(k, 0, -1):
        if PAGE.match(text[j]) and text[j - 1] == "":
            return int(text[j])
    return None


# ------------------------------------------------------------ block finding ---


def vehicle_blocks(text: list[str], book: Book, problems: list[Problem]) -> list[Block]:
    """Vehicle and walker blocks: a name line, then 'COST DEFEAT EXPERIENCE'/'COST EXPERIENCE'."""
    try:
        start = text.index(book.start)
    except ValueError:
        return []
    end = next((i for i in range(start, len(text)) if book.end.match(text[i])), len(text))
    heads = [
        i - 1 for i in range(start, end) if text[i] in ("COST DEFEAT EXPERIENCE", "COST EXPERIENCE")
    ]
    blocks = []
    faction, category = "", ""
    scan = start
    for n, head in enumerate(heads):
        for k in range(scan, head):
            if m := book.category_pattern.match(text[k]):
                faction = FACTIONS.get(m.group(1), m.group(1).title())
                category = title_case(text[k])
        scan = head
        name = text[head]
        block_faction = faction
        if book is LIGHT_AND_SKY:
            first = name.split()[0].upper()
            block_faction = LAS_FACTIONS.get(first, "")
        stop = heads[n + 1] if n + 1 < len(heads) else end
        lines = []
        for k in range(head + 1, stop):
            line = text[k]
            if not line or (PAGE.match(line) and text[k - 1] == ""):
                continue
            if book.category_pattern.match(line) or "UNIQUE VEHICLE WEAPONS" in line:
                break
            lines.append((k + 1, line))
        blocks.append(Block(name, head + 1, page_at(text, head), block_faction, category, lines))
    del problems
    return blocks


TURRET_SECTIONS = {"DIMENSIONS", "HULL", "ARMOR", "CHARACTERISTICS", "ENERGY SHIELD", "MOVEMENT"}
ARMORY = re.compile(r"^(UNSC|COVENANT|BANISHED|FORERUNNER) ARMORY$")


def turret_blocks(text: list[str], book: Book) -> list[Block]:
    """Automated turrets and gun pods: a name line followed by 'DIMENSIONS'."""
    if book is not CORE:
        return []
    vehicles_at = text.index(CORE.start)
    blocks = []
    faction = ""
    heads = [
        i - 1
        for i in range(1, vehicles_at)
        if text[i] == "DIMENSIONS" and "HULL INTEGRITY" in text[i + 1 : i + 8]
    ]
    scan = 0
    for n, head in enumerate(heads):
        for k in range(scan, head):
            if m := ARMORY.match(text[k]):
                faction = FACTIONS[m.group(1)]
        scan = head
        stop = heads[n + 1] if n + 1 < len(heads) else head + 40
        lines = []
        for k in range(head + 1, stop):
            line = text[k]
            if PAGE.match(line) and text[k - 1] == "":
                # A turret only continues onto the next page with one of its own tables.
                following = next((t for t in text[k + 1 : k + 3] if t), "")
                if following not in TURRET_SECTIONS and not following.endswith(" COST"):
                    break
                continue
            if not line:
                continue
            if ARMORY.match(line) or line in ("AUTOMATED TURRETS", "PILOTED GUN PODS", "TURRETS"):
                break
            if line.startswith("TYPE DAMAGE ROLL") or re.search(r"Weight \(", line):
                break  # the next weapon table
            lines.append((k + 1, line))
        category = "Piloted Gun Pods" if "GUN POD" in text[head] else "Automated Turrets"
        blocks.append(Block(text[head], head + 1, page_at(text, head), faction, category, lines))
    return blocks


# ------------------------------------------------------------------ parsing ---


class Parser:
    def __init__(self, block: Block, book: Book, problems: list[Problem]) -> None:
        self.b = block
        self.book = book
        self.problems = problems
        self.lines = block.lines
        self.i = 0
        self.record: dict[str, Any] = {}

    def problem(self, message: str, line: int | None = None) -> None:
        self.problems.append(Problem(self.book.key, line or self.b.line, self.b.name, message))

    def peek(self, offset: int = 0) -> str:
        k = self.i + offset
        return self.lines[k][1] if k < len(self.lines) else ""

    def lineno(self) -> int:
        return self.lines[self.i][0] if self.i < len(self.lines) else self.b.line

    def expect(self, header: str) -> bool:
        if self.peek() == header:
            self.i += 1
            return True
        return False

    def values(self) -> list[str]:
        line = self.peek()
        self.i += 1
        return line.split()

    # -- shared pieces
    def cost_row(self) -> None:
        m = re.match(rf"^\+?({NUMBER}|--|N/A) cR\s+\+?({NUMBER}|--|N/A) Exp$", self.peek())
        if m:
            self.record["cost"] = int_or_none(m.group(1))
            self.record["defeat_experience"] = int_or_none(m.group(2))
            self.i += 1
        else:
            self.problem(f"cost row not understood: {self.peek()!r}", self.lineno())

    def mobility(self) -> None:
        self.i += 1  # ACCELERATE BRAKE TOP SPEED MANEUVER
        m = re.match(
            rf"^({NUMBER}) MpT ({NUMBER}) MpT ({NUMBER}) MpT"
            rf"(?: ?\(({NUMBER}) ?K[Mm]/[Hh]\))? ({NUMBER})$",
            self.peek(),
        )
        if not m:
            self.problem(f"mobility row not understood: {self.peek()!r}", self.lineno())
            self.i += 1
            return
        self.record["movement"] = {
            "accelerate": int(num(m.group(1))),
            "brake": int(num(m.group(2))),
            "top_speed": int(num(m.group(3))),
            **({"top_speed_kmh": int(num(m.group(4)))} if m.group(4) else {}),
            "maneuver": int(num(m.group(5))),
        }
        self.i += 1

    def dimensions(self, with_points: bool) -> None:
        line = self.peek()
        self.i += 1
        # Units are sometimes missing ('12.0 6.8 M') and Tonne/Tonnes both appear.
        pattern = rf"^({NUMBER}) ?M? ({NUMBER}) ?M? ({NUMBER}) ?M? ({NUMBER}) ?(KG|Tonnes?)" + (
            r"\s+(\d+|--)\s+(\d+|--)$" if with_points else r"$"
        )
        m = re.match(pattern, line, re.IGNORECASE)
        if not m:
            self.problem(f"dimensions row not understood: {line!r}", self.lineno() - 1)
            return
        weight = num(m.group(4)) * (1000 if m.group(5).lower().startswith("tonne") else 1)
        self.record["dimensions"] = {
            "length_m": num(m.group(1)),
            "width_m": num(m.group(2)),
            "height_m": num(m.group(3)),
            "weight_kg": weight,
        }
        if with_points:
            self.record["size_points"] = int_or_none(m.group(6))
            self.record["weapon_points"] = int_or_none(m.group(7))

    def crew(self) -> None:
        self.i += 1  # CREW COMPLEMENT
        texts = []
        while (
            self.peek()
            and self.peek() not in ("BREAKPOINTS",)
            and not self.peek().startswith("WEP ")
        ):
            texts.append(self.peek())
            self.i += 1
        joined = " ".join(texts)
        crew: dict[str, Any] = {"text": joined}
        for amount, role in re.findall(r"(\d+) (Operators?|Gunners?|Pilots?)", joined):
            key = "gunners" if role.startswith("Gunner") else "operators"
            crew[key] = crew.get(key, 0) + int(amount)
        if m := re.search(r"(\d+) Passengers?", joined):
            crew["passengers"] = int(m.group(1))
        self.record["crew"] = crew

    def breakpoints(self) -> None:
        self.expect("BREAKPOINTS")
        if not self.expect("WEP MOB ENG OP HULL"):
            self.problem("no breakpoints table", self.lineno())
            return
        values = self.values()
        if len(values) != 5:
            self.problem(f"breakpoints row not understood: {values}", self.lineno() - 1)
            return
        keys = ("weapon", "mobility", "engine", "optics", "hull")
        parsed = dict(zip(keys, (int_or_none(v) for v in values), strict=True))
        if parsed["hull"] is None:
            parsed["hull"] = 0
        self.record["breakpoints"] = parsed

    def directional_armor(self) -> None:
        if not self.expect("FRONT BACK SIDE TOP BOTTOM"):
            self.problem(f"armor table not understood: {self.peek()!r}", self.lineno())
            return
        values = self.values()
        keys = ("front", "back", "side", "top", "bottom")
        if len(values) != 5:
            self.problem(f"armor row not understood: {values}", self.lineno() - 1)
            return
        self.record["armor"] = {
            k: v
            for k, v in zip(keys, (int_or_none(x) for x in values), strict=True)
            if v is not None
        }

    def shield(self) -> None:
        self.i += 1  # SHIELD (RATING|INTEGRITY) (RECHARGE )?DELAY RECHARGE RATE
        m = re.match(rf"^({NUMBER})\s+({NUMBER})(?:\s*\*?\([^)]*\)\*?)?\s+({NUMBER})$", self.peek())
        if not m:
            self.problem(f"shield row not understood: {self.peek()!r}", self.lineno())
            return
        self.record["shield"] = {
            "integrity": int(num(m.group(1))),
            "delay": int(num(m.group(2))),
            "recharge": int(num(m.group(3))),
        }
        self.i += 1

    # -- vehicles and walkers
    def parse_vehicle(self) -> dict[str, Any]:
        self.record.update(name=self.b.name)
        self.i += 1  # 'COST DEFEAT EXPERIENCE' / 'COST EXPERIENCE'
        self.cost_row()
        while self.i < len(self.lines):
            line = self.peek()
            if line == "MOBILITY" or re.match(r"^MOBILITY \(.+\) CHARACTERISTICS$", line):
                self.i += 1
                self.mobility()
            elif line == "PHYSICAL ATTRIBUTES CUSTOMIZATION":
                self.i += 2  # header + 'LENGTH WIDTH HEIGHT WEIGHT SIZE WEAPON'
                self.dimensions(with_points=True)
            elif line == "CHARACTERISTICS" or re.match(r"^WALKER \(.+\) CHARACTERISTICS$", line):
                self.walker_characteristics()
            elif line == "PHYSICAL ATTRIBUTES":
                self.i += 2
                self.dimensions(with_points=False)
            elif line == "CUSTOMIZATION AND SIZE CATEGORY":
                self.walker_size()
            elif line == "MELEE":
                self.walker_melee()
            elif line == "CREW AND COMPLEMENT":
                self.i += 1
                self.crew()
            elif line == "BREAKPOINTS":
                self.breakpoints()
            elif line == "ARMOR":
                self.i += 1
                if self.peek().startswith("HEAD "):
                    self.walker_armor()
                else:
                    self.directional_armor()
            elif line in ("ENERGY SHIELDS", "ENERGY SHIELD", "SHIELD"):
                self.i += 1
                if self.peek().startswith("SHIELD"):
                    self.shield()
            elif line.startswith("SHIELD ") and "RECHARGE" in line:
                self.shield()
            elif line == "INFORMATION":
                self.i += 1
                self.information()
            elif is_heading(line):
                self.problem(
                    f"unexpected section kept in information: {line[:60]!r}", self.lineno()
                )
                self.record["information"] = join(self.record.get("information", ""), line)
                self.i += 1
            else:
                # Notes printed between the tables (walker options, era limits, ...).
                self.record["information"] = join(self.record.get("information", ""), line)
                self.i += 1
        if self.record.get("walker"):
            self.record["kind"] = "walker"
        return self.record

    def walker_characteristics(self) -> None:
        self.i += 1
        if self.peek().startswith("STRENGTH MYTHIC STRENGTH"):
            self.i += 1
            values = self.values()
            if len(values) == 4:
                self.record["walker"] = {
                    "strength": int(values[0]),
                    "mythic_strength": int(values[1].lstrip("+")),
                    "agility": int(values[2]),
                    "mythic_agility": int(values[3].lstrip("+")),
                }
            else:
                self.problem(f"walker characteristics not understood: {values}", self.lineno() - 1)
            if self.expect("JUMP LEAP"):
                m = re.match(rf"^({NUMBER}) Meters ({NUMBER}) Meters$", self.peek())
                if m and "walker" in self.record:
                    self.record["walker"]["jump_m"] = num(m.group(1))
                    self.record["walker"]["leap_m"] = num(m.group(2))
                self.i += 1
        else:
            self.problem("characteristics table not understood", self.lineno())

    def walker_size(self) -> None:
        self.i += 2  # heading + 'SIZE POINTS WEAPON POINTS SIZE CATEGORY REACH'
        m = re.match(r"^(\d+|--)\s+(\d+|--)\s+(\S+)\s+(\S+)$", self.peek())
        if m:
            self.record["size_points"] = int_or_none(m.group(1))
            self.record["weapon_points"] = int_or_none(m.group(2))
            if "walker" in self.record:
                self.record["walker"]["size_category"] = m.group(3)
                self.record["walker"]["reach"] = m.group(4)
        else:
            self.problem(f"walker size row not understood: {self.peek()!r}", self.lineno())
        self.i += 1

    def walker_melee(self) -> None:
        self.i += 1
        if self.expect("UNARMED PUNCH STOMP"):
            line = self.peek()
            self.i += 1
            parts = re.split(r"\)\s+(?=\d+D\d+)", line, maxsplit=1)
            if "walker" in self.record:
                self.record["walker"]["punch"] = parts[0] + (")" if len(parts) > 1 else "")
                self.record["walker"]["stomp"] = parts[1] if len(parts) > 1 else ""

    def walker_armor(self) -> None:
        self.i += 1  # 'HEAD ARMS CHEST LEGS' (or 'HEAD -- CHEST LEGS' for walkers without arms)
        values = self.values()
        if len(values) != 4:
            self.problem(f"walker armor row not understood: {values}", self.lineno() - 1)
            return
        # Read by position: '--' in the row means no such location (stored as 0).
        keys = ("head", "arms", "chest", "legs")
        self.record["walker_armor"] = {
            k: int_or_none(v) or 0 for k, v in zip(keys, values, strict=True)
        }

    def information(self) -> None:
        rule_text: list[str] = []
        info: list[str] = []
        sections: list[dict[str, str]] = []
        variants: list[dict[str, Any]] = []
        # The first lines (up to the first full stop) list special rules and mobility systems.
        while self.i < len(self.lines):
            line = self.peek()
            if self.variant_header_here() or (is_heading(line) and rule_text):
                break
            rule_text.append(line)
            self.i += 1
            if line.rstrip().endswith(".") and re.search(
                r"Vehicle\.$|Special Rules?\.$|Legs?\b|Jets?\b|Arms?\.$|Propellers?\.$"
                r"|Thrusters?\b",
                " ".join(rule_text),
            ):
                break
        self.special_rules(" ".join(rule_text))
        while self.i < len(self.lines):
            line = self.peek()
            if self.variant_header_here():
                variants.append(self.variant())
            elif line.startswith("["):
                variants.append(self.variant(header="Standard"))  # weapons with no header
            elif is_heading(line):
                self.i += 1
                body = []
                while (
                    self.i < len(self.lines)
                    and not is_heading(self.peek())
                    and not self.variant_header_here()
                ):
                    body.append(self.peek())
                    self.i += 1
                sections.append({"name": title_case(line), "text": " ".join(body)})
            else:
                info.append(line)
                self.i += 1
        if info:
            self.record["information"] = join(self.record.get("information", ""), " ".join(info))
        if sections:
            self.record["sections"] = sections
        merged: list[dict[str, Any]] = []
        for variant in variants:
            # Some variants are printed twice: once with a cost, once with details.
            same = next((m for m in merged if m["name"] == variant["name"]), None)
            if same is None:
                merged.append(variant)
                continue
            same["weapons"] += variant["weapons"]
            same.setdefault("cost", variant.get("cost"))
            if variant.get("notes"):
                same["notes"] = join(same.get("notes", ""), variant["notes"])
        variants = merged
        if variants:
            self.record["armaments"] = variants
        elif any(text.startswith("[") for _, text in self.lines):
            self.problem("weapon lines found but no armament variants")

    def variant_header_here(self) -> bool:
        """Does an armament variant start here?

        'ARMAMENT VARIANT: X', any '<name> COST' line (upgrade packages excepted), or a
        short line that isn't sentence text and is followed by weapon lines.
        """
        line, after = self.peek(), self.peek(1)
        if not line or line.startswith("["):
            return False
        if line.startswith("ARMAMENT VARIANT"):
            return True
        if line.endswith(" COST"):
            return not re.search(r"UPGRADE|PACKAGE", line)
        if after.startswith("[") or after.startswith("N/A"):
            return len(line) < 70 and not line.endswith(".") and not line[:1].islower()
        return False

    def variant(self, header: str | None = None) -> dict[str, Any]:
        if header is None:
            header = self.peek()
            self.i += 1
        name = re.sub(r"^ARMAMENT VARIANT:\s*", "", header)
        name = re.sub(r"\s+(TOP SPEED )?COST$", "", name).strip()
        variant: dict[str, Any] = {"name": name or "Standard", "weapons": []}
        notes = []
        while self.i < len(self.lines):
            line = self.peek()
            if self.variant_header_here() or is_heading(line):
                break
            self.i += 1
            if m := re.match(rf"^(?:N/A\s+)?\+?({NUMBER}) cR$", line):
                variant["cost"] = int(num(m.group(1)))
                continue
            if line == "N/A":
                continue
            cost = re.search(rf"\s+\+?({NUMBER}) cR$", line)
            body = line[: cost.start()] if cost else line
            if cost:
                variant["cost"] = int(num(cost.group(1)))
            if body.startswith("["):
                variant["weapons"].append(self.weapon(body))
            elif (
                variant["weapons"]
                and not variant["weapons"][-1].get("_closed")
                and re.match(r"^(with|and|\()\b", body) is not None
            ):
                # Wrapped weapon line ('... Guns' / 'with 200 Round Belt').
                last = variant["weapons"][-1]
                last["text"] = f"{last['text']} {body}"
                self.match_weapon(last)
            elif body:
                notes.append(body)
            if cost and variant["weapons"]:
                variant["weapons"][-1]["_closed"] = True
        for weapon in variant["weapons"]:
            weapon.pop("_closed", None)
        if notes:
            variant["notes"] = " ".join(notes)
        return variant

    def weapon(self, body: str) -> dict[str, Any]:
        tags = re.match(r"^((?:\[[OGC]\]\s*)+)(.*)$", body)
        positions = re.findall(r"\[([OGC])\]", tags.group(1)) if tags else []
        text = tags.group(2).strip() if tags else body
        weapon: dict[str, Any] = {"text": text, "positions": positions}
        self.match_weapon(weapon)
        return weapon

    def match_weapon(self, weapon: dict[str, Any]) -> None:
        text = weapon["text"]
        quantity, rest = parse_quantity(text)
        linked = bool(re.match(r"^Linked\b", rest, re.IGNORECASE))
        name = re.sub(r"^Linked\s+", "", rest, flags=re.IGNORECASE)
        name = re.sub(r"\s+with\s+.*$", "", name)  # 'with 200 Round Belt'
        name = re.sub(r"^Belt-fed\s+", "", name, flags=re.IGNORECASE)
        weapon["quantity"] = quantity
        weapon["linked"] = linked
        match = match_weapons(name)
        candidates = [w.id for w in match.candidates if w.vehicle_weapon] or [
            w.id for w in match.candidates
        ]
        weapon["candidates"] = candidates[:12]
        weapon["weapon_id"] = candidates[0] if len(candidates) == 1 else None

    def special_rules(self, text: str) -> None:
        """'Open-Top and All-Terrain Special Rule. 4 Wheel Vehicle.' -> rules + mobility."""
        rules: list[str] = []
        systems: list[dict[str, Any]] = []
        leftover: list[str] = []
        for m in MOBILITY_COUNT.finditer(text):
            systems.append({"kind": m.group(2).lower(), "count": count_word(m.group(1))})
        for sentence in re.split(r"(?<=\.)\s+", text.strip()):
            body = sentence.rstrip(".").strip()
            parts = [p.strip() for p in re.split(r",\s*(?:and\s+)?|\s+and\s+", body) if p.strip()]
            found = []
            for part in parts:
                cleaned = re.sub(r"\s*Special Rules?\b.*$", "", part).strip()
                canonical = canonical_rule(cleaned)
                if canonical:
                    found.append(canonical)
                elif not cleaned or MOBILITY_PART.fullmatch(cleaned):
                    continue
                else:
                    found = []
                    break
            if found:
                rules += found
                if re.search(r"Special Rules?\s+\w", body):
                    leftover.append(sentence)  # e.g. '... Special Rule for Passengers'
            elif not MOBILITY_SENTENCE.fullmatch(body):
                leftover.append(sentence)
        if rules:
            self.record["special_rules"] = list(dict.fromkeys(rules))
        if systems:
            self.record["mobility_systems"] = systems
        if leftover:
            self.record["information"] = join(
                self.record.get("information", ""), " ".join(leftover)
            )

    # -- turrets
    def parse_turret(self) -> dict[str, Any]:
        self.record.update(name=title_case(self.b.name), kind="turret")
        while self.i < len(self.lines):
            line = self.peek()
            if line == "DIMENSIONS":
                self.i += 2
                self.dimensions(with_points=False)
            elif line == "HULL":
                self.i += 1
                if self.expect("HULL INTEGRITY"):
                    self.record["breakpoints"] = {"hull": int(num(self.values()[0]))}
            elif line == "ARMOR":
                self.i += 1
                self.directional_armor()
            elif line in ("ENERGY SHIELD", "ENERGY SHIELDS"):
                self.i += 1
                self.shield()
            elif line == "CHARACTERISTICS":
                self.i += 1
                header = self.peek().split()
                self.i += 1
                values = self.values()
                if len(header) == len(values):
                    self.record["characteristics"] = {
                        h: int(v) for h, v in zip(header, values, strict=True) if v.isdigit()
                    }
            elif re.search(r"(EXP )?COST$", line):
                self.i += 1
                self.turret_variants()
            elif is_heading(line):
                self.i += 1
                body = []
                while self.i < len(self.lines) and not is_heading(self.peek()):
                    body.append(self.peek())
                    self.i += 1
                self.record.setdefault("sections", []).append(
                    {"name": title_case(line), "text": " ".join(body)}
                )
            else:
                self.record["information"] = join(self.record.get("information", ""), line)
                self.i += 1
        return self.record

    def turret_variants(self) -> None:
        """Rows like 'Two Linked M202 XP Machine Gun 50 Exp 240 cR', or (Forerunner) the
        weapon, its rules and '380 Exp 1,830 cR' on separate lines."""
        variants: list[dict[str, Any]] = []
        pending: list[str] = []
        while self.i < len(self.lines) and not is_heading(self.peek()):
            line = self.peek()
            self.i += 1
            costs = re.match(rf"^(?:({NUMBER}) Exp\s+)?({NUMBER})(?: cR)?$", line)
            if costs and pending:
                variants.append(self.turret_variant(pending[0], costs.group(1), costs.group(2)))
                rules = " ".join(pending[1:])
                if rules:
                    variants[-1]["notes"] = rules
                    if "Heavy Plating" in rules:
                        self.record["special_rules"] = ["Heavy Plating"]
                pending = []
                continue
            m = re.match(rf"^(.+?)(?:\s+({NUMBER}) Exp)?\s+({NUMBER})(?: cR)?$", line)
            if m:
                # Earlier unpriced lines are more weapons of the same variant (M3063).
                variants.append(self.turret_variant(m.group(1), m.group(2), m.group(3), pending))
                pending = []
            elif (
                variants
                and not pending
                and not line.startswith(("Two ", "Four "))
                and (line.endswith(".") or line[:1].islower())
            ):
                variants[-1]["notes"] = join(variants[-1].get("notes", ""), line)
            else:
                pending.append(line)
        if pending:
            self.problem(f"turret variant lines not understood: {pending}", self.lineno())
        if variants:
            self.record["armaments"] = variants

    def turret_variant(
        self, name: str, experience: str | None, cost: str, more: list[str] | None = None
    ) -> dict[str, Any]:
        weapons = []
        for text in [*(more or []), name]:
            weapon: dict[str, Any] = {"text": text, "positions": []}
            self.match_weapon(weapon)
            weapons.append(weapon)
        label = " + ".join([*(more or []), name])
        variant: dict[str, Any] = {"name": label, "weapons": weapons, "cost": int(num(cost))}
        if experience:
            variant["defeat_experience"] = int(num(experience))
        return variant


def join(left: str, right: str) -> str:
    return f"{left} {right}".strip()


# ---------------------------------------------------------------------- run ---


def import_book(text: str, book: Book, problems: list[Problem]) -> list[dict[str, Any]]:
    lines = [line.strip() for line in text.split("\n")]
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    parsed = []
    for block in turret_blocks(lines, book):
        parsed.append((block, Parser(block, book, problems).parse_turret()))
    for block in vehicle_blocks(lines, book, problems):
        parsed.append((block, Parser(block, book, problems).parse_vehicle()))
    for block, record in parsed:
        record.update(
            faction=block.faction,
            category=block.category,
            source=book.source,
            page=block.page,
        )
        base = slug(record["name"])
        record["id"] = base if base not in seen else f"{base}_{slug(block.faction)}"
        if "breakpoints" not in record:
            problems.append(Problem(book.key, block.line, block.name, "no breakpoints; skipped"))
            continue
        try:
            vehicle = Vehicle.model_validate(record)
        except ValidationError as error:
            first = error.errors()[0]
            where = ".".join(str(p) for p in first["loc"])
            problems.append(
                Problem(book.key, block.line, block.name, f"invalid ({where}): {first['msg']}")
            )
            continue
        seen.add(vehicle.id)
        records.append(json.loads(vehicle.model_dump_json(exclude_defaults=True)))
    return records


def main(argv: list[str]) -> int:
    if len(argv) not in (2, 3):
        print(__doc__)
        return 2
    problems: list[Problem] = []
    summary = []
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    weapon_lines = matched = 0
    for path, book in zip(argv[1:], (CORE, LIGHT_AND_SKY), strict=False):
        records = import_book(Path(path).read_text(encoding="utf-8"), book, problems)
        out = OUT_DIR / f"{book.key}_vehicles.json"
        payload = {"source": book.source, "vehicles": records}
        out.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        kinds: dict[str, int] = {}
        for record in records:
            kind = record.get("kind", "vehicle")
            kinds[kind] = kinds.get(kind, 0) + 1
            for variant in record.get("armaments", []):
                for weapon in variant.get("weapons", []):
                    weapon_lines += 1
                    matched += bool(weapon.get("weapon_id") or weapon.get("candidates"))
        summary.append(f"{book.source}: {len(records)} records {kinds}")
    summary.append(f"Armament weapon lines matching catalog weapons: {matched} of {weapon_lines}")
    REPORT.write_text("\n".join([*summary, "", "PROBLEMS", *map(str, problems)]) + "\n", "utf-8")
    print("\n".join(summary))
    print(f"{len(problems)} problems; see {REPORT.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
