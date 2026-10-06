"""
Durable, append-only audit trail for the mock HSM backend (unit U2).

Every audited attempt -- a gated schedule publish or PO submit, a dashboard
data write or bulk row, a login or a logout -- becomes one self-contained
entry in an append-only JSON-lines file. The module offers exactly four
operations: ``configure`` (point at a file and initialize), ``append``
(record one entry, durably, before returning), ``append_batch`` (record a
bulk file's entries as one durable line: all of them or none, even across a
crash) and ``page`` (read one page of the scope-filtered, newest-first
view), plus the read-only query ``unavailable_reason``. There is
deliberately no update or delete; the only removal path is
the internal 90-day retention purge, which no caller can trigger directly.

Storage layout: one line per append call,

    {"hwm": 42, "entries": [{...entry 41...}, {...entry 42...}]}

``entries`` holds one entry for ``append``, every entry of the batch for
``append_batch``, and none for the metadata line a purge writes first.
``hwm`` is the high-water mark after the call: the highest entry id ever
assigned, so ids are never reused even after a purge removes every entry.
Entry ids are 12-digit zero-padded decimal strings.

The layout written by the earlier implementation is still read: a line that
is a bare entry object loads as a one-entry call whose ``hwm`` is its id, and
a first line ``{"_meta": {"next_id": N}}`` loads as an empty call with
``hwm = N - 1``. The next purge rewrites such a file in the new layout.

A line is torn exactly when it is the last line and has no terminating
newline; startup cuts it off (a torn batch is discarded whole). Any
newline-terminated line that cannot be read makes the trail unavailable and
is never repaired by the module.

Reads never touch the file: the module keeps an in-memory copy of the
retained entries, built at startup, extended after each durable append and
trimmed by each purge. ``page`` copies it under the audit lock, then filters
and slices outside the lock.

Purge: at startup, then lazily -- at the start of each ``append``,
``append_batch`` and ``page`` call, if 24 hours have passed on the (injectable)
clock since the last purge, the purge runs first. There is no background
thread.

Concurrency: two non-reentrant locks, always taken in this order: the
backend's data write lock (``db._lock``, never taken here), then
``_purge_mutex``, then ``_lock`` (the audit lock). Functions named
``*_locked`` assume the caller holds both module locks.

Failure policy: the trail fails closed. A failed append, an unreadable line
at startup or a purge that fails at or after its file swap marks the trail
unavailable; every later ``append`` and ``page`` raises ``AuditUnavailable``
until ``configure`` runs again (in practice, a backend restart after an
operator fixes the cause -- see the README's "Audit trail" section).
"""

import contextlib
import json
import os
import re
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

ENV_PATH = "HSM_AUDIT_PATH"
DEFAULT_PATH = Path(__file__).resolve().parent / "audit" / "audit.jsonl"

ENTRY_MAX_BYTES = 16 * 1024  # NFR2.3: encoded entry cap
TEXT_MAX_CHARS = 1024  # NFR2.3: caller-supplied text fields are cut to this
RETENTION = timedelta(days=90)  # BR2.5: entries older than this are purged
PURGE_INTERVAL = timedelta(hours=24)  # NFR3.14: lazy purge check interval
PAGE_SIZE = 50  # BR4.3: fixed page size
ID_WIDTH = 12  # BR1.7: zero-padded entry id width

UNKNOWN_USER = "unknown"
SOURCES = frozenset({"dashboard", "claude_code_workflow"})
ACTIONS = frozenset(
    {"add", "update", "delete", "bulk_row", "publish_schedule", "submit_purchase_order", "login", "logout"}
)
OUTCOMES = frozenset({"allowed", "violation"})

_ID_RE = re.compile(rf"\d{{{ID_WIDTH}}}")
_MAX_ID = 10**ID_WIDTH - 1


class AuditUnavailable(Exception):
    """The trail cannot be written or read; the operation must be refused (503)."""


class InvalidEntry(ValueError):
    """The entry is incomplete, malformed or too large; nothing was stored."""


class InvalidPageRequest(ValueError):
    """The page request's ``before`` is malformed (400)."""


class CorruptTrail(Exception):
    """A newline-terminated line of the trail could not be read."""

    def __init__(self, line_no, path, cause=""):
        super().__init__(f"unreadable line {line_no} in {path}" + (f" ({cause})" if cause else ""))
        self.line_no = line_no
        self.path = path


class _RollbackFailed(OSError):
    """A failed append whose truncate-back also failed: bytes from ``offset`` remain."""

    def __init__(self, cause, offset, rollback_error):
        super().__init__(str(cause))
        self.offset = offset
        self.rollback_error = rollback_error


# ================================================================== logging


def _log(level, message):
    """One line on stderr. Never include entry changes, tokens or session ids."""
    print(f"[mock-hsm] {level} audit: {message}", file=sys.stderr, flush=True)


_LOG_UNSAFE_RE = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def _log_safe(value):
    """A caller-supplied value fit for one log line (NFR3.17): control
    characters (including newlines) removed and cut to 100 characters, so a
    typed id can never forge a second log line."""
    return _LOG_UNSAFE_RE.sub("", value)[:100] if isinstance(value, str) else ""


# ============================================================ storage layer
# AuditFile: plain file helpers. None of them take a lock; the business
# logic decides which ones run under the audit lock.


def _resolve_path(path=None):
    if path is not None:
        return Path(path)
    return Path(os.environ.get(ENV_PATH) or DEFAULT_PATH)


def _tmp_path(path):
    return path.with_name(path.name + ".tmp")


def _narrow_mode(path, allowed):
    """chmod ``path`` down to ``allowed`` if it grants anything more (NFR3.9)."""
    if os.stat(path).st_mode & 0o777 & ~allowed:
        os.chmod(path, allowed)


def _ensure_storage(path):
    """Create the directory (0700) and file (0600) if missing, narrow wider
    existing ones (NFR3.9), and delete any leftover purge temp file."""
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _narrow_mode(path.parent, 0o700)
    os.close(_open_append_fd(path))
    _narrow_mode(path, 0o600)
    _tmp_path(path).unlink(missing_ok=True)


def _open_append_fd(path):
    return os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)


def _write_all(fd, data):
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("short write to audit file")
        view = view[written:]


def _append_line(fd, line):
    """Append one complete line (ending in a newline) and fsync before
    returning (BR2.1, NFR3.2). Returns the offset the line starts at.

    On failure, truncates any partial write back to that offset and re-raises,
    so a half-written line never precedes the next append. If the truncate
    fails too, raises ``_RollbackFailed`` naming the offset."""
    offset = os.fstat(fd).st_size
    try:
        _write_all(fd, line)
        os.fsync(fd)
    except OSError as e:
        try:
            os.ftruncate(fd, offset)
        except OSError as trunc_err:
            raise _RollbackFailed(e, offset, trunc_err) from e
        raise
    return offset


def _fsync_dir(path):
    dfd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def _dumps(obj):
    return json.dumps(obj, separators=(",", ":"), allow_nan=False).encode()


def _encode_call(hwm, encoded_entries):
    """One stored line: ``{"hwm": N, "entries": [...]}`` plus its newline."""
    return b'{"hwm":%d,"entries":[' % hwm + b",".join(encoded_entries) + b"]}\n"


def _parse_timestamp(value):
    ts = datetime.fromisoformat(value)
    if ts.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return ts


class _Row:
    """One retained entry in the in-memory copy (AuditMemory)."""

    __slots__ = ("call", "call_hwm", "entry", "entry_id", "site_id", "timestamp", "user_id")

    def __init__(self, entry, call, call_hwm, timestamp):
        self.entry = entry  # the stored entry dict; never handed out directly
        self.entry_id = int(entry["entry_id"])
        self.site_id = entry.get("site_id")
        self.user_id = entry.get("user_id")
        self.timestamp = timestamp  # aware datetime, for the purge
        self.call = call  # which append call (stored line) it came from
        self.call_hwm = call_hwm  # that line's high-water mark


def _check_entry(obj):
    """A loaded entry must have a well-formed id and an aware timestamp."""
    if not isinstance(obj, dict):
        raise ValueError("entry is not an object")
    entry_id = obj.get("entry_id")
    if not isinstance(entry_id, str) or not _ID_RE.fullmatch(entry_id):
        raise ValueError("bad entry_id")
    return _parse_timestamp(obj.get("timestamp"))


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_line(raw, first):
    """Parse one stored line in either layout.

    Returns ``(hwm, [(entry, timestamp), ...], legacy)``; raises ValueError
    for anything else."""
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError("line is not an object")
    if set(obj) == {"hwm", "entries"}:
        hwm, entries = obj["hwm"], obj["entries"]
        if not _is_int(hwm) or not 0 <= hwm <= _MAX_ID or not isinstance(entries, list):
            raise ValueError("bad call line")
        parsed = [(entry, _check_entry(entry)) for entry in entries]
        if any(int(entry["entry_id"]) > hwm for entry, _ in parsed):
            raise ValueError("entry id above the line's high-water mark")
        return hwm, parsed, False
    if set(obj) == {"_meta"}:  # old layout: metadata line, valid only first
        next_id = obj["_meta"].get("next_id") if isinstance(obj["_meta"], dict) else None
        if not first or not _is_int(next_id) or not 1 <= next_id <= _MAX_ID + 1:
            raise ValueError("bad metadata line")
        return next_id - 1, [], True
    ts = _check_entry(obj)  # old layout: one bare entry per line
    return int(obj["entry_id"]), [(obj, ts)], True


class _Loaded:
    """Result of reading the file at startup."""

    def __init__(self):
        self.rows = []  # _Row, in id order
        self.hwm = 0  # the larger of every line's hwm and every entry id
        self.legacy = False  # any line still in the old layout
        self.calls = 0  # number of stored lines (the next call number)
        self.torn = False  # a torn last line was cut off


def _load(path):
    """Read every line (BR2.2) and cut off a torn last line (NFR3.3).

    A newline-terminated line that cannot be parsed in either layout, or ids
    that are not strictly increasing, raise ``CorruptTrail`` before anything
    is changed: such a line came from an append that returned, so the module
    never discards it (NFR3.4)."""
    with open(path, "rb") as f:
        data = f.read()
    *complete, tail = data.split(b"\n")  # tail is b"" for a newline-terminated file
    loaded = _Loaded()
    last_id = 0
    for line_no, raw in enumerate(complete, start=1):
        try:
            hwm, parsed, legacy = _parse_line(raw, first=line_no == 1)
            for entry, ts in parsed:
                row = _Row(entry, loaded.calls, hwm, ts)
                if row.entry_id <= last_id:
                    raise ValueError("entry ids not increasing")
                last_id = row.entry_id
                loaded.rows.append(row)
        except (ValueError, TypeError, AttributeError, RecursionError) as e:
            raise CorruptTrail(line_no, path, type(e).__name__) from None
        loaded.hwm = max(loaded.hwm, hwm, last_id)
        loaded.legacy = loaded.legacy or legacy
        loaded.calls += 1
    if tail:
        with open(path, "r+b") as f:
            f.truncate(len(data) - len(tail))
            f.flush()
            os.fsync(f.fileno())
        loaded.torn = True
    return loaded


def _write_temp(path, hwm, rows):
    """Write the purge's temp file (0600): a leading ``{"hwm": H, "entries": []}``
    line, then every retained call as one line (entries from one call stay
    together), fsync-ed. Returns the temp path; removes it on failure."""
    tmp = _tmp_path(path)
    tmp.unlink(missing_ok=True)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        lines, group = [_encode_call(hwm, [])], []
        for row in rows:
            if group and group[-1].call != row.call:
                lines.append(_encode_call(group[-1].call_hwm, [_dumps(r.entry) for r in group]))
                group = []
            group.append(row)
        if group:
            lines.append(_encode_call(group[-1].call_hwm, [_dumps(r.entry) for r in group]))
        _write_all(fd, b"".join(lines))
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        tmp.unlink(missing_ok=True)
        raise
    os.close(fd)
    return tmp


# ========================================================== business logic
# AuditLog: configure / append / append_batch / page, the high-water mark,
# validation and the 16 KB cap, the unavailable state and the lazy purge.

# Entry fields in stored order (after entry_id and timestamp, which AuditLog assigns).
_FIELDS = (
    "user_id",
    "persona",
    "session_id",
    "source",
    "action",
    "outcome",
    "kind",
    "record_id",
    "site_id",
    "changes",
    "reason",
    "file_row",
)
_REQUIRED = ("user_id", "source", "action", "outcome")
_OPTIONAL_STR = ("persona", "session_id", "kind", "record_id", "site_id", "reason")
_CUT_FIELDS = ("kind", "record_id", "site_id", "reason")  # identity fields are never cut (NFR6.1)

# Bytes an entry gains when entry_id and timestamp are prefixed to its body.
# Timestamps are always written with microseconds, so this is a constant.
_TIMESTAMP_CHARS = len(datetime(2000, 1, 1, tzinfo=timezone.utc).isoformat(timespec="microseconds"))
_PREFIX_BYTES = len(b'{"entry_id":"","timestamp":"",') + ID_WIDTH + _TIMESTAMP_CHARS - 1

_lock = threading.Lock()  # the audit lock; never re-entered (see *_locked)
_purge_mutex = threading.Lock()  # serializes purges and (re)configuration; taken before _lock


def _utc_now():
    return datetime.now(timezone.utc)


class _State:
    """Everything one configured trail owns. Replaced wholesale by configure()."""

    def __init__(self, path, clock):
        self.path = path
        self.clock = clock
        self.fd = None  # the single append descriptor
        self.rows = []  # AuditMemory: retained entries, in id order
        self.next_id = 1  # one above the high-water mark
        self.next_call = 0  # call number of the next stored line
        self.legacy = False  # the file still holds old-layout lines
        self.last_purge = None  # clock time the last purge ran
        self.unavailable = None  # reason string once failed closed


class _Current:
    """Holder for the configured trail (avoids module-level ``global``)."""

    state = None  # current _State; None until configure() or first use


_current = _Current()


# ------------------------------------------------------------- configuration


def configure(path=None, clock=None):
    """Point the module at ``path`` (default: ``$HSM_AUDIT_PATH`` or
    ``mock_hsm/audit/audit.jsonl``) and initialize it: create the file, cut
    off a torn last line, load the entries and the high-water mark, purge
    entries older than 90 days and log one startup line. Clears any
    unavailable state. ``clock`` returns an aware datetime (injectable for
    tests)."""
    with _purge_mutex, _lock:
        _configure_locked(path, clock)


def unavailable_reason():
    """The reason the configured trail is unavailable, or ``None``.

    Read-only: ``configure`` never raises, so a caller that must know whether
    the trail is usable (the embedded backend's start and liveness check)
    reads the outcome back here. ``None`` also before the first configure,
    because nothing has failed yet."""
    state = _current.state
    return None if state is None else state.unavailable


def _configure_locked(path, clock):
    old = _current.state
    if old is not None and old.fd is not None:
        with contextlib.suppress(OSError):  # the old descriptor is abandoned either way
            os.close(old.fd)
    _current.state = _init_locked(_resolve_path(path), clock or _utc_now)


def _ensure_configured():
    """Lazy first-use initialization, double-checked so one thread does it."""
    if _current.state is None:
        with _purge_mutex, _lock:
            if _current.state is None:
                _configure_locked(None, None)


def _init_locked(path, clock):
    state = _State(path, clock)
    try:
        _ensure_storage(path)
        loaded = _load(path)
        state.fd = _open_append_fd(path)
    except CorruptTrail as e:
        state.unavailable = str(e)
        _log("ERROR", f"trail unavailable, unreadable line {e.line_no} in {path}")
        return state
    except OSError as e:
        state.unavailable = f"cannot open {path}: {e}"
        _log("ERROR", f"trail unavailable, cannot open {path} ({e})")
        return state
    state.rows = loaded.rows
    state.next_id = loaded.hwm + 1
    state.next_call = loaded.calls
    state.legacy = loaded.legacy
    purged = _purge_locked(state)
    if state.unavailable is None:
        _log(
            "INFO",
            f"loaded {len(loaded.rows)} entries, torn line {'dropped' if loaded.torn else 'none'}, "
            f"purged {purged}, high-water mark {state.next_id - 1:0{ID_WIDTH}d}",
        )
    return state


def _fail_locked(state, reason):
    """Fail closed: every later append and page raises AuditUnavailable."""
    state.unavailable = reason


# ---------------------------------------------------------------------- purge


def _purge_locked(state):
    """Remove entries older than 90 days (BR2.5, NFR3.14); returns how many.

    Rewrites the file only when something expired or an old-layout line is
    left; otherwise just records the time. The high-water mark is kept on the
    rewritten file's leading line, so ids are never reused (NFR3.15). A
    failure before ``os.replace`` keeps the old file and the trail available
    (retried at the next 24-hour check); a failure at or after it fails the
    trail closed, since the append descriptor may point at the wrong file."""
    now = state.clock()
    state.last_purge = now
    cutoff = now - RETENTION
    kept = [row for row in state.rows if row.timestamp >= cutoff]
    purged = len(state.rows) - len(kept)
    if not purged and not state.legacy:
        return 0
    try:
        tmp = _write_temp(state.path, state.next_id - 1, kept)
    except OSError as e:
        _log(
            "ERROR",
            f"purge failed before swap, writing temp file ({e}); old file kept, trail available, retry in 24 hours",
        )
        return 0
    try:
        os.replace(tmp, state.path)
    except OSError as e:
        tmp.unlink(missing_ok=True)
        _log(
            "ERROR",
            f"purge failed before swap, replacing file ({e}); old file kept, trail available, retry in 24 hours",
        )
        return 0
    try:
        _fsync_dir(state.path)
        new_fd = _open_append_fd(state.path)
    except OSError as e:
        _fail_locked(state, f"purge failed after swap: {e}")
        _log("ERROR", f"purge failed after swap, reopening file ({e}); trail unavailable")
        return 0
    if state.fd is not None:
        with contextlib.suppress(OSError):  # the old descriptor points at the replaced file
            os.close(state.fd)
    state.fd = new_fd
    state.rows = kept
    state.legacy = False
    return purged


def _maybe_purge():
    """The lazy 24-hour check at the start of append, append_batch and page.

    Cheap clock comparison first; if due, take the purge lock then the audit
    lock (the caller holds neither) and purge before the call's own work."""
    state = _current.state
    if state.unavailable is not None or state.clock() - state.last_purge < PURGE_INTERVAL:
        return
    with _purge_mutex, _lock:
        state = _current.state
        if state.unavailable is None and state.clock() - state.last_purge >= PURGE_INTERVAL:
            _purge_locked(state)


# --------------------------------------------------------------------- append


def append(entry):
    """Record one audited attempt durably and return its ``entry_id``.

    ``entry`` carries the C4 fields (user_id, persona, session_id, source,
    action, outcome, kind, record_id, site_id, changes, reason, file_row);
    persona details come from the caller -- this module never looks them up.
    Raises ``InvalidEntry`` (nothing stored) or ``AuditUnavailable`` (the
    entry could not be made durable; the id is not consumed)."""
    return _append_call([_prepare(entry)], "append")[0]


def append_batch(entries):
    """Record several attempts (one bulk file's rows) and return their ids.

    Every entry gets ``append``'s checks and 16 KB cap first, so one invalid
    entry raises ``InvalidEntry`` and nothing is stored. The whole batch must
    fit the id space, else ``AuditUnavailable`` (nothing stored, the trail
    stays up). All entries are then written as one line with one fsync, so
    the batch is all or none, even across a crash (BR1.2, NFR3.3)."""
    if not isinstance(entries, list) or not entries:
        raise InvalidEntry("entries must be a non-empty list")
    return _append_call([_prepare(entry) for entry in entries], "batch append")


def _append_call(prepared, operation):
    _ensure_configured()
    _maybe_purge()
    with _lock:
        state = _current.state
        if state.unavailable is not None:
            raise AuditUnavailable(state.unavailable)
        first_id = state.next_id
        hwm = first_id + len(prepared) - 1
        if hwm > _MAX_ID:
            raise AuditUnavailable("entry id space exhausted")
        now = state.clock().astimezone(timezone.utc)
        timestamp = now.isoformat(timespec="microseconds")
        ids = [f"{first_id + i:0{ID_WIDTH}d}" for i in range(len(prepared))]
        encoded = [
            b'{"entry_id":"%s","timestamp":"%s",' % (entry_id.encode(), timestamp.encode()) + body[1:]
            for entry_id, (body, _) in zip(ids, prepared, strict=True)
        ]
        try:
            _append_line(state.fd, _encode_call(hwm, encoded))
        except OSError as e:
            _fail_locked(state, f"{operation} failed: {e}")
            _log("ERROR", _append_failure_message(operation, e, prepared, state.path))
            raise AuditUnavailable(state.unavailable) from e
        call = state.next_call
        state.rows.extend(
            _Row({"entry_id": entry_id, "timestamp": timestamp, **record}, call, hwm, now)
            for entry_id, (_, record) in zip(ids, prepared, strict=True)
        )
        state.next_id = hwm + 1
        state.next_call = call + 1
    return ids


def _append_failure_message(operation, error, prepared, path):
    """One ERROR line for a failed append (NFR3.16): operation, cause, and the
    kind and record id of the first entry, sanitized (NFR3.17)."""
    first = prepared[0][1]
    what = f"{first['action']} {_log_safe(first['kind'])}/{_log_safe(first['record_id'])}"
    if len(prepared) > 1:
        what = f"{len(prepared)} entries, first {what}"
    message = f"{operation} failed ({error}) for {what}; trail unavailable"
    if isinstance(error, _RollbackFailed):
        message += (
            f"; rollback failed ({error.rollback_error}): remove every byte from offset {error.offset}"
            f" onward in {path} before restarting"
        )
    return message


def _prepare(entry):
    """Validate, cut and cap one entry before the audit lock is taken.

    Returns ``(body, record)``: the encoded entry without ``entry_id`` and
    ``timestamp``, and a decoded copy of it that is independent of the
    caller's objects."""
    record = _validate(entry)
    for field in _CUT_FIELDS:
        if record[field] is not None:
            record[field] = record[field][:TEXT_MAX_CHARS]
    body = _encode_capped(record)
    return body, json.loads(body)


def _validate(entry):
    """BR1.3 completeness checks; returns the normalized field dict."""
    if not isinstance(entry, dict):
        raise InvalidEntry("entry must be a dict")
    unknown = set(entry) - set(_FIELDS)
    if unknown:
        raise InvalidEntry(f"unknown entry fields: {sorted(unknown, key=str)}")
    record = {field: entry.get(field) for field in _FIELDS}
    for field in _REQUIRED:
        if not isinstance(record[field], str) or not record[field].strip():
            raise InvalidEntry(f"{field} is required")
    for field, allowed in (("source", SOURCES), ("action", ACTIONS), ("outcome", OUTCOMES)):
        if record[field] not in allowed:
            raise InvalidEntry(f"{field} must be one of {sorted(allowed)}")
    for field in _OPTIONAL_STR:
        if record[field] is not None and not isinstance(record[field], str):
            raise InvalidEntry(f"{field} must be a string")
    if record["outcome"] == "violation" and not (record["reason"] or "").strip():
        raise InvalidEntry("a violation needs a reason")
    if record["action"] in ("login", "logout") and record["outcome"] != "allowed":
        raise InvalidEntry(f"{record['action']} entries are always allowed")
    if record["changes"] is not None and not isinstance(record["changes"], dict):
        raise InvalidEntry("changes must be an object")
    file_row = record["file_row"]
    if file_row is not None and (not _is_int(file_row) or file_row < 1):
        raise InvalidEntry("file_row must be a positive integer")
    return record


def _encode_capped(record):
    """Encode ``record`` within the 16 KB entry cap (BR1.6, NFR2.3).

    Unserializable ``changes`` become ``{"truncated": true, "unserializable":
    true}``; ``changes`` that push the entry over the cap become
    ``{"truncated": true, "original_bytes": n}``; an entry still over the cap
    is refused with ``InvalidEntry``. Sizes count the entry_id and timestamp
    the entry gets under the lock, so the stored entry is within the cap."""
    changes_bytes = None
    if record["changes"] is not None:
        try:
            changes_bytes = _dumps(record["changes"])
        except (TypeError, ValueError, RecursionError):
            record["changes"] = {"truncated": True, "unserializable": True}
    body = _dumps(record)
    if _PREFIX_BYTES + len(body) <= ENTRY_MAX_BYTES:
        return body
    if changes_bytes is not None:
        record["changes"] = {"truncated": True, "original_bytes": len(changes_bytes)}
        body = _dumps(record)
        if _PREFIX_BYTES + len(body) <= ENTRY_MAX_BYTES:
            return body
    raise InvalidEntry(f"entry exceeds {ENTRY_MAX_BYTES} bytes")


# ----------------------------------------------------------------------- page


def page(viewer, before=None):
    """One page of the audit view, newest first (BR4.1-BR4.4).

    ``viewer`` comes from the verified token: ``user_id``, ``persona``,
    ``site_ids`` and ``region_id``. A region-wide or SYSTEM_ADMIN viewer sees
    every entry; any other viewer sees the entries for its sites plus its own,
    with the same test applied to "unknown" entries. ``before`` (any
    well-formed 12-digit id, whether or not that entry still exists) returns
    only older entries. Raises ``InvalidPageRequest`` for a malformed
    ``before`` and ``AuditUnavailable`` when the trail is down. Reads only the
    in-memory copy, never the file."""
    visible = _visibility(viewer)
    if before is not None and (not isinstance(before, str) or not _ID_RE.fullmatch(before)):
        raise InvalidPageRequest("malformed before")
    _ensure_configured()
    _maybe_purge()
    with _lock:
        state = _current.state
        if state.unavailable is not None:
            raise AuditUnavailable(state.unavailable)
        snapshot = state.rows[:]
    return _select_page(snapshot, visible, int(before) if before is not None else None)


def _visibility(viewer):
    user_id = viewer.get("user_id")
    if not isinstance(user_id, str) or not user_id:
        raise ValueError("viewer needs a user_id")
    if viewer.get("region_id") or viewer.get("persona") == "SYSTEM_ADMIN":
        return lambda row: True  # BR4.1
    site_ids = frozenset(viewer.get("site_ids") or ())
    # BR4.2: own sites or own actions, the same test for "unknown" entries.
    return lambda row: row.site_id in site_ids or row.user_id == user_id


def _select_page(snapshot, visible, before_id):
    """Runs outside the audit lock over a snapshot of the in-memory copy."""
    total, picked, has_more = 0, [], False
    for row in reversed(snapshot):
        if not visible(row):
            continue
        total += 1
        if before_id is not None and row.entry_id >= before_id:
            continue
        if len(picked) < PAGE_SIZE:
            picked.append(row)
        else:
            has_more = True
    # Hand out copies, so no caller can change the in-memory copy.
    entries = [json.loads(_dumps(row.entry)) for row in picked]
    return {
        "entries": entries,
        "next_before": entries[-1]["entry_id"] if has_more else None,
        "limit": PAGE_SIZE,
        "total": total,
    }
