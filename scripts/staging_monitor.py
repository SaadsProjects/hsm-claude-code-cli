"""Staging monitor: open one GitHub issue when staging stays down for 5 minutes.

    python scripts/staging_monitor.py [--state PATH]

Run by .github/workflows/staging-monitor.yml every 30 minutes. Each run makes
one plain GET of the target's Streamlit health path, classifies the answer as
up, asleep or down, and compares it with what the previous runs remembered
(a small JSON state file the workflow carries in the Actions cache). A down
seen again at least 5 minutes after the first sighting opens one outage
issue; the first up or asleep afterwards closes it. It never signs in, never
wakes a sleeping app and never writes app data.

Exit codes: 0 the run did its job; 1 it opened an outage issue or a step
failed (so GitHub's failed-run email goes out); 2 bad usage.
"""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

EXIT_OK, EXIT_FAIL, EXIT_USAGE = 0, 1, 2
EXIT_CODES = "exit codes: 0 the run did its job; 1 an outage issue was opened or a step failed; 2 bad usage"
DEFAULT_STATE_PATH = ".staging-monitor/state.json"
AUTH_VARIABLE = "GITHUB_TOKEN"
PRACTICE_SUFFIX = ".invalid"

SCHEMA_VERSION = 1
MAX_STATE_ENTRIES = 16
# Streamlit Community Cloud's own wording while an app sleeps or starts, as
# in scripts/postdeploy_check.py. Matched case-insensitively; until a real
# sleep has been seen this list may need adjusting (runbook, BR1.6).
SLEEP_WORDING = ("gone to sleep", "get this app back up", "your app is in the oven", "waking up")
CONFIRM_AFTER = timedelta(minutes=5)  # down this long after the first sighting is an outage
# A suspicion not checked for this long (GitHub skipped runs) is forgotten, so
# two unrelated blips never add up to an outage. Alerted outages never go stale.
STALE_AFTER = timedelta(minutes=90)

# Answered by the app's own Streamlit server behind Streamlit Community Cloud;
# every other path redirects to the host's sign-in (functional-spec.md).
HEALTH_PATH = "/~/+/_stcore/health"
REQUEST_TIMEOUT_SECONDS = 20
BODY_LIMIT_BYTES = 65536
USER_AGENT = "hsm-staging-monitor"

API_ROOT = "https://api.github.com"
API_HOST = "api.github.com"
GITHUB_SERVER = "https://github.com"
REAL_LABEL = "staging-outage"
PRACTICE_LABEL = "staging-outage-practice"
BOT_AUTHOR = "github-actions[bot]"
RUNBOOK_PATH = "docs/staging-app.md"

REASONS = ("ok", "asleep", "no-answer", "timeout", "redirect", "error-status", "unexpected-page")

_UTC_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_RUN_ID = re.compile(r"[0-9]+")
_CONTENT_TYPE = re.compile(r"[A-Za-z0-9.+-]+/[A-Za-z0-9.+-]+")


# ------------------------------------------------------------------- times
def format_time(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(text) -> datetime:
    """Read back a time written by format_time; anything else is a ValueError."""
    if not isinstance(text, str) or not _UTC_TIME.match(text):
        raise ValueError("not an ISO-8601 UTC time")
    return datetime.fromisoformat(text[:-1] + "+00:00")


# ------------------------------------------------------------- target keys
def target_key(url: str) -> str:
    """The canonical form of a target: lower-case ``https://host[:port]``.

    Paths, queries and fragments are dropped because only the host is probed.
    Credentials in the address are refused rather than stripped, so they can
    never end up in a log line or an issue.
    """
    parts = urlsplit((url or "").strip())
    if parts.scheme.lower() != "https" or not parts.hostname or "@" in parts.netloc:
        raise ValueError("not an https URL with a host")
    port = f":{parts.port}" if parts.port else ""
    return f"https://{parts.hostname.lower()}{port}"


# ------------------------------------------------------------------- state
@dataclass(frozen=True)
class OutageState:
    """What the monitor remembers about one target between runs (entities.md)."""

    target_key: str
    last_checked_at: datetime
    last_reason: str
    first_down_at: datetime | None = None
    alerted_at: datetime | None = None
    issue_number: int | None = None
    acknowledged: bool = False
    practice: bool = False


def _key_problem(key) -> str | None:
    try:
        return None if target_key(key) == key else "target key is not canonical"
    except ValueError:
        return "target key is not an https host"


def state_problem(state: OutageState, checked_at: datetime) -> str | None:
    """Why ``state`` can't be trusted for a check at ``checked_at`` (BR2.1), or None."""
    problem = _key_problem(state.target_key)
    if problem:
        return problem
    if state.last_reason not in REASONS:
        return "unknown last reason"
    if (state.alerted_at is None) != (state.issue_number is None):
        return "alerted time and issue number must be set together"
    if state.issue_number is not None and state.issue_number < 1:
        return "issue number must be positive"
    if state.acknowledged and state.alerted_at is None:
        return "acknowledged without an alert"
    if state.first_down_at is None and state.alerted_at is not None:
        return "alerted without a first sighting"
    if state.last_checked_at > checked_at:
        return "last check is later than this check"
    return None


_TIME_FIELDS = ("last_checked_at", "first_down_at", "alerted_at")


def _entry_to_json(state: OutageState) -> dict:
    data = asdict(state)
    for name in _TIME_FIELDS:
        data[name] = format_time(data[name]) if data[name] is not None else None
    return data


def _optional_time(text) -> datetime | None:
    return None if text is None else parse_time(text)


def _entry_from_json(key, data) -> OutageState | None:
    """An entry checked field by field against entities.md, or None."""
    if not isinstance(data, dict) or set(data) != {f.name for f in fields(OutageState)}:
        return None
    try:
        last_checked_at = parse_time(data["last_checked_at"])
        first_down_at, alerted_at = (_optional_time(data[name]) for name in ("first_down_at", "alerted_at"))
    except ValueError:
        return None
    number = data["issue_number"]
    flags_ok = type(data["acknowledged"]) is bool and type(data["practice"]) is bool
    if (number is not None and type(number) is not int) or not flags_ok or data["target_key"] != key:
        return None
    if not isinstance(data["last_reason"], str):
        return None
    state = OutageState(
        target_key=key,
        last_checked_at=last_checked_at,
        last_reason=data["last_reason"],
        first_down_at=first_down_at,
        alerted_at=alerted_at,
        issue_number=number,
        acknowledged=data["acknowledged"],
        practice=data["practice"],
    )
    # Ordering against this run's time is checked when deciding (BR2.1).
    return None if state_problem(state, state.last_checked_at) else state


def load_state(path) -> tuple[dict[str, OutageState], list[str]]:
    """The saved states and notes for the log. Never raises: anything that
    can't be trusted reads as no state, and the note says why (NFR5.1)."""
    path = Path(path)
    if not path.exists():
        return {}, ["no saved state"]
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}, ["discarded (not readable)"]
    try:
        data = json.loads(text)
    except ValueError:
        return {}, ["discarded (not readable JSON)"]
    if not isinstance(data, dict):
        return {}, ["discarded (wrong shape)"]
    version = data.get("schema_version")
    if version != SCHEMA_VERSION or type(version) is not int:
        return {}, [f"discarded (schema version {_safe_version(version)} not understood)"]
    entries = data.get("entries")
    if not isinstance(entries, dict):
        return {}, ["discarded (wrong shape)"]
    states, notes = {}, []
    for key, entry in entries.items():
        state = _entry_from_json(key, entry)
        if state is None:
            notes.append("discarded an inconsistent entry")
        else:
            states[key] = state
    return states, notes


def _safe_version(version) -> str:
    # The version is printed; only an integer is echoed, never arbitrary text.
    return str(version) if type(version) is int else "None"


def save_state(path, states: dict[str, OutageState], now: datetime) -> None:
    """Write the states atomically, keeping the MAX_STATE_ENTRIES most
    recently checked. Raises OSError when the file can't be written."""
    path = Path(path)
    kept = sorted(states.values(), key=lambda s: s.last_checked_at, reverse=True)[:MAX_STATE_ENTRIES]
    data = {
        "schema_version": SCHEMA_VERSION,
        "written_at": format_time(now),
        "entries": {state.target_key: _entry_to_json(state) for state in kept},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temp = tempfile.mkstemp(dir=path.parent, prefix=".state-", suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(data, out, indent=2, sort_keys=True)
        os.replace(temp, path)
    except BaseException:
        Path(temp).unlink(missing_ok=True)
        raise


# --------------------------------------------------------------- classifier
@dataclass(frozen=True)
class ProbeResult:
    """What one GET of the health path returned. Never persisted; the body is
    only matched against fixed markers, never logged (NFR4.2)."""

    target: str
    checked_at: datetime
    status: int | None
    error_kind: str = "none"  # none, no-answer or timeout
    body_text: str = ""
    content_type: str = ""
    body_bytes: int = 0


@dataclass(frozen=True)
class Observation:
    target_key: str
    checked_at: datetime
    outcome: str  # up, asleep or down
    reason: str  # one of REASONS
    status: int | None


UP, ASLEEP, DOWN = "up", "asleep", "down"


def _reason(result: ProbeResult) -> str:
    """BR1.2-BR1.5, in that order: the first match wins."""
    if result.error_kind != "none" or result.status is None:
        return "timeout" if result.error_kind == "timeout" else "no-answer"
    if any(wording in result.body_text.casefold() for wording in SLEEP_WORDING):
        return "asleep"
    if result.status == 200 and result.body_text.strip() == "ok":
        return "ok"
    if 300 <= result.status < 400:
        return "redirect"
    return "error-status" if result.status >= 400 else "unexpected-page"


def classify(result: ProbeResult, key: str) -> Observation:
    reason = _reason(result)
    outcome = {"ok": UP, "asleep": ASLEEP}.get(reason, DOWN)
    return Observation(key, result.checked_at, outcome, reason, result.status)


# ----------------------------------------------------------------- tracker
@dataclass(frozen=True)
class OutageIssue:
    """An open issue the monitor recognised as its own for one target (BR3.1)."""

    number: int
    opened_at: datetime
    target_key: str
    practice: bool = False


@dataclass(frozen=True)
class Decision:
    """The single action for one run. ``keep_on_failure`` is the state to save
    when the GitHub call for open-issue or close-issue fails (BR4.4)."""

    action: str  # nothing, remember, open-issue, leave-open, close-issue, acknowledge, adopt-issue
    red: bool = False
    issue_number: int | None = None
    adopted: bool = False
    keep_on_failure: OutageState | None = None
    notes: tuple[str, ...] = ()


def _checked(state: OutageState, observation: Observation) -> OutageState:
    """BR2.10: every decided run records its check time and reason."""
    return replace(state, last_checked_at=observation.checked_at, last_reason=observation.reason)


def _healthy(observation: Observation, practice: bool) -> OutageState:
    return OutageState(observation.target_key, observation.checked_at, observation.reason, practice=practice)


def _trusted(state, observation, notes) -> OutageState | None:
    """BR2.1 and BR2.2: drop state that can't be trusted or a stale suspicion."""
    if state is None:
        return None
    problem = state_problem(state, observation.checked_at)
    if problem:
        notes.append(f"discarded ({problem})")
        return None
    stale = observation.checked_at - state.last_checked_at > STALE_AFTER
    if state.alerted_at is None and state.first_down_at is not None and stale:
        notes.append("stale suspicion forgotten")
        return None
    return state


def _adopt(state, issue: OutageIssue | None, observation, practice) -> tuple[OutageState | None, bool]:
    """BR2.3: an open monitor issue the state doesn't point to is adopted, so a
    lost or out-of-date state never leads to a second issue."""
    if issue is None or (state is not None and state.issue_number == issue.number):
        return state, False
    base = state or _healthy(observation, practice)
    adopted = replace(
        base,
        issue_number=issue.number,
        alerted_at=issue.opened_at,
        first_down_at=base.first_down_at or issue.opened_at,
        acknowledged=False,
    )
    return adopted, True


def decide(state, observation: Observation, open_issue: OutageIssue | None, *, practice=False):
    """Apply BR2.1-BR2.10 in order; returns ``(new_state, decision)``.

    ``open_issue`` is the monitor's open issue for this target, if GitHub has
    one. ``new_state`` is always an entry to save: since BR2.4 a closed
    practice issue starts the next drill rather than forgetting the entry.
    Pure: no clock, network or environment reads, so every transition is
    tested directly.
    """
    notes: list[str] = []
    state = _trusted(state, observation, notes)
    state, adopted = _adopt(state, open_issue, observation, practice)
    issue_open = open_issue is not None and state is not None and state.issue_number == open_issue.number
    if observation.outcome == DOWN:
        new_state, action, extra = _when_down(state, observation, issue_open, adopted, practice)
    elif issue_open:  # BR2.5, with an issue to close
        new_state, action = _healthy(observation, state.practice), "close-issue"
        extra = {"issue_number": state.issue_number, "keep_on_failure": _checked(state, observation)}
    else:  # BR2.5, nothing open on GitHub
        new_state, action, extra = _healthy(observation, state.practice if state else practice), "nothing", {}
    return new_state, Decision(action, adopted=adopted, notes=tuple(notes), **extra)


def _when_down(state, observation, issue_open, adopted, practice):
    """BR2.4 and BR2.6-BR2.9 for a down observation: (new_state, action, extra)."""
    if state is not None and state.issue_number is not None and not issue_open and not state.acknowledged:
        if state.practice:
            # BR2.4: closing a practice issue ends the drill, and this run is
            # the first sighting of the next one, so a repeat drill with the
            # same address takes two runs like the first.
            return replace(_healthy(observation, True), first_down_at=observation.checked_at), "remember", {}
        return _checked(replace(state, acknowledged=True), observation), "acknowledge", {}
    if issue_open:  # BR2.6 (or BR2.3 when the issue was just adopted)
        action = "adopt-issue" if adopted else "leave-open"
        return _checked(state, observation), action, {"issue_number": state.issue_number}
    if state is not None and state.acknowledged:  # BR2.7
        return _checked(state, observation), "nothing", {}
    if state is None or state.first_down_at is None:  # BR2.8
        return replace(_healthy(observation, practice), first_down_at=observation.checked_at), "remember", {}
    current = _checked(state, observation)
    if observation.checked_at - state.first_down_at >= CONFIRM_AFTER:  # BR2.9
        # issue_number is filled in by the caller once GitHub has created it.
        alerted = replace(current, alerted_at=observation.checked_at)
        return alerted, "open-issue", {"red": True, "keep_on_failure": current}
    return current, "nothing", {}


# --------------------------------------------------------- HTTP boundaries
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Hand every 3xx back as an HTTPError instead of following it. The probe
    reports a redirect as it is (BR1.1), and for GitHub urllib would otherwise
    re-send the Authorization header to wherever the redirect points."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _opener():
    # No cookie processor: build_opener only adds one when asked to.
    return urllib.request.build_opener(_NoRedirect())


def _content_type(headers) -> str:
    # Logged for unrecognised answers (BR1.6), so only a plain type/subtype is kept.
    value = (headers.get("Content-Type") or "").split(";")[0].strip().lower() if headers else ""
    return value if _CONTENT_TYPE.fullmatch(value) else ("other" if value else "none")


def _result(target, checked_at, status, headers, body: bytes) -> ProbeResult:
    return ProbeResult(
        target=target,
        checked_at=checked_at,
        status=status,
        body_text=body.decode("utf-8", errors="replace"),
        content_type=_content_type(headers),
        body_bytes=len(body),
    )


def _failed(target, checked_at, kind) -> ProbeResult:
    return ProbeResult(target=target, checked_at=checked_at, status=None, error_kind=kind)


def probe(target: str, checked_at: datetime, *, timeout=REQUEST_TIMEOUT_SECONDS, opener=None) -> ProbeResult:
    """One GET of the target's health path: no cookies, no credentials, no
    redirects followed, no retry (BR1.1, NFR2.4, NFR6.1). Never raises."""
    parts = urlsplit(target)
    url = f"{parts.scheme}://{parts.netloc}{HEALTH_PATH}"
    request = urllib.request.Request(url, method="GET", headers={"User-Agent": USER_AGENT})
    try:
        with (opener or _opener()).open(request, timeout=timeout) as answer:
            return _result(target, checked_at, answer.status, answer.headers, answer.read(BODY_LIMIT_BYTES))
    except urllib.error.HTTPError as answer:
        with answer:
            return _result(target, checked_at, answer.code, answer.headers, _error_body(answer))
    except TimeoutError:
        return _failed(target, checked_at, "timeout")
    except urllib.error.URLError as exc:
        return _failed(target, checked_at, "timeout" if isinstance(exc.reason, TimeoutError) else "no-answer")
    except (OSError, http.client.HTTPException, ValueError):
        # ValueError covers a host that can't be IDNA-encoded (UnicodeError):
        # nothing could be asked, so there was no answer.
        return _failed(target, checked_at, "no-answer")


def _error_body(answer) -> bytes:
    # The status already answers; a body that can't be read only loses the
    # sleep-wording check, which then falls back to the status.
    try:
        return answer.read(BODY_LIMIT_BYTES) or b""
    except (OSError, http.client.HTTPException):
        return b""


class GitHubError(Exception):
    """A GitHub call failed. Its text is only ever built from fixed words and
    the HTTP status, so it is safe to print (NFR4.3)."""

    def __init__(self, status: int | None = None, unexpected: bool = False):
        self.status = status
        super().__init__("unexpected answer" if unexpected else _status_text(status))


def _status_text(status: int | None) -> str:
    return f"HTTP {status}" if status is not None else "no answer"


def github_request(method: str, path: str, token: str, body=None) -> urllib.request.Request:
    """A request to the GitHub API host only; the token goes nowhere else (NFR6.4)."""
    url = API_ROOT + path
    parts = urlsplit(url)
    if not path.startswith("/") or parts.hostname != API_HOST or parts.scheme != "https" or "@" in parts.netloc:
        raise ValueError("GitHub requests go only to the API host")
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    return urllib.request.Request(url, data=data, method=method, headers=headers)


def send_json(request, *, opener=None, timeout=REQUEST_TIMEOUT_SECONDS):
    """Send one request and return its JSON (None for an empty answer)."""
    try:
        with (opener or _opener()).open(request, timeout=timeout) as answer:
            raw = answer.read()
    except urllib.error.HTTPError as exc:
        exc.close()
        raise GitHubError(exc.code) from None
    except (OSError, http.client.HTTPException):
        raise GitHubError() from None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        raise GitHubError(unexpected=True) from None


def _valid_repository(repository) -> bool:
    return bool(_REPOSITORY.fullmatch(repository or "")) and not {".", ".."} & set(repository.split("/"))


def make_sender(token: str, repository: str, *, opener=None):
    """``sender(method, path, body=None)`` for paths under this repository."""
    if not _valid_repository(repository):
        raise ValueError("GITHUB_REPOSITORY must look like owner/name")

    def sender(method, path, body=None):
        return send_json(github_request(method, f"/repos/{repository}{path}", token, body), opener=opener)

    return sender


# ------------------------------------------------------------------- issues
def marker(key: str) -> str:
    """The body's last line; with the label and the bot author it is how the
    monitor recognises its own issue for a target, never the title (BR3.1)."""
    return f"<!-- staging-monitor-target: {key} -->"


def _label(practice: bool) -> str:
    return PRACTICE_LABEL if practice else REAL_LABEL


def _own_issue(item, key: str, label: str) -> OutageIssue | None:
    if not isinstance(item, dict) or "pull_request" in item:
        return None
    user, body, number = item.get("user"), item.get("body"), item.get("number")
    labels = {entry.get("name") for entry in item.get("labels") or [] if isinstance(entry, dict)}
    author = user.get("login") if isinstance(user, dict) else None
    if author != BOT_AUTHOR or label not in labels or not isinstance(body, str):
        return None
    if type(number) is not int or number < 1 or marker(key) not in (line.strip() for line in body.splitlines()):
        return None
    try:
        opened_at = parse_time(item.get("created_at"))
    except ValueError:
        return None
    return OutageIssue(number, opened_at, key, label == PRACTICE_LABEL)


def find_open_issue(sender, key: str, practice: bool) -> OutageIssue | None:
    """The oldest open issue the monitor opened for this target, if any.

    Only the first 100 open issues with the label are read; the monitor keeps
    at most one open per target, so more than that is not expected."""
    label = _label(practice)
    listing = sender("GET", f"/issues?state=open&labels={label}&per_page=100")
    if not isinstance(listing, list):
        raise GitHubError(unexpected=True)
    own = [issue for issue in (_own_issue(item, key, label) for item in listing) if issue is not None]
    return min(own, key=lambda issue: issue.number, default=None)


def issue_title(key: str, practice: bool) -> str:
    return f"Practice: {key} is down" if practice else f"Staging is down: {key}"


def issue_body(key: str, practice: bool, first_down_at: datetime, observation: Observation, link) -> str:
    """The fixed template (BR3.2). Only the target and the run link are URLs;
    nothing from the answer's body, headers or an exception goes in (BR3.3)."""
    status = f"HTTP {observation.status}" if observation.status is not None else "no HTTP answer"
    if practice:
        intro = "Practice alert, started by hand against an address that cannot answer. Staging was not checked."
        ending = "Close this issue by hand to end the drill."
    else:
        intro = "The staging monitor saw staging down on two checks at least 5 minutes apart."
        ending = (
            "The monitor closes this issue itself when staging answers again. Closing it by hand during the "
            "outage keeps the monitor quiet until staging recovers."
        )
    return "\n".join(
        [
            intro,
            "",
            f"- Target: {key}",
            f"- First seen down: {format_time(first_down_at)}",
            f"- What was seen: down ({observation.reason}, {status})",
            f"- Last checked: {format_time(observation.checked_at)}",
            f"- Confirming run: {link}" if link else "- Confirming run: link not available",
            "",
            f"What to do: follow the monitoring section of the runbook, `{RUNBOOK_PATH}`.",
            ending,
            "",
            marker(key),
        ]
    )


def recovery_comment(back_at: datetime, first_down_at: datetime) -> str:
    minutes = int((back_at - first_down_at).total_seconds() // 60)
    unit = "minute" if minutes == 1 else "minutes"
    return (
        f"Seen back at {format_time(back_at)}. The outage lasted about {minutes} {unit}, as far as the "
        "monitor can tell from checks every 30 minutes."
    )


def open_outage_issue(sender, key, practice, first_down_at, observation, link) -> int:
    body = {
        "title": issue_title(key, practice),
        "body": issue_body(key, practice, first_down_at, observation, link),
        "labels": [_label(practice)],
    }
    answer = sender("POST", "/issues", body)
    number = answer.get("number") if isinstance(answer, dict) else None
    if type(number) is not int or number < 1:
        raise GitHubError(unexpected=True)
    return number


def close_outage_issue(sender, number: int, back_at: datetime, first_down_at: datetime) -> None:
    """Comment first, then close: a failed comment leaves the issue open, so
    the next up or asleep run tries both again (BR2.5, BR3.5)."""
    sender("POST", f"/issues/{number}/comments", {"body": recovery_comment(back_at, first_down_at)})
    sender("PATCH", f"/issues/{number}", {"state": "closed", "state_reason": "completed"})


def run_link(env) -> str | None:
    """This run's page on github.com, or None rather than any other URL (BR3.3)."""
    server, repository, run_id = (env.get(name) for name in ("GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID"))
    if server != GITHUB_SERVER or not _valid_repository(repository) or not _RUN_ID.fullmatch(run_id or ""):
        return None
    return f"{GITHUB_SERVER}/{repository}/actions/runs/{run_id}"


# ------------------------------------------------------------- command line
class _UsageError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    # argparse would raise SystemExit; main() returns EXIT_USAGE instead.
    def error(self, message):
        self.print_usage(sys.stderr)
        raise _UsageError(message)


def parse_args(argv):
    parser = _Parser(
        prog="staging_monitor.py",
        description="Check staging once and open or close its outage issue.",
        epilog=EXIT_CODES,
    )
    parser.add_argument("--state", default=DEFAULT_STATE_PATH, help=f"state file (default {DEFAULT_STATE_PATH})")
    return parser.parse_args(argv)


def _target(env) -> tuple[str, bool]:
    """BR4.1 and BR4.2. Messages name the variable, never its value."""
    practice = (env.get("PRACTICE_ADDRESS") or "").strip()
    if practice:
        try:
            key = target_key(practice)
        except ValueError:
            key = ""
        if not (urlsplit(key).hostname or "").endswith(PRACTICE_SUFFIX):
            raise _UsageError(f"PRACTICE_ADDRESS must be an https address under {PRACTICE_SUFFIX}")
        return key, True
    try:
        return target_key(env.get("STAGING_URL") or ""), False
    except ValueError:
        raise _UsageError("STAGING_URL is missing or is not an https address") from None


def _github_sender(env):
    if not env.get(AUTH_VARIABLE):
        raise _UsageError(f"{AUTH_VARIABLE} is not set")
    try:
        return make_sender(env[AUTH_VARIABLE], env.get("GITHUB_REPOSITORY") or "")
    except ValueError:
        raise _UsageError("GITHUB_REPOSITORY must look like owner/name") from None


def _attempt(operation: str, action):
    """Run one GitHub call; ``(True, value)`` or ``(False, None)`` after printing
    which operation failed and its HTTP status, never the exception text."""
    try:
        return True, action()
    except GitHubError as exc:
        print(f"error: {operation} failed ({exc})")
    except Exception:  # noqa: BLE001 -- any sender failure becomes a red run that names only the operation; the exception text could carry a URL or the token
        print(f"error: {operation} failed (unexpected error)")
    return False, None


def _print_check(observation: Observation, result: ProbeResult) -> None:
    status = observation.status if observation.status is not None else "none"
    print(
        f"check: target={observation.target_key} at={format_time(observation.checked_at)} "
        f"outcome={observation.outcome} reason={observation.reason} status={status}"
    )
    if observation.reason in ("redirect", "unexpected-page"):  # BR1.6: learn the real sleep answer
        print(f"check-detail: status={result.status} content-type={result.content_type} body-bytes={result.body_bytes}")


_PLAIN_DECISIONS = {"remember": "remember (first sighting)", "nothing": "nothing"}


def _act(decision: Decision, new_state, observation, practice, sender, env):
    """Carry out the decision on GitHub; returns ``(state_to_save, failed)``."""
    adopted = " (adopted)" if decision.adopted else ""
    if decision.action == "open-issue":
        ok, number = _attempt(
            "open issue",
            lambda: open_outage_issue(
                sender, observation.target_key, practice, new_state.first_down_at, observation, run_link(env)
            ),
        )
        if not ok:
            print("decision: open-issue (failed; the next run tries again)")
            return decision.keep_on_failure, True
        print(f"decision: open-issue #{number}")
        return replace(new_state, issue_number=number), False
    if decision.action == "close-issue":
        kept = decision.keep_on_failure
        ok, _ = _attempt(
            "close issue",
            lambda: close_outage_issue(sender, decision.issue_number, observation.checked_at, kept.first_down_at),
        )
        print(f"decision: close-issue #{decision.issue_number}{adopted}" + ("" if ok else " (failed)"))
        return (new_state, False) if ok else (kept, True)
    plain = _PLAIN_DECISIONS.get(decision.action)
    print(f"decision: {plain}" if plain else f"decision: {decision.action} #{decision.issue_number}{adopted}")
    return new_state, False


def _save(path, states, now, failed: bool) -> int:
    try:
        save_state(path, states, now)
    except OSError:
        print("error: save state failed")
        return EXIT_FAIL
    return EXIT_FAIL if failed else EXIT_OK


def run_once(path, key, practice, now, probe_fn, sender, env) -> int:
    """One run of W1/W2 (functional-spec.md): load, check, decide, act, save."""
    states, notes = load_state(path)
    for note in notes:
        print(f"state: {note}")
    result = probe_fn(key, now)
    observation = classify(result, key)
    _print_check(observation, result)
    ok, found = _attempt("list issues", lambda: find_open_issue(sender, key, practice))
    if not ok:  # without the issue list a decision could open a duplicate (BR4.3, BR4.4)
        print("decision: nothing (issues could not be listed)")
        return _save(path, states, now, failed=True)
    new_state, decision = decide(states.get(key), observation, found, practice=practice)
    for note in decision.notes:
        print(f"state: {note}")
    states[key], failed = _act(decision, new_state, observation, practice, sender, env)
    return _save(path, states, now, failed=failed or decision.red)


def main(argv=None, *, env=None, clock=None, probe_fn=None, sender=None) -> int:
    """The command line. Tests inject the environment, the clock, the probe and
    the GitHub sender; the workflow uses the real ones."""
    env = os.environ if env is None else env
    try:
        args = parse_args(sys.argv[1:] if argv is None else argv)
        key, practice = _target(env)
        if sender is None:
            sender = _github_sender(env)
    except _UsageError as exc:
        print(f"staging_monitor.py: error: {exc}", file=sys.stderr)
        return EXIT_USAGE
    now = (clock or (lambda: datetime.now(timezone.utc)))()
    return run_once(Path(args.state), key, practice, now, probe_fn or probe, sender, env)


if __name__ == "__main__":
    sys.exit(main())
