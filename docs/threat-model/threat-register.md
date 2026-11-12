# Project 9 — Threat Register

**Gateway and backend image release:** v0.7.1

**Regression baseline:** 197 tests passed

Statuses distinguish deployed controls, local tests, observed behavior, and residual limitations.

## AZ-001 — Invalid Identity Token

**Threat:** Missing, forged, expired, or otherwise invalid access token.

**Boundary:** TB-01 / TB-02.

**Controls:** Bearer-header enforcement; JWT signature, issuer, audience, time-claim, subject, token-version, calling-application, and role-claim checks.

**Evidence:** Local JWT tests; deployed missing and invalid tokens return HTTP 401; valid Entra authentication succeeds; denial events observed in Azure.

**Status:** Implemented and deployed; selected paths validated.

**Residual risks:** Bearer-token theft and replay; identity-provider and JWKS availability; not every local attack case has been exercised in Azure.

## AZ-002 — Unauthorized Model Access

**Threat:** An authenticated caller accesses an unauthorized model.

**Boundary:** TB-03.

**Controls:** Static deny-by-default model policy before quota admission and backend invocation.

| Model | Required role |
|---|---|
| research-model | Inference.Reader |
| restricted-model | Inference.Admin |

**Evidence:** Local Reader, Admin, and unknown-model tests; deployed Reader success and restricted-model HTTP 403; response-contract and decision-event checks.

**Status:** Implemented and deployed; selected paths validated.

**Residual risks:** Successful Admin access is locally tested but not demonstrated in the current remote flow. The local governance module does not control deployed policy changes.

## AZ-003 — Gateway Bypass

**Threat:** Direct backend invocation without gateway enforcement.

**Boundary:** TB-04.

**Controls:** Internal-only HTTPS ingress and shared service-credential authentication.

**Evidence:** External ingress disabled; workstation request received platform HTTP 404; deployed missing/invalid credentials returned HTTP 401; configured credential returned HTTP 200.

**Status:** Positive and negative service-authentication paths exercised in Azure.

**Residual risks:**

- Other environment workloads may reach the backend.
- A holder of the service credential can bypass gateway identity, model, quota, and concurrency controls.
- The credential does not attest workload identity.
- Registry image-pull identity is shared.

## AZ-004 — Inference Consumption and Concurrency Abuse

**Threat:** Excessive requests or simultaneous backend calls exhaust resources.

**Boundary:** TB-03 / TB-04.

**Controls:**

- research-model: 30 admitted requests per subject per 60-second window.
- restricted-model: 10 admitted requests per subject per 60-second window.
- Quota state bounded to 1,000 active entries.
- Quota exhaustion returns HTTP 429 with Retry-After.
- Two concurrent backend calls per process.
- Nonblocking overload rejection returns HTTP 503 with Retry-After: 1.
- Capacity released after backend success or failure.

**Evidence:** Local boundary, concurrency, isolation, and recovery tests; deployed quota exhaustion and recovery; eight-request burst produced five concurrency denials and three valid successes with matching Azure events.

**Status:** Implemented and deployed; selected abuse and recovery paths exercised.

**Residual risks:**

- Process-local state resets on restart.
- Multiple workers, replicas, or overlapping revisions maintain independent limits.
- Fixed-window boundaries permit bursts.
- No per-caller concurrency fairness.
- Quota admission precedes concurrency admission; rejected overload requests consume quota.
- These controls do not cap all incoming connections, body memory, or authentication work.
- Replica caps do not guarantee cost or denial-of-service protection.

## AZ-005 — Unauthorized Governance Change

**Threat:** Policy changes are proposed, approved, or applied without authority.

**Boundary:** TB-05.

**Local controls:** Governance-specific roles; three distinct subjects; immutable proposals; version binding; approval sequencing; stale-change and replay rejection.

**Evidence:** Fifteen local governance tests passed.

**Status:** Isolated local workflow implemented and tested.

**Residual risks:** Supplied principals are trusted test inputs. State is in memory. No authenticated governance endpoint, persistent approval record, approval expiry, or deployment enforcement path is implemented.

## AZ-006 — Backend Failure and Startup Delay

**Threat:** Startup, network, authentication, or response failures interrupt inference.

**Boundary:** TB-04.

**Controls:** Fail-closed forwarding; configurable bounded phase timeouts; no redirects; no environment-derived proxies; no automatic inference retries; response-contract validation; sanitized diagnostics.

**Evidence:** Local failure-path tests; Azure transport timeout recorded near ten seconds; a later scale-from-zero request succeeded in 36.47 seconds after increasing the read allowance to sixty seconds.

**Status:** Failure handling validated; limited cold-start success observed.

**Residual risks:** Phase timeouts are not a total execution deadline. Startup delays can still exceed configured limits. One cold-start success does not establish consistent availability.

## AZ-007 — Credential Exposure, Expiration, or Failed Rotation

**Threat:** Client or backend credentials are exposed, expire, or become unusable.

**Boundary:** TB-02 / TB-04.

**Controls:** Encrypted private key outside the project; interactive passphrase; in-memory tokens; Container Apps secret references; controlled rotation and retirement; public-certificate expiration checker.

**Evidence:**

- Service-key rotation and old-secret removal.
- Deliberate mismatch and successful rollback.
- Controlled presumed-compromised service-key replacement and retirement.
- Certificate replacement and original-registration removal.
- Retired certificate rejected for fresh token acquisition with invalid_client / 700027.
- Missing-key and incorrect-passphrase failure/recovery.
- Fourteen expiration-check tests.
- Credential cleanup followed by successful deployed validation.

**Status:** Selected rotation, retirement, and controlled recovery exercises completed.

**Residual risks:** No automatic rotation or notification delivery. Previously issued token revocation was not tested. Actual compromise detection, full incident investigation, backup recovery, and secure erasure are not established.

## AZ-008 — Missing or Incomplete Audit Evidence

**Threat:** Security decisions cannot be reconstructed or evidence is exposed or altered.

**Boundary:** TB-05.

**Controls:** Structured decision events with generated IDs, timestamps, fixed reason codes, outcomes, and allowlisted model labels; sanitized backend diagnostics.

**Evidence:** Local contract and sensitive-data exclusion tests; Azure success, identity denial, model denial, concurrency rejection, and backend-failure events.

**Status:** Application decision logging deployed and observed.

**Residual risks:**

- Raw identity omission limits caller correlation.
- Event IDs do not correlate across services.
- Framework validation failures and unexpected exceptions lack current decision-event coverage.
- Direct backend calls do not generate gateway decision events.
- Governance transitions are not integrated with deployed audit logging.
- Durable retention, tamper resistance, alerting, and log-delivery failure behavior are not validated.

## AZ-009 — Vulnerable Container Dependencies

**Threat:** Vulnerable Python or OS components become reachable during normal operation or after compromise.

**Controls:** Updated Python dependencies and packaging tools; hashed runtime lock; digest-pinned Debian 13 base; distribution updates; non-root runtime; root-owned application files; removed setuid/setgid file bits.

**Evidence:** Final Python-package scans reported no known vulnerabilities. Final OS scans reported 47 high findings across 11 advisory IDs per image, with zero critical findings in the selected severity scope.

**Status:** Python findings remediated; OS findings remain unresolved and assessed in the container security review.

**Residual risks:** A clean Python scan is not a vulnerability-free image. SQLite extensions and infocmp remain present. Local runtime restriction flags have not been established in Azure. APT contents are not snapshot-pinned.

## AZ-010 — Unsafe Request Error Handling

**Threat:** Invalid input is reflected in errors or malformed credentials cause unhandled exceptions.

**Boundary:** TB-01 / TB-04.

**Controls:** Generic HTTP 422 validation responses; non-ASCII service-credential rejection; fail-closed invalid credential configuration.

**Evidence:** Fourteen regression tests; deployed gateway and backend validation responses excluded submitted values; deployed non-ASCII credential returned HTTP 401.

**Status:** Fixed in v0.7.1 and verified locally and in Azure.

**Residual risks:** Schema validation occurs before handler authentication. Generic error responses do not establish a comprehensive request-body size limit.
