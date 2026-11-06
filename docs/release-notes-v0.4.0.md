# Boya Automation v0.4.0

This release addresses expired unified-authentication sessions, CAPTCHA failures, and the resulting
multi-day pause in automatic course selection.

## Root cause

The background worker remained alive, but the BUAA SSO session expired. Automatic password-based
reauthentication then required a CAPTCHA. The previous loop retried the CAPTCHA-required operation
repeatedly and skipped the cached course scan on each failed refresh.

## Fixes

- A refresh failure no longer prevents cached selection and attendance scanning.
- One account requiring reauthentication no longer blocks other accounts.
- CAPTCHA-required state is recorded once for the affected account, with no repeated login storm.
- A Windows warning and an in-app account warning direct the user to the manual sign-in action.
- Manual sign-in resets the account health state and background processing resumes.
- CAPTCHA images are validated; empty images and wrong codes are retried with a fresh challenge.
- The CAPTCHA dialog now has a **New code** button.
- Stale CAPTCHA files are pruned automatically.

## Important behavior

BUAA SSO sessions can expire. The app automatically renews them with the stored password when
possible. If the university requires a CAPTCHA, no background client can complete that step without
human input; the app now asks for that input instead of failing silently.

All `21` automated tests pass.
