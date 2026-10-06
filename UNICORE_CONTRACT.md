# UniCore contract

Status: **DRAFT — for maintainer review.** Sections marked **DECISION** must be
settled by the maintainer before any agent works from this file. Agents may not
change this file, and may not re-open a decided policy.

Scope: the Python-device bridge in **pymmcore-nano** (`src/bridge_devices.h`, the
bridge bindings in `src/_pymmcore_nano.cc`, `src/pymmcore_nano/protocols.py`) and
the unicore layer in **pymmcore-plus** (`src/pymmcore_plus/experimental/unicore/`).

---

## 1. Goal

Python device adapters are real MMCore devices. They reuse the C++ base
machinery (`CDeviceBase` and the `C*Base<>` templates, `PropertyCollection`,
`CStateDeviceBase` labels, `CXYStageBase` unit conversion, the circular buffer,
config files, module locks, error codes) wherever it exists. Python code exists
only where C++ cannot provide the behaviour.

The API for **Python device authors** may differ from the C++ device API. The
API for **UniMMCore users** is the `CMMCorePlus` API, with no additions except
those listed in §4.

## 2. Size budget

Size is the convergence metric. It is measured in non-blank, non-comment source
lines, excluding tests and docs, with this command (to be added as
`scripts/unicore_loc.sh` in both repos):

```
pymmcore-nano:  src/bridge_devices.h, src/pymmcore_nano/protocols.py,
                bridge-related lines of src/_pymmcore_nano.cc
pymmcore-plus:  src/pymmcore_plus/experimental/unicore/**/*.py
```

Baseline (raw `wc -l`, including comments, measured 2026-10-06):

| | main | unicore-fixes3 / nano-unicore-fixes3 |
|---|---|---|
| plus unicore src | 5783 | 3527 (−2256) |
| nano src diff vs main | — | +2725 / −20 |

Rules:

- **R-size-1.** pymmcore-plus unicore source must shrink relative to main.
  Every commit in a deletion round must lower it.
- **R-size-2.** pymmcore-nano may only add code that is the bridge itself: a
  `PyBridge*` class forwarding an MM interface method, the adapter, the property
  factory, the callbacks object, and their bindings. Anything else added to nano
  must be justified in the commit message by citing the policy in §4 that
  requires it.
- **R-size-3.** A fix that adds net lines must cite the invariant (§6) or the
  policy (§4) it serves.

**DECISION D0:** set a numeric target, e.g. "plus unicore src ≤ 2500 lines,
nano bridge ≤ 1500 lines", or leave it as "monotonically decreasing until no
deletion keeps the invariants green".

## 3. Ownership

| Concern | Owner | Python's role |
|---|---|---|
| Property storage, types, limits, allowed values, read-only, pre-init | `CDeviceBase` / `PropertyCollection` | getter/setter callables only |
| Property value format (strings, Float precision) | MMDevice (`MM::FloatProperty`, 4 decimals) | parse strings to Python types for the author |
| State labels and the `Label` property | `CStateDeviceBase` | provide `State` and default labels |
| XY µm ↔ steps, mirroring, adapter origin (steppers) | `CXYStageBase` | steps methods only |
| Locking / serialization | MMCore module lock (per adapter) | none |
| Error codes and error text | `CDeviceBase::SetErrorText`, MMCore | raise exceptions |
| Image buffering, metadata tags, overflow | MMCore circular buffer, `CoreCallback::InsertImage` | produce frames |
| Config file load/save | `CMMCore::loadSystemConfiguration` / `saveSystemConfiguration` | none (see D4) |
| Device registry, labels, roles, parents | MMCore `DeviceManager` | none |
| Which Python object backs a label | the bridge (nano) | none (see D6) |

Python code that duplicates any "Owner" column entry is a deletion target.

## 4. Policies

Each policy has a recommendation. The maintainer marks each one ACCEPTED,
CHANGED (with the replacement text) or REJECTED.

### D1. Shutdown errors — DECISION
- **(a) Recommended.** An exception in `shutdown()` is logged and recorded on the
  device, and `Shutdown()` returns `DEVICE_OK`. Unloading always succeeds.
  Rationale: `DeviceManager::UnloadAllDevices` stops at the first error, and
  `~DeviceManager` re-runs `Shutdown()` from a destructor, so any error path can
  abort the process (measured: abort with two failing devices on
  unicore-fixes3).
- (b) Errors are returned once, as for C++ (current). Requires a mechanism that
  guarantees I1 for any number of failing devices.

### D2. Hub peripherals — DECISION

C++ separates two questions, and so does this policy:

| Question | C++ | Python (this policy) |
|---|---|---|
| Which names can this adapter create? Needs no hub instance. | `InitializeModuleData()` registers fixed names (DemoCamera); `CreateDevice(name)` may also accept names it parses (ASITiger, `"ZStage:Z:32"`) | `peripherals` class attribute; optional `create_peripheral` classmethod |
| Which peripherals are attached now? Needs an initialized hub. | `hub->DetectInstalledDevices()` adds prototype devices; read by `getInstalledDevices()` | `detect_installed_devices()` returns names |
| How does a peripheral talk to its hub? | `GetParentHub()` / `AssignToHub<T>()` in `Initialize()` | `self.get_parent_hub()` in `initialize()` |

- **(a) Recommended.**
  1. **Catalogue (class level, stateless).** A `HubDevice` subclass declares
     ```python
     peripherals: ClassVar[Mapping[str, Callable[[], Device]]]   # name -> factory
     ```
     A factory is a `Device` subclass or a `functools.partial` of one (e.g.
     `partial(Motor, axis="x")`), so that the device type and description
     (`RegisterDevice` needs both) are known without creating a device. For names known only at
     runtime, the hub may override
     ```python
     @classmethod
     def create_peripheral(cls, name: str) -> Device | None: ...
     ```
     whose default looks `name` up in `peripherals`. Both must be pure: no hub
     instance, no I/O, a new device on every call. The names in `peripherals`
     are registered with the adapter when it is registered, so they appear in
     `getAvailableDevices()` and load by name at any time (as DemoCamera's do);
     the adapter's `CreateDevice(name)` asks each of its hub classes'
     `create_peripheral(name)` for any other name (as ASITiger's does), so those
     load but are not listed.
  2. **Detection (instance level, after `initialize()`).**
     ```python
     def detect_installed_devices(self) -> Iterable[str]: ...
     ```
     returns the names of the peripherals present; the default returns every
     key of `peripherals`. It is called only on an initialized hub. Each name
     must resolve through `create_peripheral`, otherwise `getInstalledDevices()`
     raises. Prototypes for `getInstalledDevices()` are C++ stubs holding a name
     and a description (the factory's docstring); no Python device is created.
  3. **Reaching the hub.**
     ```python
     def get_parent_hub(self) -> HubDevice | None: ...   # on Device
     ```
     returns the Python hub object behind `CDeviceBase::GetParentHub()`. As in
     C++, it is valid from `initialize()` on and only finds a hub loaded from the
     same adapter (`DeviceManager::GetParentDevice`); with no parent label set,
     MMCore picks the adapter's last loaded hub. A peripheral keeps the hub it
     gets in `initialize()` and sends all hardware communication through it.
  4. **Loading and order.** Peripherals are loaded by name from the hub's
     adapter (`loadDevice(label, core.getDeviceLibrary(hub_label), name)`), after
     the hub, so that the hub is initialized first: devices of one adapter
     initialize in load order (`initializeAllDevicesParallel`, one thread per
     adapter). They share the adapter's lock with the hub. A hub cannot hand over
     a pre-built device instance; peripherals are always created by the bridge.
  5. **Errors.** A Python error in `create_peripheral` or a factory makes
     `loadDevice` raise a `CMMError` with the Python message; one in
     `detect_installed_devices` makes `getInstalledDevices` raise likewise (I3).

  Deletes: the `(name, object, type)` tuple format, on-demand detection in
  `CreateDevice`, `registerDiscovered`, `isDeviceFactory`, Python-backed
  prototypes, `_HubPeripheralTracker`, `_load_hub_peripheral`, and the hub
  branch of `getDeviceLibrary`. Adds: `get_parent_hub` (bridge + `Device`), the
  C++ prototype stub, and `create_peripheral` lookup in `CreateDevice`.
  Breaking: the instance-returning pattern in the current `HubDevice`
  docstring (acceptable under D5a).
- (b) Keep the current pattern: `detect_installed_devices()` returns
  `(name, instance | class | factory, type)` and is run on demand, also before
  the hub is initialized.

### D3. Property value semantics — DECISION
- **(a) Recommended.** MM semantics. Values cross the bridge as MM strings; Float
  properties carry 4 decimals; `UniMMCore.setProperty` does no Python-side
  validation (C++ checks limits and allowed values); config presets match by
  exact string, as in MMCore. The author's setter receives the value parsed to
  the declared Python type; a parse failure is a device error.
  Deletes: the `UniMMCore.setProperty`, `defineConfig`, `getCurrentConfig`,
  `getCurrentConfigFromCache` and `loadPropertySequence` overrides.
- (b) Python-side validation and numeric-aware preset matching (current).

### D4. Configuration files — DECISION
- **(a) Recommended.** Config files are loaded and saved by C++ only. A Python
  device can be persisted only if it comes from an adapter (an entry-point
  adapter or `register_py_adapter`). Before calling the C++ loader,
  `UniMMCore.loadSystemConfiguration` registers every entry-point adapter named
  in a `Device,` line. Devices loaded with `loadPyDevice` are session-only.
  Deletes: `core/_config.py` (703 lines) and the `#py` line format.
  (Verified: `Device,` and `ConfigGroup,` lines for a registered Python adapter
  round-trip through C++ save/load.)
- (b) Keep the Python config parser and the `#py` prefix (current).

### D5. UniMMCore API compatibility with main — DECISION
- **(a) Recommended.** None required (the module is `experimental`). UniMMCore has
  exactly the `CMMCorePlus` API plus `loadPyDevice`, `register_py_adapter` and
  `getPyDevice` (D6). The optional-label SLM overloads and `getSLMImage` from
  main are dropped.
- (b) Keep main's convenience overloads.

### D6. Device tracking — DECISION
- **(a) Recommended.** The bridge is the single source of truth. nano exposes
  `CMMCore.getPyDevice(label) -> object | None`, returning the Python object
  behind a bridge device. pymmcore-plus keeps no label→device map.
  `isPyDevice(label)` is `getPyDevice(label) is not None`.
  Deletes: `_pydevices`, `_direct_pydevices`, `_pending_pydevices`,
  `_adopt_*`, `_on_bridge_label`, and the `getDeviceLibrary` / `getDeviceName` /
  `getDeviceDescription` overrides (C++ answers these).
- (b) Keep Python-side tracking (current).

### D7. XY stepper position callbacks — DECISION
- **(a) Recommended.** `UsesOnXYStagePositionChanged` returns false for all Python
  XY stages; UIs poll. A Python device may still call
  `notify.on_xy_stage_position_changed`. Deletes the bridge's notification code.
- (b) Report true for steppers and notify on every position-changing call
  (set, relative, origin, adapter origin, home, stop, move).

### Fixed policies (recommended; accept or change)
- **P8 Errors.** A Python exception in a method with an error code becomes a
  device error (code 10100; `NotImplementedError` becomes
  `DEVICE_UNSUPPORTED_COMMAND`), with the exception line first in the text. In a
  value-returning method it becomes a `CMMError` raised to the caller. In
  methods MMCore calls from paths that cannot throw (`Busy`, `IsCapturing`,
  `GetNumberOfPositions`, `Shutdown` under D1a), it is logged and recorded and
  a neutral value is returned.
- **P9 Arrays.** The bridge accepts only arrays it can hand over without
  reinterpretation. A non-C-contiguous or read-only array is copied or rejected,
  never read as if contiguous. Frame sizes must match `w*h*bpp` exactly.
- **P10 Acquisition start.** If `StartSequenceAcquisition` fails after
  `PrepareForAcq`, the bridge calls `AcqFinished` so MMCore closes the
  auto-shutter.
- **P11 Threading.** The MMCore module lock is the only serialization.
  `initializeAllDevices` may run devices from different adapters in parallel.
  Callbacks (`notify.*`, `insert_image`, `PropertyHandle`) may be called from
  any thread, and must raise, not crash, after the device is destroyed.
- **P12 One-off adapters.** `loadPyDevice` creates a private adapter that is
  released when its last device is unloaded.

## 5. Severity classes

Blocking (must be fixed before merge):

- **S1 Crash:** process abort, segfault, or deadlock.
- **S2 Memory safety:** use-after-free, out-of-bounds read or write.
- **S3 Hardware safety:** shutter or illumination left in the wrong state, or a
  stage commanded to an unrequested position.
- **S4 Silent wrong data:** an image, property value or config differs from what
  was produced or set, with no error.
- **S5 Invariant violation:** any I-rule in §6 fails.

Non-blocking (filed as issues; never fixed in a defect round): error message
quality, performance, docs, API ergonomics, style, and anything not in §4 or §6.

## 6. Invariants

Each invariant has one test module in `tests/invariants/` (nano and plus as
appropriate). The test must be **parametrized over the stated quantifiers**, not
written for one scenario.

- **I1 No abort.** For any device type, any subset of loaded devices, and any
  Python method raising (including `shutdown`, `busy`, `is_capturing`, getters,
  `__init__`, `initialize`), in any lifecycle phase (load, init, use, unload,
  `reset`, `unloadAllDevices`, `loadSystemConfiguration`, core destruction), the
  process does not abort. (Subprocess-based test.)
- **I2 No use after free.** After the bridge device behind it is destroyed
  (unload, hub prototype replaced, core destroyed), every `PropertyHandle`,
  `DeviceCallbacks` and `insert_image` call raises `RuntimeError`, from any
  thread.
- **I3 Errors surface.** Every Python exception from a device method either
  reaches the caller as a `CMMError` containing the exception's message, or (on
  P8's non-throwing paths) is recorded and logged. It is never silently
  dropped, and never replaced by an unrelated error.
- **I4 Auto-shutter.** With auto-shutter on, after any sequence of
  start/stop/snap calls, including ones that fail, the shutter is closed
  whenever no acquisition is running.
- **I5 Data fidelity.** For every array layout the API accepts (contiguity,
  writability, dtype, components), the consumer receives exactly the array the
  producer gave (camera → `getImage`/`popNextImage`; `setSLMImage` → device),
  or the call raises.
- **I6 Release.** After every device from an adapter is unloaded (and after
  `reset` or core destruction), no Python device object is referenced by the
  core (weakref test).
- **I7 Single state.** For every property of a Python device, after any
  sequence of core calls and device-author calls, the core's value, limits and
  allowed values equal what the device author last set or the device reports.
- **I8 No deadlock.** Any callback (`notify.*`, `insert_image`) called from a
  device thread while another thread is inside any core call on any device
  completes or raises within a bounded time. (Timeout-based test.)
- **I9 Config round trip.** Under D4, a configuration saved by the core reloads
  to the same devices, parents, pre-init values, groups and presets.

## 7. Process for agents

1. **Read this file first.** If a task needs a policy that is not in §4, stop
   and ask; do not choose one.
2. **Deletion round.** Every commit lowers the §2 metric and keeps every §6
   test green. No new public API and no new mechanisms. Cite the C++ code
   (`file:line` in mmcore or mmdevice) that now provides each deleted behaviour.
   List any user-visible behaviour change in the commit message. Stop when no
   deletion keeps the invariants green, and report the metric before and after.
3. **Defect round.** Report only S1–S5 findings. Each finding needs a test that
   fails now and asserts the general rule (added to `tests/invariants/` or
   extending a parametrization there). Each fix is ≤ 40 source lines and adds
   no mechanism. Non-blocking observations go into a list, not into code.
4. **Regression review.** A separate agent sees only the fix diff and this file,
   and reports only ways the diff can violate §5/§6 that the parent commit could
   not. "None" is a valid answer.
5. **Stopping rule.** The work is done when 3 independent defect-round reviews
   of the same commit report zero S1–S5 findings. Remaining non-blocking items
   are filed as issues.

## 8. Known open S1–S5 items at unicore-fixes3 / nano-unicore-fixes3

These have failing tests on branch `claude/zen-johnson-kibsas` in both repos.

| Item | Class | Resolved by |
|---|---|---|
| Core destruction aborts when two devices' `shutdown()` raise | S1 / I1 | D1a, or a fix under D1b |
| Failed sequence start leaves the auto-shutter open | S3 / I4 | P10 |
| `setSLMImage` reads non-contiguous arrays as contiguous | S4 / I5 | P9 |
| Hub prototypes take over a peripheral's pre-init handles | S4 / I7 | D2a (removed), or a fix under D2b |
| `DeviceCallbacks` use `dev_` without the device mutex | S2 / I2 | P11 |
| Hub detection error swallowed during peripheral load | I3 | D2a (removed), or a fix under D2b |
| Registered-adapter load errors masked as `ModuleNotFoundError` | I3 | D6a (removed), or a fix |
| Stepper claims callbacks but origin/home do not notify | not blocking under D7a | D7 |
