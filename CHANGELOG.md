# Changelog

## [v0.14.1](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.14.1) (2025-05-30)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.14.0...v0.14.1)

**Fixed bugs:**

- fix: dangling callback during core deletion, and disallow `registerCallback` [\#467](https://github.com/pymmcore-plus/pymmcore-plus/pull/467) ([tlambert03](https://github.com/tlambert03))

## [v0.14.0](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.14.0) (2025-05-05)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.13.7...v0.14.0)

**Implemented enhancements:**

- feat: add ChangeAccumulator pattern, for sharing control of a slow target value [\#462](https://github.com/pymmcore-plus/pymmcore-plus/pull/462) ([tlambert03](https://github.com/tlambert03))
- feat: extend object-oriented device API [\#437](https://github.com/pymmcore-plus/pymmcore-plus/pull/437) ([tlambert03](https://github.com/tlambert03))

**Fixed bugs:**

- fix: tensorstore - make sure metadata written [\#461](https://github.com/pymmcore-plus/pymmcore-plus/pull/461) ([wl-stepp](https://github.com/wl-stepp))

**Merged pull requests:**

- test: add uv lockfile and test with uv \(including minimum deps\) [\#424](https://github.com/pymmcore-plus/pymmcore-plus/pull/424) ([tlambert03](https://github.com/tlambert03))

## [v0.13.7](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.13.7) (2025-04-11)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.13.6...v0.13.7)

**Fixed bugs:**

- chore: revert mm-device-adapters usage in tests [\#460](https://github.com/pymmcore-plus/pymmcore-plus/pull/460) ([tlambert03](https://github.com/tlambert03))
- fix: Change to MM directory for `mmcore mmstudio` [\#459](https://github.com/pymmcore-plus/pymmcore-plus/pull/459) ([marktsuchida](https://github.com/marktsuchida))

**Merged pull requests:**

- ci\(pre-commit.ci\): autoupdate [\#458](https://github.com/pymmcore-plus/pymmcore-plus/pull/458) ([pre-commit-ci[bot]](https://github.com/apps/pre-commit-ci))

## [v0.13.6](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.13.6) (2025-03-31)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.13.5...v0.13.6)

**Implemented enhancements:**

- feat: Support mm-device-adapters [\#455](https://github.com/pymmcore-plus/pymmcore-plus/pull/455) ([tlambert03](https://github.com/tlambert03))

**Fixed bugs:**

- fix: fix for pydantic v2.11 [\#453](https://github.com/pymmcore-plus/pymmcore-plus/pull/453) ([tlambert03](https://github.com/tlambert03))

**Tests & CI:**

- test: fixes for pymmcore v11.5 [\#451](https://github.com/pymmcore-plus/pymmcore-plus/pull/451) ([tlambert03](https://github.com/tlambert03))

**Merged pull requests:**

- docs: clarify device interface versions, and simplify mmcore install [\#454](https://github.com/pymmcore-plus/pymmcore-plus/pull/454) ([tlambert03](https://github.com/tlambert03))
- docs: pin mkdocs-autorefs [\#452](https://github.com/pymmcore-plus/pymmcore-plus/pull/452) ([tlambert03](https://github.com/tlambert03))
- docs: better doc env vars, and add a few more [\#450](https://github.com/pymmcore-plus/pymmcore-plus/pull/450) ([tlambert03](https://github.com/tlambert03))

## [v0.13.5](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.13.5) (2025-03-18)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.13.4...v0.13.5)

**Fixed bugs:**

- fix: pin tensorstore [\#443](https://github.com/pymmcore-plus/pymmcore-plus/pull/443) ([tlambert03](https://github.com/tlambert03))
- fix: Fix missing metadata in popNextImageAndMD [\#436](https://github.com/pymmcore-plus/pymmcore-plus/pull/436) ([tlambert03](https://github.com/tlambert03))

**Merged pull requests:**

- refactor: call setConfig in MDAEngine only when different from previous call [\#448](https://github.com/pymmcore-plus/pymmcore-plus/pull/448) ([tlambert03](https://github.com/tlambert03))

## [v0.13.4](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.13.4) (2025-02-11)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.13.3...v0.13.4)

**Merged pull requests:**

- chore: support useq 0.7, don't try to exec anything but AcquireImage [\#432](https://github.com/pymmcore-plus/pymmcore-plus/pull/432) ([tlambert03](https://github.com/tlambert03))

## [v0.13.3](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.13.3) (2025-02-07)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.13.2...v0.13.3)

**Implemented enhancements:**

- feat: add continuousSequenceAcquisitionStarting and sequenceAcquisitionStarting signals [\#430](https://github.com/pymmcore-plus/pymmcore-plus/pull/430) ([tlambert03](https://github.com/tlambert03))

## [v0.13.2](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.13.2) (2025-02-05)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.13.1...v0.13.2)

**Implemented enhancements:**

- feat: add `get_output_handlers` method to `MDARunner` [\#422](https://github.com/pymmcore-plus/pymmcore-plus/pull/422) ([tlambert03](https://github.com/tlambert03))

**Fixed bugs:**

- fix!: fix focus direction enums [\#428](https://github.com/pymmcore-plus/pymmcore-plus/pull/428) ([tlambert03](https://github.com/tlambert03))
- fix: turn most exceptions to warnings when loading config file into a model [\#426](https://github.com/pymmcore-plus/pymmcore-plus/pull/426) ([tlambert03](https://github.com/tlambert03))

**Tests & CI:**

- test: unskip test on pymmcore-nano [\#423](https://github.com/pymmcore-plus/pymmcore-plus/pull/423) ([tlambert03](https://github.com/tlambert03))

**Merged pull requests:**

- ci\(pre-commit.ci\): autoupdate [\#425](https://github.com/pymmcore-plus/pymmcore-plus/pull/425) ([pre-commit-ci[bot]](https://github.com/apps/pre-commit-ci))

## [v0.13.1](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.13.1) (2025-01-21)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.13.0...v0.13.1)

**Fixed bugs:**

- Fix Issue with useq MDA Event Properties Not Being Set in MDAEngine [\#421](https://github.com/pymmcore-plus/pymmcore-plus/pull/421) ([alandolt](https://github.com/alandolt))

## [v0.13.0](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.13.0) (2025-01-16)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.12.0...v0.13.0)

**Implemented enhancements:**

- feat: Add `mmcore bench` to CLI [\#416](https://github.com/pymmcore-plus/pymmcore-plus/pull/416) ([tlambert03](https://github.com/tlambert03))
- feat: enhance describe method to include configuration groups and available devices [\#415](https://github.com/pymmcore-plus/pymmcore-plus/pull/415) ([tlambert03](https://github.com/tlambert03))
- feat: support pymmcore-nano if it's present in the environment [\#413](https://github.com/pymmcore-plus/pymmcore-plus/pull/413) ([tlambert03](https://github.com/tlambert03))
- feat: add typing to setContext [\#410](https://github.com/pymmcore-plus/pymmcore-plus/pull/410) ([tlambert03](https://github.com/tlambert03))
- feat: Unicore - a unified core object that manages both C++ devices and python side devices in the same runtime [\#407](https://github.com/pymmcore-plus/pymmcore-plus/pull/407) ([tlambert03](https://github.com/tlambert03))
- feat: support slm\_image from useq v0.6 [\#406](https://github.com/pymmcore-plus/pymmcore-plus/pull/406) ([hinderling](https://github.com/hinderling))
- perf: better sequenced event building [\#400](https://github.com/pymmcore-plus/pymmcore-plus/pull/400) ([tlambert03](https://github.com/tlambert03))
- perf: don't query position on triggered acquisition frames by default, add `include_frame_position_metadata` flag [\#392](https://github.com/pymmcore-plus/pymmcore-plus/pull/392) ([tlambert03](https://github.com/tlambert03))
- feat: use rich for logging if available [\#388](https://github.com/pymmcore-plus/pymmcore-plus/pull/388) ([tlambert03](https://github.com/tlambert03))

**Fixed bugs:**

- fix: Don't use `Engine.event_iterator` when an Iterable is directly passed to `MDARunner.run` [\#419](https://github.com/pymmcore-plus/pymmcore-plus/pull/419) ([tlambert03](https://github.com/tlambert03))

**Tests & CI:**

- test: fix file descriptor leaks, and other misc things [\#401](https://github.com/pymmcore-plus/pymmcore-plus/pull/401) ([tlambert03](https://github.com/tlambert03))

**Merged pull requests:**

- ci: don't test py3.13 for now [\#411](https://github.com/pymmcore-plus/pymmcore-plus/pull/411) ([tlambert03](https://github.com/tlambert03))
- refactor: remove wrapt synchronized [\#408](https://github.com/pymmcore-plus/pymmcore-plus/pull/408) ([tlambert03](https://github.com/tlambert03))
- ci\(dependabot\): bump codecov/codecov-action from 4 to 5 [\#402](https://github.com/pymmcore-plus/pymmcore-plus/pull/402) ([dependabot[bot]](https://github.com/apps/dependabot))
- docs: add documentation on profiling with py-spy [\#393](https://github.com/pymmcore-plus/pymmcore-plus/pull/393) ([tlambert03](https://github.com/tlambert03))
- test: fix tests by pinning pyside\<6.8 [\#389](https://github.com/pymmcore-plus/pymmcore-plus/pull/389) ([tlambert03](https://github.com/tlambert03))
- docs: Add a hint about the mmcore build-dev command [\#386](https://github.com/pymmcore-plus/pymmcore-plus/pull/386) ([ctrueden](https://github.com/ctrueden))
- ci: support python 3.13 [\#382](https://github.com/pymmcore-plus/pymmcore-plus/pull/382) ([tlambert03](https://github.com/tlambert03))

## [v0.12.0](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.12.0) (2024-10-05)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.11.1...v0.12.0)

**Implemented enhancements:**

- feat: add support for MDAEvent.reset\_event\_timer [\#383](https://github.com/pymmcore-plus/pymmcore-plus/pull/383) ([tlambert03](https://github.com/tlambert03))

**Fixed bugs:**

- fix: serialization of GridPlan in ome-zarr writer when msgspec is not installed [\#378](https://github.com/pymmcore-plus/pymmcore-plus/pull/378) ([tlambert03](https://github.com/tlambert03))

**Merged pull requests:**

- chore: fix typing on Signal.disconnect protocol [\#381](https://github.com/pymmcore-plus/pymmcore-plus/pull/381) ([tlambert03](https://github.com/tlambert03))
- build: drop python 3.8 [\#377](https://github.com/pymmcore-plus/pymmcore-plus/pull/377) ([tlambert03](https://github.com/tlambert03))
- ci\(pre-commit.ci\): autoupdate [\#374](https://github.com/pymmcore-plus/pymmcore-plus/pull/374) ([pre-commit-ci[bot]](https://github.com/apps/pre-commit-ci))

## [v0.11.1](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.11.1) (2024-08-28)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.11.0...v0.11.1)

**Implemented enhancements:**

- feat: enable hardware sequencing by default [\#373](https://github.com/pymmcore-plus/pymmcore-plus/pull/373) ([tlambert03](https://github.com/tlambert03))

**Fixed bugs:**

- docs: fix typos etc. [\#370](https://github.com/pymmcore-plus/pymmcore-plus/pull/370) ([marktsuchida](https://github.com/marktsuchida))

**Merged pull requests:**

- ci\(dependabot\): bump CodSpeedHQ/action from 2 to 3 [\#371](https://github.com/pymmcore-plus/pymmcore-plus/pull/371) ([dependabot[bot]](https://github.com/apps/dependabot))

## [v0.11.0](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.11.0) (2024-07-06)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.10.2...v0.11.0)

**Implemented enhancements:**

- feat: add `mmcore use` to set the active micro-manager installation [\#368](https://github.com/pymmcore-plus/pymmcore-plus/pull/368) ([tlambert03](https://github.com/tlambert03))
- feat:  enable StrictInitializationChecks [\#367](https://github.com/pymmcore-plus/pymmcore-plus/pull/367) ([tlambert03](https://github.com/tlambert03))
- feat: create Microscope \(model\) from summary metadata [\#359](https://github.com/pymmcore-plus/pymmcore-plus/pull/359) ([tlambert03](https://github.com/tlambert03))
- feat: Formalize schema for metadata used by MDA \(and elsewhere\) [\#358](https://github.com/pymmcore-plus/pymmcore-plus/pull/358) ([tlambert03](https://github.com/tlambert03))

**Fixed bugs:**

- fix: fix failure to collect elapsed time during sequenced acquisition [\#361](https://github.com/pymmcore-plus/pymmcore-plus/pull/361) ([tlambert03](https://github.com/tlambert03))

**Merged pull requests:**

- docs: document cli [\#369](https://github.com/pymmcore-plus/pymmcore-plus/pull/369) ([tlambert03](https://github.com/tlambert03))
- refactor: use only pydantic2 syntax [\#366](https://github.com/pymmcore-plus/pymmcore-plus/pull/366) ([tlambert03](https://github.com/tlambert03))
- perf: benchmark metadata [\#363](https://github.com/pymmcore-plus/pymmcore-plus/pull/363) ([tlambert03](https://github.com/tlambert03))
- refactor: remove state and move metadata [\#362](https://github.com/pymmcore-plus/pymmcore-plus/pull/362) ([tlambert03](https://github.com/tlambert03))
- docs: deploy docs preview [\#360](https://github.com/pymmcore-plus/pymmcore-plus/pull/360) ([tlambert03](https://github.com/tlambert03))

## [v0.10.2](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.10.2) (2024-06-13)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.10.1...v0.10.2)

**Implemented enhancements:**

- feat: make CMMCoreSignaler and MDASignaler signal groups [\#357](https://github.com/pymmcore-plus/pymmcore-plus/pull/357) ([tlambert03](https://github.com/tlambert03))

## [v0.10.1](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.10.1) (2024-06-10)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.10.0...v0.10.1)

**Fixed bugs:**

- fix: fix setup sequence [\#356](https://github.com/pymmcore-plus/pymmcore-plus/pull/356) ([tlambert03](https://github.com/tlambert03))

## [v0.10.0](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.10.0) (2024-06-07)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.9.5...v0.10.0)

**Implemented enhancements:**

- feat: add tensorstore writer [\#348](https://github.com/pymmcore-plus/pymmcore-plus/pull/348) ([tlambert03](https://github.com/tlambert03))

**Fixed bugs:**

- fix: add stopPropertySequence before loadPropertySequence in setup\_sequenced\_event [\#353](https://github.com/pymmcore-plus/pymmcore-plus/pull/353) ([tlambert03](https://github.com/tlambert03))

**Merged pull requests:**

- ci: pre-commit update [\#347](https://github.com/pymmcore-plus/pymmcore-plus/pull/347) ([tlambert03](https://github.com/tlambert03))

## [v0.9.5](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.9.5) (2024-05-04)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.9.4...v0.9.5)

**Implemented enhancements:**

- feat: update 5d writer with isel method, make zarr output nicer to xarray, add a bit more metadata [\#344](https://github.com/pymmcore-plus/pymmcore-plus/pull/344) ([tlambert03](https://github.com/tlambert03))

**Fixed bugs:**

- fix: fixing tests and better auto-qt detection [\#345](https://github.com/pymmcore-plus/pymmcore-plus/pull/345) ([tlambert03](https://github.com/tlambert03))
- ci: use pyapp-kit workflows for dependency tests [\#338](https://github.com/pymmcore-plus/pymmcore-plus/pull/338) ([tlambert03](https://github.com/tlambert03))

**Merged pull requests:**

- ci\(dependabot\): bump softprops/action-gh-release from 1 to 2 [\#340](https://github.com/pymmcore-plus/pymmcore-plus/pull/340) ([dependabot[bot]](https://github.com/apps/dependabot))

## [v0.9.4](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.9.4) (2024-03-06)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.9.3...v0.9.4)

**Fixed bugs:**

- fix: Fix pyside2 issue when disconnecting listeners\_connected [\#337](https://github.com/pymmcore-plus/pymmcore-plus/pull/337) ([tlambert03](https://github.com/tlambert03))

## [v0.9.3](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.9.3) (2024-03-04)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.9.2...v0.9.3)

**Implemented enhancements:**

- feat: support linux on `mmcore build-dev`, test on linux, make device list editable [\#331](https://github.com/pymmcore-plus/pymmcore-plus/pull/331) ([tlambert03](https://github.com/tlambert03))

**Merged pull requests:**

- chore: use ruff format instead of black [\#335](https://github.com/pymmcore-plus/pymmcore-plus/pull/335) ([tlambert03](https://github.com/tlambert03))
- ci: cache built drivers for all platforms [\#333](https://github.com/pymmcore-plus/pymmcore-plus/pull/333) ([tlambert03](https://github.com/tlambert03))
- test: allow testing without Qt installed  [\#332](https://github.com/pymmcore-plus/pymmcore-plus/pull/332) ([tlambert03](https://github.com/tlambert03))
- perf: add benchmarks [\#330](https://github.com/pymmcore-plus/pymmcore-plus/pull/330) ([tlambert03](https://github.com/tlambert03))
- chore: misc dependency updates [\#329](https://github.com/pymmcore-plus/pymmcore-plus/pull/329) ([tlambert03](https://github.com/tlambert03))

## [v0.9.2](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.9.2) (2024-02-27)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.9.1...v0.9.2)

**Implemented enhancements:**

- feat: add `mmcore info` command [\#328](https://github.com/pymmcore-plus/pymmcore-plus/pull/328) ([tlambert03](https://github.com/tlambert03))

## [v0.9.1](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.9.1) (2024-02-22)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.9.0...v0.9.1)

**Fixed bugs:**

- fix: remove zarr dependency [\#327](https://github.com/pymmcore-plus/pymmcore-plus/pull/327) ([tlambert03](https://github.com/tlambert03))

## [v0.9.0](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.9.0) (2024-02-15)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.8.7...v0.9.0)

**Implemented enhancements:**

- feat: support basic ImageJ hyperstack [\#323](https://github.com/pymmcore-plus/pymmcore-plus/pull/323) ([tlambert03](https://github.com/tlambert03))
- feat: control signal backend with MMCORE\_PLUS\_SIGNALS\_BACKEND [\#321](https://github.com/pymmcore-plus/pymmcore-plus/pull/321) ([tlambert03](https://github.com/tlambert03))
- feat: add post\_sequence\_started [\#319](https://github.com/pymmcore-plus/pymmcore-plus/pull/319) ([tlambert03](https://github.com/tlambert03))
- feat: new runner signals `awaitingEvent` and `eventStarted` [\#316](https://github.com/pymmcore-plus/pymmcore-plus/pull/316) ([tlambert03](https://github.com/tlambert03))
- feat: Add file saving `output` argument to MDARunner.run [\#313](https://github.com/pymmcore-plus/pymmcore-plus/pull/313) ([tlambert03](https://github.com/tlambert03))
- feat: OMETiff writer [\#265](https://github.com/pymmcore-plus/pymmcore-plus/pull/265) ([tlambert03](https://github.com/tlambert03))

**Fixed bugs:**

- fix: re-engage hardware autofocus after performing autofocus action if it was engaged [\#326](https://github.com/pymmcore-plus/pymmcore-plus/pull/326) ([fdrgsp](https://github.com/fdrgsp))
- fix: fix autofocus z\_correction delta [\#317](https://github.com/pymmcore-plus/pymmcore-plus/pull/317) ([fdrgsp](https://github.com/fdrgsp))
- fix: only allow 'AcquireImage' Actions \(or None\) to be sequenced [\#315](https://github.com/pymmcore-plus/pymmcore-plus/pull/315) ([fdrgsp](https://github.com/fdrgsp))
- fix: fix excess reading of frame metadata in OMEZarrWriter [\#305](https://github.com/pymmcore-plus/pymmcore-plus/pull/305) ([wl-stepp](https://github.com/wl-stepp))

**Merged pull requests:**

- ci\(dependabot\): bump codecov/codecov-action from 3 to 4 [\#325](https://github.com/pymmcore-plus/pymmcore-plus/pull/325) ([dependabot[bot]](https://github.com/apps/dependabot))
- chore: remove deprecated stuff for next version bump [\#320](https://github.com/pymmcore-plus/pymmcore-plus/pull/320) ([tlambert03](https://github.com/tlambert03))
- refactor: move imageSnapped event [\#314](https://github.com/pymmcore-plus/pymmcore-plus/pull/314) ([tlambert03](https://github.com/tlambert03))
- refactor!: more minimal, and overridable MDA metadata [\#312](https://github.com/pymmcore-plus/pymmcore-plus/pull/312) ([tlambert03](https://github.com/tlambert03))

## [v0.8.7](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.8.7) (2024-01-25)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.8.6...v0.8.7)

**Fixed bugs:**

- fix: fix available peripherals for libraries with multiple hubs [\#309](https://github.com/pymmcore-plus/pymmcore-plus/pull/309) ([tlambert03](https://github.com/tlambert03))

## [v0.8.6](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.8.6) (2024-01-24)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.8.5...v0.8.6)

**Implemented enhancements:**

- feat: update OMEZarrWriter to position-specific sub-MDAsequences [\#299](https://github.com/pymmcore-plus/pymmcore-plus/pull/299) ([fdrgsp](https://github.com/fdrgsp))

**Fixed bugs:**

- fix: fix available\_peripherals for loaded hub devices [\#308](https://github.com/pymmcore-plus/pymmcore-plus/pull/308) ([tlambert03](https://github.com/tlambert03))
- fix: Zarr part mda [\#302](https://github.com/pymmcore-plus/pymmcore-plus/pull/302) ([wl-stepp](https://github.com/wl-stepp))

**Merged pull requests:**

- fix: avoid hardware errors while running sequences with NIDAQ stages [\#307](https://github.com/pymmcore-plus/pymmcore-plus/pull/307) ([tlambert03](https://github.com/tlambert03))

## [v0.8.5](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.8.5) (2023-12-18)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.8.4...v0.8.5)

**Implemented enhancements:**

- feat: OMEZarr writer [\#263](https://github.com/pymmcore-plus/pymmcore-plus/pull/263) ([tlambert03](https://github.com/tlambert03))

**Fixed bugs:**

- fix: fix available version lookup on windows [\#301](https://github.com/pymmcore-plus/pymmcore-plus/pull/301) ([tlambert03](https://github.com/tlambert03))
- docs: minor update [\#297](https://github.com/pymmcore-plus/pymmcore-plus/pull/297) ([fdrgsp](https://github.com/fdrgsp))

**Merged pull requests:**

- ci\(dependabot\): bump actions/setup-python from 4 to 5 [\#298](https://github.com/pymmcore-plus/pymmcore-plus/pull/298) ([dependabot[bot]](https://github.com/apps/dependabot))

## [v0.8.4](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.8.4) (2023-12-06)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.8.3...v0.8.4)

**Implemented enhancements:**

- feat: Add basic msgpack decoding for images from SequenceTester  [\#296](https://github.com/pymmcore-plus/pymmcore-plus/pull/296) ([tlambert03](https://github.com/tlambert03))

**Fixed bugs:**

- fix: subclass apply\_to\_core method for PixelSizeGroup in model [\#287](https://github.com/pymmcore-plus/pymmcore-plus/pull/287) ([fdrgsp](https://github.com/fdrgsp))

**Merged pull requests:**

- fix: trying to fix windows tests [\#293](https://github.com/pymmcore-plus/pymmcore-plus/pull/293) ([tlambert03](https://github.com/tlambert03))
- fix: remove alpha on rgb images [\#292](https://github.com/pymmcore-plus/pymmcore-plus/pull/292) ([tlambert03](https://github.com/tlambert03))
- refactor: change exec\_events to iterable [\#290](https://github.com/pymmcore-plus/pymmcore-plus/pull/290) ([tlambert03](https://github.com/tlambert03))
- fix: Remove unused fields from SystemInfoDict for mmcore11 compatibility [\#284](https://github.com/pymmcore-plus/pymmcore-plus/pull/284) ([tlambert03](https://github.com/tlambert03))
- chore: convert verysilent to silent [\#282](https://github.com/pymmcore-plus/pymmcore-plus/pull/282) ([tlambert03](https://github.com/tlambert03))

## [v0.8.3](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.8.3) (2023-10-24)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.8.2...v0.8.3)

**Implemented enhancements:**

- feat: support py312 [\#281](https://github.com/pymmcore-plus/pymmcore-plus/pull/281) ([tlambert03](https://github.com/tlambert03))
- feat: add systemConfigurationFile  to retrieve last config path [\#277](https://github.com/pymmcore-plus/pymmcore-plus/pull/277) ([tlambert03](https://github.com/tlambert03))
- feat: ImageSequenceWriter [\#267](https://github.com/pymmcore-plus/pymmcore-plus/pull/267) ([tlambert03](https://github.com/tlambert03))

**Tests & CI:**

- test: skip flaky thread tests [\#279](https://github.com/pymmcore-plus/pymmcore-plus/pull/279) ([tlambert03](https://github.com/tlambert03))

**Merged pull requests:**

- feat: make pretty output optional when using `mmcore install` [\#280](https://github.com/pymmcore-plus/pymmcore-plus/pull/280) ([tlambert03](https://github.com/tlambert03))
- fix: some fixes to mmcore install on macos [\#278](https://github.com/pymmcore-plus/pymmcore-plus/pull/278) ([tlambert03](https://github.com/tlambert03))
- feat: support DeviceInitializationState, fix issue with microscope model [\#276](https://github.com/pymmcore-plus/pymmcore-plus/pull/276) ([tlambert03](https://github.com/tlambert03))
- chore: deprecate `mmcore find` in favor of `mmcore list` [\#275](https://github.com/pymmcore-plus/pymmcore-plus/pull/275) ([tlambert03](https://github.com/tlambert03))
- refactor: update state method on MMCorePlus [\#274](https://github.com/pymmcore-plus/pymmcore-plus/pull/274) ([tlambert03](https://github.com/tlambert03))
- fix: Fix propertyChanged value type for setShutterOpen [\#273](https://github.com/pymmcore-plus/pymmcore-plus/pull/273) ([tlambert03](https://github.com/tlambert03))
- feat: autofind autofocus offset devices [\#270](https://github.com/pymmcore-plus/pymmcore-plus/pull/270) ([tlambert03](https://github.com/tlambert03))
- docs: clarify get/setZPosition in docs and update call [\#269](https://github.com/pymmcore-plus/pymmcore-plus/pull/269) ([tlambert03](https://github.com/tlambert03))
- feat: emit metadata as second argument of `sequenceStarted`  [\#268](https://github.com/pymmcore-plus/pymmcore-plus/pull/268) ([tlambert03](https://github.com/tlambert03))
- docs: fix Documentation of events might be out of date.  [\#266](https://github.com/pymmcore-plus/pymmcore-plus/pull/266) ([tlambert03](https://github.com/tlambert03))
- feat: make first instance of CMMCorePlus the global instance [\#264](https://github.com/pymmcore-plus/pymmcore-plus/pull/264) ([tlambert03](https://github.com/tlambert03))
- feat: add mda thread relay [\#262](https://github.com/pymmcore-plus/pymmcore-plus/pull/262) ([tlambert03](https://github.com/tlambert03))
- feat: add name\_map to listeners\_connect [\#260](https://github.com/pymmcore-plus/pymmcore-plus/pull/260) ([tlambert03](https://github.com/tlambert03))

## [v0.8.2](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.8.2) (2023-09-05)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.8.1...v0.8.2)

**Merged pull requests:**

- fix: don't check is\_busy when updating device in model [\#258](https://github.com/pymmcore-plus/pymmcore-plus/pull/258) ([tlambert03](https://github.com/tlambert03))
- ci\(dependabot\): bump actions/checkout from 3 to 4 [\#257](https://github.com/pymmcore-plus/pymmcore-plus/pull/257) ([dependabot[bot]](https://github.com/apps/dependabot))

## [v0.8.1](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.8.1) (2023-08-30)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.8.0...v0.8.1)

**Fixed bugs:**

- fix: fix a bug in saveSystemConfiguration method [\#248](https://github.com/pymmcore-plus/pymmcore-plus/pull/248) ([fdrgsp](https://github.com/fdrgsp))

**Merged pull requests:**

- feat:  microscope model, for building configs and in-memory representations of core [\#255](https://github.com/pymmcore-plus/pymmcore-plus/pull/255) ([tlambert03](https://github.com/tlambert03))
- feat: add keyword, CFGCommand and other enums on global strings [\#254](https://github.com/pymmcore-plus/pymmcore-plus/pull/254) ([tlambert03](https://github.com/tlambert03))
- fix: fix find micromanager bug [\#253](https://github.com/pymmcore-plus/pymmcore-plus/pull/253) ([tlambert03](https://github.com/tlambert03))
- feat: add getMultiROI method, bump core dep [\#251](https://github.com/pymmcore-plus/pymmcore-plus/pull/251) ([tlambert03](https://github.com/tlambert03))
- refactor: remove AvailableDevice [\#250](https://github.com/pymmcore-plus/pymmcore-plus/pull/250) ([tlambert03](https://github.com/tlambert03))
- docs: mark deprecated functions [\#249](https://github.com/pymmcore-plus/pymmcore-plus/pull/249) ([tlambert03](https://github.com/tlambert03))
- feat: add listeners\_connected utility [\#247](https://github.com/pymmcore-plus/pymmcore-plus/pull/247) ([tlambert03](https://github.com/tlambert03))
- feat: add metadata to frameready signal, add getTaggedImage [\#246](https://github.com/pymmcore-plus/pymmcore-plus/pull/246) ([tlambert03](https://github.com/tlambert03))
- docs: add pycro-manager API adapter as an educational example [\#245](https://github.com/pymmcore-plus/pymmcore-plus/pull/245) ([tlambert03](https://github.com/tlambert03))
- test: adding test and coverage [\#244](https://github.com/pymmcore-plus/pymmcore-plus/pull/244) ([tlambert03](https://github.com/tlambert03))
- docs: add migration info for pycro-manager users [\#243](https://github.com/pymmcore-plus/pymmcore-plus/pull/243) ([tlambert03](https://github.com/tlambert03))
- docs: adding acquisition engine docs [\#242](https://github.com/pymmcore-plus/pymmcore-plus/pull/242) ([tlambert03](https://github.com/tlambert03))
- build: make cli dependencies \(typer and rich\) optional [\#240](https://github.com/pymmcore-plus/pymmcore-plus/pull/240) ([tlambert03](https://github.com/tlambert03))
- refactor: remove loguru [\#239](https://github.com/pymmcore-plus/pymmcore-plus/pull/239) ([tlambert03](https://github.com/tlambert03))

## [v0.8.0](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.8.0) (2023-07-31)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.7.1...v0.8.0)

**Tests & CI:**

- test: don't test private attribute of useq [\#230](https://github.com/pymmcore-plus/pymmcore-plus/pull/230) ([tlambert03](https://github.com/tlambert03))

**Merged pull requests:**

- feat: implement keep shutter open for engine [\#237](https://github.com/pymmcore-plus/pymmcore-plus/pull/237) ([tlambert03](https://github.com/tlambert03))
- refactor: rename \_events to \_signals in Runner [\#236](https://github.com/pymmcore-plus/pymmcore-plus/pull/236) ([tlambert03](https://github.com/tlambert03))
- refactor: make hardware sequencing detection opt-in [\#235](https://github.com/pymmcore-plus/pymmcore-plus/pull/235) ([tlambert03](https://github.com/tlambert03))
- bug: add warnings if devices are not found [\#233](https://github.com/pymmcore-plus/pymmcore-plus/pull/233) ([fdrgsp](https://github.com/fdrgsp))
- feat: use new fov on useq grid objects, support pydantic2 [\#231](https://github.com/pymmcore-plus/pymmcore-plus/pull/231) ([tlambert03](https://github.com/tlambert03))
- fix: fix payload for sequenced objects [\#228](https://github.com/pymmcore-plus/pymmcore-plus/pull/228) ([tlambert03](https://github.com/tlambert03))
- feat: add attribute to control hardware sequencing [\#227](https://github.com/pymmcore-plus/pymmcore-plus/pull/227) ([tlambert03](https://github.com/tlambert03))
- chore: miscellaneous build and linting updates [\#224](https://github.com/pymmcore-plus/pymmcore-plus/pull/224) ([tlambert03](https://github.com/tlambert03))

## [v0.7.1](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.7.1) (2023-07-28)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.7.0...v0.7.1)

**Merged pull requests:**

- fix: fix bug in sequencing [\#225](https://github.com/pymmcore-plus/pymmcore-plus/pull/225) ([tlambert03](https://github.com/tlambert03))
- perf: Pop images from circular buffer during sequence [\#223](https://github.com/pymmcore-plus/pymmcore-plus/pull/223) ([tlambert03](https://github.com/tlambert03))
- ci: test napari-micromanager [\#221](https://github.com/pymmcore-plus/pymmcore-plus/pull/221) ([tlambert03](https://github.com/tlambert03))

## [v0.7.0](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.7.0) (2023-07-27)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.6.7...v0.7.0)

**Implemented enhancements:**

- feat:update saveSystemConfiguration method [\#214](https://github.com/pymmcore-plus/pymmcore-plus/pull/214) ([fdrgsp](https://github.com/fdrgsp))
- feat: update engine with autofocus using user Action [\#204](https://github.com/pymmcore-plus/pymmcore-plus/pull/204) ([fdrgsp](https://github.com/fdrgsp))
- feat: set sequence fov size in engine setup\_sequence + add test [\#198](https://github.com/pymmcore-plus/pymmcore-plus/pull/198) ([fdrgsp](https://github.com/fdrgsp))

**Merged pull requests:**

- feat: add logging to file and cli command [\#219](https://github.com/pymmcore-plus/pymmcore-plus/pull/219) ([tlambert03](https://github.com/tlambert03))
- feat: add MMCorePlus.describe method [\#218](https://github.com/pymmcore-plus/pymmcore-plus/pull/218) ([tlambert03](https://github.com/tlambert03))
- docs: fix docs build [\#216](https://github.com/pymmcore-plus/pymmcore-plus/pull/216) ([tlambert03](https://github.com/tlambert03))
- feat: add Adapter object [\#213](https://github.com/pymmcore-plus/pymmcore-plus/pull/213) ([tlambert03](https://github.com/tlambert03))
- refactor: move loadDevice logic from Device to MMCorePlus [\#212](https://github.com/pymmcore-plus/pymmcore-plus/pull/212) ([tlambert03](https://github.com/tlambert03))
- fix: don't use invalid plans in test [\#211](https://github.com/pymmcore-plus/pymmcore-plus/pull/211) ([tlambert03](https://github.com/tlambert03))
- fix doc [\#209](https://github.com/pymmcore-plus/pymmcore-plus/pull/209) ([tlambert03](https://github.com/tlambert03))
- refactor: Remove remote feature [\#208](https://github.com/pymmcore-plus/pymmcore-plus/pull/208) ([tlambert03](https://github.com/tlambert03))
- feat: add general retry utility [\#207](https://github.com/pymmcore-plus/pymmcore-plus/pull/207) ([tlambert03](https://github.com/tlambert03))
- feat: Add support for hardware sequencing [\#206](https://github.com/pymmcore-plus/pymmcore-plus/pull/206) ([tlambert03](https://github.com/tlambert03))
- refactor: relax signature of `MDARunner.run` to `Iterable[MDAEvent]` [\#205](https://github.com/pymmcore-plus/pymmcore-plus/pull/205) ([tlambert03](https://github.com/tlambert03))
- test: use PyQt6 for testing [\#203](https://github.com/pymmcore-plus/pymmcore-plus/pull/203) ([fdrgsp](https://github.com/fdrgsp))
- feat: add build-dev command to build dev dependencies on apple silicon [\#202](https://github.com/pymmcore-plus/pymmcore-plus/pull/202) ([tlambert03](https://github.com/tlambert03))
- fix: fix snap emission events [\#197](https://github.com/pymmcore-plus/pymmcore-plus/pull/197) ([tlambert03](https://github.com/tlambert03))
- test: fix scope of ignore warning on test [\#195](https://github.com/pymmcore-plus/pymmcore-plus/pull/195) ([tlambert03](https://github.com/tlambert03))

## [v0.6.7](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.6.7) (2023-04-10)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.6.6...v0.6.7)

**Merged pull requests:**

- fix: fix for loguru 0.7.0 [\#193](https://github.com/pymmcore-plus/pymmcore-plus/pull/193) ([tlambert03](https://github.com/tlambert03))
- docs: fix links [\#188](https://github.com/pymmcore-plus/pymmcore-plus/pull/188) ([tlambert03](https://github.com/tlambert03))
- fix: small fix in get state [\#185](https://github.com/pymmcore-plus/pymmcore-plus/pull/185) ([tlambert03](https://github.com/tlambert03))

## [v0.6.6](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.6.6) (2023-01-13)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.6.5...v0.6.6)

**Implemented enhancements:**

- feat: add propertyChanged to setFocusDevice method + test [\#182](https://github.com/pymmcore-plus/pymmcore-plus/pull/182) ([fdrgsp](https://github.com/fdrgsp))
- feat: emit channelGroupChanged signal when calling setChannelGroup [\#180](https://github.com/pymmcore-plus/pymmcore-plus/pull/180) ([fdrgsp](https://github.com/fdrgsp))

**Fixed bugs:**

- fix: update for newest micromanager demo cfg [\#183](https://github.com/pymmcore-plus/pymmcore-plus/pull/183) ([fdrgsp](https://github.com/fdrgsp))

**Merged pull requests:**

- style: update pre-commit [\#184](https://github.com/pymmcore-plus/pymmcore-plus/pull/184) ([tlambert03](https://github.com/tlambert03))

## [v0.6.5](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.6.5) (2022-12-07)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.6.4...v0.6.5)

**Merged pull requests:**

- fix: fix logging import [\#179](https://github.com/pymmcore-plus/pymmcore-plus/pull/179) ([tlambert03](https://github.com/tlambert03))
- docs: add favicon [\#178](https://github.com/pymmcore-plus/pymmcore-plus/pull/178) ([ianhi](https://github.com/ianhi))
- feat: add `run` \(mda\) command to cli [\#171](https://github.com/pymmcore-plus/pymmcore-plus/pull/171) ([tlambert03](https://github.com/tlambert03))

## [v0.6.4](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.6.4) (2022-12-05)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.6.3...v0.6.4)

**Merged pull requests:**

- style: update precommit [\#177](https://github.com/pymmcore-plus/pymmcore-plus/pull/177) ([tlambert03](https://github.com/tlambert03))
- fix: fix \_PropertySignal cleanup [\#176](https://github.com/pymmcore-plus/pymmcore-plus/pull/176) ([tlambert03](https://github.com/tlambert03))
- ci: add test for pymmcore-widgets [\#174](https://github.com/pymmcore-plus/pymmcore-plus/pull/174) ([tlambert03](https://github.com/tlambert03))

## [v0.6.3](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.6.3) (2022-12-05)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.6.2...v0.6.3)

**Merged pull requests:**

- feat: enhanced iterProperties and iterDevices [\#173](https://github.com/pymmcore-plus/pymmcore-plus/pull/173) ([tlambert03](https://github.com/tlambert03))
- feat: add `mmcore` command line program [\#170](https://github.com/pymmcore-plus/pymmcore-plus/pull/170) ([tlambert03](https://github.com/tlambert03))
- feat: add config group object [\#169](https://github.com/pymmcore-plus/pymmcore-plus/pull/169) ([tlambert03](https://github.com/tlambert03))

## [v0.6.2](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.6.2) (2022-11-29)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.6.1...v0.6.2)

**Merged pull requests:**

- fix: vendor private psygnal func [\#168](https://github.com/pymmcore-plus/pymmcore-plus/pull/168) ([tlambert03](https://github.com/tlambert03))
- build: support python 3.11  [\#167](https://github.com/pymmcore-plus/pymmcore-plus/pull/167) ([tlambert03](https://github.com/tlambert03))

## [v0.6.1](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.6.1) (2022-11-24)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.6.0...v0.6.1)

**Merged pull requests:**

- refactor: enable strict typing [\#166](https://github.com/pymmcore-plus/pymmcore-plus/pull/166) ([tlambert03](https://github.com/tlambert03))
- docs: remove direct griffe from extra [\#165](https://github.com/pymmcore-plus/pymmcore-plus/pull/165) ([tlambert03](https://github.com/tlambert03))

## [v0.6.0](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.6.0) (2022-11-22)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.5.1...v0.6.0)

**Implemented enhancements:**

- feat: New engine protocol [\#140](https://github.com/pymmcore-plus/pymmcore-plus/pull/140) ([tlambert03](https://github.com/tlambert03))

**Fixed bugs:**

- fix: fix signal names [\#163](https://github.com/pymmcore-plus/pymmcore-plus/pull/163) ([fdrgsp](https://github.com/fdrgsp))

**Merged pull requests:**

- docs: update readme [\#164](https://github.com/pymmcore-plus/pymmcore-plus/pull/164) ([tlambert03](https://github.com/tlambert03))
- fix: return getLastImageMD to original signature, add getLastImageAndMD [\#161](https://github.com/pymmcore-plus/pymmcore-plus/pull/161) ([tlambert03](https://github.com/tlambert03))
- docs: update documentation \(using mkdocs\) [\#160](https://github.com/pymmcore-plus/pymmcore-plus/pull/160) ([tlambert03](https://github.com/tlambert03))
- docs: fix api docs [\#159](https://github.com/pymmcore-plus/pymmcore-plus/pull/159) ([tlambert03](https://github.com/tlambert03))
- docs: fix docs after cleanup [\#158](https://github.com/pymmcore-plus/pymmcore-plus/pull/158) ([tlambert03](https://github.com/tlambert03))
- ci\(dependabot\): bump styfle/cancel-workflow-action from 0.9.1 to 0.11.0 [\#157](https://github.com/pymmcore-plus/pymmcore-plus/pull/157) ([dependabot[bot]](https://github.com/apps/dependabot))
- ci\(dependabot\): bump actions/setup-python from 2 to 4 [\#156](https://github.com/pymmcore-plus/pymmcore-plus/pull/156) ([dependabot[bot]](https://github.com/apps/dependabot))
- ci\(dependabot\): bump actions/checkout from 2 to 3 [\#155](https://github.com/pymmcore-plus/pymmcore-plus/pull/155) ([dependabot[bot]](https://github.com/apps/dependabot))
- ci\(dependabot\): bump codecov/codecov-action from 2 to 3 [\#154](https://github.com/pymmcore-plus/pymmcore-plus/pull/154) ([dependabot[bot]](https://github.com/apps/dependabot))
- refactor: big typing cleanup, move to using hatch and ruff [\#153](https://github.com/pymmcore-plus/pymmcore-plus/pull/153) ([tlambert03](https://github.com/tlambert03))
- test: fix tests and update pre-commit [\#152](https://github.com/pymmcore-plus/pymmcore-plus/pull/152) ([tlambert03](https://github.com/tlambert03))

## [v0.5.1](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.5.1) (2022-10-31)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.5.0...v0.5.1)

**Merged pull requests:**

- fix: fix missing typing import from psygnal [\#149](https://github.com/pymmcore-plus/pymmcore-plus/pull/149) ([tlambert03](https://github.com/tlambert03))

## [v0.5.0](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.5.0) (2022-10-17)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.4.5...v0.5.0)

**Implemented enhancements:**

- feat: use private loguru logger [\#146](https://github.com/pymmcore-plus/pymmcore-plus/pull/146) ([tlambert03](https://github.com/tlambert03))
- feat: new signals to handle pixel size configurations [\#143](https://github.com/pymmcore-plus/pymmcore-plus/pull/143) ([fdrgsp](https://github.com/fdrgsp))
- feat: add a new signals and methods for groups and presets + test [\#139](https://github.com/pymmcore-plus/pymmcore-plus/pull/139) ([fdrgsp](https://github.com/fdrgsp))

**Merged pull requests:**

- fix: fix test error after psygnal update [\#147](https://github.com/pymmcore-plus/pymmcore-plus/pull/147) ([tlambert03](https://github.com/tlambert03))
- test: skip `test_lock_and_callbacks` on windows CI [\#142](https://github.com/pymmcore-plus/pymmcore-plus/pull/142) ([tlambert03](https://github.com/tlambert03))
- feat: add a signal when the camera ROI changes + test [\#138](https://github.com/pymmcore-plus/pymmcore-plus/pull/138) ([fdrgsp](https://github.com/fdrgsp))
- chore: update links to new organization [\#135](https://github.com/pymmcore-plus/pymmcore-plus/pull/135) ([tlambert03](https://github.com/tlambert03))
- fix: make mda engine exit gracefully after an exception [\#133](https://github.com/pymmcore-plus/pymmcore-plus/pull/133) ([ianhi](https://github.com/ianhi))
- fix: Make sure to set xy in mda even if they are 0 [\#131](https://github.com/pymmcore-plus/pymmcore-plus/pull/131) ([ianhi](https://github.com/ianhi))

## [v0.4.5](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.4.5) (2022-05-19)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.4.4...v0.4.5)

**Merged pull requests:**

- fix nightly link [\#128](https://github.com/pymmcore-plus/pymmcore-plus/pull/128) ([tlambert03](https://github.com/tlambert03))

## [v0.4.4](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.4.4) (2022-05-12)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.4.3...v0.4.4)

**Merged pull requests:**

- fix potential typererror if canceled while waiting [\#127](https://github.com/pymmcore-plus/pymmcore-plus/pull/127) ([ianhi](https://github.com/ianhi))
- Fix waiting for mda events [\#126](https://github.com/pymmcore-plus/pymmcore-plus/pull/126) ([ianhi](https://github.com/ianhi))

## [v0.4.3](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.4.3) (2022-05-02)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.4.2...v0.4.3)

**Fixed bugs:**

- update setShutterOpen\(\) method [\#124](https://github.com/pymmcore-plus/pymmcore-plus/pull/124) ([fdrgsp](https://github.com/fdrgsp))

## [v0.4.2](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.4.2) (2022-04-23)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.4.1...v0.4.2)

**Merged pull requests:**

- Ensure import of QtWidgets in `check_qt_app` [\#122](https://github.com/pymmcore-plus/pymmcore-plus/pull/122) ([ianhi](https://github.com/ianhi))
- add `setContext` method [\#120](https://github.com/pymmcore-plus/pymmcore-plus/pull/120) ([ianhi](https://github.com/ianhi))

## [v0.4.1](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.4.1) (2022-04-21)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.4.0...v0.4.1)

**Merged pull requests:**

- micromanager shutter and autoshutter signals [\#123](https://github.com/pymmcore-plus/pymmcore-plus/pull/123) ([fdrgsp](https://github.com/fdrgsp))
- Add a new SequenceAcquisition  event signals [\#115](https://github.com/pymmcore-plus/pymmcore-plus/pull/115) ([fdrgsp](https://github.com/fdrgsp))
- fix flaky tests [\#114](https://github.com/pymmcore-plus/pymmcore-plus/pull/114) ([ianhi](https://github.com/ianhi))

## [v0.4.0](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.4.0) (2022-03-08)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.3.1...v0.4.0)

**Implemented enhancements:**

- Adds DeviceProperty class - a view onto a core property with a nicer API [\#107](https://github.com/pymmcore-plus/pymmcore-plus/pull/107) ([tlambert03](https://github.com/tlambert03))

**Fixed bugs:**

- Switch to user swappable mda-engines [\#102](https://github.com/pymmcore-plus/pymmcore-plus/pull/102) ([ianhi](https://github.com/ianhi))

**Merged pull requests:**

- add devicePropertyChanged and valueChanged signal on `DeviceProperty` object. [\#111](https://github.com/pymmcore-plus/pymmcore-plus/pull/111) ([tlambert03](https://github.com/tlambert03))
- reconfigure MDAEngine to make it easier to subclass [\#110](https://github.com/pymmcore-plus/pymmcore-plus/pull/110) ([ianhi](https://github.com/ianhi))
- Adds Device class - a view onto a core device with a nicer API [\#109](https://github.com/pymmcore-plus/pymmcore-plus/pull/109) ([tlambert03](https://github.com/tlambert03))
- use better globals for State and Label [\#106](https://github.com/pymmcore-plus/pymmcore-plus/pull/106) ([tlambert03](https://github.com/tlambert03))

## [v0.3.1](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.3.1) (2022-03-04)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.3.0...v0.3.1)

**Fixed bugs:**

- Fix event emission when setting property on a state device [\#105](https://github.com/pymmcore-plus/pymmcore-plus/pull/105) ([tlambert03](https://github.com/tlambert03))
- fix remote typing [\#103](https://github.com/pymmcore-plus/pymmcore-plus/pull/103) ([ianhi](https://github.com/ianhi))

## [v0.3.0](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.3.0) (2022-03-03)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.2.1...v0.3.0)

**Merged pull requests:**

- undo subclass of QCoreSignaler in remote [\#99](https://github.com/pymmcore-plus/pymmcore-plus/pull/99) ([tlambert03](https://github.com/tlambert03))
- Add events protocol, rename some internal classes, make CMMCoreSignaler public, and fix flaky thread test [\#98](https://github.com/pymmcore-plus/pymmcore-plus/pull/98) ([tlambert03](https://github.com/tlambert03))
- Ensure propertyChanged event occurs for setState and setStateLabel [\#97](https://github.com/pymmcore-plus/pymmcore-plus/pull/97) ([tlambert03](https://github.com/tlambert03))
- Doc follow ups [\#94](https://github.com/pymmcore-plus/pymmcore-plus/pull/94) ([ianhi](https://github.com/ianhi))
- fix python version in RTD build [\#93](https://github.com/pymmcore-plus/pymmcore-plus/pull/93) ([tlambert03](https://github.com/tlambert03))
- Move remote stuff to subfolder, make pyro5 optional \[remote\] extra [\#91](https://github.com/pymmcore-plus/pymmcore-plus/pull/91) ([tlambert03](https://github.com/tlambert03))
- remove setup.py, add ian as author [\#90](https://github.com/pymmcore-plus/pymmcore-plus/pull/90) ([tlambert03](https://github.com/tlambert03))
- remove leftover debug statements [\#89](https://github.com/pymmcore-plus/pymmcore-plus/pull/89) ([ianhi](https://github.com/ianhi))
- Fix flaky metadata test [\#88](https://github.com/pymmcore-plus/pymmcore-plus/pull/88) ([tlambert03](https://github.com/tlambert03))
- make `find_micromanager` public [\#86](https://github.com/pymmcore-plus/pymmcore-plus/pull/86) ([tlambert03](https://github.com/tlambert03))
- add quiet `--yes` install flag [\#85](https://github.com/pymmcore-plus/pymmcore-plus/pull/85) ([tlambert03](https://github.com/tlambert03))
- create docs [\#84](https://github.com/pymmcore-plus/pymmcore-plus/pull/84) ([ianhi](https://github.com/ianhi))
- fix QSignal instance check in test\_core [\#83](https://github.com/pymmcore-plus/pymmcore-plus/pull/83) ([tlambert03](https://github.com/tlambert03))

## [v0.2.1](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.2.1) (2022-02-21)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.2.0...v0.2.1)

**Merged pull requests:**

- restore setPosition overloading [\#82](https://github.com/pymmcore-plus/pymmcore-plus/pull/82) ([ianhi](https://github.com/ianhi))

## [v0.2.0](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.2.0) (2022-02-19)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.1.8...v0.2.0)

**Merged pull requests:**

- remove caching [\#76](https://github.com/pymmcore-plus/pymmcore-plus/pull/76) ([ianhi](https://github.com/ianhi))
- update install link [\#75](https://github.com/pymmcore-plus/pymmcore-plus/pull/75) ([ianhi](https://github.com/ianhi))
- Add a `snap` method and `signal` [\#74](https://github.com/pymmcore-plus/pymmcore-plus/pull/74) ([ianhi](https://github.com/ianhi))
- Start using threads [\#73](https://github.com/pymmcore-plus/pymmcore-plus/pull/73) ([ianhi](https://github.com/ianhi))

## [v0.1.8](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.1.8) (2022-01-28)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.1.7...v0.1.8)

**Merged pull requests:**

- Allow more options when loading config [\#71](https://github.com/pymmcore-plus/pymmcore-plus/pull/71) ([ianhi](https://github.com/ianhi))
- Download latest MM by default [\#69](https://github.com/pymmcore-plus/pymmcore-plus/pull/69) ([ianhi](https://github.com/ianhi))
- getOrGuessChannelGroup -\> list [\#67](https://github.com/pymmcore-plus/pymmcore-plus/pull/67) ([fdrgsp](https://github.com/fdrgsp))
- Add getPixelSizeConfigData\(\) to config overrides [\#61](https://github.com/pymmcore-plus/pymmcore-plus/pull/61) ([fdrgsp](https://github.com/fdrgsp))

## [v0.1.7](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.1.7) (2021-11-30)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.1.6...v0.1.7)

**Merged pull requests:**

- Run test suite once weekly [\#65](https://github.com/pymmcore-plus/pymmcore-plus/pull/65) ([ianhi](https://github.com/ianhi))
- Fix Aliased signals [\#64](https://github.com/pymmcore-plus/pymmcore-plus/pull/64) ([ianhi](https://github.com/ianhi))

## [v0.1.6](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.1.6) (2021-10-25)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.1.5...v0.1.6)

**Merged pull requests:**

- catch communication error on atexit [\#60](https://github.com/pymmcore-plus/pymmcore-plus/pull/60) ([tlambert03](https://github.com/tlambert03))
- Remove special casing of ENV path in tests [\#59](https://github.com/pymmcore-plus/pymmcore-plus/pull/59) ([ianhi](https://github.com/ianhi))
- \[pre-commit.ci\] pre-commit autoupdate [\#57](https://github.com/pymmcore-plus/pymmcore-plus/pull/57) ([pre-commit-ci[bot]](https://github.com/apps/pre-commit-ci))
- \[pre-commit.ci\] pre-commit autoupdate [\#56](https://github.com/pymmcore-plus/pymmcore-plus/pull/56) ([pre-commit-ci[bot]](https://github.com/apps/pre-commit-ci))
- \[pre-commit.ci\] pre-commit autoupdate [\#55](https://github.com/pymmcore-plus/pymmcore-plus/pull/55) ([pre-commit-ci[bot]](https://github.com/apps/pre-commit-ci))
- \[pre-commit.ci\] pre-commit autoupdate [\#54](https://github.com/pymmcore-plus/pymmcore-plus/pull/54) ([pre-commit-ci[bot]](https://github.com/apps/pre-commit-ci))
- Add robust guess/get methods for objectives and channel group [\#53](https://github.com/pymmcore-plus/pymmcore-plus/pull/53) ([ianhi](https://github.com/ianhi))

## [v0.1.5](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.1.5) (2021-08-31)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.1.4...v0.1.5)

**Merged pull requests:**

- \[pre-commit.ci\] pre-commit autoupdate [\#50](https://github.com/pymmcore-plus/pymmcore-plus/pull/50) ([pre-commit-ci[bot]](https://github.com/apps/pre-commit-ci))
- \[pre-commit.ci\] pre-commit autoupdate [\#49](https://github.com/pymmcore-plus/pymmcore-plus/pull/49) ([pre-commit-ci[bot]](https://github.com/apps/pre-commit-ci))
- Set minimum pymmcore version [\#48](https://github.com/pymmcore-plus/pymmcore-plus/pull/48) ([ianhi](https://github.com/ianhi))
- Always call `unloadAllDevices` [\#47](https://github.com/pymmcore-plus/pymmcore-plus/pull/47) ([ianhi](https://github.com/ianhi))
- Fix serialization of Configuration and Metadata objects [\#46](https://github.com/pymmcore-plus/pymmcore-plus/pull/46) ([tlambert03](https://github.com/tlambert03))
- fix func name in docstring [\#45](https://github.com/pymmcore-plus/pymmcore-plus/pull/45) ([ianhi](https://github.com/ianhi))

## [v0.1.4](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.1.4) (2021-08-14)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.1.3...v0.1.4)

**Merged pull requests:**

- \[pre-commit.ci\] pre-commit autoupdate [\#41](https://github.com/pymmcore-plus/pymmcore-plus/pull/41) ([pre-commit-ci[bot]](https://github.com/apps/pre-commit-ci))
- Return better config objects [\#40](https://github.com/pymmcore-plus/pymmcore-plus/pull/40) ([tlambert03](https://github.com/tlambert03))
- Change order of channels in `_fix_image` to BGRA [\#39](https://github.com/pymmcore-plus/pymmcore-plus/pull/39) ([tlambert03](https://github.com/tlambert03))
- add setProperty override that emits propertyChanged [\#38](https://github.com/pymmcore-plus/pymmcore-plus/pull/38) ([tlambert03](https://github.com/tlambert03))
- slightly better deviceSchema implementation [\#37](https://github.com/pymmcore-plus/pymmcore-plus/pull/37) ([tlambert03](https://github.com/tlambert03))
- add fix\_image for cameras with `getNumberOfComponents` != 1 [\#36](https://github.com/pymmcore-plus/pymmcore-plus/pull/36) ([tlambert03](https://github.com/tlambert03))
- add getDeviceSchema and getDeviceProperties methods [\#35](https://github.com/pymmcore-plus/pymmcore-plus/pull/35) ([tlambert03](https://github.com/tlambert03))
- fix shared mem [\#34](https://github.com/pymmcore-plus/pymmcore-plus/pull/34) ([tlambert03](https://github.com/tlambert03))
- \[pre-commit.ci\] pre-commit autoupdate [\#33](https://github.com/pymmcore-plus/pymmcore-plus/pull/33) ([pre-commit-ci[bot]](https://github.com/apps/pre-commit-ci))
- ENH: Check for mda canceled while waiting [\#32](https://github.com/pymmcore-plus/pymmcore-plus/pull/32) ([ianhi](https://github.com/ianhi))
- add new configSet signal to qcallback [\#28](https://github.com/pymmcore-plus/pymmcore-plus/pull/28) ([ianhi](https://github.com/ianhi))
- Add new `configSet` signal. [\#26](https://github.com/pymmcore-plus/pymmcore-plus/pull/26) ([ianhi](https://github.com/ianhi))
- Set exposure after setting channel in run\_mda [\#24](https://github.com/pymmcore-plus/pymmcore-plus/pull/24) ([ianhi](https://github.com/ianhi))
- misc fixes [\#22](https://github.com/pymmcore-plus/pymmcore-plus/pull/22) ([tlambert03](https://github.com/tlambert03))
- improve test coverage [\#20](https://github.com/pymmcore-plus/pymmcore-plus/pull/20) ([tlambert03](https://github.com/tlambert03))
- Add pythonic Enums, Metadata and Configuration objects [\#16](https://github.com/pymmcore-plus/pymmcore-plus/pull/16) ([tlambert03](https://github.com/tlambert03))

## [v0.1.3](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.1.3) (2021-07-15)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.1.2...v0.1.3)

**Merged pull requests:**

- bring back qcallback [\#19](https://github.com/pymmcore-plus/pymmcore-plus/pull/19) ([tlambert03](https://github.com/tlambert03))

## [v0.1.2](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.1.2) (2021-07-13)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.1.1...v0.1.2)

## [v0.1.1](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.1.1) (2021-07-08)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.1.0...v0.1.1)

**Merged pull requests:**

- Unify callback API and restructure package [\#14](https://github.com/pymmcore-plus/pymmcore-plus/pull/14) ([tlambert03](https://github.com/tlambert03))
- Add automatic micromanager discovery for linux [\#12](https://github.com/pymmcore-plus/pymmcore-plus/pull/12) ([ianhi](https://github.com/ianhi))
- \[pre-commit.ci\] pre-commit autoupdate [\#11](https://github.com/pymmcore-plus/pymmcore-plus/pull/11) ([pre-commit-ci[bot]](https://github.com/apps/pre-commit-ci))

## [v0.1.0](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.1.0) (2021-07-03)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/v0.0.1...v0.1.0)

**Merged pull requests:**

- Rename to pymmcore-plus, update readme [\#8](https://github.com/pymmcore-plus/pymmcore-plus/pull/8) ([tlambert03](https://github.com/tlambert03))
- add typing\_extensions to install requires [\#5](https://github.com/pymmcore-plus/pymmcore-plus/pull/5) ([ianhi](https://github.com/ianhi))
- emit\_signal\("onMDAFinished", sequence\)  [\#4](https://github.com/pymmcore-plus/pymmcore-plus/pull/4) ([fdrgsp](https://github.com/fdrgsp))
- fix find-micromanager, add CI tests [\#3](https://github.com/pymmcore-plus/pymmcore-plus/pull/3) ([tlambert03](https://github.com/tlambert03))
- fix mda event serialization [\#2](https://github.com/pymmcore-plus/pymmcore-plus/pull/2) ([tlambert03](https://github.com/tlambert03))
- onMDAFrameReady [\#1](https://github.com/pymmcore-plus/pymmcore-plus/pull/1) ([fdrgsp](https://github.com/fdrgsp))

## [v0.0.1](https://github.com/pymmcore-plus/pymmcore-plus/tree/v0.0.1) (2021-05-17)

[Full Changelog](https://github.com/pymmcore-plus/pymmcore-plus/compare/10feec7b166047f4da3322396960ca1aae87ef6a...v0.0.1)



\* *This Changelog was automatically generated by [github_changelog_generator](https://github.com/github-changelog-generator/github-changelog-generator)*
