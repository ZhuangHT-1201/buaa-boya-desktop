# Changelog

## 0.5.2

- Keeps safe auto-selection available when the large course-catalog endpoint times out by using
  recent cached candidates and validating each candidate through the live course-detail endpoint.
- Allows courses cached as full to be reconsidered after an external course drop, while still
  blocking regular-signin, Hangzhou, closed, and genuinely full courses.
- Updates the UI to explain that cached candidates are being live-revalidated instead of claiming
  auto-selection is paused.

## 0.5.1

- Refreshes account statuses concurrently and reads the shared course catalog from one recent healthy
  account, so one WebVPN timeout no longer blocks the complete worker cycle.
- Uses fast one-attempt reads for background cache refresh; failed accounts are retried on the next
  scheduled cycle while successful accounts continue.
- Reduces Boya data-read timeouts and records the next refresh schedule after each completed attempt.
- Coalesces a manual refresh request with any full refresh already completed in the current cycle,
  preventing users from waiting through a duplicate refresh.
- When the large course-catalog endpoint times out, recent cached candidates are allowed only after
  a live per-course detail check confirms availability and autonomous check-in eligibility.
- Serializes `ddddocr` model inference so simultaneous account recovery cannot corrupt or crash the
  shared OCR engine.
- Removes duplicate reauthentication warnings when OCR fails and keeps manual CAPTCHA fallback in
  the desktop app.

## 0.5.0

- Background re-login now uses local `ddddocr` to read SSO CAPTCHA images and restore expired
  sessions automatically, so check-in/out is less likely to stop after a successful selection.
- Category gaps reconcile Boya statistics with each chosen course's `pass` / check-in fields, so
  failed assessments continue to trigger replacement selection.
- Live course availability and account status refresh on separate intervals, and selection prefers
  courses that still have remaining seats.
- Added cross-process account-login locks, exponential retry backoff, and duplicate-notification
  suppression so the desktop console and background runner cannot trigger competing CAPTCHA login
  attempts.
- CAPTCHA OCR now fails fast when its bundled runtime is unavailable instead of repeating the same
  login request, and packaged builds explicitly include the OCR model data.
- Selection is capped by each category's remaining quota, preventing one unfilled category from
  consuming several slots while another category is still missing.
- Added rotating worker logs and centralized missing-session recovery before Boya requests.

## 0.4.1

- Added a prominent Overview warning for accounts that require interactive sign-in.
- Marked expired account cards and status badges in red with clear cached-data context.
- Added a one-click queue that signs in every expired account sequentially.
- Continued automatically through each account's CAPTCHA dialog and reported partial failures
  without stopping the remaining accounts.
- Replaced the startup sign-in modal with a non-disruptive Overview warning and bulk action.

## 0.4.0

- Prevented one expired account from blocking refreshes and scans for other accounts.
- Stopped repeated CAPTCHA-triggered login attempts and marked affected accounts as requiring
  interactive sign-in.
- Added a Windows notification and in-app warning when background reauthentication needs a CAPTCHA.
- Added CAPTCHA image validation, automatic retry for invalid images and wrong codes, and a
  **New code** button.
- Added per-account authentication health state to the account table and status dialog.
- Pruned stale CAPTCHA image files.
- Continued scanning cached selections even when online refresh fails.

## 0.3.4

- Lowered the default full refresh interval to five minutes so external course drops are detected
  promptly.
- Added automatic status refresh when opening the desktop app with stale cache data.
- Added a manual **Refresh Boya status** action that delegates to the running background worker.
- Added cache and course-catalog update timestamps.
- Added an upcoming autonomous-course table with category, campus, selection window, course start,
  and remaining capacity.
- Added retry handling for transient Boya API timeouts.

## 0.3.3

- Restricted automation-selected courses to Beijing, Shahe, and all-campus offerings.
- Hangzhou-campus courses can no longer be selected by the automation runner.
- Existing manually selected courses remain untouched.

## 0.3.2

- Removed campus matching from machine course selection; autonomous check-in courses from either
  campus are eligible.
- Corrected category-gap detection to use unfilled requirement slots (`required - selected`) rather
  than the `undoneAssessmentCount` field.
- Prevented fallback selection when statistics are missing or no requirement slots remain.
- Added per-account status details with category requirements, selected, passed, pending, failed, and
  remaining-to-select counts.
- Added assessment status and score to the selected-course list.

## 0.3.1

- Fixed the gap-aware runner methods so the custom account filtering is actually used.
- Restricted machine selection to currently selectable autonomous check-in courses with two
  independent eligibility checks.
- Preserved manually selected courses and left regular-signin courses untouched.
- Added persistent manual/automation provenance for every selected course.
- Allowed autonomous check-in and check-out for both manually and automatically selected courses.
- Changed the pending-course cap to count automation-selected courses only.
- Added a selected-course detail view and new selection-policy tests.

## 0.3.0

- Added an in-app English / Chinese language switch with persisted preference.
- Added complete English UI copy for the dashboard, accounts, settings, logs, and dialogs.
- Added English and Chinese README files with real interface screenshots.
- Added English and Chinese Windows launchers.
- Added English-named `BoyaAutomation.exe` alongside the compatibility executable.
- Added PyPI-style project metadata, tests, CI, contribution, security, and MIT license files.

## 0.2.0

- Added the desktop console, multi-account management, worker lifecycle controls, settings,
  progress views, and Windows packaging.
