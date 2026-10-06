# Unit Test Instructions — U4 build-and-banner

## Framework and Setup

- `pytest` and Streamlit's `AppTest`, from `requirements-dev.txt`. No new dependency or configuration.
- Dashboard tests build the app only through `tests/gate_app.py` (allowed visitor by default), as the sign-in gate unit established.
- `tests/conftest.py` already supplies the signing secret and a temp `HSM_AUDIT_PATH`.

## Running This Unit's Tests

The runner check before the first Red step (Step 1):

```bash
python3 -m pytest tests/test_dashboard_gate.py tests/test_dashboard_app.py -q
```

This unit's tests:

```bash
python3 -m pytest tests/test_build_info.py tests/test_dashboard_build_banner.py tests/test_dashboard_gate.py tests/test_dashboard_app.py tests/test_dashboard_embedded.py -q
```

A single behaviour, for example the fingerprint:

```bash
python3 -m pytest tests/test_build_info.py -k fingerprint -q
```

## Test Files and Volume (Standard strategy)

| File | Component | Tests (at least) |
|------|-----------|------------------|
| `tests/test_build_info.py` | BuildInfo | 12: loose ref; packed ref; detached HEAD; `.git` file; real repository against `git rev-parse` (skipped without git); fingerprint stable; fingerprint changes on an edit; ignores `__pycache__`, `.pyc` and the audit file; malformed `.git` falls back; labels; `python -m agents.build_info`; no Streamlit import |
| `tests/test_dashboard_build_banner.py` | DashboardShell caption and banner (`AppTest`) | 8: caption last in sidebar before and after a persona login; caption on Screen 4; none on gate screens; "Build unknown" on error; banner once with copy and icon before the tabs; banner before a persona login; banner absent on Screen 4 and gate screens; unsaved-write notice below the banner |
| Existing dashboard files | Whole dashboard | Unchanged in number; assertions adjusted only where they meet the new caption or banner |

## Coverage Targets

- `agents/build_info.py` fully covered.
- The new `app.py` helpers fully covered.
- Repository coverage stays at or above `.coverage-floor` (95.00) and the 80% gate. The passing count stays at or above `.test-floor` (745). No floor file, `.coveragerc` omit or `# pragma: no cover` is touched.

## Mocking and Stubbing

- **Git trees:** build them in `tmp_path` by writing `.git/HEAD`, `.git/refs/heads/<branch>` and `.git/packed-refs` by hand. No git binary is needed, except for the one real-repository test.
- **Fingerprint trees:** copy a few small `.py` files into `tmp_path/agents/` and `tmp_path/dashboard/`, without `.git`.
- **In the app:** patch `agents.build_info.build_info` (through the module attribute `app.py` uses) to return a fixed `BuildInfo`, or to raise for the B7 test. Force Screen 4 by patching `embedded.start`, as `test_dashboard_embedded.py` does.

## Test Data

- Commit SHA `0123456789abcdef0123456789abcdef01234567` gives the label "Build 0123456".
- A fingerprint label is "Build src-" plus the first 8 hex characters of the digest.
- Banner copy: "Demo data: changes you make are reset periodically." with icon "ℹ️".
