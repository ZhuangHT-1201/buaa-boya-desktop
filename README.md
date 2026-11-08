# Boya Automation

[English](README.md) | [简体中文](README.zh-CN.md)

**A bilingual Windows desktop controller for safer, gap-aware BUAA Boya automation.**

[![CI](https://github.com/ZhuangHT-1201/buaa-boya-desktop/actions/workflows/ci.yml/badge.svg)](https://github.com/ZhuangHT-1201/buaa-boya-desktop/actions/workflows/ci.yml)
[![Windows](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D4)](https://github.com/ZhuangHT-1201/buaa-boya-desktop/releases/latest)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](pyproject.toml)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

Boya Automation turns the command-line [AutoBoya](https://github.com/DeNeRATe-cool/AutoBoya)
workflow into a local, visual desktop application. It handles multiple accounts, reads Boya data
directly, tracks category gaps and failed assessments, selects eligible autonomous check-in
courses, and keeps attendance running after the main window is closed.

![Boya Automation overview](docs/screenshots/dashboard-en.png)

> This is an independent community project. It is not affiliated with Beihang University or the
> Boya platform. Automation may violate university rules. Confirm that your use is permitted and
> never falsify attendance.

## What it does

- Keeps every enabled account signed in when possible and continues after the console is closed.
- Reads course availability, selected courses, assessment results, and requirement statistics
  directly from Boya instead of estimating them from screenshots.
- Selects **autonomous check-in courses only**. Regular-signin courses and Hangzhou-campus courses
  are never selected by the automation.
- Preserves existing manual selections and labels whether each course was chosen manually or by
  the automation.
- Performs location check-in and check-out for both manually selected and automatically selected
  autonomous courses. Manual regular-signin courses are left untouched.
- Detects failed assessments and missing category slots, then keeps looking for replacement
  autonomous courses.
- Shows per-account progress, failed courses, upcoming opportunities, login health, and background
  activity in one interface.

## Safety and selection rules

The selection pipeline is intentionally conservative:

1. It reads the official Boya statistics and each selected course's result/check-in fields.
2. It calculates usable selected slots as `selected - failed`, then compares that value with the
   official category requirement.
3. It filters courses by category quota, autonomous location check-in, eligibility window, campus,
   and live capacity.
4. It rechecks the course again immediately before sending a selection request.

Manual selections are never removed, replaced, or changed. If someone else drops a course,
availability is refreshed and the course can re-enter the candidate list.

When the large course-catalog API is slow, the app may use a recent cached catalog only as an
index. Every candidate must still pass a live per-course detail check before it can be selected.
If that live check cannot be completed, nothing is selected from stale capacity data.

## Session recovery

- A worker-instance lock prevents duplicate background runners.
- A per-account login lock prevents the desktop console and worker from competing for the same
  SSO session.
- Expired sessions are reauthenticated with the locally stored password when no CAPTCHA is needed.
- CAPTCHA OCR is attempted with a bundled local `ddddocr` runtime.
- In the desktop app, the first CAPTCHA attempt uses OCR and immediately falls back to a manual
  dialog if the result is rejected.
- Repeated failures use exponential backoff instead of creating a login storm.
- Other valid accounts continue refreshing and attending while one account needs attention.

CAPTCHA recognition is not guaranteed. When OCR cannot complete sign-in, the account is highlighted
in red and can be recovered from the account list or with **Sign in all** on the Overview.

## Screenshots

| Account management | Settings |
| --- | --- |
| ![Account management](docs/screenshots/accounts-en.png) | ![Settings](docs/screenshots/settings-en.png) |

The account status view shows category requirements, assessment status, upcoming opportunities,
and whether each selected course was manual or machine-selected:

![Account status and selection provenance](docs/screenshots/selection-origin-en.png)

## How it works

The desktop console and background worker are separate processes.

1. The console stores credentials in Windows Credential Manager when available.
2. The worker refreshes account state and the shared course catalog directly from Boya.
3. It maps unfilled requirement slots to categories and builds a per-account selection plan.
4. Eligible autonomous courses are rechecked live and selected within the remaining category
   quota.
5. At the configured attendance windows, it performs check-in and check-out for autonomous courses.
6. The worker keeps running when the GUI is closed. Use **Stop background** to end automation.

Account statuses refresh in parallel, so one slow account does not block the others. The shared
course catalog is read from one recent healthy account and falls back to another account when
needed.

## Account statuses

| Status | Meaning |
| --- | --- |
| **Signed in** | The account can currently use its stored session. |
| **Sign in required** | The session is missing or expired. |
| **Captcha required** | Interactive sign-in may be needed if automatic OCR cannot complete. |
| **Sign-in error** | A network or API error occurred; the next cycle retries automatically. |
| **Enabled** | The account participates in batch automation. |
| **Disabled** | The account is retained but paused. |

Red cards on the Overview indicate accounts that require sign-in. The **Sign in all** button
processes all affected accounts one at a time.

## Quick start

### Portable Windows build

1. Download the [latest release](https://github.com/ZhuangHT-1201/buaa-boya-desktop/releases/latest).
2. Extract the ZIP archive.
3. Double-click `Launch Boya Automation.vbs` or run `release\BoyaAutomation.exe`.
4. Open **Accounts**, choose **Add account**, and complete SSO sign-in.
5. Return to **Overview** and choose **Start automation**.

The first launch can take longer because the single-file executable unpacks its Python, OCR, and
model runtime.

### From source

Requirements: Windows 10/11 and Python 3.10 or newer with Tk support.

```powershell
git clone https://github.com/ZhuangHT-1201/buaa-boya-desktop.git
cd buaa-boya-desktop
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python -m boya_kit init
python -m boya_kit.launcher
```

Or run the one-click source bootstrap:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\bootstrap.ps1
```

## First-run checklist

- Add at least one account and wait for sign-in to complete.
- Open **Account status** and verify the category requirements and existing selections.
- Confirm that manually selected regular-signin courses are present and untouched.
- Optionally enable dry-run once to inspect the planned decisions.
- Start automation and confirm that the Overview shows **Background running**.

## Language switching

Use the **English** or **中文** button at the bottom of the sidebar. The full interface, dialogs,
status messages, and validation prompts switch immediately. The preference is stored locally in
`~/.autoboya/ui-preferences.json`.

## Configuration

The GUI writes `config.yaml` next to the executable. Passwords are never stored there.

| Key | Default | Purpose |
| --- | --- | --- |
| `username` | `null` | `null` processes all enabled accounts |
| `campus` | `北京` | Account metadata; course eligibility is enforced independently |
| `only_gap_categories` | `true` | Restrict automation to categories with an unfilled quota |
| `prefer_categories` | moral / aesthetic / labor / health | Category priority order |
| `exclude_categories` | `其他方面` | Categories never selected automatically |
| `max_pending_selected` | `4` | Cap for pending automation-selected courses; manual choices are not counted |
| `poll_seconds` | `60` | Attendance and decision scan interval |
| `course_refresh_seconds` | `30` | Live course availability refresh interval |
| `status_refresh_seconds` | `60` | Direct account-statistics refresh interval |
| `refresh_seconds` | `300` | Legacy compatibility value; live intervals above control refresh |
| `dry_run` | `false` | Record decisions without making real selection or attendance requests |

Use a dry run first, verify the selected categories and course types, then disable it.

## Command-line interface

The original command-line workflow is still available:

```powershell
python -m boya_kit init
python -m boya_kit setup
python -m boya_kit refresh
python -m boya_kit status
python -m boya_kit preview
python -m boya_kit run-once
python -m boya_kit run
python -m boya_kit stop
python -m boya_kit logs --lines 100
```

## Troubleshooting

### The account is red or says “Sign in required”

Open **Accounts**, select the affected account, and choose **Sign in again**. If several accounts
need attention, use **Sign in all** on the Overview and complete each CAPTCHA dialog as it appears.

### The app says live course data is being revalidated

The large course-catalog request was slow. Recent cached candidates are still checked one by one
against the live course-detail endpoint. Selection only proceeds after that check succeeds.

### No course was selected although a category is missing

Possible reasons include:

- no open autonomous check-in course currently matches the missing category;
- every matching course is full or outside its selection window;
- the account status could not be refreshed;
- the machine-selected pending-course limit has been reached;
- the category is listed in `exclude_categories`.

Open **Account status** for the exact requirements and upcoming opportunities.

### Check-in or check-out did not complete

The worker retries failed attendance actions while the attendance window remains open. If the
session requires interactive authentication, the account is marked in red and other accounts
continue running.

## Privacy and local data

- Credentials are stored through Windows Credential Manager when available.
- Local sessions, caches, logs, and preferences live under `C:\Users\<you>\.autoboya`.
- Selection provenance is stored in `.autoboya/cache/selection_origins.json`.
- The application does not upload account data to this project.
- Removing an account from the GUI does not automatically remove its Windows credential entry.
- Never attach passwords, cookies, session exports, or identifiable screenshots to public issues.

Please report security issues using GitHub's private vulnerability reporting. See
[SECURITY.md](SECURITY.md).

## Build the Windows executable

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build-exe.ps1
```

The build creates `release\BoyaAutomation.exe` and a Chinese-named compatibility executable. It
also bundles the OCR engine, model files, and runtime dependencies.

To regenerate the three main English screenshots with the anonymous demo store:

```powershell
python scripts\capture-doc-screenshots.py
```

## Development

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Project layout:

```text
boya_kit/
  gui.py          Bilingual Tkinter desktop console
  i18n.py         English UI catalog
  runner.py       Gap-aware worker, live refresh, recovery, and attendance
  service.py      Keyring, SSO login, CAPTCHA, and worker lifecycle
  gaps.py         Official-statistics and assessment reconciliation
  selections.py   Manual/automation provenance
docs/screenshots/ Current English UI screenshots
scripts/          Setup, launch, screenshot, and packaging scripts
tests/            Regression tests for gaps, sessions, locking, and selection rules
```

## Limitations

- Windows only.
- CAPTCHA OCR can fail; manual confirmation is still required in some cases.
- WebVPN can be slow or intermittent. The app pauses unsafe actions and retries, but it cannot
  control the university's network availability.
- The project cannot guarantee a seat in a full or rapidly changing course.

## Contributing

Contributions are welcome. Read [CONTRIBUTING.md](CONTRIBUTING.md), keep secrets and personal
caches out of commits, and include tests for behavior changes.

## License

Released under the [MIT License](LICENSE).

The automation layer builds on the MIT-licensed
[AutoBoya](https://github.com/DeNeRATe-cool/AutoBoya) project. Its limitations and third-party
notices continue to apply.
