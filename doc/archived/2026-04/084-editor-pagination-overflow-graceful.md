# 084 Editor Pagination Overflow Graceful Handling

## Why

`_collect_paginated_candidates()` treated WordPress REST page overflow as a fatal pagination failure. When WordPress returned `400 rest_post_invalid_page_number` for page `N+1`, the lane discarded already collected candidates from pages `1..N` and emitted `wp_pagination_failed`.

## What

- Treat `RuntimeError` messages containing `rest_post_invalid_page_number` as the normal end-of-pagination signal.
- Keep already collected candidates and break out of the loop.
- Continue returning `None` for other pagination errors so the runner still emits `wp_pagination_failed`.

## Non-Goals

- Changing WordPress REST behavior.
- Redesigning the pagination loop or editor runner.
- Touching editor thresholds, creator logic, front-end files, or unrelated lanes.

## Acceptance

1. Page overflow after earlier pages returns the collected candidates instead of failing.
2. Page 1 overflow returns an empty candidate list without a stop reason.
3. Non-overflow pagination errors still return `None` and preserve `wp_pagination_failed`.
4. `python3 -m unittest discover -s tests` stays green.
5. No diffs are introduced outside the scoped files for this ticket.
