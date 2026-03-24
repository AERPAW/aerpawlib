# aerpawlib Roadmap

Planned features and improvements for future releases.

## v1 API (Stable, no breaking changes)
- [x] nothing planned 

## v2 API (Development)
- [x] Add more data to structured logging, including periodic telemetry data and set_velocity calls

## Both versions
- [ ] Fix integration tests
- [x] CI Pipeline w/ GitHub
- [ ] Fix weird rotation drift bug?

## CLI
- [x] Improve configs:
  - [x]  None values mean nothing else passed (think `--debug`)
  - [x] Make configs patches to the runtime (drone runtime, eg) and rename them to make better sense
  - [x] Add more configs, especially for v2
- [x] Remove `--debug-dump` and use `--structured-log` for JSONL (v1 and v2)