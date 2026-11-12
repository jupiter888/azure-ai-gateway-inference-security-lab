# Project 9 — Azure AI Gateway System Architecture

## 1. Purpose

An Azure-hosted security laboratory examining identity enforcement, model authorization, inference admission, backend authentication, and security decision logging.

The backend returns synthetic responses. No actual AI model is invoked.

Gateway and backend image release: v0.7.1.

## 2. Components

### Test Client and Microsoft Entra ID

A Python client authenticates to Entra ID using a registered certificate.

The encrypted private key resides outside the project. Its passphrase is entered interactively, and access tokens are held in memory by the validation workflow.

Entra signs the access token. The client certificate authenticates the client to Entra; it does not directly sign the token accepted by the gateway.

### Public Gateway

A FastAPI application runs on Azure Container Apps with external HTTPS ingress.

FastAPI validates request syntax and schema before the inference handler runs. Invalid requests receive a generic HTTP 422 response that excludes submitted values.

For valid request bodies, enforcement proceeds through:

1. Bearer-header validation.
2. JWT signature and claims validation.
3. Model authorization.
4. Subject/model quota admission.
5. Backend concurrency admission.
6. Authenticated backend invocation.
7. Backend response validation.
8. Security decision logging.

Authentication and model denials do not invoke the backend.

### Model Authorization

| Model | Required role |
|---|---|
| research-model | Inference.Reader |
| restricted-model | Inference.Admin |

Unknown models are denied. Roles are not implicitly hierarchical.

The deployed policy is static application code.

### Quota Admission

| Model | Admitted requests per subject per 60-second window |
|---|---:|
| research-model | 30 |
| restricted-model | 10 |

Fixed windows begin with the first admitted request.

Quota state is thread-safe and bounded to 1,000 active subject/model entries. Expired entries are removed during admission.

Quota exhaustion returns HTTP 429 with Retry-After. State-capacity exhaustion returns HTTP 503.

Counters are process-local and reset on restart.

### Concurrency Admission

A nonblocking semaphore permits at most two backend calls per gateway process.

Saturation returns HTTP 503 with Retry-After: 1. Capacity is released after backend success or failure.

Quota admission happens first. Concurrency rejections and backend failures therefore consume quota admissions.

This does not limit all incoming connections or guarantee fairness between callers.

### Backend Forwarding

Azure uses backend mode. Missing or invalid backend configuration fails closed.

Explicit local-synthetic mode is retained for offline tests.

Backend calls:

- Use the configured backend origin.
- Supply X-Service-Key.
- Do not forward the external bearer token.
- Disable redirect following.
- Disable environment-derived proxy configuration.
- Do not automatically retry inference.

| HTTP phase | Configured timeout |
|---|---:|
| Connect | 10 seconds |
| Read | 60 seconds |
| Write | 10 seconds |
| Pool | 5 seconds |

Configuration accepts finite values from 0.1–30 seconds for connect, write, and pool, and 0.1–120 seconds for read.

HTTPX phase timeouts are not a strict end-to-end deadline.

Transport failures, upstream rejection, invalid JSON, and invalid response contracts return HTTP 502. Configuration failures return HTTP 503.

### Internal Synthetic Backend

A separate FastAPI application runs in the same Container Apps environment.

Controls include:

- Internal-only ingress.
- Insecure HTTP ingress disabled.
- Shared service-credential authentication.
- Constant-time credential comparison.
- Rejection of missing, invalid, and non-ASCII credentials.
- Fail-closed behavior for invalid credential configuration.
- Generic request-validation responses.
- Synthetic inference output.

The health endpoint does not require service authentication and does not prove that gateway and backend credentials match.

Internal ingress is an environment-level boundary. Other workloads in the environment may be able to reach the backend.

### Registry and Container Images

Both images are stored in Azure Container Registry.

- Registry admin authentication is disabled.
- A shared user-assigned managed identity authenticates image pulls.
- Application deployments reference exact image digests.
- The Python 3.11 Debian 13 base is digest-pinned.
- Runtime application dependencies are installed from a hashed Linux lockfile.
- Packaging tools are separately version-pinned.
- Available distribution updates are applied during builds.
- Images configure a non-root runtime.
- Application files are root-owned and not runtime-writable.
- Setuid/setgid bits are removed from regular image files.

APT repository contents remain time-dependent despite the pinned base.

Registry managed identity does not authenticate inference calls.

### Security Decision Logging

Structured inference_decision events contain:

- Server-generated event UUID.
- UTC timestamp.
- Fixed outcome and reason codes.
- Allowlisted model label.

Covered handler paths include authentication denial, model denial, quota denial, capacity rejection, backend failure, and inference success.

Separate backend_failure events contain a fixed category, elapsed milliseconds, and upstream status where applicable.

Structured events omit tokens, credentials, prompts, raw identities, caller request IDs, URLs, exception messages, and backend response bodies.

Framework-level validation failures receive sanitized responses but do not currently produce these decision events.

### Local Governance Workflow

A separate in-memory workflow requires:

| Action | Required role |
|---|---|
| Propose | Governance.Proposer |
| Approve | Governance.Approver |
| Apply | Governance.Deployer |

Three distinct subjects are required, even when one subject holds multiple roles.

Immutable proposals bind the requested change to a base policy version. Approval is required before application; stale changes and repeated application are rejected.

Inference.Admin grants no governance authority.

This module trusts supplied local principals and maintains isolated policy state. It does not authenticate governance callers or change the deployed gateway policy.

## 3. Trust Boundaries

| Boundary | Relationship | Controls |
|---|---|---|
| TB-01 | External client to gateway | HTTPS and bearer-token enforcement |
| TB-02 | Gateway to identity-provider trust | Signature, claims, token-version, and calling-application checks |
| TB-03 | Identity to inference admission | Model policy, subject/model quotas, concurrency admission |
| TB-04 | Gateway to backend | Internal ingress, HTTPS, service credential, response validation |
| TB-05 | Decisions and governance changes | Deployed application decision logs; separate local governance workflow |

## 4. Availability and Scaling

Both applications have zero minimum replicas and one maximum replica.

A zero configured minimum does not establish that no replica is currently running. Replica listings and lifecycle events can reflect different points in an asynchronous transition.

Earlier diagnostics captured a backend transport timeout after approximately ten seconds.

After the read allowance increased to sixty seconds, a scale-from-zero request returned HTTP 200 in 36.47 seconds, correlated with a new backend replica starting.

This supports the timeout adjustment as a mitigation for observed startup delay. It does not establish guaranteed cold-start performance or explain every earlier failure.

## 5. Verification

- 197 local regression tests passed.
- 197 tests passed against the final gateway image under a restricted Linux runtime.
- Deployed authorization and response-contract checks passed 4/4.
- Azure quota exhaustion and recovery were exercised.
- Azure concurrency rejection and matching decision events were observed.
- Direct backend service-authentication checks passed 3/3 inside Azure.
- Generic request-validation responses and non-ASCII credential rejection were verified after v0.7.1 deployment.
- Certificate and service-key rotation, retirement, rollback, and controlled recovery exercises were completed.

See the validation report for individual results and scope distinctions.

## 6. Residual Limitations

- Quotas and concurrency are process-local.
- Shared credentials do not provide workload identity attestation or mTLS.
- Internal ingress is not gateway-exclusive isolation.
- A caller with backend reachability and the service credential can bypass gateway controls.
- Comprehensive incoming body-size and connection limits are not established.
- Decision logs are not a durable, tamper-evident audit system.
- The governance workflow does not control live deployments.
- Automatic credential rotation and expiration notifications are not implemented.
- Previously issued token revocation was not tested.
- Final image scans retain 47 high OS findings across 11 advisory IDs per image.
- Local read-only filesystem, capability-drop, and no-new-privileges settings have not been established as Azure runtime settings.

See the container security review for the residual OS assessment.

Production readiness, regulatory certification, comprehensive attack coverage, and guaranteed availability are not claimed.
