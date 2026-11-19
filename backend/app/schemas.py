"""Request models. Strict bounds on every field keep input small and safe."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Lang = Literal["en", "hi"]
AgeGroup = Literal["infant", "child", "teen", "adult", "elderly"]
Condition = Literal["asthma", "copd", "heart", "pregnant", "allergy", "diabetes"]
Mode = Literal[
    "car_petrol", "car_diesel", "car_cng", "car_ev", "two_wheeler", "e_two_wheeler",
    "auto_cng", "bus", "metro", "cycle", "walk",
]


class Coords(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    name: str | None = Field(default=None, max_length=80)


class Member(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    age_group: AgeGroup = "adult"
    conditions: list[Condition] = Field(default_factory=list, max_length=6)
    outdoor_hours: float = Field(default=1.0, ge=0, le=16)
    exercises_outdoors: bool = False
    commute_mode: Mode | None = None


class Home(BaseModel):
    has_purifier: bool = False
    cooking_fuel: Literal["lpg", "png", "induction", "biomass", "kerosene"] = "lpg"
    smoker_at_home: bool = False
    burns_incense: bool = False
    has_pets: bool = False


class Household(BaseModel):
    members: list[Member] = Field(min_length=1, max_length=12)
    home: Home = Field(default_factory=Home)


class PlanRequest(Coords):
    household: Household
    lang: Lang = "en"


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=2000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=12)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    place: str | None = Field(default=None, max_length=80)
    household: Household | None = None
    lang: Lang = "en"


class Room(BaseModel):
    kind: Literal["kitchen", "bedroom", "living", "kids", "study", "bathroom"]
    area_m2: float = Field(default=12, gt=1, le=200)
    height_m: float = Field(default=2.8, gt=1.5, le=6)


class IndoorRequest(Coords):
    home: Home = Field(default_factory=Home)
    rooms: list[Room] = Field(default_factory=lambda: [Room(kind="living"), Room(kind="bedroom")], max_length=10)
    lang: Lang = "en"


class Trip(BaseModel):
    distance_km: float = Field(gt=0, le=500)
    occupants: int = Field(default=1, ge=1, le=8)


class MobilityRequest(Trip):
    modes: list[Mode] | None = None


class ModeShift(BaseModel):
    from_mode: Mode
    to_mode: Mode
    distance_km_one_way: float = Field(gt=0, le=200)
    days_per_week: int = Field(ge=1, le=7)
    occupants: int = Field(default=1, ge=1, le=8)


class ExerciseShift(BaseModel):
    current_hour: int = Field(ge=0, le=23)
    duration_min: int = Field(default=45, ge=5, le=300)
    intensity: Literal["light", "moderate", "vigorous"] = "moderate"


class WasteBurning(BaseModel):
    kg_per_week: float = Field(gt=0, le=200)


class EnergySaving(BaseModel):
    kwh_per_month: float = Field(gt=0, le=2000)


class WhatIfRequest(BaseModel):
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    mode_shift: ModeShift | None = None
    exercise_shift: ExerciseShift | None = None
    waste_burning: WasteBurning | None = None
    energy_saving: EnergySaving | None = None
    lang: Lang = "en"
    explain: bool = False


class Activity(BaseModel):
    title: str = Field(min_length=1, max_length=60)
    start: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$")
    duration_min: int = Field(default=60, ge=5, le=720)
    who: str | None = Field(default=None, max_length=40)
    sensitive: bool = False


class AlertsRequest(Coords):
    activities: list[Activity] = Field(default_factory=list, max_length=20)
    household: Household | None = None
    lang: Lang = "en"


class RoutineRequest(Coords):
    household: Household
    commute_mode: Mode | None = None
    lang: Lang = "en"


ReportCategory = Literal[
    "waste_burning", "construction_dust", "industrial_smoke", "vehicle_smoke", "traffic_jam", "crop_burning", "other"
]


class ReportCreate(BaseModel):
    category: ReportCategory
    description: str = Field(min_length=5, max_length=500)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    ai_assisted: bool = False

    @field_validator("description")
    @classmethod
    def strip_text(cls, v: str) -> str:
        v = " ".join(v.split())
        if len(v) < 5:
            raise ValueError("Description too short")
        return v
