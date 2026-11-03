# Boya Automation v0.3.1

This release tightens course-selection boundaries and adds visible selection provenance.

## Safety changes

- Fixed a runner indentation bug that could fall back to upstream default behavior.
- Machine selection now requires a currently selectable course with explicit autonomous check-in
  points. Regular-signin courses are rejected both during planning and immediately before execution.
- Existing selections are registered as manual choices and are never changed, dropped, or replaced.
- The pending-course limit applies only to automation-selected courses, so pre-existing manual
  selections do not block the runner.
- Manual and automated selections are both eligible for autonomous location check-in and check-out.
  Regular-signin courses are never touched by attendance automation.

## Visibility

- Added a **View selected** table showing course, category, attendance type, selection origin, status,
  and time.
- Added manual/automation counts to the account overview.

## Verification

- `11` automated tests pass.
- Both signed-in accounts were refreshed successfully.
- Real cached data contains `8` existing manual selections: `5` autonomous check-in and `3` regular
  check-in. No machine-selected courses existed at migration time.
- No autonomous course was available in the current selection window, so the read-only preview
  correctly produced zero selection or attendance actions.
