"""
STRATUM -- geographic world simulation
Run:  python3 -m stratum
Load: python3 -m stratum --load [file]   (omit file for latest save)

Controls
  Arrow keys          move cursor 1 cell
  WASD                move cursor 10 cells (fast pan)
  z / x               zoom in / out
  +/-                 speed up / slow down
  p / Space           pause
  l                   open/close scrollable history log
    up/down / j/k     scroll log
    PgUp/PgDn         scroll log by page
  f                   found a settlement at cursor
  c                   trigger a conflict between nearby settlements
  e                   trigger a drought
  v                   trigger a volcanic eruption at cursor
  S                   save world
  r                   regenerate world
  q                   quit
"""

import argparse
import curses
import random
import time

from .world  import WorldMap, WORLD_W, WORLD_H
from .geo    import GeologyLayer
from .civ    import CivLayer
from .render import (Camera, draw, draw_log, draw_generating,
                     init_colors, ZOOM_LEVELS, DEFAULT_ZOOM)
from .save   import save, load, latest_save

TARGET_FPS    = 20
MIN_SPEED     = 1
MAX_SPEED     = 8
DEFAULT_SPEED = 3

CURSOR_STEP      = 1    # arrow keys
CURSOR_STEP_FAST = 10   # WASD

# (ticks_per_frame, frames_per_tick); 4 ticks = 1 year
SPEED_TABLE = {
    1: (0, 8),
    2: (0, 4),
    3: (0, 2),
    4: (1, 0),
    5: (2, 0),
    6: (4, 0),
    7: (8, 0),
    8: (16, 0),
}


def _make_world(stdscr, seed: int):
    def progress(msg):
        draw_generating(stdscr, msg)

    draw_generating(stdscr, 'starting...')
    world = WorldMap(seed, on_progress=progress)
    geo   = GeologyLayer()
    civ   = CivLayer()
    return world, geo, civ


def _tick(world, geo, civ):
    world.step()
    if world.tick == 0:
        geo.step_year(world)
        civ.step_year(world)


def _move_cursor(cx, cy, dx, dy):
    return (max(0, min(WORLD_W - 1, cx + dx)),
            max(0, min(WORLD_H - 1, cy + dy)))


def run(stdscr, args):
    curses.curs_set(0)
    stdscr.nodelay(True)
    init_colors()

    save_path = None
    if args.load is not None:
        path = args.load if args.load else latest_save()
        if path:
            world, geo, civ = load(path)
            save_path = str(path)
        else:
            world, geo, civ = _make_world(stdscr, random.randint(1, 99999))
    else:
        world, geo, civ = _make_world(stdscr, random.randint(1, 99999))

    # Cursor starts at world centre
    cursor_x, cursor_y = WORLD_W // 2, WORLD_H // 2
    cam = Camera(WORLD_W, WORLD_H)
    cam.wx, cam.wy = float(cursor_x), float(cursor_y)

    paused      = False
    speed       = DEFAULT_SPEED
    frame_count = 0
    frame_dt    = 1.0 / TARGET_FPS
    log_open    = False
    log_scroll  = 0

    draw(stdscr, world, civ, cam, paused, speed, (cursor_x, cursor_y), save_path)

    while True:
        t0  = time.monotonic()
        key = stdscr.getch()

        if key in (ord('q'), ord('Q')):
            break

        elif key in (ord('l'), ord('L')):
            log_open   = not log_open
            log_scroll = 0

        elif log_open:
            rows, _ = stdscr.getmaxyx()
            body_h     = rows - 2
            max_scroll = max(0, len(civ.history) - body_h)
            if key in (curses.KEY_UP,   ord('k')):
                log_scroll = min(max_scroll, log_scroll + 1)
            elif key in (curses.KEY_DOWN, ord('j')):
                log_scroll = max(0, log_scroll - 1)
            elif key == curses.KEY_PPAGE:
                log_scroll = min(max_scroll, log_scroll + body_h)
            elif key == curses.KEY_NPAGE:
                log_scroll = max(0, log_scroll - body_h)
            elif key == ord('S'):
                path = save(world, geo, civ)
                save_path = str(path)
            elif key == curses.KEY_RESIZE:
                stdscr.clear()

        else:
            # ── Cursor movement ───────────────────────────────────
            if key == curses.KEY_UP:
                cursor_x, cursor_y = _move_cursor(cursor_x, cursor_y, 0, -CURSOR_STEP)
            elif key == curses.KEY_DOWN:
                cursor_x, cursor_y = _move_cursor(cursor_x, cursor_y, 0,  CURSOR_STEP)
            elif key == curses.KEY_LEFT:
                cursor_x, cursor_y = _move_cursor(cursor_x, cursor_y, -CURSOR_STEP, 0)
            elif key == curses.KEY_RIGHT:
                cursor_x, cursor_y = _move_cursor(cursor_x, cursor_y,  CURSOR_STEP, 0)

            elif key in (ord('w'), ord('W')):
                cursor_x, cursor_y = _move_cursor(cursor_x, cursor_y, 0, -CURSOR_STEP_FAST)
            elif key == ord('s'):
                cursor_x, cursor_y = _move_cursor(cursor_x, cursor_y, 0,  CURSOR_STEP_FAST)
            elif key in (ord('a'), ord('A')):
                cursor_x, cursor_y = _move_cursor(cursor_x, cursor_y, -CURSOR_STEP_FAST, 0)
            elif key in (ord('d'), ord('D')):
                cursor_x, cursor_y = _move_cursor(cursor_x, cursor_y,  CURSOR_STEP_FAST, 0)

            # Camera always follows cursor
            cam.wx = float(cursor_x)
            cam.wy = float(cursor_y)

            # ── Other controls ────────────────────────────────────
            if key in (ord('p'), ord(' ')):
                paused = not paused

            elif key in (ord('+'), ord('=')):
                speed = min(MAX_SPEED, speed + 1)

            elif key == ord('-'):
                speed = max(MIN_SPEED, speed - 1)

            elif key in (ord('z'), ord('Z')):
                cam.zoom_in()

            elif key in (ord('x'), ord('X')):
                cam.zoom_out()

            elif key in (ord('r'), ord('R')):
                world, geo, civ = _make_world(stdscr, random.randint(1, 99999))
                cursor_x, cursor_y = WORLD_W // 2, WORLD_H // 2
                cam = Camera(WORLD_W, WORLD_H)
                cam.wx, cam.wy = float(cursor_x), float(cursor_y)
                frame_count = 0
                save_path   = None

            elif key == curses.KEY_RESIZE:
                stdscr.clear()

            elif key in (ord('f'), ord('F')):
                msg = civ.found(world, cursor_x, cursor_y)
                if not msg:
                    civ.history.append(
                        f"Year {world.year}: Cannot found here (sea or mountain)")
                    civ.recent.append(civ.history[-1])

            elif key in (ord('c'), ord('C')):
                civ.trigger_conflict(world)

            elif key in (ord('e'), ord('E')):
                civ.trigger_drought(world)

            elif key in (ord('v'), ord('V')):
                msg = geo._erupt(world)
                if msg:
                    civ.history.append(f"Year {world.year}: {msg} [player]")
                    civ.recent.append(civ.history[-1])

            elif key == ord('S'):
                path = save(world, geo, civ)
                save_path = str(path)
                civ.history.append(f"Year {world.year}: World saved")
                civ.recent.append(civ.history[-1])

        # ── Advance simulation ────────────────────────────────────
        if not paused:
            ticks_per_frame, frames_per_tick = SPEED_TABLE[speed]
            if ticks_per_frame > 0:
                for _ in range(ticks_per_frame):
                    _tick(world, geo, civ)
            elif frames_per_tick > 0 and frame_count % frames_per_tick == 0:
                _tick(world, geo, civ)
            frame_count += 1

        # ── Draw ──────────────────────────────────────────────────
        if log_open:
            draw_log(stdscr, world, civ, log_scroll, paused, speed, save_path)
        else:
            draw(stdscr, world, civ, cam, paused, speed,
                 (cursor_x, cursor_y), save_path)

        elapsed = time.monotonic() - t0
        wait    = frame_dt - elapsed
        if wait > 0:
            time.sleep(wait)


def main():
    parser = argparse.ArgumentParser(description='STRATUM world simulation')
    parser.add_argument(
        '--load', nargs='?', const='', default=None, metavar='FILE',
        help='load a save file (omit FILE to load the latest save)',
    )
    args = parser.parse_args()
    curses.wrapper(lambda scr: run(scr, args))


if __name__ == '__main__':
    main()
