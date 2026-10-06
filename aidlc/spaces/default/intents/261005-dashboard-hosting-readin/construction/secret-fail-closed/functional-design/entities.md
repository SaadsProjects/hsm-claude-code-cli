# Entities — U1 secret-fail-closed

## Sources

- `inception/domain-design/components.md` (TokenAuth, LocalSecretTooling, BurnedSecretCheck; entities PersonaToken, LocalSecretFile)
- `inception/contract-design/contract-summary.md` C1, C2
- `functional-design-questions.md` Q1–Q4

```yaml
entities:
  - name: SigningSecret
    description: The HMAC key every process uses to mint and verify persona tokens. Never stored in source or committed config.
    attributes:
      - name: variable_name
        type: string
        required: true
        default: "HSM_SIGNING_SECRET"
      - name: value
        type: secret string
        required: true
        constraints: [at least 32 bytes when encoded as UTF-8, never logged, never shown, never written to committed files]
      - name: source
        type: enum
        required: true
        allowed: [process_environment, local_secret_file, streamlit_secrets, test_fixture]
    constraints:
      - There is no default or fallback value
      - It is read at the moment a token is minted or verified, not when code is loaded
    relationships:
      - signs PersonaToken (one secret signs many tokens)

  - name: PersonaToken
    description: Signed claims identifying a demo persona; unchanged in shape by this unit.
    attributes:
      - name: token
        type: string
        required: true
        unique: true
      - name: user_id
        type: string
        required: true
        references: demo user list (mock_hsm.db.USERS)
      - name: persona
        type: string
        required: true
      - name: expires_at
        type: timestamp
        required: true
      - name: signature
        type: string
        required: true
    relationships:
      - signed by exactly one SigningSecret value

  - name: LocalSecretFile
    description: The git-ignored file holding the developer's local signing secret.
    attributes:
      - name: path
        type: path
        required: true
        default: ".env.local in the project root"
      - name: entries
        type: list of KEY=VALUE lines
        required: true
        constraints: [contains a HSM_SIGNING_SECRET entry of at least 32 bytes]
    constraints:
      - Always ignored by git through an explicit line outside the AI-DLC-managed block
      - Created only by the dev-secret script; overwritten only with its overwrite option
    relationships:
      - is one source of SigningSecret

  - name: SecretRefusal
    description: The outcome of any check that finds the secret missing or too short.
    attributes:
      - name: reason
        type: enum
        required: true
        allowed: [missing, too_short]
      - name: message
        type: string
        required: true
        constraints: [names HSM_SIGNING_SECRET, never contains the secret value]
      - name: surface
        type: enum
        required: true
        allowed: [exception, process_exit, hook_deny, tool_error, http_503]
    relationships:
      - raised about one SigningSecret

  - name: BurnedSecretExclusionList
    description: The scan's list of files allowed to contain the burned value (TEMPORARY_EXCLUSIONS).
    attributes:
      - name: entries
        type: list of paths
        required: true
        constraints: [empty after this unit]
```

## Summary

- **SigningSecret** is the key at the centre of this unit. It comes from the environment, the local `.env.local`, Streamlit secrets (hosted, used from U3 on), or a per-run test value. It has no default, and it is checked whenever a token is minted or verified.
- **PersonaToken** is unchanged in shape. Only where its key comes from changes.
- **LocalSecretFile** is the developer's `.env.local`, which the dev-secret script writes.
- **SecretRefusal** is the single shape of "no valid secret". It surfaces as an exception, a process exit, a hook deny, a tool error or an HTTP 503, always naming the variable and never its value.
- **BurnedSecretExclusionList** becomes empty when the burned value is removed.

## Assumptions & Open Questions

None.
