"""Module entrypoint for `python -m stratum`."""

from .main import run


if __name__ == "__main__":
    raise SystemExit(run())
