"""Write a Markdown job summary for a CI test leg.

    python scripts/job_summary.py ci --python 3.14 --sha <commit> junit.xml [...] \
        [--coverage-json coverage.json --coverage-floor .coverage-floor] >> "$GITHUB_STEP_SUMMARY"

It only formats counts, names, percentages and SHAs it is given; it never
reads environment variables, so no secret can reach the summary.
"""

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from coverage_gate import total_percent
from floor_ratchet import read_floor
from test_floor import count


def reruns(paths):
    """Tests that were retried. pytest-rerunfailures writes a retried test as
    a repeated <testcase> (one entry per attempt); older versions instead add a
    <rerunFailure>/<rerunError> child. Both are recognised."""
    seen, names = set(), []
    for path in paths:
        for case in ET.parse(path).getroot().iter("testcase"):
            name = f"{case.get('classname')}::{case.get('name')}"
            repeated = name in seen
            seen.add(name)
            marked = case.find("rerunFailure") is not None or case.find("rerunError") is not None
            if (repeated or marked) and name not in names:
                names.append(name)
    return names


def ci_summary(python, sha, junit, coverage_json=None, coverage_floor=None):
    counts = count(junit)
    lines = [
        f"### Tests — Python {python}",
        "",
        f"Commit `{sha}`",
        "",
        "| Result | Count |",
        "|---|---|",
        f"| Passed | {counts.passed} |",
        f"| Skipped | {counts.skipped} |",
        f"| Failed | {counts.failed} |",
        "",
    ]
    if coverage_json:
        line = f"Coverage: {total_percent(coverage_json):.2f}%"
        if coverage_floor:
            line += f" (floor {read_floor(coverage_floor):.2f}%)"
        lines += [line, ""]
    rerun = reruns(junit)
    lines.append("Reruns: none" if not rerun else "Reruns (passed on retry):")
    lines += [f"- `{name}`" for name in rerun]
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("kind", choices=["ci"])
    parser.add_argument("--python", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("junit", nargs="+")
    parser.add_argument("--coverage-json")
    parser.add_argument("--coverage-floor")
    args = parser.parse_args(argv)
    print(ci_summary(args.python, args.sha, args.junit, args.coverage_json, args.coverage_floor))
    return 0


if __name__ == "__main__":
    sys.exit(main())
