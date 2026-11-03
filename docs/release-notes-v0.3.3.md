# Boya Automation v0.3.3

This release applies the requested campus restriction to machine selection.

## Changes

- Automation may select autonomous check-in courses offered at Beijing, Shahe, or all campuses.
- Hangzhou-campus courses are rejected during planning and again immediately before selection.
- Existing manually selected courses remain unchanged.
- Status diagnostics also exclude Hangzhou-campus courses from open and upcoming automation counts.

## Verification

- Automated tests cover rejection of a Hangzhou autonomous course.
- Existing manual-selection provenance and autonomous check-in behavior are unchanged.
