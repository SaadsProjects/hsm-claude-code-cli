"""Shared helpers for the ratcheting floors in .test-floor and .coverage-floor.

A floor file holds one number. CI fails when a run falls below it, and when a
pull request lowers it: a floor may only rise, so it can't be weakened to make
a run pass.
"""

import math
import subprocess
from pathlib import Path


class FloorError(Exception):
    """A floor file or report could not be read."""


def parse_floor(text, source):
    try:
        value = float(text.strip())
    except ValueError:
        raise FloorError(f"{source}: expected one number, got {text.strip()!r}") from None
    if math.isnan(value) or value < 0:
        raise FloorError(f"{source}: floor must be a non-negative number, got {text.strip()!r}")
    return value


def read_floor(path):
    path = Path(path)
    try:
        return parse_floor(path.read_text(), path)
    except OSError as e:
        raise FloorError(f"cannot read {path}: {e.strerror}") from None


def floor_at_ref(ref, path):
    """The floor recorded in ``path`` at git ``ref``, or None if it didn't exist there."""
    result = subprocess.run(
        ["git", "show", f"{ref}:{Path(path).as_posix()}"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        if "does not exist" in result.stderr or "exists on disk, but not in" in result.stderr:
            return None
        raise FloorError(f"git show {ref}:{path} failed: {result.stderr.strip()}")
    return parse_floor(result.stdout, f"{ref}:{path}")


def lowered(base, current):
    return base is not None and current < base
