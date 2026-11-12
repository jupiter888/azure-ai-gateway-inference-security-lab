# Project 9 — Container Security Review

**Review date:** November 12, 2026

**Deployed image release:** v0.7.1

**Scope:** Personal laboratory using synthetic inference data

## 1. Result

Both reviewed images were deployed by exact digest and reached ready revisions.

| Check | Gateway | Backend |
|---|---:|---:|
| Known Python-package vulnerabilities reported | 0 | 0 |
| High OS package/advisory findings | 47 | 47 |
| Critical OS findings | 0 | 0 |
| Unique OS advisory IDs | 11 | 11 |

The remaining OS findings are unresolved. This is not a vulnerability-free image or production approval.

No blanket vulnerability exclusions were applied.

## 2. Build Controls

- Digest-pinned Python 3.11 Debian 13 base.
- Available distribution updates applied.
- Twenty-two runtime Python packages pinned with hashes.
- Runtime installation uses --require-hashes and --only-binary=:all:.
- Packaging tools separately version-pinned.
- Non-root runtime configuration.
- Root-owned application files.
- Setuid/setgid file bits removed.

APT repository contents remain time-dependent.

The application lockfile does not hash-pin separately installed packaging tools. Development requirements do not provide a complete hashed development-environment lock.

## 3. Verification

- Final gateway image regression suite: 197 passed.
- Local checks confirmed UID 999, imports, dependency consistency, and non-writable application files.
- Local checks found no setuid/setgid executables in the inspected binary directories.
- Restricted local runtime tests used zero capabilities, no-new-privileges, and a read-only root filesystem.
- Deployed gateway validation passed 4/4.
- Deployed request-error safety fixes were exercised.
- Backend internal-only HTTPS ingress and recovery-secret references were preserved.

Equivalent capability-drop, no-new-privileges, and read-only filesystem settings have not been independently established in Azure.

## 4. Scan Scope

Python-package scans used pip-audit.

OS scans used Trivy 0.76.2 and selected HIGH and CRITICAL severities. Lower-severity OS findings are outside the reported totals.

Trivy reported that some severities came from other vendors. Those classifications were retained.

Forty-seven findings are package/advisory combinations, not forty-seven unique advisory IDs.

## 5. Residual Assessment

| Advisory | Assessment |
|---|---|
| CVE-2025-69720 | infocmp is present. No explicit application invocation was found. Component remains affected. |
| CVE-2026-119373 | SQLite FTS5 is enabled. No explicit application SQLite path was found; vulnerable functionality remains available. |
| CVE-2026-119374 | SQLite FTS5 is enabled. No database-upload or SQL-execution path was identified in application code. Complete reachability was not proven. |
| CVE-2026-119379 | SQLite session extension is enabled. No explicit changeset-processing path was found. Component remains affected. |
| CVE-2026-16742 | systemd-homed was absent from checked standard locations. Library findings remain visible; this is prerequisite evidence, not a patch. |
| CVE-2026-54369 | No explicit application pathname-based ACL operation was found. Non-root execution reduces exposure without fixing libacl. |
| CVE-2026-76642 | No application mount-helper path was identified. Privilege-bit removal reduces exposure; package remains affected. |
| CVE-2026-78408 | No application nsenter/cgroup path was identified. Azure capability state has not been established. |
| CVE-2026-78409 | No application mount-configuration path was identified. Package remains affected. |
| CVE-2026-78410 | Privileged bind-mount prerequisites are reduced by removed privilege bits and non-root execution. Package remains affected. |
| CVE-2026-9538 | Archive::Tar was not loadable in either tested image. The perl-base finding remains recorded. |

The inspected reports listed no fixed distribution-package version for these remaining findings.

Application searches are not complete static or dynamic reachability proofs. Local absence checks do not prove every vulnerable code path is absent.

## 6. Residual Disposition

The remediated images improve the lab baseline through patched Python dependencies, a newer base, hash-enforced runtime dependencies, reduced filesystem privileges, and safer request handling.

Remaining OS vulnerabilities are retained as disclosed lab risks. Successful tests do not constitute formal organizational risk acceptance.

Production use requires a separate assessment of vulnerability exposure, runtime privileges, operational monitoring, and availability requirements.

Do not mix unstable distribution packages into the runtime merely to reduce a scanner count without separate review.

## 7. Reassessment Triggers

Reassess when:

- Relevant distribution security updates become available.
- The base image or dependencies change.
- SQL, archive processing, terminal tooling, or command execution is introduced.
- Runtime privileges increase.
- The system expands beyond synthetic personal-lab use.

## 8. Advisory Sources

- [ncurses](https://security-tracker.debian.org/tracker/CVE-2025-69720)
- [SQLite FTS5 merge](https://security-tracker.debian.org/tracker/CVE-2026-119373)
- [SQLite secure-delete](https://security-tracker.debian.org/tracker/CVE-2026-119374)
- [SQLite changesets](https://security-tracker.debian.org/tracker/CVE-2026-119379)
- [systemd-homed](https://security-tracker.debian.org/tracker/CVE-2026-16742)
- [libacl](https://security-tracker.debian.org/tracker/CVE-2026-54369)
- [util-linux mount helpers](https://security-tracker.debian.org/tracker/CVE-2026-76642)
- [util-linux cgroup handling](https://security-tracker.debian.org/tracker/CVE-2026-78408)
- [util-linux mount subdirectories](https://security-tracker.debian.org/tracker/CVE-2026-78409)
- [util-linux bind mounts](https://security-tracker.debian.org/tracker/CVE-2026-78410)
- [Perl Archive::Tar](https://security-tracker.debian.org/tracker/CVE-2026-9538)
