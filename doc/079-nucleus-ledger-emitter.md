# 079 Nucleus Ledger Emitter

## Purpose

Ticket 079 wires the 071 nucleus validator and 078 ledger adapter into a local JSONL sink so `run_notice_fixed_lane` can append partial nucleus ledger entries without touching the canonical ledger in `baseballwordpress`.

## Hook Point

The only runner change is a guarded hook in `src/tools/run_notice_fixed_lane.py` on the draft-create success path, immediately before the final `return ProcessResult(...)`. The hook:

- builds `DraftMeta` from the created draft and candidate metadata
- calls `emit_nucleus_ledger_entry(...)`
- swallows emitter failures with a single stderr warning so the runner result stays unchanged

## Local Sink

Default sink:

```text
logs/nucleus_ledger/YYYY-MM-DD.jsonl
```

- Date is always JST.
- Parent directories are auto-created.
- `NUCLEUS_LEDGER_SINK_DIR` overrides the sink root for tests or local debugging.

## Env Gate

- `NUCLEUS_LEDGER_EMIT_ENABLED=1` enables real append behavior.
- Default is off.
- When the gate is off, the emitter returns `status="gate_off"` and writes nothing.
- The dry-run CLI can force the gate on with `--enabled`.

Optional metadata env fallbacks:

- `NUCLEUS_LEDGER_PROMPT_VERSION`
- `NUCLEUS_LEDGER_TEMPLATE_VERSION`

## Partial Entry Format

Each line is a JSON object with the local partial ledger fields needed for 079:

- `date`
- `draft_id`
- `candidate_key`
- `subtype`
- `fail_tags`
- `context_flags`
- `source_trust`
- `source_family`
- `chosen_lane`
- `chosen_model`
- `prompt_version`
- `template_version`
- `repair_applied`
- `repair_trigger`
- `repair_actions`
- `source_recheck_used`
- `search_used`
- `changed_scope`
- `outcome`
- `note`

`context_flags` is intentionally emitted as a separate key from `fail_tags`.

## CLI Dry-Run

Fixture file:

```bash
python3 -m src.tools.run_nucleus_ledger_emit_dry_run \
  --fixture /tmp/nucleus-fixture.json \
  --enabled \
  --sink-dir /tmp/nucleus-test
```

Stdin:

```bash
python3 -m src.tools.run_nucleus_ledger_emit_dry_run --stdin --enabled <<'EOF'
{"draft_id":63175,"candidate_key":"transaction-notice-giants-20260420","subtype":"fact_notice","title":"巨人、田中俊太を支配下登録","body":"読売ジャイアンツは24日、...","source_trust":"primary","source_family":"npb_roster","chosen_lane":"fixed"}
EOF
```

The CLI prints the emitter result as JSON to stdout and exits with `0` for `emitted` / `gate_off`, `1` for `error`.

## Non-Goals

- canonical ledger merge into `baseballwordpress`
- `automation.toml` or scheduler wiring
- runtime restart or Windows-side automation changes
- hooks for any runner other than `run_notice_fixed_lane`
