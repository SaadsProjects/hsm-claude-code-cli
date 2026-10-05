"""
The mock backend running inside the dashboard's own process (unit U2).

Streamlit Community Cloud runs one process, so the dashboard cannot rely on a
separately started ``python3 -m mock_hsm.server``. ``start()`` hosts the same
request handler (``mock_hsm.server.Handler``) on ``127.0.0.1`` in a daemon
thread and returns a ``BackendHandle``. Module state lives for the whole
process, so the one instance survives every Streamlit rerun and is shared by
every visitor session.

Standard library and ``mock_hsm`` only: this module must never import
Streamlit (team.md Code Style, layer boundaries).
"""

import logging
import os
import socket
import stat
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
from pathlib import Path

from mock_hsm import audit
from mock_hsm.auth import SecretMissingError, require_secret
from mock_hsm.server import Handler

HOST = "127.0.0.1"
AUDIT_FILE_NAME = "audit.jsonl"
LIVENESS_TIMEOUT_S = 0.5  # NFR2.2: a refused or slower connect means "not live"
SHUTDOWN_WAIT_S = 1.0  # bound on stopping a serve loop that is alive but not answering
POLL_INTERVAL_S = 0.1  # how often the serve loop checks for shutdown
REPLACED_MESSAGE = "embedded backend replaced on a new port; the demo data is kept"

_log = logging.getLogger(__name__)
# Module level so a test can stand in for the connect (a simulated timeout).
_connect = socket.create_connection


class BackendNotRunning(RuntimeError):
    """A backend client was asked for while no embedded backend is live."""


@dataclass(frozen=True)
class BackendHandle:
    """What callers see of the one backend (contract C3)."""

    address: str
    host: str
    port: int
    started_at: datetime
    status: str  # "running" | "failed"
    failure_cause: str | None = None


class _Holder:
    """The process-wide instance; every field is read and written under ``lock``."""

    lock = threading.Lock()
    handle = None
    server = None
    thread = None


_holder = _Holder()


class _AuditDirRefused(Exception):
    """The default audit directory can't be used safely; the message is the start's failure cause."""


def _current_uid():
    return os.getuid() if hasattr(os, "getuid") else None


def _default_audit_path():
    """``<temp>/hsm-demo-<user id>/audit.jsonl`` in a directory only this user can enter (NFR1.13).

    The audit module narrows its parent directory to 0700, so the file never
    goes directly in a shared directory such as /tmp. A directory created here
    is made 0700; an existing one is used only if it is a real directory owned
    by this user with no group or other access, and is never changed."""
    uid = _current_uid()
    directory = Path(tempfile.gettempdir()) / f"hsm-demo-{uid if uid is not None else os.getlogin()}"
    try:
        directory.mkdir(mode=0o700)
    except FileExistsError:
        _check_existing_audit_dir(directory, uid)
    except OSError as e:
        raise _AuditDirRefused(f"audit directory {directory} cannot be created: {e}") from e
    else:
        directory.chmod(0o700)  # mkdir's mode is also cut by the umask; we created it, so make it exact
    return directory / AUDIT_FILE_NAME


def _check_existing_audit_dir(directory, uid):
    info = directory.lstat()  # lstat: a symlink is reported, never followed
    if stat.S_ISLNK(info.st_mode):
        problem = "is a symlink"
    elif not stat.S_ISDIR(info.st_mode):
        problem = "is not a directory"
    elif uid is not None and info.st_uid != uid:
        problem = f"is owned by uid {info.st_uid}, not {uid}"
    elif info.st_mode & 0o077:
        problem = f"allows group or other access (mode {stat.S_IMODE(info.st_mode):o}); it must be 700"
    else:
        return
    raise _AuditDirRefused(f"audit directory {directory} {problem}")


def _configure_audit():
    """Point the audit trail at ``HSM_AUDIT_PATH`` (passed through unchanged; the
    operator's choice) or the private default. Returns the failure cause, or ``None``."""
    explicit = os.environ.get(audit.ENV_PATH)
    try:
        path = Path(explicit) if explicit else _default_audit_path()
    except _AuditDirRefused as e:
        return str(e)
    audit.configure(path)
    return audit.unavailable_reason()  # configure() never raises; it records why the trail is unusable


def _failed(port, cause):
    return BackendHandle(
        address=f"http://{HOST}:{port}",
        host=HOST,
        port=port,
        started_at=datetime.now(timezone.utc),
        status="failed",
        failure_cause=cause,
    )


def _probe(port):
    """True if a TCP connect to the port succeeds within LIVENESS_TIMEOUT_S.

    A serve loop that is wedged but still listening completes the handshake
    from the backlog, so this can't see it (plan P2); a dead thread or a
    closed socket it does see."""
    try:
        _connect((HOST, port), timeout=LIVENESS_TIMEOUT_S).close()
    except OSError:  # refused, timed out or reset
        return False
    return True


def _is_live_locked():
    """Live = server thread alive, socket answering, and the audit trail usable
    (a trail that failed at runtime is fixed only by configuring it again)."""
    return (
        _holder.handle is not None
        and _holder.thread.is_alive()
        and _probe(_holder.handle.port)
        and audit.unavailable_reason() is None
    )


def _stop_locked():
    """Stop the serve loop (bounded) if it still runs, always release the socket, forget the instance."""
    server, thread = _holder.server, _holder.thread
    if thread.is_alive():
        # shutdown() waits for the serve loop and would block forever if it is
        # stuck, so it runs on its own thread with a bounded wait.
        stopper = threading.Thread(target=server.shutdown, daemon=True)
        stopper.start()
        stopper.join(SHUTDOWN_WAIT_S)
    server.server_close()
    _holder.handle = _holder.server = _holder.thread = None


def _attempt_locked(port):
    """One start attempt; returns a running or failed handle and never raises or retries."""
    try:
        require_secret()
    except SecretMissingError as e:  # the message names the variable, never the value
        return _failed(port, str(e))
    cause = _configure_audit()
    if cause is not None:
        return _failed(port, cause)
    try:
        server = ThreadingHTTPServer((HOST, port), Handler)
    except OSError as e:
        return _failed(port, f"cannot bind {HOST}:{port}: {e}")
    thread = threading.Thread(
        target=server.serve_forever,
        kwargs={"poll_interval": POLL_INTERVAL_S},
        name="hsm-embedded-backend",
        daemon=True,
    )
    thread.start()
    bound = server.server_address[1]
    _holder.server, _holder.thread = server, thread
    _holder.handle = BackendHandle(
        address=f"http://{HOST}:{bound}",
        host=HOST,
        port=bound,
        started_at=datetime.now(timezone.utc),
        status="running",
    )
    return _holder.handle


def start(port=0):
    """Return the live backend, or make one attempt to start it on ``127.0.0.1``.

    Lock-guarded, so concurrent callers (reruns, visitor sessions) get one
    backend. A live instance is returned as is and ``port`` is ignored. A dead
    one is stopped and its socket closed first, with a warning. A failure comes
    back as ``status="failed"`` with its cause; this never raises and never
    retries, so the caller's next rerun is the retry."""
    with _holder.lock:
        if _holder.handle is not None:
            if _is_live_locked():
                return _holder.handle  # reused: no start work and nothing logged
            _stop_locked()
            _log.warning(REPLACED_MESSAGE)
        handle = _attempt_locked(port)
    if handle.status == "running":
        _log.info("embedded backend listening on %s", handle.address)
    else:  # the cause never holds the secret value: see SecretMissingError and the audit reasons
        _log.warning("embedded backend failed to start: %s", handle.failure_cause)
    return handle


def current():
    """The live backend's handle, or ``None``. Never starts or replaces one."""
    with _holder.lock:
        return _holder.handle if _is_live_locked() else None


def bound_address():
    """The (host, port) the current server's socket is bound to, or ``None``."""
    with _holder.lock:
        return None if _holder.server is None else _holder.server.server_address[:2]


def reset_for_tests():
    """Stop and forget the current instance, so no test sees another's backend."""
    with _holder.lock:
        if _holder.handle is not None:
            _stop_locked()
