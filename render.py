"""
Renderer: draws terrain + overlays + settlements + status/history bars.
"""

import curses
import numpy as np
from .world import (WorldMap, SEA_DEEP, SEA_SHALLOW, COAST, PLAINS,
                    FOREST, HILLS, MOUNTAIN, SNOW,
                    M_ARID, M_DRY,
                    OVERLAY_ROAD, OVERLAY_FARM, OVERLAY_RUINS,
                    OVERLAY_BURN, OVERLAY_LAVA, OVERLAY_BRIDGE)
from .civ import CivLayer, Settlement

# ── Zoom ──────────────────────────────────────────────────────────
ZOOM_LEVELS  = [0.125, 0.25, 0.5, 1.0, 2.0, 4.0]
DEFAULT_ZOOM = 3
PAN_CELLS    = 6

# ── Color pair IDs ────────────────────────────────────────────────
C_ABYSS    = 1
C_SEA      = 2
C_SHOAL    = 3
C_COAST    = 4
C_DESERT   = 5
C_SAVANNA  = 6
C_PLAINS   = 7
C_FOREST   = 8
C_HILLS    = 9
C_MOUNT    = 10
C_SNOW     = 11
C_RIVER    = 12
C_STATUS   = 13
C_OOB      = 14
C_ROAD     = 15
C_FARM     = 16
C_RUINS    = 17
C_BURN     = 18
C_LAVA     = 19
C_CITY     = 20
C_HISTORY  = 21
C_BRIDGE   = 22

# ── Braille density glyphs ────────────────────────────────────────
_B = {
    'empty':   '\u2800',
    'sparse':  '\u2802',
    'ripple':  '\u2812',
    'scatter': '\u2826',
    'medium':  '\u2836',
    'dense':   '\u283f',
    'heavy':   '\u28f6',
    'thick':   '\u28fe',
    'solid':   '\u28ff',
}


def draw_generating(stdscr, msg: str = ''):
    """Simple splash shown while world generates."""
    rows, cols = stdscr.getmaxyx()
    stdscr.erase()
    line1 = 'STRATUM  --  generating world'
    line2 = msg
    try:
        stdscr.addstr(rows // 2 - 1, max(0, (cols - len(line1)) // 2),
                      line1, curses.A_BOLD)
        stdscr.addstr(rows // 2 + 1, max(0, (cols - len(line2)) // 2), line2)
    except curses.error:
        pass
    stdscr.refresh()


def biome_name(elev, moist, river=False, overlay=0) -> str:
    from .world import (SEA_DEEP, SEA_SHALLOW, COAST, PLAINS, FOREST,
                        HILLS, MOUNTAIN, SNOW, M_ARID, M_DRY,
                        OVERLAY_ROAD, OVERLAY_FARM, OVERLAY_RUINS,
                        OVERLAY_BURN, OVERLAY_LAVA)
    if elev < SEA_DEEP:    return 'Deep Ocean'
    if elev < SEA_SHALLOW: return 'Ocean'
    if elev < COAST:       return 'Shoals'
    base = ''
    if elev < PLAINS:
        base = 'Desert Coast' if moist < M_ARID else 'Coast'
    elif elev < FOREST:
        if moist < M_ARID: base = 'Desert'
        elif moist < M_DRY: base = 'Savanna'
        else: base = 'Plains'
    elif elev < HILLS:
        base = 'Scrubland' if moist < M_DRY else 'Forest'
    elif elev < MOUNTAIN:  base = 'Hills'
    elif elev < SNOW:      base = 'Mountain'
    else:                  base = 'Snow Peak'
    if river:   base += ' (river)'
    ov_labels = {1: ' [road]', 2: ' [farmland]', 3: ' [ruins]',
                 4: ' [burned]', 5: ' [lava]', 6: ' [bridge]'}
    return base + ov_labels.get(overlay, '')


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    pairs = [
        (C_ABYSS,   curses.COLOR_BLUE,    -1),
        (C_SEA,     curses.COLOR_BLUE,    -1),
        (C_SHOAL,   curses.COLOR_CYAN,    -1),
        (C_COAST,   curses.COLOR_YELLOW,  -1),
        (C_DESERT,  curses.COLOR_YELLOW,  -1),
        (C_SAVANNA, curses.COLOR_YELLOW,  -1),
        (C_PLAINS,  curses.COLOR_GREEN,   -1),
        (C_FOREST,  curses.COLOR_GREEN,   -1),
        (C_HILLS,   curses.COLOR_YELLOW,  -1),
        (C_MOUNT,   curses.COLOR_WHITE,   -1),
        (C_SNOW,    curses.COLOR_WHITE,   -1),
        (C_RIVER,   curses.COLOR_CYAN,    -1),
        (C_STATUS,  curses.COLOR_CYAN,    -1),
        (C_OOB,     curses.COLOR_BLACK,   -1),
        (C_ROAD,    curses.COLOR_WHITE,   -1),
        (C_FARM,    curses.COLOR_GREEN,   -1),
        (C_RUINS,   curses.COLOR_RED,     -1),
        (C_BURN,    curses.COLOR_RED,     -1),
        (C_LAVA,    curses.COLOR_RED,     -1),
        (C_CITY,    curses.COLOR_WHITE,   -1),
        (C_HISTORY, curses.COLOR_WHITE,   -1),
        (C_BRIDGE,  curses.COLOR_YELLOW,  -1),
    ]
    for pid, fg, bg in pairs:
        curses.init_pair(pid, fg, bg)


# ── Terrain glyph ─────────────────────────────────────────────────

def terrain_glyph(elev, moist=0.5, river=False, overlay=0):
    """Return (char, colour_id, bold)."""

    # Overlays take priority on land
    if elev >= COAST:
        if overlay == OVERLAY_LAVA:
            return '\u2588', C_LAVA, True
        if overlay == OVERLAY_BURN:
            return _B['scatter'], C_BURN, False
        if overlay == OVERLAY_RUINS:
            return '\u2020', C_RUINS, False    # dagger: crumbling stonework
        if overlay == OVERLAY_BRIDGE:
            return '\u2550', C_BRIDGE, True    # ═  double horizontal bar
        if overlay == OVERLAY_ROAD:
            return '\u00b7', C_ROAD, False     # · middle dot, dim white
        if overlay == OVERLAY_FARM:
            t = (elev - COAST) / max(0.01, PLAINS - COAST)
            ch = _B['ripple'] if t < 0.5 else _B['medium']
            return ch, C_FARM, False

    if river and elev >= COAST:
        return _B['ripple'], C_RIVER, True

    # Water
    if elev < SEA_DEEP:
        ch = _B['empty'] if elev / SEA_DEEP < 0.45 else _B['sparse']
        return ch, C_ABYSS, False
    if elev < SEA_SHALLOW:
        return _B['ripple'], C_SEA, False
    if elev < COAST:
        return _B['scatter'], C_SHOAL, True

    # Low land
    if elev < PLAINS:
        if moist < M_ARID:
            return _B['scatter'], C_DESERT, True
        t  = (elev - COAST) / (PLAINS - COAST)
        ch = _B['ripple'] if t < 0.4 else _B['medium']
        return ch, C_COAST, t > 0.5

    # Plains / savanna / desert
    if elev < FOREST:
        if moist < M_ARID:
            return _B['scatter'], C_DESERT, False
        if moist < M_DRY:
            t  = (elev - PLAINS) / (FOREST - PLAINS)
            ch = _B['medium'] if t < 0.5 else _B['dense']
            return ch, C_SAVANNA, False
        t  = (elev - PLAINS) / (FOREST - PLAINS)
        ch = _B['medium'] if t < 0.55 else _B['dense']
        return ch, C_PLAINS, False

    # Forest / arid hills
    if elev < HILLS:
        if moist < M_DRY:
            return _B['medium'], C_SAVANNA, False
        t  = (elev - FOREST) / (HILLS - FOREST)
        ch = _B['dense'] if t < 0.5 else _B['thick']
        return ch, C_FOREST, False

    # Hills / upland
    if elev < MOUNTAIN:
        t  = (elev - HILLS) / (MOUNTAIN - HILLS)
        ch = _B['heavy'] if t < 0.5 else _B['thick']
        return ch, C_HILLS, t > 0.65

    if elev < SNOW:
        return _B['solid'], C_MOUNT, False
    return _B['solid'], C_SNOW, True


_DIM_PAIRS = {C_ABYSS, C_FOREST, C_SAVANNA}

def _cell_attr(pair, bold):
    attr = curses.color_pair(pair)
    if pair in _DIM_PAIRS:
        attr |= curses.A_DIM
    elif bold:
        attr |= curses.A_BOLD
    return attr


# ── Camera ────────────────────────────────────────────────────────

class Camera:
    def __init__(self, world_w, world_h):
        self.wx  = float(world_w) / 2.0
        self.wy  = float(world_h) / 2.0
        self._zi = DEFAULT_ZOOM

    @property
    def zoom(self): return ZOOM_LEVELS[self._zi]

    def zoom_in(self):  self._zi = min(len(ZOOM_LEVELS) - 1, self._zi + 1)
    def zoom_out(self): self._zi = max(0, self._zi - 1)

    def pan(self, dx, dy):
        self.wx += dx / self.zoom
        self.wy += dy / self.zoom

    def clamp(self, ww, wh):
        self.wx = float(np.clip(self.wx, 0, ww - 1))
        self.wy = float(np.clip(self.wy, 0, wh - 1))

    def screen_to_world(self, sx, sy, sw, sh):
        return (self.wx + (sx - sw / 2) / self.zoom,
                self.wy + (sy - sh / 2) / self.zoom)

    def zoom_label(self):
        z = self.zoom
        return f'{int(z)}x' if z >= 1 else f'1/{int(1/z)}x'


# ── Settlement glyphs ─────────────────────────────────────────────
# Ordered by population thresholds
_CITY_GLYPHS = [
    (0,    '*',  False),   # ruins / tiny
    (10,   'o',  False),   # hamlet
    (30,   'o',  True),    # village
    (120,  'O',  False),   # town
    (400,  'O',  True),    # city
    (1000, '@',  True),    # metropolis
]

def _settlement_glyph(s: Settlement):
    if s.state == 'abandoned':
        return '\u2020', C_RUINS, False   # dagger for ruins
    ch, bold = 'o', False
    for thresh, g, b in _CITY_GLYPHS:
        if s.ipop >= thresh:
            ch, bold = g, b
    return ch, C_CITY, bold


# ── Main draw call ────────────────────────────────────────────────

HISTORY_LINES = 4   # lines shown in normal mode


def draw_log(stdscr, world: WorldMap, civ: CivLayer, scroll: int,
             paused: bool, speed: int, save_path: str | None):
    """Full-screen scrollable history log panel."""
    rows, cols = stdscr.getmaxyx()
    stdscr.erase()

    title_attr = curses.color_pair(C_STATUS) | curses.A_BOLD
    body_attr  = curses.color_pair(C_HISTORY)
    dim_attr   = curses.color_pair(C_HISTORY) | curses.A_DIM

    # Title bar
    title = (f"  HISTORY LOG  |  Year {world.year}  |  "
             f"{len(civ.history)} events  |  "
             f"[up/down] scroll   [l] close   [q] quit")
    try:
        stdscr.addstr(0, 0, title[:cols - 1].ljust(cols - 1), title_attr)
    except curses.error:
        pass

    # Scrollable body: rows 1 .. rows-2
    body_h   = rows - 2
    total    = len(civ.history)
    # scroll=0 means show the end; positive scroll goes further back
    end_idx  = max(total, body_h) - scroll
    start_idx = end_idx - body_h

    for row in range(body_h):
        idx = start_idx + row
        if 0 <= idx < total:
            line = civ.history[idx]
            attr = body_attr if idx >= total - 20 else dim_attr
        else:
            line = ''
            attr = dim_attr
        try:
            stdscr.addstr(1 + row, 0, line[:cols - 1].ljust(cols - 1), attr)
        except curses.error:
            pass

    # Scroll indicator
    pct = int(100 * max(0, end_idx - body_h) / max(1, total - body_h)) if total > body_h else 100
    save_hint = f"  [S] save" + (f" -- last save: {save_path}" if save_path else "")
    bar = f"  {pct:>3d}% of log{save_hint}"
    try:
        stdscr.addstr(rows - 1, 0, bar[:cols - 1].ljust(cols - 1), title_attr)
    except curses.error:
        pass

    stdscr.refresh()


def draw(stdscr, world: WorldMap, civ: CivLayer, cam: Camera,
         paused: bool, speed: int,
         cursor: tuple[int, int] | None = None,
         save_path: str | None = None):
    rows, cols = stdscr.getmaxyx()
    h_hist = HISTORY_LINES + 2   # info line + history rows + status bar
    sh     = rows - h_hist
    sw     = cols
    wh, ww = world.elev.shape
    zoom   = cam.zoom
    stdscr.erase()

    # ── Vectorised world sampling ─────────────────────────────────
    # Compute world coords for every screen column/row in one step,
    # then gather all four world arrays with a single fancy-index each.
    sx_f = np.arange(sw, dtype=np.float32)
    sy_f = np.arange(sh, dtype=np.float32)
    wx_f = cam.wx + (sx_f - sw * 0.5) / zoom   # (sw,)
    wy_f = cam.wy + (sy_f - sh * 0.5) / zoom   # (sh,)

    ix = np.clip(wx_f.astype(np.int32), 0, ww - 1)  # (sw,)
    iy = np.clip(wy_f.astype(np.int32), 0, wh - 1)  # (sh,)

    oob_x = (wx_f < 0) | (wx_f >= ww)  # (sw,) bool
    oob_y = (wy_f < 0) | (wy_f >= wh)  # (sh,) bool

    # Four world arrays sampled for the whole viewport at once
    ev_grid = world.elev    [iy[:, None], ix[None, :]]  # (sh, sw) float32
    mv_grid = world.moisture[iy[:, None], ix[None, :]]  # (sh, sw) float32
    ov_grid = world.overlay [iy[:, None], ix[None, :]]  # (sh, sw) uint8

    # Rivers are sparse; at zoom-out check a small neighbourhood
    if zoom >= 0.5:
        rv_grid = world.rivers[iy[:, None], ix[None, :]]  # (sh, sw) bool
    else:
        # Step in world-space equals 1/zoom screen cells; check ±1 world cell
        ix2 = np.clip(ix + 1, 0, ww - 1)
        iy2 = np.clip(iy + 1, 0, wh - 1)
        rv_grid = (world.rivers[iy[:, None],  ix[None, :]] |
                   world.rivers[iy2[:, None], ix[None, :]] |
                   world.rivers[iy[:, None],  ix2[None, :]])

    # Convert to plain Python lists once -- element access is ~5x faster
    # than repeated numpy scalar extraction inside the tight loop.
    ev_list = ev_grid.tolist()
    mv_list = mv_grid.tolist()
    rv_list = rv_grid.tolist()
    ov_list = ov_grid.tolist()
    oob_x_l = oob_x.tolist()
    oob_y_l = oob_y.tolist()

    # ── Cursor & settlement screen positions ──────────────────────
    cur_sx = cur_sy = -1
    if cursor is not None:
        cur_sx = int((cursor[0] - cam.wx) * zoom + sw * 0.5)
        cur_sy = int((cursor[1] - cam.wy) * zoom + sh * 0.5)

    settle_at: dict[tuple[int, int], Settlement] = {}
    for s in civ.settlements:
        ssx = int((s.x - cam.wx) * zoom + sw * 0.5)
        ssy = int((s.y - cam.wy) * zoom + sh * 0.5)
        if 0 <= ssx < sw and 0 <= ssy < sh:
            settle_at[(ssx, ssy)] = s

    # ── Render rows with run-length encoding ──────────────────────
    # Batch consecutive same-attr characters into one addstr call.
    # Reduces curses calls from sw*sh to ~(colour_changes)*sh.
    oob_attr = curses.color_pair(C_OOB)

    for py in range(sh):
        ev_row = ev_list[py]
        mv_row = mv_list[py]
        rv_row = rv_list[py]
        ov_row = ov_list[py]

        if oob_y_l[py]:
            try:
                stdscr.addstr(py, 0, ' ' * min(sw - 1, sw), oob_attr)
            except curses.error:
                pass
            continue

        run_buf  = []   # chars in current run
        run_attr = -1
        run_x    = 0

        for px in range(sw):
            # --- determine char and attr for this cell ---
            if oob_x_l[px]:
                ch, attr = ' ', oob_attr
            elif (px, py) in settle_at:
                s = settle_at[(px, py)]
                gch, pair, bold = _settlement_glyph(s)
                attr = curses.color_pair(pair)
                if bold:       attr |= curses.A_BOLD
                if px == cur_sx and py == cur_sy:
                    attr |= curses.A_REVERSE
                ch = gch
            else:
                ch, pair, bold = terrain_glyph(
                    ev_row[px], mv_row[px], rv_row[px], ov_row[px])
                attr = _cell_attr(pair, bold)
                if px == cur_sx and py == cur_sy:
                    attr |= curses.A_REVERSE

            # --- RLE flush ---
            if attr != run_attr:
                if run_buf:
                    try:
                        stdscr.addstr(py, run_x, ''.join(run_buf), run_attr)
                    except curses.error:
                        pass
                run_x    = px
                run_buf  = [ch]
                run_attr = attr
            else:
                run_buf.append(ch)

        if run_buf:
            try:
                stdscr.addstr(py, run_x, ''.join(run_buf), run_attr)
            except curses.error:
                pass

    # ── Tile info line ────────────────────────────────────────────
    info_y = sh
    if cursor is not None:
        cx, cy = cursor
        if 0 <= cx < ww and 0 <= cy < wh:
            ev = float(world.elev    [cy, cx])
            mv = float(world.moisture[cy, cx])
            sv = float(world.soil    [cy, cx])
            rv = bool (world.rivers  [cy, cx])
            ov = int  (world.overlay [cy, cx])
            bname = biome_name(ev, mv, rv, ov)
            here  = next((s for s in civ.settlements
                          if s.x == cx and s.y == cy), None)
            sinfo = (f'  --  {here.name} ({here.size_label()}, '
                     f'pop {here.ipop})') if here else ''
            info  = (f'  ({cx:>4d},{cy:>3d})  {bname:<20s}'
                     f'  elev {ev:.2f}  moist {mv:.2f}'
                     f'  soil {sv:.2f}{sinfo}')
        else:
            info = f'  ({cx},{cy})  out of bounds'
    else:
        info = ''
    try:
        stdscr.addstr(info_y, 0, info[:cols - 1].ljust(cols - 1),
                      curses.color_pair(C_STATUS))
    except curses.error:
        pass

    # ── History panel ─────────────────────────────────────────────
    hist_attr = curses.color_pair(C_HISTORY) | curses.A_DIM
    for i, line in enumerate(civ.history[-HISTORY_LINES:]):
        try:
            stdscr.addstr(sh + 1 + i, 0,
                          line[:cols - 1].ljust(cols - 1), hist_attr)
        except curses.error:
            pass

    # ── Status bar ────────────────────────────────────────────────
    active = sum(1 for s in civ.settlements if s.state != 'abandoned')
    pop    = sum(s.ipop for s in civ.settlements if s.state != 'abandoned')
    saved  = f'  saved: {save_path}' if save_path else ''
    bar = (
        f'  Year {world.year:>5d}  |  settlements {active:>2d}  '
        f'pop {pop:>5d}  |  zoom {cam.zoom_label():>5s}  |  speed {speed}x'
        f'  |  [f] found  [c] conflict  [e] drought  [v] volcano'
        f'  |  [l] log  [S] save  [p] pause  [+/-] speed  [r] regen  [q] quit'
        + ('   [PAUSED]' if paused else '') + saved
    )
    try:
        stdscr.addstr(rows - 1, 0, bar[:cols - 1],
                      curses.color_pair(C_STATUS) | curses.A_BOLD)
    except curses.error:
        pass

    stdscr.refresh()
