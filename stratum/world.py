"""World generation models for Stratum."""

from __future__ import annotations

from dataclasses import dataclass
import math
import random


CONTINENT_STYLES = (
    "island",
    "elongated",
    "archipelago",
    "twin-mass",
    "atoll",
    "coastal shelf",
    "dual-arm",
)


@dataclass(slots=True)
class WorldMap:
    """Minimal world state placeholder for the first scaffold."""

    width: int = 2400
    height: int = 800
    seed: int = 0
    continent_style: str = "island"
    land_coverage: float = 0.4
    moisture_iterations: int = 45
    river_cells: int = 0

    def to_dict(self) -> dict[str, int | float | str]:
        """Serialize world parameters."""
        return {
            "width": self.width,
            "height": self.height,
            "seed": self.seed,
            "continent_style": self.continent_style,
            "land_coverage": self.land_coverage,
            "moisture_iterations": self.moisture_iterations,
            "river_cells": self.river_cells,
        }

    @classmethod
    def from_dict(cls, data: dict[str, int | float | str]) -> "WorldMap":
        """Rebuild the world from serialized parameters."""
        return cls(
            width=int(data.get("width", 2400)),
            height=int(data.get("height", 800)),
            seed=int(data.get("seed", 0)),
            continent_style=str(data.get("continent_style", "island")),
            land_coverage=float(data.get("land_coverage", 0.4)),
            moisture_iterations=int(data.get("moisture_iterations", 45)),
            river_cells=int(data.get("river_cells", 0)),
        )

    @classmethod
    def generate(cls, seed: int) -> "WorldMap":
        rng = random.Random(seed)
        return cls(
            seed=seed,
            continent_style=rng.choice(CONTINENT_STYLES),
            land_coverage=round(rng.uniform(0.30, 0.55), 3),
            river_cells=rng.randint(8_000, 13_000),
        )

    @property
    def sea_level(self) -> float:
        """Derive a rough sea level from the target land coverage."""
        return 0.68 - (self.land_coverage * 0.6)

    def tile_at(self, x: int, y: int) -> "Tile":
        """Sample a deterministic terrain tile without materializing the whole map."""
        nx = x / max(self.width - 1, 1)
        ny = y / max(self.height - 1, 1)
        dx = (nx - 0.5) * 2.0
        dy = (ny - 0.5) * 2.0

        radial = max(0.0, 1.0 - math.sqrt(dx * dx + dy * dy))
        style_bias = self._style_bias(dx, dy)
        elevation = (
            0.52 * self._fractal_noise(x, y, 180)
            + 0.24 * self._fractal_noise(x, y, 72)
            + 0.14 * self._fractal_noise(x, y, 28)
            + 0.32 * radial
            + style_bias
        )
        elevation = max(0.0, min(1.0, elevation))

        water_depth = self.sea_level - elevation
        coastal_boost = max(0.0, 0.16 - abs(water_depth)) * 3.0 if water_depth > -0.16 else 0.0
        moisture = (
            0.58 * self._fractal_noise(x + 811, y - 211, 160)
            + 0.28 * self._fractal_noise(x - 401, y + 503, 48)
            + 0.18 * radial
            + coastal_boost
        )
        moisture = max(0.0, min(1.0, moisture))

        is_water = elevation < self.sea_level
        river_value = abs(self._fractal_noise(x + 97, y - 57, 24) - 0.5)
        is_river = (not is_water) and moisture > 0.52 and elevation < 0.78 and river_value < 0.018

        biome = self._biome_for(elevation, moisture, is_water, is_river)
        glyph = self._glyph_for(biome)
        return Tile(
            x=x,
            y=y,
            elevation=elevation,
            moisture=moisture,
            biome=biome,
            glyph=glyph,
            is_water=is_water,
            is_river=is_river,
        )

    def _style_bias(self, dx: float, dy: float) -> float:
        if self.continent_style == "island":
            return 0.10
        if self.continent_style == "elongated":
            return 0.20 - abs(dy) * 0.22
        if self.continent_style == "archipelago":
            return -0.07 + self._wave(dx, 4.5) * 0.06 + self._wave(dy, 3.2) * 0.05
        if self.continent_style == "twin-mass":
            lobe = max(0.0, 0.25 - min((dx + 0.35) ** 2 + dy**2, (dx - 0.35) ** 2 + dy**2))
            return lobe * 1.4 - 0.05
        if self.continent_style == "atoll":
            ring = abs(math.sqrt(dx * dx + dy * dy) - 0.48)
            return 0.18 - ring * 0.65
        if self.continent_style == "coastal shelf":
            return 0.14 - (dx + 0.35) * 0.22
        if self.continent_style == "dual-arm":
            arm = max(0.0, 0.18 - abs(dy - dx * 0.55)) + max(0.0, 0.18 - abs(dy + dx * 0.55))
            return arm * 0.34 - 0.06
        return 0.0

    def _fractal_noise(self, x: int, y: int, scale: int) -> float:
        total = 0.0
        weight = 0.0
        current_scale = float(scale)
        current_weight = 1.0
        for _ in range(3):
            total += self._value_noise(x / current_scale, y / current_scale) * current_weight
            weight += current_weight
            current_scale /= 2.0
            current_weight *= 0.5
        return total / weight

    def _value_noise(self, x: float, y: float) -> float:
        x0 = math.floor(x)
        y0 = math.floor(y)
        tx = x - x0
        ty = y - y0

        n00 = self._hash(x0, y0)
        n10 = self._hash(x0 + 1, y0)
        n01 = self._hash(x0, y0 + 1)
        n11 = self._hash(x0 + 1, y0 + 1)

        sx = tx * tx * (3.0 - 2.0 * tx)
        sy = ty * ty * (3.0 - 2.0 * ty)
        nx0 = n00 + (n10 - n00) * sx
        nx1 = n01 + (n11 - n01) * sx
        return nx0 + (nx1 - nx0) * sy

    def _hash(self, x: int, y: int) -> float:
        value = x * 374761393 + y * 668265263 + self.seed * 2246822519
        value = (value ^ (value >> 13)) * 1274126177
        value ^= value >> 16
        return (value & 0xFFFFFFFF) / 0xFFFFFFFF

    @staticmethod
    def _wave(value: float, frequency: float) -> float:
        return math.sin(value * math.pi * frequency)

    @staticmethod
    def _biome_for(elevation: float, moisture: float, is_water: bool, is_river: bool) -> str:
        if is_river:
            return "river"
        if is_water:
            return "coast" if elevation > 0.38 else "ocean"
        if elevation > 0.80:
            return "snow"
        if elevation > 0.70:
            return "mountain"
        if moisture < 0.22:
            return "desert"
        if moisture < 0.42:
            return "plains"
        if moisture < 0.70:
            return "forest"
        return "wetlands"

    @staticmethod
    def _glyph_for(biome: str) -> str:
        return {
            "ocean": "~",
            "coast": ".",
            "river": "=",
            "desert": ".",
            "plains": ",",
            "forest": '"',
            "wetlands": ";",
            "mountain": "^",
            "snow": "A",
        }.get(biome, "?")


@dataclass(slots=True)
class Tile:
    """A sampled world tile used by the renderer."""

    x: int
    y: int
    elevation: float
    moisture: float
    biome: str
    glyph: str
    is_water: bool
    is_river: bool
