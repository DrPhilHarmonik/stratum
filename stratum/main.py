"""Command-line entrypoint for Stratum."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import random
import sys

from .civ import CivLayer
from .geo import GeologyLayer
from .render import launch_viewport, render_summary, viewport_from_dict
from .save import latest_save_path, read_save, save_dir
from .world import WorldMap


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stratum",
        description="Bootstrap build of a terminal-first world simulation.",
    )
    parser.add_argument(
        "--load",
        nargs="?",
        const="__LATEST__",
        metavar="FILE",
        help="load the most recent save or a specific save file",
    )
    parser.add_argument(
        "--seed",
        type=int,
        help="generate a deterministic bootstrap world",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="print a textual summary instead of launching the curses viewport",
    )
    return parser


def resolve_load_path(load_value: str | None) -> Path | None:
    """Resolve a load target into a concrete path."""
    if load_value is None:
        return None
    if load_value == "__LATEST__":
        latest = latest_save_path()
        if latest is None:
            raise FileNotFoundError(f"no save files found in {save_dir()}")
        return latest
    return Path(load_value).expanduser()


def run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    history: list[str] | None = None
    state = None
    rng_state = None
    load_notice = None

    try:
        if args.load is not None:
            load_path = resolve_load_path(args.load)
            save_game = read_save(load_path)
            world = save_game.world
            geo = save_game.geo
            civ = save_game.civ
            history = save_game.history
            state = viewport_from_dict(save_game.viewport, world, message=f"loaded {load_path}")
            rng_state = save_game.rng_state
            load_notice = f"loaded {load_path}"
        else:
            seed = args.seed if args.seed is not None else random.randint(0, 999_999)
            world = WorldMap.generate(seed)
            geo = GeologyLayer()
            civ = CivLayer()
            civ.seed_demo_data(world)
    except (FileNotFoundError, OSError, ValueError, SyntaxError, KeyError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    interactive = not args.summary and sys.stdin.isatty() and sys.stdout.isatty()
    if interactive:
        return launch_viewport(world, geo, civ, load_notice, history, state, rng_state)

    summary = render_summary(world, geo, civ, state, history)
    if load_notice:
        summary = f"{summary}\n{load_notice}"
    print(summary)
    return 0
