"""CI gate: total line coverage must not fall below .coverage-floor.

    python scripts/coverage_gate.py [--coverage-json coverage.json] [--floor-file .coverage-floor] [--base-ref origin/main]

Once the floor is 80 or more, the 80% gate is on as well; a floor below 80
works as a ratchet only. With --base-ref, it also fails when the floor file is
lower than it was at that ref.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import floor_ratchet
from floor_ratchet import FloorError, lowered, read_floor

GATE = 80.0


def gate_80_on(floor):
    return floor >= GATE


def total_percent(report_path):
    try:
        data = json.loads(Path(report_path).read_text())
        return float(data["totals"]["percent_covered"])
    except (OSError, ValueError, KeyError, TypeError) as e:
        raise FloorError(f"cannot read total coverage from {report_path}: {e}") from None


def check(report_path, floor):
    total = total_percent(report_path)
    problems = []
    if total < floor:
        problems.append(f"coverage {total:.2f}% is below the floor of {floor:.2f}% in .coverage-floor")
    if gate_80_on(floor) and total < GATE:
        problems.append(f"coverage {total:.2f}% is below the {GATE:.0f}% gate")
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--coverage-json", default="coverage.json")
    parser.add_argument("--floor-file", default=".coverage-floor")
    parser.add_argument("--base-ref")
    args = parser.parse_args(argv)
    try:
        floor = read_floor(args.floor_file)
        problems = check(args.coverage_json, floor)
        if args.base_ref and lowered(floor_ratchet.floor_at_ref(args.base_ref, args.floor_file), floor):
            problems.append(f"{args.floor_file} was lowered compared with {args.base_ref}; floors may only rise")
    except FloorError as e:
        print(f"coverage gate: {e}")
        return 1
    for problem in problems:
        print(f"coverage gate: {problem}")
    if not problems:
        state = "on" if gate_80_on(floor) else "off (ratchet only)"
        print(f"coverage gate: ok ({total_percent(args.coverage_json):.2f}%, floor {floor:.2f}%, 80% gate {state})")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
