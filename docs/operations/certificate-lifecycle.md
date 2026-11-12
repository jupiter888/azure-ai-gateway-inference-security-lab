# Credential Lifecycle and Recovery Runbook

**Project:** Azure AI Gateway & Inference Security Lab

**Last exercised:** November 12, 2026

**Scope:** Entra client certificate and backend service credential

## 1. Purpose

Document credential protection, rotation, retirement, rollback, controlled recovery, and expiration checks.

Detailed observed results are recorded in:
[Validation report](../validation/validation-report.md).

## 2. Credential Architecture

### Client Certificate

The client authenticates to Microsoft Entra ID using a registered public certificate and an encrypted private key stored outside the project.

The passphrase is entered interactively. Entra signs the access token; the client certificate does not directly sign the token accepted by the gateway.

Current default files, outside the project:

- client-key.pem
- client-cert.pem

Current verified certificate expiration:
December 12, 2026 at 11:50:43 UTC.

### Backend Service Credential

Gateway and backend reference matching Container Apps secrets.

The gateway supplies X-Service-Key. The backend validates the credential using constant-time comparison and rejects missing, invalid, or non-ASCII credentials.

The backend accepts one service credential at a time. Rotation therefore requires coordinated changes and can interrupt inference.

Registry image-pull managed identity is separate from service authentication.

## 3. Protection Requirements

- Keep private keys and service credentials outside the project.
- Encrypt private keys and restrict local credential-directory permissions.
- Enter passphrases interactively.
- Do not print tokens, private keys, passphrases, or service credentials.
- Avoid literal credential values in command history.
- Disable shell tracing during credential operations.
- Use Container Apps secret references.
- Clear temporary credential variables after validation.
- Restrict Azure secret administration, container execution, and Entra credential registration.
- Sanitize evidence before publication.

Local file deletion does not guarantee erasure from backups or filesystem snapshots.

## 4. Certificate Rotation Procedure

1. Inspect local certificate validity and Entra registration metadata.
2. Generate a replacement encrypted key outside the project.
3. Verify the key before generating the certificate.
4. Create and inspect its public certificate.
5. Append the public certificate to Entra while preserving the working registration.
6. Acquire a fresh token with the replacement.
7. Pass the deployed gateway authorization checks.
8. Preserve the original encrypted files temporarily.
9. Install the replacement as the default client credential.
10. Pass the normal validation command.
11. Remove only the original Entra certificate registration.
12. Attempt fresh token acquisition with the original credential.
13. Confirm rejection and revalidate the replacement.
14. Retire original and duplicate local files after evidence review.

Use --cert when listing or deleting certificate credentials.

Use --append when registering the replacement. Do not replace all application credentials unintentionally.

Removing a certificate registration does not establish immediate invalidation of previously issued tokens.

## 5. Service-Credential Rotation Procedure

1. Confirm working ready revisions and current secret reference names.
2. Generate a fresh random credential without printing it.
3. Stage it under a distinct secret name in both applications.
4. Preserve working references while staging.
5. Switch the backend to the replacement reference.
6. Wait for its new revision to become ready.
7. Verify that the old gateway credential is rejected.
8. Switch the gateway to the replacement reference.
9. Wait for readiness and run deployed authorization validation.
10. Check all revisions, including inactive revisions, for old references.
11. Ensure revisions referencing the old secret are inactive.
12. Remove old secret entries from both applications.
13. Verify absence and revalidate service operation.
14. Clear temporary shell variables.

The health endpoint does not prove that service credentials match.

Secret staging alone does not change the active environment reference. Updating a reference creates a new revision; readiness must be checked.

### Expected Interruption

The backend-first sequence creates an interval when the old gateway credential is rejected. Authorized inference may return HTTP 502.

Authentication, model authorization, and internal-only backend ingress must remain enabled throughout.

Zero-downtime rotation is not implemented.

## 6. Failed-Change Rollback

For a planned exercise where the working credential is not compromised:

1. Record the known-working gateway reference.
2. Stage a separate deliberately mismatched gateway credential.
3. Switch the gateway and wait for readiness.
4. Verify inference fails closed.
5. Confirm a backend-rejection diagnostic with upstream HTTP 401.
6. Verify authentication and model denials remain enforced.
7. Restore the known-working reference.
8. Wait for readiness and pass deployed validation.
9. Confirm the exercise revision is inactive.
10. Remove the exercise secret and clear temporary variables.

A timeout alone is not proof of credential rejection.

This rollback procedure must not restore a credential believed compromised.

## 7. Controlled Service-Credential Compromise Recovery

1. Designate the current credential presumed-compromised for the exercise.
2. Stage a fresh recovery credential in both applications.
3. Switch the backend.
4. Verify rejection of the presumed-compromised gateway credential.
5. Switch the gateway to the recovery credential.
6. Wait for readiness and pass deployed validation.
7. Confirm old-reference revisions are inactive.
8. Remove presumed-compromised secret entries from both applications.
9. Verify absence and revalidate.
10. Clear temporary credential variables.

Do not recover by disabling authentication, enabling public backend ingress, or restoring the presumed-compromised credential.

This exercise validates response actions. It does not simulate an actual leak, validate incident detection, or resolve ongoing Azure administrative compromise.

## 8. Client Configuration Recovery

The exercised client failures were:

- Missing private-key path.
- Incorrect private-key passphrase.

Both failed before token acquisition. Restoring the normal configuration permitted token acquisition and deployed validation.

The exercise changed configuration in memory; it did not delete working credentials or simulate lost backups.

For genuine key compromise, remove the affected Entra registration, replace the credential, investigate unauthorized token issuance, and revalidate access. Full incident investigation has not been exercised.

## 9. Expiration Monitoring

Run the public-certificate checker:

```bash
python scripts/check_certificate_expiry.py
