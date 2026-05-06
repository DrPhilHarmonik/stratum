"""Geology layer placeholders."""

from __future__ import annotations

from dataclasses import dataclass
import random

from .civ import CivLayer
from .world import WorldMap


@dataclass(slots=True)
class GeologyLayer:
    """Track slow terrain changes and rare eruptions."""

    erosion_rate_per_year: float = 0.00015
    volcanic_event_chance_per_year: float = 0.0
    lava_cooldown_years: int = 3
    eruption_cooldown_years: int = 90
    last_eruption_year: int = -9999

    def to_dict(self) -> dict[str, float | int]:
        """Serialize the geology layer."""
        return {
            "erosion_rate_per_year": self.erosion_rate_per_year,
            "volcanic_event_chance_per_year": self.volcanic_event_chance_per_year,
            "lava_cooldown_years": self.lava_cooldown_years,
            "eruption_cooldown_years": self.eruption_cooldown_years,
            "last_eruption_year": self.last_eruption_year,
        }

    @classmethod
    def from_dict(cls, data: dict[str, float | int]) -> "GeologyLayer":
        """Rebuild the geology layer from serialized data."""
        return cls(
            erosion_rate_per_year=float(data.get("erosion_rate_per_year", 0.00015)),
            volcanic_event_chance_per_year=float(data.get("volcanic_event_chance_per_year", 0.0)),
            lava_cooldown_years=int(data.get("lava_cooldown_years", 3)),
            eruption_cooldown_years=int(data.get("eruption_cooldown_years", 90)),
            last_eruption_year=int(data.get("last_eruption_year", -9999)),
        )

    def advance_year(self, world: WorldMap, civ: CivLayer, year: int, rng: random.Random) -> list[str]:
        """Geology is currently passive; eruptions are disabled."""
        return []
