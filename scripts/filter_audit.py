"""CI gate: fail on high or critical vulnerabilities in a pip-audit JSON report.

    python scripts/filter_audit.py audit.json [--exceptions security-exceptions.toml]

pip-audit has no severity gate and its report carries no severity, so each
finding and its aliases are looked up in the OSV API. A finding blocks when the
worst rating across all of those records is high: any advisory label
(`database_specific.severity`) of HIGH or CRITICAL, or any scored CVSS v3/v4
vector of 7.0 or more. It also blocks (fail closed) when no record carries a
usable rating, or when a lookup fails for any reason other than OSV not knowing
an alias (HTTP 404). Findings listed in security-exceptions.toml are skipped.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_exceptions import load_exceptions

# A fixed https:// URL; bandit still reports its urlopen as B310 (medium), which
# does not block. CI runs bandit with --ignore-nosec, so findings are waived only
# through security-exceptions.toml, never inline.
OSV_URL = "https://api.osv.dev/v1/vulns/{}"
TIMEOUT_SECONDS = 10
BLOCKING_LABELS = ("HIGH", "CRITICAL")
PASSING_LABELS = ("LOW", "MODERATE", "MEDIUM")
BLOCKING_SCORE = 7.0


@dataclass
class Finding:
    package: str
    id: str
    reason: str


def osv_fetch(vuln_id):
    """The OSV record for ``vuln_id``, or None when OSV doesn't know the id (404)."""
    try:
        with urllib.request.urlopen(OSV_URL.format(vuln_id), timeout=TIMEOUT_SECONDS) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def _cvss_score(vector):
    from cvss import CVSS3, CVSS4
    from cvss.exceptions import CVSSError

    try:
        if vector.startswith("CVSS:4"):
            return float(CVSS4(vector).base_score)
        if vector.startswith("CVSS:3"):
            return float(CVSS3(vector).scores()[0])
    except CVSSError:
        return None  # a malformed vector counts as no rating
    return None


def severity(records):
    """Return ``(blocks, reason)`` from the OSV records of one finding and its aliases.

    The worst rating wins: one record saying MODERATE never hides another
    saying CRITICAL, and a lenient label never hides a high CVSS score.
    """
    labels = {str((record.get("database_specific") or {}).get("severity", "")).upper() for record in records}
    scores = [
        score
        for record in records
        for entry in record.get("severity") or []
        if entry.get("type") in ("CVSS_V3", "CVSS_V4")
        for score in [_cvss_score(entry.get("score", ""))]
        if score is not None
    ]
    blocking_labels = sorted(labels & set(BLOCKING_LABELS))
    if blocking_labels:
        return True, f"severity {blocking_labels[0] if len(blocking_labels) == 1 else 'CRITICAL'}"
    if scores and max(scores) >= BLOCKING_SCORE:
        return True, f"CVSS {max(scores):.1f}"
    if labels & set(PASSING_LABELS) or scores:
        rating = ", ".join(sorted(labels & set(PASSING_LABELS))) or f"CVSS {max(scores):.1f}"
        return False, f"severity {rating}"
    return True, "no severity found (fail closed)"


def blocking(report, fetch, excepted):
    found = []
    for dependency in report.get("dependencies", []):
        for vuln in dependency.get("vulns", []):
            ids = [vuln["id"], *vuln.get("aliases", [])]
            if any(("pip-audit", i) in excepted for i in ids):
                continue
            try:
                records = [r for r in (fetch(i) for i in ids) if r]
            except (OSError, ValueError) as e:
                found.append(Finding(dependency.get("name", "?"), vuln["id"], f"lookup failed: {e} (fail closed)"))
                continue
            blocks, reason = severity(records)
            if blocks:
                found.append(Finding(dependency.get("name", "?"), vuln["id"], reason))
    return found


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report")
    parser.add_argument("--exceptions", default="security-exceptions.toml")
    args = parser.parse_args(argv)
    excepted, problems, _ = load_exceptions(args.exceptions)
    if problems:
        for problem in problems:
            print(f"dependency audit: {problem}")
        return 1
    try:
        report = json.loads(Path(args.report).read_text())
    except (OSError, ValueError) as e:
        print(f"dependency audit: cannot read {args.report}: {e}")
        return 1
    found = blocking(report, fetch=osv_fetch, excepted=excepted)
    for f in found:
        print(f"dependency audit: {f.package}: {f.id}: {f.reason}")
    if not found:
        print("dependency audit: ok (no high or critical vulnerabilities)")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
