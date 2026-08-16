# aerpawlib documentation style guide

This guide applies to all content published through pdoc: markdown files under `docs/` (included via `.. include::` in package `__init__.py`) and public Python docstrings on symbols visible in the API reference.

## Audience

Write for AERPAW researchers building experiment scripts. Assume:

- Python 3.10+ and basic `asyncio` (`async`/`await`)
- Familiarity with drones/rovers in a testbed context
- No requirement to understand MAVSDK, MAVLink, or internal threading details

## Voice and tone

| Context | Style |
|---------|--------|
| User actions | Second person, imperative: "Connect to SITL…", "Return the next state name…" |
| System behavior | Neutral third person: "The runner schedules states on the event loop." |
| Warnings and notes | `> **Note:**` or `> **Warning:**` callouts; no casual asides or emoji |

Avoid: first-person ("we"), developer-internal jargon without explanation, and duplicate history essays about DroneKit or v1/v2 migration.

## Module page structure

Every included markdown module page should follow this skeleton (see `docs/_templates/module_page.md`):

1. **Overview**: 1 to 2 sentences on what the module does for an experiment
1. **When to use this**: when to import or configure it
1. **Common workflow**: one minimal, runnable example (SITL defaults)
1. **Key concepts / API surface**: bullets or tables
1. **Errors**: if applicable: exception → what the researcher should check
1. **See also**: cross-links to related modules (`runner`, `vehicle`, `safety`, `cli`)

Use `##` headings only in module pages. pdoc already renders the module name as the page title; do not add a top-level `#` title that duplicates it.

## Examples

- Use SITL-friendly defaults: `udpin://127.0.0.1:14550`, `--vehicle drone`, `--api-version v2` where relevant
- Show experiment intent: connect → takeoff → move → collect data → land
- Prefer `aerpawlib.v1` or `aerpawlib.v2` imports matching the documented API version
- Keep examples short; link to `examples/` for full missions

## Python docstrings

pdoc uses Google format (`configs/pdoc.json` → `docformat: google`).

### Public symbols

- One-line summary in imperative or descriptive form
- `Args`, `Returns`, `Raises` sections when behavior is not obvious from the signature
- Document units (metres, degrees, seconds) and defaults
- Match parameter descriptions across v1 and v2 counterparts where APIs align

### Module docstrings in implementation files

Keep to 2 to 3 lines plus a pointer: "See `aerpawlib.v2.vehicle` module documentation." Do not repeat the included markdown narrative.

### Internal symbols

Private helpers (`_prefix`) and excluded modules need not be documented for pdoc.

## v1 and v2 pairs

When both versions expose the same concept (runner, vehicle, safety):

- Use matching section headings
- Note API differences in one line (e.g. connection string format, `blocking=False` on v2 goto)
- Cross-link the other version: "For the v1 API, see `aerpawlib.v1.runner`."

## Building docs locally

```bash
python -m scripts.generate_pdoc --clean
```

Output is written to `docs/pdoc/` and published via GitHub Pages.
