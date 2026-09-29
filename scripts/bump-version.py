"""Keep package metadata and the public client version synchronized."""

import argparse
import os
import re
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")


def version_files(root: Path) -> Tuple[str, Dict[Path, Tuple[str, re.Match]]]:
    """Read both declarations and reject missing, invalid, or mismatched versions."""
    files = {}
    versions = []
    for relative, pattern in (
        ("pyproject.toml", r'(?ms)^\[project\]\s*\n(?:(?!^\[).)*?^version = "([^"]+)"'),
        ("src/subfork/__init__.py", r'(?m)^__version__ = "([^"]+)"'),
    ):
        path = root / relative
        content = path.read_text(encoding="utf-8")
        matches = list(re.finditer(pattern, content))
        if len(matches) != 1 or not SEMVER.fullmatch(matches[0].group(1)):
            raise ValueError("Expected one stable x.y.z version in {}.".format(relative))
        files[path] = (content, matches[0])
        versions.append(matches[0].group(1))
    if versions[0] != versions[1]:
        raise ValueError("Version drift between pyproject.toml and __version__; no files changed.")
    return versions[0], files


def next_version(current: str, requested: str) -> str:
    """Compute a stable release version, resetting lower components on major/minor bumps."""
    if SEMVER.fullmatch(requested):
        return requested
    major, minor, patch = map(int, current.split("."))
    if requested == "major":
        return "{}.0.0".format(major + 1)
    if requested == "minor":
        return "{}.{}.0".format(major, minor + 1)
    if requested == "patch":
        return "{}.{}.{}".format(major, minor, patch + 1)
    raise ValueError("Use major, minor, patch, or a stable x.y.z version.")


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Show, check, or update the version without committing or tagging a release."""
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--show", action="store_true")
    group.add_argument("--check", action="store_true")
    group.add_argument("--bump", choices=("major", "minor", "patch"))
    group.add_argument("--set", action="store_true", help="Read the explicit version from VERSION")
    args = parser.parse_args(argv)
    try:
        current, files = version_files(ROOT)
        if args.show or args.check:
            print(current if args.show else "Version fields match: " + current)
            return 0
        requested = os.environ.get("VERSION", "") if args.set else args.bump
        if not requested:
            raise ValueError("Usage: make bump-version VERSION=x.y.z")
        version = next_version(current, requested)
        for path, (content, match) in files.items():
            updated = content[: match.start(1)] + version + content[match.end(1) :]
            if updated != content:
                path.write_text(updated, encoding="utf-8")
        print("{} -> {}".format(current, version))
        return 0
    except (OSError, ValueError) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
