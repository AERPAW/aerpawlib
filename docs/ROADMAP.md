# aerpawlib Roadmap

Planned features and improvements for future releases.

## v1 API (Stable, no breaking changes)
- [x] nothing planned 

## v2 API (Development)
- [ ] Add more data to structured logging, including periodic telemetry and velocity sets

## Both versions
- [ ] Fix integration tests
- [ ] CI Pipeline w/ GitHub

## CLI
- [ ] Improve configs:
  - [ ]  None values mean nothing else passed (think `--debug`)
  - [ ] Make configs patches to the runtime (drone runtime, eg) and rename them to make better sense
  - [ ] Add more configs, especially for v2
- [ ] `Remove --debug-dump` and fold it in the `--structured-logging` option in v1