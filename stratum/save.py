"""Save and load helpers for Stratum."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import json
import os
from pathlib import Path

from .civ import CivLayer
from .geo import GeologyLayer
from .world import WorldMap


def save_dir() -> Path:
    """Return the default save directory."""
    override = os.environ.get("STRATUM_SAVE_DIR")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".local" / "share" / "stratum"


@dataclass(slots=True)
class SaveGame:
    """Serializable snapshot of simulation and UI state."""

    world: WorldMap
    geo: GeologyLayer
    civ: CivLayer
    history: list[str]
    viewport: dict[str, int | bool | str]
    rng_state: object
    path: Path | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize the save game to plain JSON-compatible data."""
        return {
            "world": self.world.to_dict(),
            "geo": self.geo.to_dict(),
            "civ": self.civ.to_dict(),
            "history": self.history,
            "viewport": self.viewport,
            "rng_state": repr(self.rng_state),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object], path: Path | None = None) -> "SaveGame":
        """Rebuild a save game from persisted data."""
        return cls(
            world=WorldMap.from_dict(dict(data.get("world", {}))),
            geo=GeologyLayer.from_dict(dict(data.get("geo", {}))),
            civ=CivLayer.from_dict(dict(data.get("civ", {}))),
            history=[str(item) for item in list(data.get("history", []))],
            viewport={str(key): value for key, value in dict(data.get("viewport", {})).items()},
            rng_state=ast.literal_eval(str(data.get("rng_state", repr((3, (), None))))),
            path=path,
        )


def default_save_path(world: WorldMap, year: int) -> Path:
    """Build a default save filename for the current world/year."""
    return save_dir() / f"seed-{world.seed}-year-{year}.json"


def latest_save_path() -> Path | None:
    """Return the most recently modified save file, if one exists."""
    directory = save_dir()
    if not directory.exists():
        return None
    candidates = sorted(directory.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    return candidates[0] if candidates else None


def write_save(save_game: SaveGame, path: Path | None = None) -> Path:
    """Write a save file to disk and return its path."""
    target = path or default_save_path(save_game.world, int(save_game.viewport.get("year", 0)))
    target = target.expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(save_game.to_dict(), indent=2), encoding="utf-8")
    save_game.path = target
    return target


def read_save(path: Path) -> SaveGame:
    """Load a save file from disk."""
    payload = json.loads(path.expanduser().read_text(encoding="utf-8"))
    return SaveGame.from_dict(payload, path=path.expanduser())
