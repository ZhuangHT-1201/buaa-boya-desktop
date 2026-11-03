# Changelog

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
