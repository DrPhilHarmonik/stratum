"""Rendering helpers for the bootstrap and first interactive build."""

from __future__ import annotations

import curses
from dataclasses import dataclass, field
import random
import time

from .civ import CivLayer
from .geo import GeologyLayer
from .save import SaveGame, write_save
from .world import WorldMap


def render_summary(
    world: WorldMap,
    geo: GeologyLayer,
    civ: CivLayer,
    state: ViewportState | None = None,
    history: list[str] | None = None,
) -> str:
    """Return a textual summary for non-interactive runs."""
    lines = [
        "STRATUM bootstrap build",
        f"seed: {world.seed}",
        f"world: {world.width}x{world.height} ({world.continent_style})",
        f"land coverage: {world.land_coverage:.1%}",
        f"river cells: {world.river_cells}",
        f"erosion/year: {geo.erosion_rate_per_year}",
        f"volcanic chance/year: {geo.volcanic_event_chance_per_year:.1%}",
        f"settlements: {len(civ.settlements)}",
        f"total population: {civ.total_population()}",
    ]
    if state is not None:
        lines.extend(
            [
                f"year: {state.year}",
                f"simulation: {'paused' if state.paused else 'running'} at speed {SPEED_LEVELS[state.speed_index]}",
                f"cursor: {state.cursor_x},{state.cursor_y} at zoom {ZOOM_LEVELS[state.zoom_index]}x",
            ]
        )
    if history:
        lines.append(f"latest event: {history[-1]}")
    lines.extend(
        [
            "",
            "Interactive mode is available when launched from a real terminal.",
        ]
    )
    return "\n".join(lines)


@dataclass(slots=True)
class ViewportState:
    """Track cursor, camera, and zoom for the curses viewport."""

    cursor_x: int
    cursor_y: int
    camera_x: int
    camera_y: int
    zoom_index: int = 1
    paused: bool = False
    speed_index: int = 2
    show_log: bool = False
    show_settlements: bool = False
    settlement_index: int = 0
    log_scroll: int = 0
    tick_count: int = 0
    year: int = 0
    message: str = ""
    overlay_cache_tick: int = -1
    cached_road_positions: dict[tuple[int, int], str] = field(default_factory=dict, repr=False)
    cached_urban_positions: dict[tuple[int, int], str] = field(default_factory=dict, repr=False)
    cached_landmark_positions: dict[tuple[int, int], str] = field(default_factory=dict, repr=False)
    cached_farm_positions: set[tuple[int, int]] = field(default_factory=set, repr=False)
    cached_damaged_farm_positions: set[tuple[int, int]] = field(default_factory=set, repr=False)
    cached_road_count: int = 0
    cached_farm_count: int = 0
    cached_active_roads: int = 0
    cached_blocked_roads: int = 0
    cached_drought_count: int = 0
    minimap_cache_key: tuple[int, int, int] | None = None
    minimap_cache: list[list[tuple[str, str]]] = field(default_factory=list, repr=False)
    settlement_list_cache_tick: int = -1
    settlement_list_cache: list = field(default_factory=list, repr=False)


ZOOM_LEVELS = (1, 2, 4, 8)
SPEED_LEVELS = (1, 2, 4, 8)
TICKS_PER_YEAR = 4
COLOR_IDS = {
    "ocean": 1,
    "coast": 2,
    "river": 3,
    "desert": 4,
    "plains": 5,
    "forest": 6,
    "wetlands": 7,
    "mountain": 8,
    "snow": 9,
    "settlement": 10,
    "road": 11,
    "farm": 12,
    "damaged_farm": 13,
    "broken_road": 14,
    "urban": 15,
    "wall": 16,
    "port": 17,
    "market": 18,
    "citadel": 19,
    "ruin": 20,
    "minimap_frame": 21,
    "minimap_view": 22,
}


def launch_viewport(
    world: WorldMap,
    geo: GeologyLayer,
    civ: CivLayer,
    load_notice: str | None = None,
    history: list[str] | None = None,
    state: ViewportState | None = None,
    rng_state: object | None = None,
) -> int:
    """Start the curses viewport."""

    def _main(stdscr: curses.window) -> int:
        return _run_curses(stdscr, world, geo, civ, load_notice, history, state, rng_state)

    return curses.wrapper(_main)


def _run_curses(
    stdscr: curses.window,
    world: WorldMap,
    geo: GeologyLayer,
    civ: CivLayer,
    load_notice: str | None,
    initial_history: list[str] | None,
    initial_state: ViewportState | None,
    initial_rng_state: object | None,
) -> int:
    curses.curs_set(0)
    stdscr.nodelay(False)
    stdscr.keypad(True)
    _init_colors()
    starting_settlement = civ.settlements[0] if civ.settlements else None
    rng = random.Random(world.seed)
    if initial_rng_state is not None:
        rng.setstate(initial_rng_state)
    history = initial_history[:] if initial_history is not None else _seed_history(civ)

    state = initial_state or ViewportState(
        cursor_x=starting_settlement.x if starting_settlement else world.width // 2,
        cursor_y=starting_settlement.y if starting_settlement else world.height // 2,
        camera_x=max(0, (starting_settlement.x if starting_settlement else world.width // 2) - 20),
        camera_y=max(0, (starting_settlement.y if starting_settlement else world.height // 2) - 8),
        message="Arrows move 1 cell, WASD move 10, z/x zoom, +/- speed, g cities, l log, S save, r regenerate, q quit.",
    )
    if load_notice:
        state.message = load_notice

    current_world = world
    current_civ = civ
    last_frame = time.monotonic()
    stdscr.timeout(120)

    while True:
        now = time.monotonic()
        if not state.paused:
            elapsed = now - last_frame
            if elapsed >= 0.12:
                steps = max(1, int(elapsed / 0.12))
                for _ in range(steps):
                    _advance_simulation(current_world, geo, current_civ, state, history, rng)
                last_frame = now
        else:
            last_frame = now

        _draw_frame(stdscr, current_world, geo, current_civ, state, history)
        key = stdscr.getch()

        if key in (ord("q"), ord("Q")):
            return 0
        if key == curses.KEY_RESIZE:
            continue
        if key in (ord("p"), ord("P"), ord(" ")):
            state.paused = not state.paused
            state.message = "paused" if state.paused else "running"
            continue
        if key in (ord("+"), ord("=")):
            state.speed_index = min(len(SPEED_LEVELS) - 1, state.speed_index + 1)
            state.message = f"speed: {SPEED_LEVELS[state.speed_index]} tick/frame"
            continue
        if key == ord("-"):
            state.speed_index = max(0, state.speed_index - 1)
            state.message = f"speed: {SPEED_LEVELS[state.speed_index]} tick/frame"
            continue
        if key in (ord("l"), ord("L")):
            state.show_log = not state.show_log
            state.show_settlements = False
            state.log_scroll = 0
            state.message = "history log open" if state.show_log else ""
            continue
        if key in (ord("g"), ord("G")):
            state.show_settlements = not state.show_settlements
            state.show_log = False
            state.message = "settlement list open" if state.show_settlements else ""
            continue
        if state.show_log and key in (curses.KEY_UP, ord("k"), ord("K")):
            state.log_scroll = min(state.log_scroll + 1, max(0, len(history) - 1))
            continue
        if state.show_log and key in (curses.KEY_DOWN, ord("j"), ord("J")):
            state.log_scroll = max(0, state.log_scroll - 1)
            continue
        if state.show_settlements and key in (curses.KEY_UP, ord("k"), ord("K")):
            state.settlement_index = max(0, state.settlement_index - 1)
            continue
        if state.show_settlements and key in (curses.KEY_DOWN, ord("j"), ord("J")):
            state.settlement_index = min(max(0, len(current_civ.settlements) - 1), state.settlement_index + 1)
            continue
        if state.show_settlements and key in (10, 13, curses.KEY_ENTER):
            _jump_to_settlement(current_world, current_civ, state)
            state.show_settlements = False
            state.message = "jumped to selected settlement"
            continue
        if key in (curses.KEY_LEFT, curses.KEY_RIGHT, curses.KEY_UP, curses.KEY_DOWN):
            dx, dy = {
                curses.KEY_LEFT: (-1, 0),
                curses.KEY_RIGHT: (1, 0),
                curses.KEY_UP: (0, -1),
                curses.KEY_DOWN: (0, 1),
            }[key]
            _move_cursor(current_world, state, dx, dy)
            continue
        if key in (ord("w"), ord("a"), ord("s"), ord("d")):
            dx, dy = {
                ord("a"): (-10, 0),
                ord("d"): (10, 0),
                ord("w"): (0, -10),
                ord("s"): (0, 10),
            }[key]
            _move_cursor(current_world, state, dx, dy)
            continue
        if key in (ord("z"), ord("Z")):
            state.zoom_index = max(0, state.zoom_index - 1)
            state.message = f"zoom: {ZOOM_LEVELS[state.zoom_index]}x"
            continue
        if key in (ord("x"), ord("X")):
            state.zoom_index = min(len(ZOOM_LEVELS) - 1, state.zoom_index + 1)
            state.message = f"zoom: {ZOOM_LEVELS[state.zoom_index]}x"
            continue
        if key in (ord("r"), ord("R")):
            new_seed = random.randint(0, 999_999)
            current_world = WorldMap.generate(new_seed)
            current_civ = CivLayer()
            current_civ.seed_demo_data(current_world)
            rng = random.Random(new_seed)
            history = _seed_history(current_civ)
            starting_settlement = current_civ.settlements[0] if current_civ.settlements else None
            state.cursor_x = starting_settlement.x if starting_settlement else current_world.width // 2
            state.cursor_y = starting_settlement.y if starting_settlement else current_world.height // 2
            state.camera_x = max(0, state.cursor_x - 20)
            state.camera_y = max(0, state.cursor_y - 8)
            state.tick_count = 0
            state.year = 0
            state.paused = False
            state.show_log = False
            state.show_settlements = False
            state.settlement_index = 0
            state.log_scroll = 0
            state.message = f"regenerated world with seed {new_seed}"
            continue
        if key == ord("S"):
            save_game = SaveGame(
                world=current_world,
                geo=geo,
                civ=current_civ,
                history=history[:],
                viewport=_viewport_to_dict(state),
                rng_state=rng.getstate(),
            )
            path = write_save(save_game)
            state.message = f"saved to {path}"
            continue

        if key != -1:
            state.message = "Supported keys: arrows, WASD, z/x, +/-, g, l, S, r, q."


def _draw_frame(
    stdscr: curses.window,
    world: WorldMap,
    geo: GeologyLayer,
    civ: CivLayer,
    state: ViewportState,
    history: list[str],
) -> None:
    stdscr.erase()
    height, width = stdscr.getmaxyx()
    map_height = max(1, height - 2)
    zoom = ZOOM_LEVELS[state.zoom_index]
    _clamp_camera(world, state, width, map_height, zoom)

    if state.show_log:
        _draw_history(stdscr, height, width, history, state)
        stdscr.refresh()
        return

    _refresh_overlay_cache(world, civ, state)
    settlement_positions = {(settlement.x, settlement.y): settlement for settlement in civ.settlements}
    road_positions = state.cached_road_positions
    urban_positions = state.cached_urban_positions
    landmark_positions = state.cached_landmark_positions
    farm_positions = state.cached_farm_positions
    damaged_farm_positions = state.cached_damaged_farm_positions
    for screen_y in range(map_height):
        world_y = min(state.camera_y + screen_y * zoom, world.height - 1)
        for screen_x in range(width):
            world_x = min(state.camera_x + screen_x * zoom, world.width - 1)
            tile = world.tile_at(world_x, world_y)
            settlement = settlement_positions.get((world_x, world_y))
            overlay = road_positions.get((world_x, world_y))
            landmark = landmark_positions.get((world_x, world_y))
            if landmark:
                glyph = landmark
                attr = _color_attr(
                    {
                        "P": "port",
                        "M": "market",
                        "C": "citadel",
                        "R": "ruin",
                    }[landmark]
                )
            elif settlement:
                glyph = civ.settlement_glyph(settlement)
                attr = _color_attr("settlement")
            elif (world_x, world_y) in urban_positions and not tile.is_water:
                glyph = urban_positions[(world_x, world_y)]
                attr = _color_attr("wall" if glyph == "%" else "urban")
            elif overlay:
                glyph = overlay if overlay != "+" else ("+" if not tile.is_river else "#")
                attr = _color_attr("broken_road" if overlay == "x" else "road")
            elif (world_x, world_y) in damaged_farm_positions and not tile.is_water:
                glyph = "x"
                attr = _color_attr("damaged_farm")
            elif (world_x, world_y) in farm_positions and not tile.is_water:
                glyph = ":"
                attr = _color_attr("farm")
            else:
                glyph = tile.glyph
                attr = _color_attr(tile.biome)
            if _cursor_in_cell(state.cursor_x, state.cursor_y, world_x, world_y, zoom):
                attr |= curses.A_REVERSE
            try:
                stdscr.addstr(screen_y, screen_x, glyph, attr)
            except curses.error:
                pass

    tile = world.tile_at(state.cursor_x, state.cursor_y)
    settlement = next((item for item in civ.settlements if item.x == state.cursor_x and item.y == state.cursor_y), None)
    status = (
        f"seed {world.seed} | year {state.year} | {'paused' if state.paused else 'running'} | speed {SPEED_LEVELS[state.speed_index]} | "
        f"pop {civ.total_population()} | cursor {state.cursor_x},{state.cursor_y} | zoom {zoom}x | "
        f"biome {tile.biome} | elev {tile.elevation:.2f} | moist {tile.moisture:.2f}"
    )
    if settlement:
        status += f" | settlement {settlement.name} pop {settlement.population}"
    status += (
        f" | roads {state.cached_active_roads}/{len(civ.roads)} active ({state.cached_road_count} cells)"
        f" | blocked {state.cached_blocked_roads} | farms {state.cached_farm_count} | droughts {state.cached_drought_count}"
    )
    status += f" | erosion {geo.erosion_rate_per_year}"
    help_line = state.message
    _add_line(stdscr, map_height, status, curses.A_BOLD)
    _add_line(stdscr, map_height + 1, help_line, curses.A_DIM)
    _draw_minimap(stdscr, world, civ, state, width, map_height)
    if state.show_settlements:
        _draw_settlement_list(stdscr, world, civ, state, width, map_height)
    stdscr.refresh()


def _move_cursor(world: WorldMap, state: ViewportState, dx: int, dy: int) -> None:
    state.cursor_x = min(max(state.cursor_x + dx, 0), world.width - 1)
    state.cursor_y = min(max(state.cursor_y + dy, 0), world.height - 1)
    state.message = ""


def _advance_simulation(
    world: WorldMap,
    geo: GeologyLayer,
    civ: CivLayer,
    state: ViewportState,
    history: list[str],
    rng: random.Random,
) -> None:
    ticks = SPEED_LEVELS[state.speed_index]
    for _ in range(ticks):
        state.tick_count += 1
        if state.tick_count % TICKS_PER_YEAR != 0:
            continue
        state.year += 1
        events = civ.advance_year(world, state.year, rng)
        events.extend(geo.advance_year(world, civ, state.year, rng))
        if not events and state.year % 5 == 0:
            events.append(f"Year {state.year}: the world settles into another quiet decade.")
        history.extend(events)
        history[:] = history[-200:]
        if events:
            state.message = events[-1]


def _refresh_overlay_cache(world: WorldMap, civ: CivLayer, state: ViewportState) -> None:
    if state.overlay_cache_tick == state.tick_count:
        return
    state.cached_road_positions = civ.road_cells(world)
    state.cached_urban_positions = civ.urban_cells()
    state.cached_landmark_positions = civ.landmark_cells(world)
    farm_positions: set[tuple[int, int]] = set()
    for settlement in civ.settlements:
        farm_positions.update(civ.farm_cells(settlement))
    state.cached_farm_positions = farm_positions
    state.cached_damaged_farm_positions = civ.damaged_farm_cells()
    state.cached_road_count = len(state.cached_road_positions)
    state.cached_farm_count = len(state.cached_farm_positions)
    state.cached_active_roads, state.cached_blocked_roads = civ.road_status_counts()
    state.cached_drought_count = sum(1 for item in civ.settlements if item.drought_years > 0)
    state.overlay_cache_tick = state.tick_count
    state.settlement_list_cache_tick = -1


def _viewport_to_dict(state: ViewportState) -> dict[str, int | bool | str]:
    """Serialize viewport state for save files."""
    return {
        "cursor_x": state.cursor_x,
        "cursor_y": state.cursor_y,
        "camera_x": state.camera_x,
        "camera_y": state.camera_y,
        "zoom_index": state.zoom_index,
        "paused": state.paused,
        "speed_index": state.speed_index,
        "show_log": state.show_log,
        "show_settlements": state.show_settlements,
        "settlement_index": state.settlement_index,
        "log_scroll": state.log_scroll,
        "tick_count": state.tick_count,
        "year": state.year,
        "message": state.message,
    }


def viewport_from_dict(data: dict[str, object], world: WorldMap, message: str = "") -> ViewportState:
    """Rebuild viewport state from persisted data."""
    state = ViewportState(
        cursor_x=int(data.get("cursor_x", world.width // 2)),
        cursor_y=int(data.get("cursor_y", world.height // 2)),
        camera_x=int(data.get("camera_x", max(0, world.width // 2 - 20))),
        camera_y=int(data.get("camera_y", max(0, world.height // 2 - 8))),
        zoom_index=int(data.get("zoom_index", 1)),
        paused=bool(data.get("paused", False)),
        speed_index=int(data.get("speed_index", 2)),
        show_log=bool(data.get("show_log", False)),
        show_settlements=bool(data.get("show_settlements", False)),
        settlement_index=int(data.get("settlement_index", 0)),
        log_scroll=int(data.get("log_scroll", 0)),
        tick_count=int(data.get("tick_count", 0)),
        year=int(data.get("year", 0)),
        message=str(data.get("message", "")),
    )
    state.zoom_index = min(max(state.zoom_index, 0), len(ZOOM_LEVELS) - 1)
    state.speed_index = min(max(state.speed_index, 0), len(SPEED_LEVELS) - 1)
    state.cursor_x = min(max(state.cursor_x, 0), world.width - 1)
    state.cursor_y = min(max(state.cursor_y, 0), world.height - 1)
    state.camera_x = min(max(state.camera_x, 0), world.width - 1)
    state.camera_y = min(max(state.camera_y, 0), world.height - 1)
    if message:
        state.message = message
    return state


def _seed_history(civ: CivLayer) -> list[str]:
    history = ["Year 0: the world is generated."]
    for settlement in sorted(civ.settlements, key=lambda item: item.founded_year):
        history.append(f"Year {settlement.founded_year}: {settlement.name} is founded.")
    return history


def _draw_history(
    stdscr: curses.window,
    height: int,
    width: int,
    history: list[str],
    state: ViewportState,
) -> None:
    title = f"History Log | entries {len(history)} | scroll {state.log_scroll} | l closes"
    _add_line(stdscr, 0, title, curses.A_BOLD)
    visible_rows = max(1, height - 2)
    max_offset = max(0, len(history) - visible_rows)
    offset = min(state.log_scroll, max_offset)
    start = max(0, len(history) - visible_rows - offset)
    lines = history[start : start + visible_rows]
    for index, line in enumerate(lines, start=1):
        _add_line(stdscr, index, line[: max(0, width - 1)], curses.A_NORMAL)
    footer = "Up/Down or j/k scroll. p pauses simulation in background. q quits."
    _add_line(stdscr, height - 1, footer, curses.A_DIM)


def _draw_settlement_list(
    stdscr: curses.window,
    world: WorldMap,
    civ: CivLayer,
    state: ViewportState,
    width: int,
    map_height: int,
) -> None:
    settlements = _settlement_list(state, civ)
    if not settlements:
        return
    state.settlement_index = min(state.settlement_index, len(settlements) - 1)
    panel_width = min(34, max(24, width // 3))
    start_x = max(0, width - panel_width)
    visible_rows = max(4, min(map_height - 2, 10))
    start_index = min(max(0, state.settlement_index - visible_rows // 2), max(0, len(settlements) - visible_rows))
    landmark_positions = state.cached_landmark_positions
    _draw_box(stdscr, 0, start_x, visible_rows + 1, panel_width, "Settlements (g)")
    for row, settlement in enumerate(settlements[start_index : start_index + visible_rows], start=1):
        actual_index = start_index + row - 1
        landmark = landmark_positions.get((settlement.x, settlement.y), " ")
        prefix = ">" if actual_index == state.settlement_index else " "
        text = f"{prefix} {landmark:1} {settlement.name[:12]:12} {settlement.population:4}"
        attr = curses.A_REVERSE if actual_index == state.settlement_index else curses.A_NORMAL
        _add_at(stdscr, row, start_x + 1, text[: panel_width - 2], attr)


def _draw_minimap(
    stdscr: curses.window,
    world: WorldMap,
    civ: CivLayer,
    state: ViewportState,
    width: int,
    map_height: int,
) -> None:
    mini_w = min(22, max(16, width // 5))
    mini_h = min(10, max(6, map_height // 4))
    start_x = max(0, width - mini_w - 1)
    start_y = max(0, map_height - mini_h - 1)
    if start_y < 0:
        return
    _draw_box(stdscr, start_y, start_x, mini_h, mini_w, "Map")
    inner_w = max(2, mini_w - 2)
    inner_h = max(2, mini_h - 2)
    key = (world.seed, inner_w, inner_h)
    if state.minimap_cache_key != key:
        cache: list[list[tuple[str, str]]] = []
        for sy in range(inner_h):
            row: list[tuple[str, str]] = []
            world_y = min(world.height - 1, int((sy / max(1, inner_h - 1)) * (world.height - 1)))
            for sx in range(inner_w):
                world_x = min(world.width - 1, int((sx / max(1, inner_w - 1)) * (world.width - 1)))
                tile = world.tile_at(world_x, world_y)
                row.append(("~" if tile.is_water else ".", "ocean" if tile.is_water else "plains"))
            cache.append(row)
        state.minimap_cache = cache
        state.minimap_cache_key = key
    for sy, row in enumerate(state.minimap_cache):
        for sx, (glyph, color_name) in enumerate(row):
            _add_at(stdscr, start_y + 1 + sy, start_x + 1 + sx, glyph, _color_attr(color_name))

    for settlement in civ.settlements:
        sx = min(inner_w - 1, max(0, int(settlement.x / max(1, world.width - 1) * (inner_w - 1))))
        sy = min(inner_h - 1, max(0, int(settlement.y / max(1, world.height - 1) * (inner_h - 1))))
        _add_at(stdscr, start_y + 1 + sy, start_x + 1 + sx, "*", _color_attr("settlement"))

    zoom = ZOOM_LEVELS[state.zoom_index]
    view_left = int(state.camera_x / max(1, world.width - 1) * (inner_w - 1))
    view_top = int(state.camera_y / max(1, world.height - 1) * (inner_h - 1))
    view_right = int(min(world.width - 1, state.camera_x + width * zoom) / max(1, world.width - 1) * (inner_w - 1))
    view_bottom = int(min(world.height - 1, state.camera_y + map_height * zoom) / max(1, world.height - 1) * (inner_h - 1))
    for sx in range(view_left, min(inner_w, view_right + 1)):
        _add_at(stdscr, start_y + 1 + max(0, view_top), start_x + 1 + sx, "-", _color_attr("minimap_view"))
        _add_at(stdscr, start_y + 1 + min(inner_h - 1, view_bottom), start_x + 1 + sx, "-", _color_attr("minimap_view"))
    for sy in range(view_top, min(inner_h, view_bottom + 1)):
        _add_at(stdscr, start_y + 1 + sy, start_x + 1 + max(0, view_left), "|", _color_attr("minimap_view"))
        _add_at(stdscr, start_y + 1 + sy, start_x + 1 + min(inner_w - 1, view_right), "|", _color_attr("minimap_view"))


def _jump_to_settlement(world: WorldMap, civ: CivLayer, state: ViewportState) -> None:
    settlements = _settlement_list(state, civ)
    if not settlements:
        return
    settlement = settlements[min(state.settlement_index, len(settlements) - 1)]
    state.cursor_x = settlement.x
    state.cursor_y = settlement.y
    state.camera_x = max(0, settlement.x - 20)
    state.camera_y = max(0, settlement.y - 8)


def _settlement_list(state: ViewportState, civ: CivLayer) -> list:
    if state.settlement_list_cache_tick != state.tick_count:
        state.settlement_list_cache = sorted(civ.settlements, key=lambda item: item.population, reverse=True)
        state.settlement_list_cache_tick = state.tick_count
    return state.settlement_list_cache


def _draw_box(stdscr: curses.window, y: int, x: int, height: int, width: int, title: str) -> None:
    if height < 2 or width < 4:
        return
    horizontal = "-" * max(0, width - 2)
    _add_at(stdscr, y, x, f"+{horizontal}+", _color_attr("minimap_frame"))
    for row in range(1, max(1, height - 1)):
        _add_at(stdscr, y + row, x, "|", _color_attr("minimap_frame"))
        _add_at(stdscr, y + row, x + width - 1, "|", _color_attr("minimap_frame"))
    _add_at(stdscr, y + height - 1, x, f"+{horizontal}+", _color_attr("minimap_frame"))
    if title:
        _add_at(stdscr, y, x + 2, title[: max(0, width - 4)], _color_attr("minimap_frame"))


def _add_at(stdscr: curses.window, y: int, x: int, text: str, attr: int) -> None:
    try:
        stdscr.addstr(y, x, text, attr)
    except curses.error:
        pass


def _clamp_camera(world: WorldMap, state: ViewportState, screen_width: int, map_height: int, zoom: int) -> None:
    visible_world_width = max(1, screen_width * zoom)
    visible_world_height = max(1, map_height * zoom)

    left_margin = state.camera_x + zoom * 2
    right_margin = state.camera_x + visible_world_width - zoom * 3
    top_margin = state.camera_y + zoom
    bottom_margin = state.camera_y + visible_world_height - zoom * 2

    if state.cursor_x < left_margin:
        state.camera_x = max(0, state.cursor_x - zoom * 2)
    elif state.cursor_x > right_margin:
        state.camera_x = min(world.width - visible_world_width, state.cursor_x - visible_world_width + zoom * 3)

    if state.cursor_y < top_margin:
        state.camera_y = max(0, state.cursor_y - zoom)
    elif state.cursor_y > bottom_margin:
        state.camera_y = min(world.height - visible_world_height, state.cursor_y - visible_world_height + zoom * 2)

    state.camera_x = min(max(state.camera_x, 0), max(0, world.width - visible_world_width))
    state.camera_y = min(max(state.camera_y, 0), max(0, world.height - visible_world_height))


def _cursor_in_cell(cursor_x: int, cursor_y: int, world_x: int, world_y: int, zoom: int) -> bool:
    return world_x <= cursor_x < world_x + zoom and world_y <= cursor_y < world_y + zoom


def _add_line(stdscr: curses.window, y: int, text: str, attr: int) -> None:
    _, width = stdscr.getmaxyx()
    try:
        stdscr.addstr(y, 0, text[: max(0, width - 1)], attr)
    except curses.error:
        pass


def _init_colors() -> None:
    if not curses.has_colors():
        return
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(COLOR_IDS["ocean"], curses.COLOR_BLUE, -1)
    curses.init_pair(COLOR_IDS["coast"], curses.COLOR_CYAN, -1)
    curses.init_pair(COLOR_IDS["river"], curses.COLOR_CYAN, -1)
    curses.init_pair(COLOR_IDS["desert"], curses.COLOR_YELLOW, -1)
    curses.init_pair(COLOR_IDS["plains"], curses.COLOR_GREEN, -1)
    curses.init_pair(COLOR_IDS["forest"], curses.COLOR_GREEN, -1)
    curses.init_pair(COLOR_IDS["wetlands"], curses.COLOR_MAGENTA, -1)
    curses.init_pair(COLOR_IDS["mountain"], curses.COLOR_WHITE, -1)
    curses.init_pair(COLOR_IDS["snow"], curses.COLOR_WHITE, -1)
    curses.init_pair(COLOR_IDS["settlement"], curses.COLOR_RED, -1)
    curses.init_pair(COLOR_IDS["road"], curses.COLOR_YELLOW, -1)
    curses.init_pair(COLOR_IDS["farm"], curses.COLOR_GREEN, -1)
    curses.init_pair(COLOR_IDS["damaged_farm"], curses.COLOR_RED, -1)
    curses.init_pair(COLOR_IDS["broken_road"], curses.COLOR_MAGENTA, -1)
    curses.init_pair(COLOR_IDS["urban"], curses.COLOR_CYAN, -1)
    curses.init_pair(COLOR_IDS["wall"], curses.COLOR_WHITE, -1)
    curses.init_pair(COLOR_IDS["port"], curses.COLOR_BLUE, -1)
    curses.init_pair(COLOR_IDS["market"], curses.COLOR_YELLOW, -1)
    curses.init_pair(COLOR_IDS["citadel"], curses.COLOR_WHITE, -1)
    curses.init_pair(COLOR_IDS["ruin"], curses.COLOR_MAGENTA, -1)
    curses.init_pair(COLOR_IDS["minimap_frame"], curses.COLOR_WHITE, -1)
    curses.init_pair(COLOR_IDS["minimap_view"], curses.COLOR_CYAN, -1)


def _color_attr(biome: str) -> int:
    if not curses.has_colors():
        return curses.A_NORMAL
    color_id = COLOR_IDS.get(biome)
    if color_id is None:
        return curses.A_NORMAL
    return curses.color_pair(color_id)
