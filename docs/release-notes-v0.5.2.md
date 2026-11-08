# Boya Automation v0.5.2

This patch keeps selection safe when the full course-catalog API becomes slow or unavailable.

## Highlights

- Uses recent cached course candidates only as an index when the large catalog response times out.
- Rechecks every candidate through the live course-detail endpoint before selecting it.
- Reconsiders courses previously cached as full after someone else drops the course.
- Still blocks regular-signin courses, Hangzhou courses, closed selection windows, and genuinely
  full courses.
- Improves the Overview and account-status wording to distinguish cached discovery from paused
  selection.

## Upgrade

Download and extract `BoyaAutomation-v0.5.2-windows-x64.zip`, then launch
`BoyaAutomation.exe` or `Launch Boya Automation.vbs`. Existing data and sessions are preserved.
