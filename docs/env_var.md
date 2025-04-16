# Environment Variables

The following environment variables may be used to configure pymmcore-plus globally.

<small>*Boolean variables can be set to `1`, `0`, `True`, or `False` (case insensitive).*</small>

| <div style="width:140px">Variable</div>    | Description     | Default |
|--------------------------------------------|-----------------| ------- |
| **`PYMM_DEBUG_LOG`**  | Call `enableDebugLog(True)` when initializing a `CMMCore`.  |      |
| **`PYMM_STDERR_LOG`**  | Call `enableStderrLog(True)` when initializing a `CMMCore`.  |      |
| **`PYMM_BUFFER_SIZE_MB`**  | Circular buffer memory footprint in MB.  |  250 MB    |
| **`PYMM_STRICT_INIT_CHECKS`**  | Enable/disable strict initialization checks  |  Enabled    |
| **`PYMM_PARALLEL_INIT`**  | Enable/disable parallel device initialization  |  Enabled    |
| **`PYMM_LOG_LEVEL`**                       | pymmcore-plus [logging](./guides/logging.md) level.  | `'INFO'`    |
| **`PYMM_LOG_FILE`**   | Logfile location. | `pymmcore_plus.log` in the pymmcore-plus [log directory](./guides/logging.md#customizing-logging) |
| **`MICROMANAGER_PATH`**   | Override location of Micro-Manager directory (with device adapters) | User-directory, described [here](./install.md#set-the-active-micro-manager-installation)   |
| **`PYMM_SIGNALS_BACKEND`** | The event backend to use. Must be one of `'qt'`, `'psygnal'`, or `'auto'`  | `auto` (Qt if `QApplication` exists, otherwise psygnal) |
