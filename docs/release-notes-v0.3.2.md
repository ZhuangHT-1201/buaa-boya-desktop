# Boya Automation v0.3.2

This release makes gap detection match the actual Boya statistics fields and removes campus
restrictions from machine selection.

## Changes

- Autonomous check-in courses are now eligible regardless of Beijing or Hangzhou campus.
- Remaining selection demand is calculated as `required - selected`, so categories with no selected
  courses are no longer missed when `undoneAssessmentCount` is zero.
- Selection and completion are tracked separately: selected, passed, pending assessment, failed, and
  remaining slots.
- Missing statistics or fully occupied category slots no longer trigger fallback course selection.
- The account-status view now shows per-category requirements and per-course assessment results.

## Current live account diagnosis

- Both accounts have two unfilled `劳动教育` slots.
- `德育` has two selected courses: one passed and one awaiting assessment.
- `美育` has one selected course awaiting assessment / showing a non-pass state in statistics.
- `安全健康` is complete.
- At diagnosis time there were 67 autonomous check-in courses in the catalog, but only one was in its
  selection window and it was full. Upcoming courses will be evaluated as their windows open.

## Verification

- `14` automated tests pass.
- Cross-campus autonomous-course selection is covered by a regression test.
- Real statistics now resolve the unfilled category as `劳动教育` for both accounts.
