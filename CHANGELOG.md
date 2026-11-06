# Changelog

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
