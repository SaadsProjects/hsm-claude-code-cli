"""CI gate: the test suite must have no failures and at least .test-floor passing tests.

    python scripts/test_floor.py junit.xml [more.xml ...] [--floor-file .test-floor] [--base-ref origin/main]

Exits 1 with one line per problem. With --base-ref, it also fails when the
floor file is lower than it was at that ref.
"""

import argparse
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import floor_ratchet
from floor_ratchet import FloorError, lowered, read_floor

__test__ = False  # a script under test, not a pytest test module


@dataclass
class Counts:
    passed: int = 0
    failed: int = 0
    skipped: int = 0


def count(paths):
    total = Counts()
    for path in paths:
        try:
            root = ET.parse(path).getroot()
        except (OSError, ET.ParseError) as e:
            raise FloorError(f"cannot read JUnit report {path}: {e}") from None
        suites = [root] if root.tag == "testsuite" else root.findall("testsuite")
        if not suites:
            raise FloorError(f"{path}: no <testsuite> element")
        for suite in suites:
            tests = int(suite.get("tests", 0))
            failed = int(suite.get("failures", 0)) + int(suite.get("errors", 0))
            skipped = int(suite.get("skipped", 0))
            total.passed += tests - failed - skipped
            total.failed += failed
            total.skipped += skipped
    return total


def check(paths, floor):
    counts = count(paths)
    problems = []
    if counts.failed:
        problems.append(f"{counts.failed} failed or errored tests (the floor allows none)")
    if counts.passed < floor:
        problems.append(f"{counts.passed} passed, below the floor of {floor:g} in .test-floor")
    return problems


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("junit", nargs="+")
    parser.add_argument("--floor-file", default=".test-floor")
    parser.add_argument("--base-ref")
    args = parser.parse_args(argv)
    try:
        floor = read_floor(args.floor_file)
        problems = check(args.junit, floor)
        if args.base_ref and lowered(floor_ratchet.floor_at_ref(args.base_ref, args.floor_file), floor):
            problems.append(f"{args.floor_file} was lowered compared with {args.base_ref}; floors may only rise")
    except FloorError as e:
        print(f"test floor: {e}")
        return 1
    for problem in problems:
        print(f"test floor: {problem}")
    if not problems:
        print(f"test floor: ok ({count(args.junit).passed} passed, floor {floor:g})")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
