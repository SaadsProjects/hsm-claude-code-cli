"""CI gate: fail on high-severity bandit findings in a bandit JSON report.

    bandit -r <paths> -f json -o bandit.json; python scripts/filter_bandit.py bandit.json

A finding can be let through by a security-exceptions.toml entry with
`tool = "bandit"` and `id = "<test id>:<file path>"`, e.g. "B602:mock_hsm/x.py".
Files bandit could not scan block too.
"""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_exceptions import load_exceptions

BLOCKING = "HIGH"


@dataclass
class Finding:
    key: str
    reason: str


def blocking(report, excepted):
    found = [
        Finding(error.get("filename", "?"), f"could not scan: {error.get('reason', 'unknown error')}")
        for error in report.get("errors", [])
    ]
    for result in report.get("results", []):
        if str(result.get("issue_severity", "")).upper() != BLOCKING:
            continue
        key = f"{result.get('test_id')}:{Path(result.get('filename', '')).as_posix().removeprefix('./')}"
        if ("bandit", key) in excepted:
            continue
        found.append(Finding(key, f"line {result.get('line_number')}: {result.get('issue_text', '')}"))
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report")
    parser.add_argument("--exceptions", default="security-exceptions.toml")
    args = parser.parse_args(argv)
    excepted, problems, _ = load_exceptions(args.exceptions)
    if problems:
        for problem in problems:
            print(f"bandit: {problem}")
        return 1
    try:
        report = json.loads(Path(args.report).read_text())
    except (OSError, ValueError) as e:
        print(f"bandit: cannot read {args.report}: {e}")
        return 1
    found = blocking(report, excepted)
    for f in found:
        print(f"bandit: {f.key}: {f.reason}")
    if not found:
        print("bandit: ok (no high-severity findings)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
