# Project 9 — Validation Report

**Validation date:** November 12, 2026

**Deployed gateway and backend image release:** v0.7.1

**Backend behavior:** Synthetic inference responses

## 1. Evidence Scope

This report consolidates observed local and Azure results.

It is a manually prepared summary, not an automatically generated transcript. Several deployed exercises were performed interactively.

Credential values, live tokens, tenant identifiers, subscription identifiers, and workstation identifiers are excluded.

## 2. Regression Baseline

| Environment | Result |
|---|---|
| Developer Python 3.11 environment | 197 passed |
| Final gateway image under restricted Linux runtime | 197 passed |
| Existing test-client dependency warning | One deprecation warning |

Tests cover JWT validation, model policy, backend authentication, quotas, concurrency, safe diagnostics, audit events, timeout configuration, local governance, certificate expiration, and request-error safety.

These are test counts, not counts of independently deployed controls.

## 3. Container Verification

Both final candidates built successfully using:

- A digest-pinned Python 3.11 Debian 13 base.
- A hashed Linux runtime dependency lockfile.
- Hash-enforced binary-package installation.
- Updated version-pinned packaging tools.
- Distribution package updates.
- Root-owned application files.
- Removed setuid/setgid file bits.
- Non-root runtime configuration.

Local checks verified UID 999, imports, dependency consistency, and non-writable application files.

Additional local runtime tests explicitly enabled zero capabilities, no-new-privileges, a read-only root filesystem, and temporary storage.

Those Docker runtime flags are not claimed as independently verified Azure settings.

Six hardened container boundary checks passed before the final request-error changes. The later final-image regression suite includes those source-error regression tests.

The final backend image separately rejected a non-ASCII credential with HTTP 401.

## 4. Deployed Authorization

After both v0.7.1 image references were ready:

| Request | Result |
|---|---|
| Reader requests research-model | HTTP 200; exact synthetic contract |
| Reader requests restricted-model | HTTP 403; denial contract |
| Missing token | HTTP 401; denial contract |
| Invalid token | HTTP 401; denial contract |

The remote validator also checks denied responses for absence of inference output.

Successful Admin restricted-model access is locally tested but was not exercised in the current Azure remote flow.

## 5. Backend Boundary

Configuration inspection confirmed:

- Internal-only backend ingress.
- Insecure HTTP ingress disabled.
- Matching recovery-secret references.
- Ready gateway and backend revisions.

A workstation request to the internal backend received platform HTTP 404.

Direct requests from inside the gateway container verified:

| Credential | Result |
|---|---|
| Missing | HTTP 401 |
| Invalid | HTTP 401 |
| Configured | HTTP 200; expected response |

Internal ingress is not exclusive gateway-only reachability.

## 6. Deployed Quota and Concurrency

### Quota

Observed HTTP 429 with the expected error contract and Retry-After: 13.

Inference succeeded after the quota window expired.

The rejection occurred on request 30 of that run; earlier admitted requests could consume the same window.

### Concurrency

An eight-request burst returned:

- Five concurrency HTTP 503 responses with Retry-After: 1.
- Three HTTP 200 responses with valid contracts.

Azure logs contained five concurrency_exceeded and three inference_succeeded events.

Three aggregate successes do not imply three simultaneous backend calls. Local tests establish the two-slot invariant.

These exercises were performed during implementation before the final dependency and request-error release. They are not claimed as repeated load tests of every later revision.

## 7. Startup and Timeout Evidence

An earlier gateway diagnostic recorded transport_timeout after approximately ten seconds.

After the read allowance increased to sixty seconds, a request following scale-down returned HTTP 200 in 36.47 seconds. Backend events showed a new replica starting.

This is one correlated scale-from-zero observation on v0.5.1. It supports the mitigation but does not establish guaranteed cold-start latency.

Automatic inference retries remain disabled.

## 8. Request-Error Safety

Two source-review issues were reproduced:

1. HTTP 422 validation details could reflect submitted input.
2. Non-ASCII backend credentials could raise TypeError.

Fourteen regression tests were added.

After v0.7.1 deployment:

- Invalid gateway input returned HTTP 422 with only a generic error.
- Invalid backend input returned the same generic error contract.
- A non-ASCII backend credential returned HTTP 401.

No authentication bypass was demonstrated by these findings.

## 9. Security Decision Logging

Azure events were observed for inference success, model denial, missing token, invalid token, concurrency rejection, and backend failure during the rollback exercise.

Local tests verify fixed event fields and sensitive-data exclusion.

Framework validation failures receive sanitized responses but are outside current structured decision-event coverage.

Durable retention, tamper resistance, caller identity correlation, alerting, and log-delivery failure behavior were not validated.

## 10. Service-Credential Exercises

### Rotation and Retirement

- Replacement staged under a distinct name in both applications.
- Backend switched first.
- Old gateway credential rejected.
- Gateway switched and validation passed.
- Old-reference revisions inspected and inactive.
- Old secrets removed from both applications.
- Absence verified and validation passed again.

### Failed-Change Rollback

- Deliberately mismatched gateway credential produced HTTP 502.
- Diagnostic recorded upstream_rejected and upstream HTTP 401.
- Identity and model denials remained enforced.
- Working reference restored; validation passed 4/4.
- Exercise secret removed after its revision became inactive.

### Controlled Compromise Recovery

- Existing credential designated presumed-compromised.
- Fresh recovery credential staged and applied.
- Presumed-compromised credential rejected with HTTP 401.
- Service restored using the fresh credential.
- Old-reference revisions confirmed inactive.
- Presumed-compromised secret entries removed from both applications.
- Absence verified; validation passed 4/4.

This validates response actions, not actual leakage, incident detection, or a full compromise investigation.

## 11. Certificate Exercises

- Replacement encrypted key generated and checked.
- Public certificate appended to Entra alongside the original.
- Replacement acquired a token and passed deployed validation.
- Replacement installed as the default local credential.
- Original Entra registration removed.
- Original credential rejected for fresh token acquisition with invalid_client / 700027.
- Replacement passed validation afterward.

Previously issued token revocation was not tested.

## 12. Client Recovery, Expiration, and Cleanup

Controlled missing-key and incorrect-passphrase cases failed before token acquisition.

Restoring normal configuration permitted deployed validation to pass 4/4.

Fourteen expiration tests cover validity boundaries, warnings, invalid configuration, missing files, and malformed certificates.

The live public certificate was healthy and expires December 12, 2026 at 11:50:43 UTC.

Retired local credentials, duplicate rotation files, and the empty failed-generation file were removed. The default key and certificate were preserved; expiration and deployed validation checks passed afterward.

Deletion does not establish erasure from backups or snapshots.

## 13. Local Governance

Fifteen tests passed for role authorization, three distinct subjects, approval sequencing, immutable proposals, stale-change rejection, replay rejection, and isolated snapshots.

The workflow trusts local test principals and does not control deployed policy changes.

## 14. Dependency and OS Scans

| Scan | Gateway | Backend |
|---|---:|---:|
| Known Python-package vulnerabilities reported | 0 | 0 |
| High OS package/advisory findings | 47 | 47 |
| Critical OS findings | 0 | 0 |
| Unique OS advisory IDs | 11 | 11 |

OS scanning selected high and critical severities.

The remaining findings were retained, not suppressed. See the container security review for applicability evidence and limitations.

## 15. Final Scaling Observation

Both deployed applications were inspected with:

- Minimum replicas: 0.
- Maximum replicas: 1.

This is configuration evidence, not proof that no replica is currently running.

## 16. Validation Script Scope

| Script | Scope |
|---|---|
| validate_azure_gateway.py | Deployed HTTPS gateway |
| validate_live_gateway.py | Real Entra token with in-process synthetic inference |
| validate_container_gateway.py | Already running loopback HTTP gateway |
| check_certificate_expiry.py | Local public-certificate validity |

The revised in-process validator passed 4/4.

The revised loopback HTTP validator was not separately exercised during the final review. It must not be treated as additional deployed Azure evidence.
