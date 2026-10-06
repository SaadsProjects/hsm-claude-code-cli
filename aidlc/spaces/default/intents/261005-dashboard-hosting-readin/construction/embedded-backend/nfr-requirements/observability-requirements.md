# Observability Requirements — U2 embedded-backend

## Sources

- `inception/requirements-analysis/requirements.md` NFR4, NFR5
- `construction/embedded-backend/functional-design/rules.md` BR2.4, BR5.1–BR5.3

## Requirements

| ID | Requirement | Pass condition | Source |
|----|-------------|----------------|--------|
| NFR4.2 | A failed start writes its technical cause to the app log at warning level or above; the cause never reaches the screen | A test captures the log and the rendered screen for a forced failure | NFR4, BR5.2 |
| NFR4.3 | A replacement of a dead backend is logged as a warning that the backend was replaced and its demo data reset | A test triggers a replacement and finds the warning | BR2.4 |
| NFR4.4 | The sidebar backend caption shows the live backend's real address at render time | An `AppTest` asserts the caption text matches the running instance's address | BR5.3 |
| NFR5.1 | Screen 4 uses text, not colour alone, under the page's h1 title, with no tabs | An `AppTest` asserts the exact message under the title and no tabs. The keyboard-reachable "Sign out" on Screen 4 comes from U3 and is verified by U3's tests | NFR5, BR5.1 |

No metrics or alerting are added: the hosted demo has no monitoring stack, and the post-deploy check (U5) is the deployment health signal.

## Assumptions & Open Questions

None.
