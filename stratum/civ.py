"""Civilization layer placeholders."""

from __future__ import annotations

from dataclasses import dataclass, field
import random

from .world import WorldMap


@dataclass(slots=True)
class Settlement:
    """A minimal settlement record for the initial scaffold."""

    name: str
    population: int
    founded_year: int
    x: int
    y: int
    parent: str | None = None
    drought_years: int = 0
    decline_years: int = 0

    def to_dict(self) -> dict[str, int | str | None]:
        """Serialize a settlement for save files."""
        return {
            "name": self.name,
            "population": self.population,
            "founded_year": self.founded_year,
            "x": self.x,
            "y": self.y,
            "parent": self.parent,
            "drought_years": self.drought_years,
            "decline_years": self.decline_years,
        }

    @classmethod
    def from_dict(cls, data: dict[str, int | str | None]) -> "Settlement":
        """Rebuild a settlement from serialized data."""
        return cls(
            name=str(data["name"]),
            population=int(data["population"]),
            founded_year=int(data["founded_year"]),
            x=int(data["x"]),
            y=int(data["y"]),
            parent=None if data.get("parent") is None else str(data["parent"]),
            drought_years=int(data.get("drought_years", 0)),
            decline_years=int(data.get("decline_years", 0)),
        )


@dataclass(slots=True)
class Road:
    """Simple road connection between settlements."""

    a: str
    b: str
    built_year: int
    path: list[tuple[int, int]] = field(default_factory=list)
    condition: int = 100
    blocked_years: int = 0

    def to_dict(self) -> dict[str, int | str | list[list[int]]]:
        return {
            "a": self.a,
            "b": self.b,
            "built_year": self.built_year,
            "path": [[x, y] for x, y in self.path],
            "condition": self.condition,
            "blocked_years": self.blocked_years,
        }

    @classmethod
    def from_dict(cls, data: dict[str, int | str | list[list[int]]]) -> "Road":
        return cls(
            a=str(data["a"]),
            b=str(data["b"]),
            built_year=int(data["built_year"]),
            path=[(int(item[0]), int(item[1])) for item in list(data.get("path", []))],
            condition=int(data.get("condition", 100)),
            blocked_years=int(data.get("blocked_years", 0)),
        )


@dataclass(slots=True)
class CivLayer:
    """High-level civilization simulation settings."""

    growth_model: str = "logistic"
    bridge_support: bool = True
    settlements: list[Settlement] = field(default_factory=list)
    roads: list[Road] = field(default_factory=list)

    def seed_demo_data(self, world: WorldMap) -> None:
        """Provide a few deterministic settlements on land for the bootstrap UI."""
        candidates = [
            ("Aster", 120, 0, 0.32, 0.44),
            ("Brine", 85, 3, 0.61, 0.52),
            ("Cinder", 260, 8, 0.48, 0.30),
            ("Dune", 150, 11, 0.72, 0.38),
        ]

        self.settlements.clear()
        for name, population, founded_year, x_ratio, y_ratio in candidates:
            x, y = self._find_land_near(world, int(world.width * x_ratio), int(world.height * y_ratio))
            self.settlements.append(
                Settlement(
                    name=name,
                    population=population,
                    founded_year=founded_year,
                    x=x,
                    y=y,
                )
            )
        self._ensure_initial_roads(world)

    @staticmethod
    def _find_land_near(world: WorldMap, origin_x: int, origin_y: int) -> tuple[int, int]:
        for radius in range(0, 50):
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    x = min(max(origin_x + dx, 0), world.width - 1)
                    y = min(max(origin_y + dy, 0), world.height - 1)
                    if not world.tile_at(x, y).is_water:
                        return x, y
        return origin_x, origin_y

    def total_population(self) -> int:
        """Return total population across all settlements."""
        return sum(settlement.population for settlement in self.settlements)

    def to_dict(self) -> dict[str, object]:
        """Serialize the civilization layer."""
        return {
            "growth_model": self.growth_model,
            "bridge_support": self.bridge_support,
            "settlements": [settlement.to_dict() for settlement in self.settlements],
            "roads": [road.to_dict() for road in self.roads],
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "CivLayer":
        """Rebuild the civilization layer from serialized data."""
        return cls(
            growth_model=str(data.get("growth_model", "logistic")),
            bridge_support=bool(data.get("bridge_support", True)),
            settlements=[Settlement.from_dict(item) for item in list(data.get("settlements", []))],
            roads=[Road.from_dict(item) for item in list(data.get("roads", []))],
        )

    def advance_year(self, world: WorldMap, year: int, rng: random.Random) -> list[str]:
        """Advance the lightweight civilization model by one year."""
        events: list[str] = []
        road_degree = self._road_degree()

        road_events = self._advance_roads(world, year, rng)
        if road_events:
            events.extend(road_events)
            road_degree = self._road_degree()

        for settlement in self.settlements:
            tile = world.tile_at(settlement.x, settlement.y)
            biome_growth = {
                "desert": 0.01,
                "plains": 0.04,
                "forest": 0.03,
                "wetlands": 0.02,
                "mountain": 0.015,
                "snow": 0.008,
                "coast": 0.035,
                "river": 0.045,
            }.get(tile.biome, 0.02)
            trade_links = road_degree.get(settlement.name, 0)
            drought_penalty = 0.028 if settlement.drought_years > 0 else 0.0
            trade_bonus = min(0.018, trade_links * 0.006)
            carrying_capacity = 420 + int(tile.moisture * 320) + trade_links * 75 + self._farm_radius(settlement) * 28
            pressure = settlement.population / max(carrying_capacity, 1)
            growth_rate = (
                biome_growth
                + trade_bonus
                - drought_penalty
                - max(0.0, pressure - 0.65) * 0.06
                + rng.uniform(-0.01, 0.012)
            )
            delta = max(-18, min(30, int(round(settlement.population * growth_rate))))
            settlement.population = max(25, settlement.population + delta)

            if delta >= 12:
                settlement.decline_years = max(0, settlement.decline_years - 1)
                events.append(f"Year {year}: {settlement.name} grows to {settlement.population}.")
            elif delta <= -10:
                settlement.decline_years += 1
                events.append(f"Year {year}: {settlement.name} contracts to {settlement.population}.")
            else:
                settlement.decline_years = max(0, settlement.decline_years - 1)

            if settlement.drought_years > 0:
                settlement.drought_years -= 1
                if settlement.drought_years == 0:
                    events.append(f"Year {year}: fields around {settlement.name} recover after drought.")

        if self.settlements and rng.random() < 0.12:
            settlement = rng.choice(self.settlements)
            settlement.drought_years = max(settlement.drought_years, rng.randint(3, 5))
            loss = max(8, int(settlement.population * rng.uniform(0.05, 0.12)))
            settlement.population = max(25, settlement.population - loss)
            events.append(
                f"Year {year}: drought withers farms around {settlement.name}, costing about {loss} people."
            )

        if len(self.settlements) >= 2 and rng.random() < 0.10:
            first, second = rng.sample(self.settlements, 2)
            first_loss = max(6, int(first.population * 0.07))
            second_loss = max(6, int(second.population * 0.06))
            first.population = max(25, first.population - first_loss)
            second.population = max(25, second.population - second_loss)
            events.append(f"Year {year}: conflict flares between {first.name} and {second.name}.")
            road_damage = self._damage_road_from_conflict(world, year, rng, first.name, second.name)
            if road_damage:
                events.append(road_damage)

        road_event = self._maybe_build_trade_road(world, year, rng)
        if road_event:
            events.append(road_event)

        if self._should_found_colony(rng):
            founder = max(self.settlements, key=lambda settlement: settlement.population)
            child_coords = self._find_colony_site(world, founder.x, founder.y, rng)
            if child_coords is not None:
                child_name = self._next_name(rng)
                child_population = max(40, int(founder.population * 0.22))
                founder.population = max(30, founder.population - child_population // 2)
                self.settlements.append(
                    Settlement(
                        name=child_name,
                        population=child_population,
                        founded_year=year,
                        x=child_coords[0],
                        y=child_coords[1],
                        parent=founder.name,
                    )
                )
                self._ensure_road(world, founder.name, child_name, year)
                events.append(f"Year {year}: {founder.name} founds the daughter settlement {child_name}.")

        return events

    def settlement_glyph(self, settlement: Settlement) -> str:
        """Return a visible glyph tier based on settlement size."""
        if settlement.population >= 280:
            return "#"
        if settlement.population >= 180:
            return "@"
        if settlement.population >= 110:
            return "O"
        return "o"

    def farm_cells(self, settlement: Settlement) -> set[tuple[int, int]]:
        """Return the visible farm ring around a settlement."""
        radius = self._farm_radius(settlement)
        if radius == 0:
            return set()
        cells: set[tuple[int, int]] = set()
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if abs(dx) + abs(dy) > radius + 1:
                    continue
                if dx == 0 and dy == 0:
                    continue
                cells.add((settlement.x + dx, settlement.y + dy))
        return cells

    def road_cells(self, world: WorldMap) -> dict[tuple[int, int], str]:
        """Return a road overlay map."""
        overlay: dict[tuple[int, int], str] = {}
        positions = {settlement.name: settlement for settlement in self.settlements}
        for road in self.roads:
            first = positions.get(road.a)
            second = positions.get(road.b)
            if first is None or second is None:
                continue
            if not road.path:
                road.path = self._route_between(world, first.x, first.y, second.x, second.y)
            for x, y in road.path[1:-1]:
                overlay[(x, y)] = "x" if road.blocked_years > 0 else "+"
        return overlay

    def infrastructure_counts(self, world: WorldMap) -> tuple[int, int]:
        """Return simple road and farm counts for status displays."""
        road_cells = len(self.road_cells(world))
        farm_cells = sum(len(self.farm_cells(settlement)) for settlement in self.settlements)
        return road_cells, farm_cells

    def urban_cells(self) -> dict[tuple[int, int], str]:
        """Return visible urban footprints around larger settlements."""
        overlay: dict[tuple[int, int], str] = {}
        for settlement in self.settlements:
            radius = self._urban_radius(settlement.population)
            if radius == 0:
                continue
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    if dx == 0 and dy == 0:
                        continue
                    distance = abs(dx) + abs(dy)
                    if distance > radius + 1:
                        continue
                    cell = (settlement.x + dx, settlement.y + dy)
                    if distance >= radius and settlement.population >= 320:
                        overlay[cell] = "%"
                    else:
                        overlay[cell] = "H"
        return overlay

    def landmark_cells(self, world: WorldMap) -> dict[tuple[int, int], str]:
        """Return major landmark overlays for settlements."""
        overlay: dict[tuple[int, int], str] = {}
        road_degree = self._road_degree()
        for settlement in self.settlements:
            if settlement.population >= 420:
                overlay[(settlement.x, settlement.y)] = "C"
                continue
            if road_degree.get(settlement.name, 0) >= 3 and settlement.population >= 180:
                overlay[(settlement.x, settlement.y)] = "M"
                continue
            if self._is_port(world, settlement):
                overlay[(settlement.x, settlement.y)] = "P"
                continue
            if settlement.decline_years >= 3 and settlement.population < 120:
                overlay[(settlement.x, settlement.y)] = "R"
        return overlay

    def road_status_counts(self) -> tuple[int, int]:
        """Return active and blocked road counts."""
        active = sum(1 for road in self.roads if road.blocked_years == 0)
        blocked = len(self.roads) - active
        return active, blocked

    def damaged_farm_cells(self) -> set[tuple[int, int]]:
        """Return visible drought-damaged farm cells."""
        cells: set[tuple[int, int]] = set()
        for settlement in self.settlements:
            if settlement.drought_years <= 0:
                continue
            radius = max(1, self._base_farm_radius(settlement.population))
            reduced = self._farm_radius(settlement)
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    if dx == 0 and dy == 0:
                        continue
                    if abs(dx) + abs(dy) > radius + 1:
                        continue
                    if abs(dx) <= reduced and abs(dy) <= reduced:
                        continue
                    cells.add((settlement.x + dx, settlement.y + dy))
        return cells

    def _ensure_initial_roads(self, world: WorldMap) -> None:
        if len(self.settlements) < 2:
            return
        ordered = sorted(self.settlements, key=lambda item: item.founded_year)
        for first, second in zip(ordered, ordered[1:]):
            self._ensure_road(world, first.name, second.name, second.founded_year)

    def _maybe_build_trade_road(self, world: WorldMap, year: int, rng: random.Random) -> str | None:
        if len(self.settlements) < 2 or len(self.roads) >= 14 or rng.random() >= 0.08:
            return None
        candidates = sorted(self.settlements, key=lambda item: item.population, reverse=True)
        for first in candidates:
            for second in candidates:
                if first.name == second.name:
                    continue
                if self._has_road(first.name, second.name):
                    continue
                distance = abs(first.x - second.x) + abs(first.y - second.y)
                if distance > 220:
                    continue
                if first.population < 140 or second.population < 110:
                    continue
                self._ensure_road(world, first.name, second.name, year)
                return f"Year {year}: merchants cut a road between {first.name} and {second.name}."
        return None

    def _ensure_road(self, world: WorldMap, a: str, b: str, year: int) -> None:
        if self._has_road(a, b):
            return
        positions = {settlement.name: settlement for settlement in self.settlements}
        first = positions.get(a)
        second = positions.get(b)
        if first is None or second is None:
            return
        self.roads.append(
            Road(
                a=a,
                b=b,
                built_year=year,
                path=self._route_between(world, first.x, first.y, second.x, second.y),
                condition=100,
                blocked_years=0,
            )
        )

    def _has_road(self, a: str, b: str) -> bool:
        return any({road.a, road.b} == {a, b} for road in self.roads)

    @staticmethod
    def _base_farm_radius(population: int) -> int:
        if population >= 260:
            return 4
        if population >= 180:
            return 3
        if population >= 110:
            return 2
        if population >= 70:
            return 1
        return 0

    @classmethod
    def _farm_radius(cls, settlement: Settlement) -> int:
        radius = cls._base_farm_radius(settlement.population)
        if settlement.drought_years > 0:
            return max(0, radius - 2)
        return radius

    def _road_degree(self) -> dict[str, int]:
        degree = {settlement.name: 0 for settlement in self.settlements}
        for road in self.roads:
            if road.blocked_years > 0:
                continue
            if road.a in degree:
                degree[road.a] += 1
            if road.b in degree:
                degree[road.b] += 1
        return degree

    @staticmethod
    def _is_port(world: WorldMap, settlement: Settlement) -> bool:
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                if dx == 0 and dy == 0:
                    continue
                x = settlement.x + dx
                y = settlement.y + dy
                if not (0 <= x < world.width and 0 <= y < world.height):
                    continue
                tile = world.tile_at(x, y)
                if tile.is_water or tile.biome == "coast":
                    return settlement.population >= 120
        return False

    def _advance_roads(self, world: WorldMap, year: int, rng: random.Random) -> list[str]:
        events: list[str] = []
        populations = {settlement.name: settlement.population for settlement in self.settlements}
        for road in self.roads:
            endpoint_pop = populations.get(road.a, 0) + populations.get(road.b, 0)
            if road.blocked_years > 0:
                road.blocked_years -= 1
                if road.blocked_years == 0:
                    events.append(self._restore_road(world, road, year, rng))
                continue

            decay = 0
            if endpoint_pop < 220:
                decay += rng.randint(3, 7)
            if year - road.built_year > 30:
                decay += rng.randint(1, 4)
            if rng.random() < 0.05:
                decay += rng.randint(2, 5)
            road.condition = max(20, road.condition - decay)

            if road.condition < 42 and rng.random() < 0.18:
                road.blocked_years = rng.randint(3, 7)
                events.append(f"Year {year}: the road between {road.a} and {road.b} falls into disrepair.")

        if rng.random() < 0.10:
            repair = self._repair_isolated_link(world, year, rng)
            if repair:
                events.append(repair)
        return events

    def _restore_road(self, world: WorldMap, road: Road, year: int, rng: random.Random) -> str:
        positions = {settlement.name: settlement for settlement in self.settlements}
        first = positions.get(road.a)
        second = positions.get(road.b)
        if first is None or second is None:
            return f"Year {year}: an abandoned road segment disappears."
        road.path = self._route_between(world, first.x, first.y, second.x, second.y)
        road.condition = min(100, road.condition + rng.randint(18, 30))
        return f"Year {year}: laborers reopen the road between {road.a} and {road.b}."

    def _repair_isolated_link(self, world: WorldMap, year: int, rng: random.Random) -> str | None:
        degree = self._road_degree()
        viable = [settlement for settlement in self.settlements if settlement.population >= 120 and degree.get(settlement.name, 0) == 0]
        if not viable:
            return None
        settlement = max(viable, key=lambda item: item.population)
        blocked_roads = [
            road for road in self.roads
            if road.blocked_years > 0 and settlement.name in {road.a, road.b}
        ]
        if blocked_roads:
            road = rng.choice(blocked_roads)
            road.blocked_years = 0
            return self._restore_road(world, road, year, rng)
        return None

    def _damage_road_from_conflict(
        self,
        world: WorldMap,
        year: int,
        rng: random.Random,
        first_name: str,
        second_name: str,
    ) -> str | None:
        candidates = [road for road in self.roads if road.blocked_years == 0 and ({road.a, road.b} & {first_name, second_name})]
        if not candidates or rng.random() >= 0.45:
            return None
        road = rng.choice(candidates)
        road.condition = max(20, road.condition - rng.randint(20, 35))
        if road.condition < 38:
            road.blocked_years = rng.randint(2, 5)
            return f"Year {year}: raiders sever the road between {road.a} and {road.b}."
        road.path = self._route_between(
            world,
            next(item.x for item in self.settlements if item.name == road.a),
            next(item.y for item in self.settlements if item.name == road.a),
            next(item.x for item in self.settlements if item.name == road.b),
            next(item.y for item in self.settlements if item.name == road.b),
        )
        return f"Year {year}: fighting damages the road between {road.a} and {road.b}."

    def _route_between(self, world: WorldMap, x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
        current = (x0, y0)
        goal = (x1, y1)
        path = [current]
        visited = {current}
        max_steps = max(abs(x1 - x0), abs(y1 - y0)) * 5 + 40

        while current != goal and len(path) < max_steps:
            candidates: list[tuple[float, tuple[int, int]]] = []
            for neighbor in self._neighbor_candidates(world, current[0], current[1]):
                if neighbor in visited:
                    continue
                score = self._road_step_cost(world, current, neighbor)
                score += abs(goal[0] - neighbor[0]) * 0.22 + abs(goal[1] - neighbor[1]) * 0.22
                if current[0] != goal[0] and neighbor[0] == current[0]:
                    score += 0.35
                if current[1] != goal[1] and neighbor[1] == current[1]:
                    score += 0.35
                candidates.append((score, neighbor))

            if not candidates:
                return self._fallback_line(x0, y0, x1, y1)

            candidates.sort(key=lambda item: item[0])
            current = candidates[0][1]
            visited.add(current)
            path.append(current)

        if current != goal:
            tail = self._fallback_line(current[0], current[1], x1, y1)
            path.extend(tail[1:])
        return path

    @staticmethod
    def _neighbor_candidates(world: WorldMap, x: int, y: int) -> list[tuple[int, int]]:
        points: list[tuple[int, int]] = []
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx = x + dx
                ny = y + dy
                if 0 <= nx < world.width and 0 <= ny < world.height:
                    points.append((nx, ny))
        return points

    def _road_step_cost(
        self,
        world: WorldMap,
        current: tuple[int, int],
        nxt: tuple[int, int],
    ) -> float:
        tile = world.tile_at(nxt[0], nxt[1])
        current_tile = world.tile_at(current[0], current[1])
        diagonal = 1.4 if nxt[0] != current[0] and nxt[1] != current[1] else 1.0
        elevation_change = max(0.0, tile.elevation - current_tile.elevation)
        cost = diagonal
        if tile.is_water:
            cost += 9.0
        if tile.is_river:
            cost += 1.6
        if tile.biome == "mountain":
            cost += 4.0
        elif tile.biome == "snow":
            cost += 5.0
        elif tile.biome == "wetlands":
            cost += 2.4
        elif tile.biome == "forest":
            cost += 0.9
        cost += elevation_change * 12.0
        return cost

    @staticmethod
    def _fallback_line(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
        cells: list[tuple[int, int]] = []
        dx = abs(x1 - x0)
        sx = 1 if x0 < x1 else -1
        dy = -abs(y1 - y0)
        sy = 1 if y0 < y1 else -1
        error = dx + dy
        while True:
            cells.append((x0, y0))
            if x0 == x1 and y0 == y1:
                return cells
            doubled = 2 * error
            if doubled >= dy:
                error += dy
                x0 += sx
            if doubled <= dx:
                error += dx
                y0 += sy

    def _should_found_colony(self, rng: random.Random) -> bool:
        if len(self.settlements) >= 30:
            return False
        if not self.settlements:
            return False
        return max(settlement.population for settlement in self.settlements) >= 180 and rng.random() < 0.18

    @staticmethod
    def _urban_radius(population: int) -> int:
        if population >= 700:
            return 5
        if population >= 420:
            return 4
        if population >= 240:
            return 3
        if population >= 95:
            return 2
        return 0

    def _find_colony_site(
        self,
        world: WorldMap,
        origin_x: int,
        origin_y: int,
        rng: random.Random,
    ) -> tuple[int, int] | None:
        for _ in range(80):
            x = min(max(origin_x + rng.randint(-120, 120), 0), world.width - 1)
            y = min(max(origin_y + rng.randint(-80, 80), 0), world.height - 1)
            tile = world.tile_at(x, y)
            if tile.is_water or tile.biome in {"snow", "mountain"}:
                continue
            if any(abs(existing.x - x) < 25 and abs(existing.y - y) < 18 for existing in self.settlements):
                continue
            return x, y
        return None

    @staticmethod
    def _next_name(rng: random.Random) -> str:
        prefixes = ("Ash", "Stone", "River", "North", "South", "High", "Low", "Red")
        suffixes = ("ford", "watch", "mere", "gate", "fall", "haven", "field", "crest")
        return f"{rng.choice(prefixes)}{rng.choice(suffixes)}"
