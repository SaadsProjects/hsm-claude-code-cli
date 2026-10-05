"""CI gate: validate security-exceptions.toml.

    python scripts/check_exceptions.py [security-exceptions.toml]

Each `[[exception]]` entry lets one finding through the pip-audit or bandit
gate. It must name the finding (`id`), the `tool`, a `reason`, the date it was
`added`, and an `expires` date at most 90 days later. Expired or malformed
entries fail the build; entries expiring within 14 days print a warning.
"""

import datetime as dt
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib

TOOLS = ("pip-audit", "bandit")
MAX_DAYS = 90
WARN_DAYS = 14


def load_exceptions(path, today=None):
    """Return ``(ids, problems, warnings)``; ``ids`` holds ``(tool, id)`` pairs."""
    today = today or dt.datetime.now(dt.timezone.utc).date()
    path = Path(path)
    if not path.exists():
        return set(), [], []
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as e:
        return set(), [f"{path}: cannot parse ({e})"], []

    ids, problems, warnings = set(), [], []
    for index, entry in enumerate(data.get("exception", []), start=1):
        entry_problems = _entry_problems(entry, f"{path} entry {index}", path, today, warnings)
        if entry_problems:
            problems += entry_problems
        else:
            ids.add((entry["tool"], entry["id"]))
    return ids, problems, warnings


def _entry_problems(entry, where, path, today, warnings):
    id_, tool, reason = entry.get("id"), entry.get("tool"), entry.get("reason")
    added, expires = entry.get("added"), entry.get("expires")
    if not isinstance(id_, str) or not id_:
        return [f"{where}: missing id"]
    where = f"{path} {id_}"
    problems = []
    if tool not in TOOLS:
        problems.append(f"{where}: tool must be one of {', '.join(TOOLS)}")
    if not isinstance(reason, str) or not reason.strip():
        problems.append(f"{where}: missing reason")
    # tomllib returns datetime for date-times; datetime is a date subclass, so
    # reject it explicitly to keep the arithmetic on plain dates.
    if any(not isinstance(d, dt.date) or isinstance(d, dt.datetime) for d in (added, expires)):
        return [*problems, f"{where}: added and expires must be dates (YYYY-MM-DD)"]
    if added > today:
        problems.append(f"{where}: added date is in the future ({added.isoformat()})")
    if (expires - added).days > MAX_DAYS or (expires - today).days > MAX_DAYS:
        problems.append(f"{where}: expires more than {MAX_DAYS} days after it was added or after today")
    if expires < today:
        problems.append(f"{where}: expired on {expires.isoformat()}")
    elif not problems and (expires - today).days <= WARN_DAYS:
        warnings.append(f"{where}: expires on {expires.isoformat()}")
    return problems


def main(argv=None):
    path = (argv or sys.argv[1:] or ["security-exceptions.toml"])[0]
    _, problems, warnings = load_exceptions(path)
    for warning in warnings:
        print(f"security exceptions: warning: {warning}")
    for problem in problems:
        print(f"security exceptions: {problem}")
    if not problems:
        print("security exceptions: ok")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
