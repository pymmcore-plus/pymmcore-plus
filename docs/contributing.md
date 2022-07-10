# Contributing

Thanks for thinking of a way to help improve this library! Remember that contributions come in all shapes and sizes beyond writing bug fixes. Contributing to [documentation](#documentation), opening new [issues](https://github.com/pymmcore-plus/pymmcore-plus/issues) for bugs, asking for clarification on things you find unclear, and requesting new features, are all super valuable contributions.

## Code Improvements

All development for this library happens on GitHub [here](https://github.com/pymmcore-plus/pymmcore-plus). We recommend you work with a [Conda](https://www.anaconda.com/products/individual) environment (or an alternative virtual environment like [`venv`](https://docs.python.org/3/library/venv.html)).

The below instructions also use [Mamba](https://github.com/mamba-org/mamba#the-fast-cross-platform-package-manager) which is a very fast implementation of `conda`.

```bash
git clone <your fork>
cd pymmcore-plus
mamba create -n pymm-dev -c conda-forge python
conda actiavte pymm-dev
pip install -e ".[testing, docs]"
pip install pre-commit
pre-commit install
```

The {command}`-e .` flag installs the `pymmcore_plus` folder in ["editable" mode](https://pip.pypa.io/en/stable/cli/pip_install/#editable-installs) and {command}`[testing, docs]` installs the [optional dependencies](https://setuptools.readthedocs.io/en/latest/userguide/dependency_management.html#optional-dependencies) you need for developing `pymmcore_plus`.


### Working with Git

pymmcore-plus is developed using the [github flow](https://docs.github.com/en/get-started/quickstart/github-flow). Using Git/GitHub can confusing (<https://xkcd.com/1597>), so if you're new to Git, you may find it helpful to use a program like [GitHub Desktop](https://desktop.github.com) and to follow a [guide](https://github.com/firstcontributions/first-contributions#first-contributions).

Also feel free to ask for help/advice on the relevant GitHub [issue](https://github.com/pymmcore-plus/pymmcore-plus/issues).

## Documentation

Our documentation on Read the Docs ([pymmcore-plus.rtfd.io](https://pymmcore-plus.readthedocs.io)) is built with [Sphinx](https://www.sphinx-doc.org) from the notebooks in the `docs` folder. It contains both Markdown files and Jupyter notebooks.

Examples are best written as `ipynb` or an `md` file. To write a new example, create in a notebook in the `docs/examples` directory and list its path under one of the [`toctree`s](https://www.sphinx-doc.org/en/master/usage/restructuredtext/directives.html#directive-toctree) in the `index.md` file. When the docs are generated, they will be rendered as static html pages by [myst-nb](https://myst-nb.readthedocs.io).


If you have installed all developer dependencies (see [above](#contributing)), you can rebuild the docs with the following `make` command run from inside the `docs` folder:

```
make html
```

Then you can open the `_build/index.html` file in your browser you should now be able to see the rendered documentation.

Alternatively, you can use [sphinx-autobuild](https://github.com/executablebooks/sphinx-autobuild) to continuously watch source files for changes and rebuild the documentation for you. Sphinx-autobuild will be installed automatically in the dev environment you created earlier so all you need to do is run

```bash
make watch
```
from inside the `docs` folder

In a few seconds your web browser should open up the documentation. Now whenever you save a file the documentation will automatically regenerate and the webpage will refresh for you!
