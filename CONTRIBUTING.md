# Contributing

To contribute to this Python client, install its development dependencies using
Python 3.8+ and a modern pip:

```bash
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
```

## Code quality

Install `.[dev]` to get the pinned development tools. Black 24.8.0, isort 5.13.2,
and Flake8 7.1.1 use 100-column formatting, isort's Black profile, and a Python
3.8 target.

```bash
make format       # Sort imports and apply Black to src/ and tests/
make lint         # Check formatting, imports, Flake8 and Google-style docstrings
make typecheck    # Check annotated library code with mypy
make test         # Run the HTTP contract tests
make check        # Run lint, type checking and tests
make build        # Build distributions and check their metadata
```

Activate your environment first, or specify it explicitly, for example:
`make check PYTHON=.venv/bin/python`. The CI lint job uses the same commands.
EditorConfig defines whitespace and newline conventions for supporting editors.

Add annotations and docstrings to new functions, methods and classes, including
constructors and test helpers. Public docstrings should explain side effects,
permissions, return values and failure behavior where useful. JSON dictionaries
retain `Any` values because node parameters and server response fields are dynamic;
this release does not pretend to provide complete generated response models.
Mypy checks library signatures and bodies; Flake8 and formatting cover both the
library and tests. Runtime tests continue to cover Python 3.8 in CI.

## Versioning

```bash
make version                       # Show the current version
make check-version                 # Verify both version fields agree
make bump-patch                    # 2.0.0 -> 2.0.1
make bump-minor                    # 2.0.0 -> 2.1.0
make bump-major                    # 2.0.0 -> 3.0.0
make bump-version VERSION=2.1.0     # Set an explicit stable version
```

Bumps update `pyproject.toml` and `subfork.__version__` together. They do not
commit, tag, or publish. Review and commit the changes before releasing.

## Documentation site

Public documentation lives in `docs/`. Its `mkpages.yml` selects the dark theme.
To generate the Jekyll source with Python 3.12:

```bash
python -m pip install -e '.[docs]'
mkpages build docs --output .mkpages
mkpages preview docs/
```
