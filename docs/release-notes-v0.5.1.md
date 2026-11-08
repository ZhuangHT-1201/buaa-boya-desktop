# Boya Automation v0.5.1

This patch improves background responsiveness during unstable WebVPN connections.

## Highlights

- Account statuses refresh in parallel. The shared course catalog uses one recent healthy account
  and falls back to another account only when that read fails.
- A timed-out account no longer delays successful accounts or blocks the complete worker cycle.
- Background cache reads fail fast after one attempt and retry on the next scheduled interval.
- Manual refresh requests are coalesced with an in-progress or just-completed refresh cycle.
- Boya data reads use a shorter timeout, while attendance and selection actions retain their normal
  validation flow.
- CAPTCHA OCR inference is serialized, preventing concurrent account recovery from racing inside the
  shared OCR model.
- Duplicate reauthentication warnings were removed.

## Upgrade

Download and extract `BoyaAutomation-v0.5.1-windows-x64.zip`, then launch
`BoyaAutomation.exe` or `Launch Boya Automation.vbs`. Existing accounts, sessions, preferences, and
caches are preserved.
