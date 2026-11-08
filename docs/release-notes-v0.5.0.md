# Boya Automation v0.5.0

This release focuses on recovery after expired sessions, accurate assessment gaps, and live course
availability.

## Highlights

- Adds local CAPTCHA OCR with the runtime and model files included in the Windows build.
- Cross-process locks prevent the desktop console and background worker from signing in to the same
  account at the same time.
- A worker-instance lock prevents duplicate background runners after restart or rapid clicks.
- Failed automatic logins use exponential backoff, reducing repeated requests and notification
  spam.
- In the desktop app, the first CAPTCHA attempt uses OCR and falls back to a manual dialog if the
  recognized text is rejected.
- Missing or expired sessions are restored before a Boya request instead of being discovered only
  after a selection has already completed.
- Course availability is read directly on a faster interval. Auto-selection pauses when a live
  catalog cannot be verified.
- Assessment gaps reconcile the official statistics with each chosen course's result and check-in
  fields. Failed courses no longer occupy a completed requirement slot.
- Category selection is limited to the remaining quota for that category.
- Successful selection, check-in, or check-out is retained even if the immediate status refresh
  fails; the next cycle retries the read without treating the action as failed.
- Worker logs rotate automatically to avoid unbounded log growth.

## Upgrade

Download and extract `BoyaAutomation-v0.5.0-windows-x64.zip`, then launch
`BoyaAutomation.exe` or `Launch Boya Automation.vbs`. Existing accounts, sessions, preferences, and
caches are preserved.
