# 091 Title Style Audit CLI

## Why

Ticket 086 landed `validate_title_style()` and the five reason codes, but the creator path still emits old speculative templates. That leaves no read-only way to observe how much draft inventory violates the 086 contract before deciding whether ticket 088 should move.

## What

- Add a new read-only CLI at `src/tools/run_title_style_audit.py`.
- Reuse `validate_title_style()` from ticket 086 instead of reimplementing title checks.
- Reuse the editor lane subtype inference entrypoint to bucket existing posts by subtype.
- Fetch WordPress posts page by page, audit each title, and print reason-code counts, subtype pass/fail counts, and sample failures to stdout.

## Non-Goals

- Writing back to WordPress.
- Extending ticket 086 rules or changing the validator.
- Touching creator/editor wiring.
- Adding automation, scheduler wiring, or 087-A/front-lane work.

## Acceptance

1. One run can scan all current drafts with a single read-only CLI invocation.
2. The output includes counts for all five 086 reason codes.
3. The output includes subtype-level pass/fail counts.
4. The output includes up to 10 sample failures.
5. The audit performs zero WordPress writes.
6. `python3 -m unittest discover -s tests` remains green.
