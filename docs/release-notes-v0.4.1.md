# Boya Automation v0.4.1

This release makes expired sessions visible and recoverable directly from the Overview page.

## Highlights

- Accounts that require interactive sign-in are highlighted in red on the Overview.
- A one-click **Sign in all** action processes every expired account in sequence.
- Each account receives its own CAPTCHA prompt; completing one login continues the queue
  automatically.
- Failed accounts are reported together without preventing other accounts from signing in.
- The previous blocking startup warning was replaced with a non-disruptive dashboard alert.
- Updated the English README screenshot to show the new recovery dashboard.

## Upgrade

Download and extract `BoyaAutomation-v0.4.1-windows-x64.zip`, then launch
`BoyaAutomation.exe` or `Launch Boya Automation.vbs`. Existing local accounts, preferences, and
caches are preserved.

SHA-256 checksums are included in `SHA256SUMS.txt`.
