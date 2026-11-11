# Boya Automation v0.5.3

This patch fixes a long-running background failure that could make every account appear to have a
sign-in problem even though no new credentials or CAPTCHA were required.

## Root cause

The single-file Windows build normally keeps its supporting files in a temporary extraction
directory. After the worker had been running for a long time, that directory could disappear. New
HTTPS clients then failed while loading the CA certificate bundle, and the status was reported as a
generic sign-in error instead of reaching the session-expiry reauthentication path.

## Changes

- The CA certificate bundle is copied to `%USERPROFILE%\.autoboya\runtime\cacert.pem`.
- `SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`, and `CURL_CA_BUNDLE` point to that persistent copy.
- The persistent setup runs in the GUI, worker, and login service before creating HTTPS clients.
- Log rollover failures caused by another process reading the log no longer dump repeated
  tracebacks or block normal logging.
- Rotation retries later instead of failing continuously on Windows.
- Transient network and API failures are labeled **Request error**, not **Sign-in error**.

## Upgrade

Download and extract `BoyaAutomation-v0.5.3-windows-x64.zip`. Existing accounts, sessions, caches,
and preferences are preserved.
