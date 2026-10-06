# Entities — U2 embedded-backend

## Sources

- `inception/domain-design/components.md` (EmbeddedBackend, MockBackend, DashboardShell, HsmClient; BackendInstance, AuditTrail)
- `inception/contract-design/contract-summary.md` C2 (process environment), C3 (EmbeddedBackend API)
- `inception/user-stories/stories.md` US3.1–US3.4
- `functional-design-questions.md` Q1–Q4 (all answered A, summary confirmed)

## Entity Model

```yaml
entities:
  - name: BackendInstance
    description: >
      The one mock backend running inside a dashboard process, as reported to callers.
      Owned by EmbeddedBackend. At most one live instance exists per process.
    identifier: address
    attributes:
      - name: address
        type: text
        required: true
        unique: true
        constraints: "http://127.0.0.1:<port>; never any other host"
      - name: host
        type: text
        required: true
        allowed_values: ["127.0.0.1"]
      - name: port
        type: integer
        required: true
        min: 1
        max: 65535
        constraints: "chosen by the operating system (free port) unless a port is passed explicitly"
      - name: started_at
        type: timestamp (UTC)
        required: true
      - name: status
        type: enum
        required: true
        allowed_values: [running, failed]
      - name: failure_cause
        type: text
        required: false
        constraints: "present only when status is failed; technical text for the log, never shown on screen; never contains the secret value"
    constraints:
      - "status = running implies failure_cause is absent"
      - "status = failed implies failure_cause is present"
      - "callers read the address from the current live instance at each use and never cache it"
      - "a replaced instance is shut down and its socket closed first; its in-memory demo data is lost, and the replacement is logged"
    relationships:
      - target: AuditTrail
        cardinality: many-to-one
        direction: BackendInstance -> AuditTrail
        description: every instance writes to the audit trail configured at its start
      - target: StartAttempt
        cardinality: one-to-one
        direction: StartAttempt -> BackendInstance
        description: each start attempt yields exactly one reported instance (running or failed)

  - name: StartAttempt
    description: >
      One call to start the backend. Serialised by a process-wide lock, so at most one attempt
      runs at a time. Either reuses the live instance or makes one new attempt; never loops.
    identifier: none (transient)
    attributes:
      - name: requested_port
        type: integer
        required: true
        default: 0
        constraints: "0 means a free port; applies only when a new attempt is made, and is ignored when a live instance is reused"
      - name: outcome
        type: enum
        required: true
        allowed_values: [reused, started, failed]
    relationships:
      - target: BackendInstance
        cardinality: one-to-one
        direction: StartAttempt -> BackendInstance

  - name: AuditTrail
    description: >
      The append-only audit file the backend writes on every data write, publish and PO attempt.
      Process-global configuration owned by MockBackend; set by EmbeddedBackend before serving.
    identifier: path
    attributes:
      - name: path
        type: text
        required: true
        constraints: >
          HSM_AUDIT_PATH when set; otherwise <system temp dir>/hsm-demo-<user id>/audit.jsonl for the embedded
          backend, in a directory the app creates with owner-only access. Never a file directly in a shared
          directory (the audit module narrows its parent directory's permissions).
      - name: configured
        type: boolean
        required: true
      - name: unavailable_reason
        type: text
        required: false
        constraints: "set by the audit module instead of raising (OS error or corrupt trail); read back after configuring; present means the start attempt fails"
    relationships: []

  - name: ClientRequest
    description: >
      A dashboard request for a backend client for one persona. Resolves the base address from
      the live BackendInstance only; never from HSM_BASE_URL.
    identifier: none (transient)
    attributes:
      - name: user_id
        type: text
        required: true
      - name: base_url
        type: text
        required: false
        constraints: "when absent, taken from the live BackendInstance address"
    relationships:
      - target: BackendInstance
        cardinality: many-to-one
        direction: ClientRequest -> BackendInstance
        description: requires a live instance; none live is an error naming the cause
```

## Summary

- **BackendInstance** is the only lasting entity this unit adds. It is what callers see: an address on `127.0.0.1`, a status, and a cause when the start failed.
- **StartAttempt** and **ClientRequest** are transient. They exist to state when a start may happen and where a client's address comes from.
- **AuditTrail** already exists in MockBackend. This unit only fixes where its path comes from when the backend runs inside the dashboard.
