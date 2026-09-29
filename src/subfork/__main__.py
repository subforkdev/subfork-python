"""Support invocation with python -m subfork."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
