# Boya Automation v0.3.4

This release fixes stale account status after manual changes on the Boya website and adds upcoming
course discovery.

## Status synchronization

- The app requests a fresh status check when opened with data older than two minutes.
- **Refresh Boya status** now delegates to the background worker instead of requiring it to stop.
- The default full refresh interval is now five minutes.
- Account status shows when selections/statistics and the course catalog were last updated.
- Transient HTTP timeouts are retried up to three times.

## Upcoming course discovery

- Each account shows future autonomous check-in courses that match unfilled categories.
- The list includes campus, selection window, course start time, and remaining capacity.
- Hangzhou courses remain excluded.
- Courses already in the catalog are checked every polling cycle; the catalog itself refreshes every
  five minutes by default.

## Verified account state

After refreshing both accounts directly from Boya:

- Both accounts now show `3` selected courses, for a total of `6`.
- Both accounts need `1` Moral Education course and `2` Labor Education courses.
- Course `10307` is detected as an upcoming Beijing Moral Education opportunity, with `150` seats
  and a selection window starting at `2026-11-04 09:00:00`.

All `17` automated tests pass.
