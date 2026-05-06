# STRATUM

Stratum is a terminal-first world simulation focused on geography, climate, and
civilization over long time scales. The target experience is: generate a
continent, watch rivers and biomes emerge, then let settlements found, spread,
fight, collapse, and leave visible history on the map.

## Status

This repository now contains a bootstrap Python package that matches the planned
module layout. It is runnable, but it is still an early scaffold: the current
build provides a minimal curses viewport, basic time advancement, a history log,
and a plain-text summary mode.

```bash
python3 -m stratum
python3 -m stratum --seed 42
python3 -m stratum --summary
python3 -m stratum --load
python3 -m stratum --load ~/.local/share/stratum/example.save
```

Saves are written to `~/.local/share/stratum/` by default. Set
`STRATUM_SAVE_DIR` to override that location.

If you are landing here fresh, treat the current build as a thin vertical slice
that establishes package structure, basic rendering, and command-line behavior
before the real simulation loop arrives.

## Target experience

- Large procedural continent rendered directly in a terminal UI
- Time-lapse simulation of terrain, moisture, rivers, geology, and settlement
  growth
- Player-triggered interventions such as founding settlements, starting wars,
  and droughts
- Persistent saves and an in-world history log that turns raw simulation output
  into readable events

## Planned package layout

```text
stratum/
  world.py    # Heightmap, moisture, rivers, overlays, soil
  geo.py      # Eruptions, lava cooling, long-term erosion
  civ.py      # Settlements, roads, farms, bridges, decay, history
  render.py   # Curses renderer, camera, zoom, batching, tile inspection
  main.py     # Game loop, input handling, simulation speed
  save.py     # Save/load support
```

## Runtime assumptions

The current scaffold requires:

- Python 3.11+
- A terminal with Unicode and color support
- A Unix-like environment with `curses`

The full simulation will likely add `numpy` once world generation and rendering
move beyond on-demand tile sampling.

Windows support is possible, but not the initial target. If Windows becomes a
goal, the renderer should be validated separately instead of assuming `curses`
behavior will match Linux/macOS terminals.

## Design notes

### World generation

- World size target: `2400 x 800` cells, about 1.92 million tiles
- Heightmap generated from multi-octave noise and a domain-warped land mask
- Continent shapes vary by seeded style: island, elongated, archipelago,
  twin-mass, atoll, coastal shelf, and dual-arm
- Land coverage should normalize into a roughly `30%` to `55%` range regardless
  of seed
- Moisture model combines coastal diffusion, rain shadow, and fine noise
- Rivers should trace from highlands to the sea while avoiding small local
  minima without requiring heavy preprocessing

### Geology

- Rivers slowly erode terrain over simulated years
- Volcanic events are currently disabled in the playable scaffold

### Civilizations

- Settlements prefer habitable cells, with river and coast bonuses
- Population growth is logistic rather than unbounded
- Successful settlements can found daughter colonies
- Roads, bridges, farms, ruin states, and narrative event history are core
  parts of the simulation rather than optional flavor
- Larger settlements should develop visible urban footprints instead of reading
  as a single map glyph
- Ports, markets, citadels, and ruins should make different city roles legible
  at a glance

### Rendering

- Current build: curses viewport with camera movement, zoom, regeneration, and
  tile inspection
- Current build: always-visible minimap and settlement list for navigation
- Current build: seeded on-demand tile sampling rather than a fully simulated
  materialized map
- Planned: denser glyph language, stronger batching, and a scrollable history
  view

### Time scale

- `4` ticks per in-game year
- Multiple simulation speeds, from readable event-by-event playback to fast
  time-lapse
- Default speed should be slow enough to observe changes without constant
  pausing

## Intended controls

Currently implemented:

| Key | Action |
|-----|--------|
| Arrow keys | Move cursor 1 cell |
| WASD | Move cursor 10 cells |
| `z` / `x` | Zoom in / out |
| `+` / `-` | Speed up / slow down |
| `p` / `Space` | Pause / resume time |
| `g` | Toggle settlement list and jump to a city with `Enter` |
| `l` | Toggle the history log |
| `S` | Save the current simulation state |
| `r` | Regenerate world |
| `q` | Quit |

Planned but not implemented yet:

| Key | Action |
|-----|--------|
| `+` / `-` | Speed up / slow down |
| `p` / `Space` | Pause |
| `f` | Found a settlement at cursor |
| `c` | Trigger a nearby conflict |
| `e` | Trigger a drought |
| `v` | Trigger a volcanic eruption at cursor |
| `l` | Toggle the scrollable history log |
| `S` | Save world |

## Milestones

### First playable

- Generate a world from a seed in a few seconds
- Render terrain, rivers, and settlements in the terminal
- Advance time with pausing and speed controls
- Show readable history events for founding, growth, war, drought, and
  eruption
- Support manual world regeneration and save/load
- Make roads and farms visibly change settlement outcomes
- Let road networks decay, break, and recover over time

### Simulation depth

- Trade route effects for well-connected settlements
- Maritime colonization for coastal polities
- Culture or faction systems so conflict is not purely pairwise and local
- Deeper decay and abandonment for failing regions

### Visual and UX improvements

- Biome smoothing at low zoom levels
- Wider rendering for major rivers
- Population trend overlay or sparkline
- Small always-visible minimap

### Longer-term systems

- Religion, monuments, and pilgrimage effects
- Technology progression with unlockable infrastructure
- Plague and other network-driven disasters
- Multi-century climate shifts

## Risks and open questions

- Moisture banding is a likely artifact risk and should be validated early with
  image captures from several seeds
- A `2400 x 800` world is large enough that renderer design matters from day
  one; per-cell terminal drawing will likely be too slow
- Save format should avoid locking the project into fragile Python object
  layouts if the simulation evolves quickly
- Narrative logging can become spammy fast, so event aggregation rules will
  matter

## Recommended next steps

1. Build the world generation and renderer loop before deeper civilization
   systems.
2. Make geography react to events instead of treating the map as static.
3. Add a screenshot or asciinema once the first playable build exists.
4. Split implementation notes into `docs/` if this README starts growing again.
