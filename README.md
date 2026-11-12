# Project 9 — Azure AI Gateway & Inference Security

**Microsoft Entra ID | JWT Validation | Model Authorization | Azure Container Apps | Service Authentication | Quotas | Concurrency | Security Decision Logging**

## Overview

An Azure-deployed security laboratory examining identity enforcement, inference admission controls, and gateway-to-backend trust boundaries.

A certificate-authenticated client obtains a Microsoft Entra token. A public HTTPS gateway validates identity, authorizes the model, applies process-local quotas, and limits concurrent backend calls.

A separate backend uses internal-only HTTPS ingress and a shared service credential. It returns synthetic responses; no actual AI model is invoked.

## Verified Baseline

- Gateway and backend image release: **v0.7.1**.
- Both images deployed and confirmed ready during validation.
- Local regression suite: **197 passed**, one dependency deprecation warning.
- Final gateway image regression suite: **197 passed** under a restricted Linux runtime.
- Azure authorization and response-contract validation: **4/4 passed**.
- Credential rotation, retirement, rollback, and controlled recovery exercises completed.
- Source and packaging review completed for the 52-file review archive.
- Unresolved container OS vulnerabilities remain documented below.

Results describe the tested baseline, not continuous monitoring or guaranteed current availability.

## Implemented Controls

- Entra JWT signature, issuer, audience, time-claim, subject, token-version, and calling-application checks.
- Deny-by-default model authorization.
- Per-subject, per-model process-local quotas.
- Nonblocking admission for two backend calls per gateway process.
- Internal-only HTTPS backend ingress.
- Shared service credential supplied through Container Apps secret references.
- Configurable and bounded backend HTTP phase timeouts.
- Backend response-contract validation.
- No automatic inference retries.
- Generic request-validation errors that do not reflect submitted values.
- Controlled rejection of non-ASCII backend credentials.
- Structured security decision events and sanitized backend diagnostics.
- Managed identity for registry image pulls.
- Digest-pinned deployment references and Python base image.
- Hashed Linux runtime dependency lockfile.
- Non-root runtime, root-owned application files, and removed setuid/setgid file bits.

## Request Processing

FastAPI validates request syntax and schema before the inference handler runs. Invalid requests receive a generic HTTP 422 response.

For valid request bodies, the handler:

1. Validates bearer-header syntax.
2. Validates the Entra token.
3. Authorizes model access.
4. Applies the subject/model quota.
5. Attempts backend concurrency admission.
6. Calls the backend with the service credential.
7. Validates the backend response.
8. Records the decision outcome.

Authentication and model denials do not invoke the backend.

## Model and Admission Policy

| Model | Required role | Admitted requests per subject per 60 seconds |
|---|---|---:|
| research-model | Inference.Reader | 30 |
| restricted-model | Inference.Admin | 10 |

Roles are not implicitly hierarchical.

Quota exhaustion returns HTTP 429 with Retry-After. Backend concurrency exhaustion returns HTTP 503 with Retry-After: 1.

Quota admission precedes concurrency admission. Concurrency rejections and backend failures consume quota admissions.

Both controls are process-local and reset on restart. They do not provide distributed enforcement or caller fairness.

## Verified Results

| Exercise | Result |
|---|---|
| Local regression suite | 197 passed |
| Final gateway image regression suite under restricted Linux runtime | 197 passed |
| Azure authorization and response contracts | 4/4 passed |
| Azure quota exhaustion and recovery | Passed |
| Azure concurrent burst | Five overload rejections and three valid successes |
| Azure decision logging | Expected success and denial events observed |
| Backend service authentication inside Azure | Missing/invalid credentials rejected; configured credential accepted |
| Direct backend request from developer workstation | Platform HTTP 404 |
| Deployed request-error safety | Generic HTTP 422 responses verified |
| Deployed non-ASCII backend credential | HTTP 401 verified |
| Service-key rotation and retirement | Verified |
| Failed-change rollback | Verified |
| Controlled service-key compromise recovery | Verified |
| Certificate rotation and original-certificate rejection | Verified |
| Missing-key and incorrect-passphrase failure handling | Verified |
| Certificate expiration checker | Fourteen tests passed |

The replacement client certificate was verified to expire on December 12, 2026, at 11:50:43 UTC. Its status should be checked again before subsequent live exercises.

A scale-from-zero request on v0.5.1 succeeded in 36.47 seconds with corresponding backend startup events. This is limited availability evidence, not a reliability guarantee.

## Dependency and Container Review

Both final deployed images were scanned before upload:

- Python-package scans: no known vulnerabilities reported.
- OS scans: 47 high package/advisory findings across 11 unique advisory IDs per image.
- Critical OS findings: zero in the selected scan.
- OS scan severity scope: high and critical.

The remaining OS findings are unresolved and documented. The images are not vulnerability-free.

Application packages are installed using requirements-runtime.lock with hash verification. Packaging tools are separately version-pinned. APT repository contents remain time-dependent.

Local verification additionally used dropped capabilities, no-new-privileges, a read-only root filesystem, and temporary storage. Equivalent Azure runtime settings have not been established.

The source review found no credential material matching the automated checks. Pattern checks and manual review do not guarantee detection of every possible secret.

## Validation Commands

Local regression:

```bash
python -m pytest -q
```

Deployed gateway:

```bash
python scripts/validate_azure_gateway.py
```

Real Entra token with in-process synthetic inference:

```bash
python scripts/validate_live_gateway.py
```

Local public-certificate expiration:

```bash
python scripts/check_certificate_expiry.py
```

The container validator requires an already running local gateway on 127.0.0.1:8000:

```bash
python scripts/validate_container_gateway.py
```

The in-process validator does not test the deployed gateway or backend boundary.

Live validation requires privately configured identity settings, a registered certificate, its encrypted private key, and available Azure resources. Credentials are not included in the repository.

## Governance

A separate local workflow requires distinct proposer, approver, and deployer subjects with governance-specific roles.

It tests approval sequencing, stale-change rejection, replay prevention, and separation of duties.

It uses trusted local principals and isolated in-memory policy state. It does not authorize or change deployed gateway policy.

## Operational Limits

- Shared backend credentials do not provide workload identity attestation or mTLS.
- Internal ingress is an environment-level boundary, not gateway-exclusive isolation.
- A holder of the service credential with backend reachability can bypass gateway controls.
- HTTPX timeouts are network-phase limits, not an end-to-end deadline.
- Comprehensive incoming body-size and connection limits are not established.
- Decision logs omit identities and do not provide durable, tamper-evident audit storage.
- Automatic credential rotation and expiration notifications are not implemented.
- Certificate removal does not establish revocation of previously issued tokens.
- Controlled recovery exercises do not demonstrate incident detection or a real compromise investigation.
- Local file cleanup does not establish erasure from backups.

## Shutdown and Cost Control

The last verified scaling settings were zero minimum replicas and one maximum replica for both Azure applications.

Scale-to-zero permits idle application replicas to stop. It does not delete infrastructure or eliminate all Azure costs.

The lab shutdown and retirement process includes:

1. Stop local project containers and any local application servers.
2. Quit Docker Desktop when local container work is finished.
3. Preserve sanitized validation evidence before removing cloud resources.
4. Inventory the dedicated Azure resource group and confirm its contents.
5. Delete unneeded lab resources when live exercises are complete.
6. Verify deletion and check for remaining resources and subscription costs.

Stopping Docker Desktop does not stop Azure resources.

Azure resource deletion and final cost verification remain outstanding at this documented baseline. The repository does not establish that the cloud environment has been removed.

## Documentation

- [System architecture](docs/architecture/system-architecture.md)
- [Threat register](docs/threat-model/threat-register.md)
- [Credential lifecycle and recovery](docs/operations/certificate-lifecycle.md)
- [Validation report](docs/validation/validation-report.md)
- [Container security review](docs/validation/container-security-review.md)

## Scope

Request data is synthetic; Azure resources and identities are real.

This personal laboratory does not claim production readiness, regulatory certification, comprehensive threat coverage, or guaranteed availability.
