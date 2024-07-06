# CLI Reference

This page provides documentation for the `mmcore` command line tool.

Usage of the CLI requires the `cli` extra to be installed:

```shell
pip install "pymmcore_plus[cli]"
```

The CLI can be used to interact with the `pymmcore_plus` package from the command line,
including the installation, removal, and selection of micro-manager drivers, as
well as executing an experiment and/or showing log files.

::: mkdocs-typer
    :module: pymmcore_plus._cli
    :command: app
