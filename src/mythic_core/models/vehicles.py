"""Vehicles, walkers and automated turrets, following the book's Vehicle Armory layout.

A :class:`Vehicle` is the catalog entry exactly as the book prints it (every armament
variant). Live damage (Breakpoints lost, Doomed State, ...) is tracked by the apps.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from mythic_core.models.protection import ArmorRating, EnergyShield


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class VehicleKind(StrEnum):
    VEHICLE = "vehicle"
    #: Bipedal/multi-legged walkers (Mantis, Scarab, ...): characteristics, melee and
    #: Head/Arms/Chest/Legs armor instead of directional armor.
    WALKER = "walker"
    #: Automated Turrets and gun pods: Hull Integrity only.
    TURRET = "turret"


class Component(StrEnum):
    """Vehicle components with Breakpoints, in Hit Location order."""

    WEAPON = "weapon"
    MOBILITY = "mobility"
    ENGINE = "engine"
    OPTICS = "optics"
    HULL = "hull"


class Breakpoints(_Frozen):
    """Breakpoints per component (``--`` in the book = the vehicle doesn't have one)."""

    weapon: int | None = Field(default=None, ge=0)
    mobility: int | None = Field(default=None, ge=0)
    engine: int | None = Field(default=None, ge=0)
    optics: int | None = Field(default=None, ge=0)
    hull: int = Field(ge=0)

    def of(self, component: Component) -> int | None:
        value: int | None = getattr(self, component.value)
        return value


class ArmorFacing(StrEnum):
    FRONT = "front"
    BACK = "back"
    SIDE = "side"
    TOP = "top"
    BOTTOM = "bottom"


class VehicleArmor(_Frozen):
    """Directional armor. ``None`` where the book prints ``--``."""

    front: int | None = Field(default=None, ge=0)
    back: int | None = Field(default=None, ge=0)
    side: int | None = Field(default=None, ge=0)
    top: int | None = Field(default=None, ge=0)
    bottom: int | None = Field(default=None, ge=0)

    def at(self, facing: ArmorFacing) -> int | None:
        value: int | None = getattr(self, facing.value)
        return value


class Movement(_Frozen):
    """Mobility characteristics in Meters per Turn (MpT)."""

    accelerate: int = Field(ge=0)
    brake: int = Field(ge=0)
    top_speed: int = Field(ge=0)
    top_speed_kmh: int | None = None
    maneuver: int = Field(ge=0)


class Dimensions(_Frozen):
    length_m: float | None = None
    width_m: float | None = None
    height_m: float | None = None
    weight_kg: float | None = None


class Crew(_Frozen):
    operators: int = Field(default=0, ge=0)
    gunners: int = Field(default=0, ge=0)
    #: Passenger seats (``0`` for ``--``).
    passengers: int = Field(default=0, ge=0)
    #: The crew/complement lines as printed (cargo, carried vehicles, ...).
    text: str = ""

    @property
    def size(self) -> int:
        return self.operators + self.gunners


class MobilityKind(StrEnum):
    WHEEL = "wheel"
    TREAD = "tread"
    LEG = "leg"
    JET = "jet"
    PROPELLER = "propeller"
    THRUSTER = "thruster"


class MobilitySystem(_Frozen):
    """'4 Wheel Vehicle', 'Two Jets', '2 Legs': each one has its own Mobility Breakpoints."""

    kind: MobilityKind
    count: int = Field(ge=1)


class WeaponPosition(StrEnum):
    OPERATOR = "O"
    GUNNER = "G"
    COMPLEMENT = "C"


class ArmamentWeapon(_Frozen):
    """One weapon line of an armament variant, e.g. '[G] Two Linked M247H Machine Guns'."""

    text: str
    positions: list[WeaponPosition] = Field(default_factory=list)
    quantity: int = Field(default=1, ge=1)
    #: Linked weapons fire together and share one To Hit roll; each deals its own Damage.
    linked: bool = False
    #: Catalog weapon, when the line names exactly one.
    weapon_id: str | None = None
    #: Catalog weapons the line could mean (the GM picks).
    candidates: list[str] = Field(default_factory=list)


class ArmamentVariant(_Frozen):
    name: str
    weapons: list[ArmamentWeapon] = Field(default_factory=list)
    cost: int | None = None
    #: Only some variants (mostly turrets) list their own Experience; otherwise the
    #: vehicle's applies.
    defeat_experience: int | None = None
    notes: str = ""


class WalkerStats(_Frozen):
    strength: int
    mythic_strength: int = 0
    agility: int
    mythic_agility: int = 0
    jump_m: float | None = None
    leap_m: float | None = None
    size_category: str = ""
    reach: str = ""
    punch: str = ""
    stomp: str = ""


class VehicleSection(_Frozen):
    """A named rules section printed with the vehicle ('ORBITAL DEPLOYMENT', ...)."""

    name: str
    text: str


#: Defeat XP for vehicles that list none: Cost / 5, never more than 2,000.
MAX_VEHICLE_EXPERIENCE = 2000


class Vehicle(_Frozen):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str
    kind: VehicleKind = VehicleKind.VEHICLE
    faction: str = ""
    #: The armory section, e.g. 'UNSC Ground Vehicles'.
    category: str = ""
    cost: int | None = None
    defeat_experience: int | None = None

    movement: Movement | None = None
    dimensions: Dimensions = Dimensions()
    size_points: int | None = None
    weapon_points: int | None = None
    crew: Crew = Crew()
    breakpoints: Breakpoints
    armor: VehicleArmor | None = None
    #: Walkers use body-location armor instead of directional armor.
    walker_armor: ArmorRating | None = None
    walker: WalkerStats | None = None
    shield: EnergyShield | None = None
    #: Turret characteristics (WFR/INT/PER), as printed.
    characteristics: dict[str, int] = Field(default_factory=dict)

    special_rules: list[str] = Field(default_factory=list)
    mobility_systems: list[MobilitySystem] = Field(default_factory=list)
    armaments: list[ArmamentVariant] = Field(default_factory=list)
    sections: list[VehicleSection] = Field(default_factory=list)
    information: str = ""
    source: str = ""
    page: int | None = None

    def has_rule(self, name: str) -> bool:
        key = name.casefold()
        return any(
            r.casefold() == key or r.casefold().startswith(key + " (") for r in self.special_rules
        )

    @property
    def heavy_plating(self) -> bool:
        return self.has_rule("Heavy Plating")

    @property
    def open_top(self) -> bool:
        return self.has_rule("Open-Top")

    def armament(self, name: str | None = None) -> ArmamentVariant | None:
        """The named armament variant, or the default (the first listed)."""
        if name is None:
            return self.armaments[0] if self.armaments else None
        for variant in self.armaments:
            if variant.name == name:
                return variant
        raise KeyError(f"{self.name} has no armament variant {name!r}")

    def experience_payout(self, variant: str | None = None) -> int:
        """Defeat XP (crew not included): the variant's, the vehicle's, or Cost / 5."""
        chosen = self.armament(variant)
        if chosen is not None and chosen.defeat_experience is not None:
            return chosen.defeat_experience
        if self.defeat_experience is not None:
            return self.defeat_experience
        cost = (chosen.cost if chosen and chosen.cost is not None else None) or self.cost or 0
        return min(MAX_VEHICLE_EXPERIENCE, cost // 5)
