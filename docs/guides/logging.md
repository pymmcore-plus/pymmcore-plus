# Logging

By default, pymmcore-plus logs to the console at the `INFO` level and to a
logfile in the pymmcore-plus application data directory at the `DEBUG` level.
The logfile is named `pymmcore_plus.log` and is rotated at 40MB, with a maximum
retention of 20 logfiles.

## Customizing logging

The [`pymmcore_plus.configure_logging`][] function allows you to customize the
log level, logfile name, and logfile rotation settings.

You may also configure logging using the following environment variables:

| Variable       | Default                                                | Description           |
| -------------- | ------------------------------------------------------ | --------------------- |
| PYMM_LOG_LEVEL | INFO                                                   | The log level.        |
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

Note that both pymmcore-plus and the underlying CMMCore object will write to the log
file. By default, [CMMCorePlus](../api/cmmcoreplus.md) will call `setPrimaryLogFile()`
with the location of the pymmcore-plus logfile upon instantiation.

## Managing logs with the CLI

The `mmcore` CLI provides a `logs` subcommand for managing logs.

{{ CLI_Logs }}

A particularly useful command is `mmcore logs --tail`, which will continually
stream the current logfile to the console. This can be started in another
process and left running to monitor an experiment in progress.

To delete all logfiles, use `mmcore logs --clear`.
