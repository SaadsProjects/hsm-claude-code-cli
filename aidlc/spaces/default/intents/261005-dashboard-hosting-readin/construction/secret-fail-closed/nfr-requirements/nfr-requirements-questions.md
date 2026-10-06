# NFR Requirements Questions — U1 secret-fail-closed

## Sources

- `construction/secret-fail-closed/functional-design/` (functional-spec, rules BR1.1–BR6.1, and the five review items carried to the code plan)
- `inception/requirements-analysis/requirements.md` NFR1 (fail closed, no secret in source, config, logs or errors), NFR3 (quality), NFR4 (observability), NFR7 (supply chain)
- `inception/contract-design/contract-summary.md` C1, C2; code knowledge base `technology-stack.md`

Already set, so not asked: the 32-byte minimum, no fallback, no value in messages, explicit denies, test-first, the coverage and test floors, standard library only, and no new dependencies in this unit.

## Q1. Should the secret check also refuse the old burned value?

It is 37 bytes, so the length rule alone would accept it if someone pasted it into `.env.local`.

A. Yes: `require_secret()` also refuses the burned value specifically (compared by hash, so the literal never reappears in the code), with the same "missing or invalid" style of message
B. No: the length rule and the burned-secret scan are enough
X. Other (please specify)

[Answer]: A

## Q2. What file permissions should `.env.local` get?

A. The dev-secret script creates it readable and writable by you only (mode 600), and a test checks that
B. Leave it to the default for new files
X. Other (please specify)

[Answer]: A

## Consolidated Summary Confirmation

- Burned value (Q1): `require_secret()` also refuses the old burned value, compared by hash so the literal never reappears in the code, with the same style of message.
- `.env.local` permissions (Q2): the dev-secret script creates it with mode 600 (owner read and write only), and a test checks that.

Does this all look correct before I generate the artifact?

- Looks correct
- Request changes

[Answer]: Looks correct
