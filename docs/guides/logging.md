# Logging

pymmcore-plus routes Python log messages from the `pymmcore-plus` logger to the
underlying CMMCore object via `CMMCore.log()`. CMMCore is the single sink: it
writes records to the primary log file and (optionally) to stderr, applying
its own level thresholds for each.

By default, CMMCore writes log records to a logfile in the pymmcore-plus
application data directory (`pymmcore_plus.log`), rotated at 40 MB with
20-file retention, and to stderr at the `WARNING` threshold. Records emitted
through Python's `pymmcore-plus` logger are forwarded to the same sink, so
Python and C++ log lines share one chronological stream.

These settings are applied to the underlying core every time a `CMMCorePlus`
is instantiated. Note that compared to earlier pymmcore-plus versions, stderr
now also receives MMCore's own C++ WARNING+ messages (previously only Python
`pymmcore-plus.*` log records reached stderr). To silence stderr, call
`configure_logging(log_to_stderr=False)` or `core.enableStderrLog(False)`.
`PYMM_STDERR_LOG=1` forces stderr on.

Python `pymmcore-plus` log records emitted before any `CMMCorePlus` exists
are not captured -- they fall through to Python's standard `lastResort`
handler. To capture pre-core records, attach your own handler to
`logging.getLogger('pymmcore-plus')`.

The `PYMM_LOG_LEVEL` and `PYMM_LOG_FILE` environment variables are read once
when `pymmcore_plus` is imported; setting them after import has no effect.
Use `configure_logging()` to change settings programmatically at any time.

## Customizing logging

The [`pymmcore_plus.configure_logging`][] function lets you change the logfile
path, level thresholds, stderr toggle, and rotation settings. Calls take
effect immediately on the active core (if any) and on any core created later.
Pass `log_to_stderr=False` to silence MMCore's stderr output (or
`core.enableStderrLog(False)` after creation).

You may also configure logging using the following environment variables:

| Variable       | Default                                                | Description           |
| -------------- | ------------------------------------------------------ | --------------------- |
| PYMM_LOG_LEVEL | WARNING                                                | The **stderr** log level threshold. |
| PYMM_LOG_FILE  | `pymmcore_plus.log` in the pymmcore-plus log directory | The logfile location. |

!!! tip "pymmcore-plus log directory"

    The application data directory is platform-dependent. Here are the
    log folders for each supported platform:

    | OS     |  Path  |
    | ------ | ------ |
    | macOS  | ~/Library/Application Support/pymmcore-plus/logs |
    | Unix   | ~/.local/share/pymmcore-plus/logs |
    | Win    | C:\Users\username\AppData\Local\pymmcore-plus\pymmcore-plus\logs |

    You can also use `mmcore logs --reveal` to open the log directory in your
    file manager.

## Managing logs with the CLI

The `mmcore` CLI provides a `logs` subcommand for managing logs.

{{ CLI_Logs }}

A particularly useful command is `mmcore logs --tail`, which will continually
stream the current logfile to the console. This can be started in another
process and left running to monitor an experiment in progress.

To delete all logfiles, use `mmcore logs --clear`.
