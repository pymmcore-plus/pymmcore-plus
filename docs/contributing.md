# Contributing

Thanks for thinking of a way to help improve this library! Remember that
contributions come in all shapes and sizes beyond writing bug fixes.
Contributing to [documentation](#contributing-documentation), opening new
[issues](https://github.com/pymmcore-plus/pymmcore-plus/issues) for bugs, asking
for clarification on things you find unclear, and requesting new features, are
all super valuable contributions.

## Contributing Code

All development for this library happens in the
[pymmcore-plus/pymmcore-plus
](https://github.com/pymmcore-plus/pymmcore-plus) repo on GitHub. We recommend you work
with a [Conda](https://www.anaconda.com/products/individual) environment (or an
alternative virtual environment like
[`venv`](https://docs.python.org/3/library/venv.html)).

The below instructions also use
[Mamba](https://github.com/mamba-org/mamba#the-fast-cross-platform-package-manager)
which is a very fast implementation of `conda`.

```bash
git clone <your fork>
cd pymmcore-plus
mamba create -n pymm-dev -c conda-forge python
conda activate pymm-dev
pip install -e ".[testing, docs]"
pip install pre-commit
pre-commit install
```

The `-e .` flag installs `pymmcore_plus`in ["editable"
mode](https://pip.pypa.io/en/stable/cli/pip_install/#editable-installs) and
`[testing, docs]` installs the optional dependencies you need for developing
`pymmcore-plus`.

!!! note

    `pymmcore-plus` is developed using the [github
    flow](https://docs.github.com/en/get-started/quickstart/github-flow). Using
    Git/GitHub can [confusing](https://xkcd.com/1597) :thinking_face:, so if you're new to Git, you
    may find it helpful to use a program like [GitHub
    Desktop](https://desktop.github.com) and to follow a
    [guide](https://github.com/firstcontributions/first-contributions#first-contributions).

    Also feel free to ask for help/advice on the relevant GitHub
    [issue](https://github.com/pymmcore-plus/pymmcore-plus/issues).

## Contributing Documentation

Our documentation is built with [mkdocs](https://www.mkdocs.org/) from the files
in the `docs` folder.  To build docs locally:

```shell
# install docs dependencies
pip install -e ".[docs]"

# build docs and serve locally
mkdocs serve
```

The docs should be live at <http://127.0.0.1:8000> and will update automatically
as you edit and save them.

## Developing on Apple Silicon

To build a native version of the DemoCamera for local testing on apple silicon, you
can run the following command (you must have [homebrew](https://brew.sh) installed)

```shell
mmcore build-dev
```

This will download the micro-manager repo, build it, and drop the DemoCamera and
Utilities devices into a folder in your pymmcore-plus install folder (by default
`~/Library/Application Support/pymmcore-plus/mm`).  This path is on the default
search path so you should be good to go.  You can confirm by running:

```py
from pymmcore_plus import CMMCorePlus

core = CMMCorePlus()
core.loadSystemConfiguration()
core.snap()
```
