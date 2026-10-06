# Security Design — U2 embedded-backend

## Sources

- `nfr-requirements/security-requirements.md` NFR1.11–NFR1.14, NFR7.2
- `functional-design/rules.md` BR1.1, BR1.2, BR3.1–BR3.3, BR5.1, BR5.2
- `inception/contract-design/contract-summary.md` C1 (secret check), C2 (audit path), C3 (EmbeddedBackend API)
- `nfr-design-questions.md` Q1, Q2 (both A)

## Design Decisions

### S1 — Loopback only (NFR1.11)

The embedded start always constructs the existing threaded server with host `127.0.0.1`; the host is not a parameter of the start function, so no caller can widen it. The only other process-level reachability is from the same host, where every route still requires a signed persona token (C1).

### S2 — Secret check before anything binds (NFR1.12)

The start function calls the U1 secret check (`require_secret`) as its first action after the liveness check fails. A refusal becomes a failed handle whose cause is the refusal's reason text, which names `HSM_SIGNING_SECRET` and never contains the value (C1 message contract). No audit directory is created and no socket is bound.

### S3 — Private audit directory, validated before the audit module sees it (NFR1.13, Q1 A)

```
resolve_audit_path():
    if HSM_AUDIT_PATH set: return it unchanged (operator's choice; the audit module handles it as today)
    dir = <tempfile.gettempdir()>/hsm-demo-<os.getuid() or username>
    try: mkdir(dir, mode=0o700)            # create only; never exist_ok
    except FileExistsError:
        st = lstat(dir)                    # lstat: a symlink is not followed
        refuse unless S_ISDIR(st) and st.st_uid == current uid and (st.st_mode & 0o077) == 0
    return dir / "audit.jsonl"
```

- The embedded start never changes the mode of a directory it did not create in this call, so the audit module's own narrowing of the parent finds nothing to narrow on a valid directory.
- A refusal is a failed start with a cause naming the audit directory and the rule broken (owner, mode or symlink).
- `mock_hsm/audit.py` is unchanged; the separate-process backend keeps its default path and behaviour.
- On a platform without `os.getuid`, the directory name uses the login name and the owner check is skipped; that platform is not a deployment target.

### S4 — Secret never logged; cause never shown (NFR1.14)

- Log messages are built only from the handle's `failure_cause`, which comes from the secret refusal reason, the audit module's unavailable reason, or an `OSError`'s text; none of these contains the secret value.
- The dashboard's Screen 4 renders a fixed string and nothing derived from the handle. Tests assert the absence of the value on both surfaces and of path, address and exception name on the screen.

### S5 — Standard library only (NFR7.2)

`mock_hsm/embedded.py` imports only `logging`, `os`, `socket`, `stat`, `tempfile`, `threading`, `dataclasses`, `datetime`, and `mock_hsm` modules. An AST test enforces this, as U1 did for `mock_hsm/auth.py`.

## Assumptions & Open Questions

None.
