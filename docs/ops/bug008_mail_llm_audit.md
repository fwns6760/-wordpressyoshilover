# BUG-008 mail send path LLM audit

- Date: 2026-05-03 JST
- Conclusion: **CLEAN**
- Finding summary:
  - Core publish-notice mail path contains **0 callable LLM imports** and **0 LLM API invocations**.
  - Keyword grep found **2 metadata-only hits** (`"gemini"` / `"openai_api"` strings), but both are ledger/schema labels, not model execution.
  - Non-LLM cloud SDK usage exists for Secret Manager and GCS state sync only.

## Scope

- Runtime entrypoint: [bin/publish_notice_entrypoint.sh](/home/fwns6/code/wordpressyoshilover/bin/publish_notice_entrypoint.sh:1)
- Core runtime modules:
  - [src/cloud_run_persistence.py](/home/fwns6/code/wordpressyoshilover/src/cloud_run_persistence.py:20)
  - [src/tools/run_publish_notice_email_dry_run.py](/home/fwns6/code/wordpressyoshilover/src/tools/run_publish_notice_email_dry_run.py:20)
  - [src/publish_notice_scanner.py](/home/fwns6/code/wordpressyoshilover/src/publish_notice_scanner.py:2665)
  - [src/publish_notice_email_sender.py](/home/fwns6/code/wordpressyoshilover/src/publish_notice_email_sender.py:2085)
  - [src/mail_delivery_bridge.py](/home/fwns6/code/wordpressyoshilover/src/mail_delivery_bridge.py:250)
- Transitive helper modules checked because they are imported from the mail path:
  - [src/baseball_numeric_fact_consistency.py](/home/fwns6/code/wordpressyoshilover/src/baseball_numeric_fact_consistency.py:1)
  - [src/runner_ledger_integration.py](/home/fwns6/code/wordpressyoshilover/src/runner_ledger_integration.py:68)
  - [src/repair_provider_ledger.py](/home/fwns6/code/wordpressyoshilover/src/repair_provider_ledger.py:21)

## Method

1. Traced runtime from shell entrypoint to SMTP send function.
2. Grepped the transitive call graph for:
   - `gemini|Gemini|GEMINI`
   - `openai|OpenAI`
   - `generateContent|generate_content`
   - `genai|google.generativeai`
   - `anthropic|claude`
   - `llm_call|llm.call|llm_request`
   - `_request_gemini_|_gemini_text_`
   - `vertexai|vertex_ai`
3. Reviewed imports and nearby code for every hit to classify `callable LLM use` vs `metadata-only string`.

## Runtime path identified

### Actual SMTP delivery path

1. [bin/publish_notice_entrypoint.sh](/home/fwns6/code/wordpressyoshilover/bin/publish_notice_entrypoint.sh:8)
   - executes `python3 -m src.cloud_run_persistence entrypoint`
2. [src.cloud_run_persistence.run_publish_notice_entrypoint](/home/fwns6/code/wordpressyoshilover/src/cloud_run_persistence.py:335)
   - builds `python -m src.tools.run_publish_notice_email_dry_run --scan --send ...`
   - runs it via `subprocess.run(...)` at [src/cloud_run_persistence.py](/home/fwns6/code/wordpressyoshilover/src/cloud_run_persistence.py:386)
3. [src.tools.run_publish_notice_email_dry_run.main](/home/fwns6/code/wordpressyoshilover/src/tools/run_publish_notice_email_dry_run.py:217)
   - `scan(...)` for queued per-post / review mail candidates
   - `send(...)` for per-post mail at [src/tools/run_publish_notice_email_dry_run.py](/home/fwns6/code/wordpressyoshilover/src/tools/run_publish_notice_email_dry_run.py:242)
   - `send_summary(...)` for batch summary mail at [src/tools/run_publish_notice_email_dry_run.py](/home/fwns6/code/wordpressyoshilover/src/tools/run_publish_notice_email_dry_run.py:285)
   - `send_alert(...)` for alert mail at [src/tools/run_publish_notice_email_dry_run.py](/home/fwns6/code/wordpressyoshilover/src/tools/run_publish_notice_email_dry_run.py:378)
4. [src.publish_notice_scanner.scan](/home/fwns6/code/wordpressyoshilover/src/publish_notice_scanner.py:2665)
   - fetches published WP posts via [_default_fetch](/home/fwns6/code/wordpressyoshilover/src/publish_notice_scanner.py:1297)
   - builds `PublishNoticeRequest` via [_request_from_post](/home/fwns6/code/wordpressyoshilover/src/publish_notice_scanner.py:1366)
   - adds review-side candidates from:
     - [scan_guarded_publish_history](/home/fwns6/code/wordpressyoshilover/src/publish_notice_scanner.py:1649)
     - [scan_post_gen_validate_history](/home/fwns6/code/wordpressyoshilover/src/publish_notice_scanner.py:1974)
     - [scan_preflight_skip_history](/home/fwns6/code/wordpressyoshilover/src/publish_notice_scanner.py:2170)
5. [src.publish_notice_email_sender.send](/home/fwns6/code/wordpressyoshilover/src/publish_notice_email_sender.py:2085)
   - classifies mail, builds subject/body, then calls [_deliver_mail](/home/fwns6/code/wordpressyoshilover/src/publish_notice_email_sender.py:2017)
6. [src.publish_notice_email_sender.send_summary](/home/fwns6/code/wordpressyoshilover/src/publish_notice_email_sender.py:2167)
   - builds summary body, then calls `_deliver_mail`
7. [src.publish_notice_email_sender.send_alert](/home/fwns6/code/wordpressyoshilover/src/publish_notice_email_sender.py:2192)
   - builds alert body, then calls `_deliver_mail`
8. [src.mail_delivery_bridge.send](/home/fwns6/code/wordpressyoshilover/src/mail_delivery_bridge.py:250)
   - resolves SMTP credentials and sends through `smtplib.SMTP_SSL(...).send_message(...)` at [src/mail_delivery_bridge.py](/home/fwns6/code/wordpressyoshilover/src/mail_delivery_bridge.py:279)

### Sidecar path executed in the same runner

- [src.tools.run_publish_notice_email_dry_run._emit_notice_ledger](/home/fwns6/code/wordpressyoshilover/src/tools/run_publish_notice_email_dry_run.py:177)
  - records mail execution metadata after `send` / `send_summary` / `send_alert`
  - calls [src.runner_ledger_integration.build_entry](/home/fwns6/code/wordpressyoshilover/src/runner_ledger_integration.py:68)
  - then [src.runner_ledger_integration.BestEffortLedgerSink.persist](/home/fwns6/code/wordpressyoshilover/src/runner_ledger_integration.py:191)
  - this path persists artifacts to GCS / Firestore if enabled, but does not import or call any LLM SDK

## Function audit

| Function / path | Role | Direct downstream / imports checked | LLM keyword hit | Judgment | Evidence |
|---|---|---|---|---|---|
| `bin/publish_notice_entrypoint.sh` | shell entrypoint | `src.cloud_run_persistence entrypoint` | no | clean | [bin/publish_notice_entrypoint.sh:8](/home/fwns6/code/wordpressyoshilover/bin/publish_notice_entrypoint.sh:8) |
| `cloud_run_persistence.build_publish_notice_command` | builds runner command | `src.tools.run_publish_notice_email_dry_run --scan --send` | no | clean | [src/cloud_run_persistence.py:308](/home/fwns6/code/wordpressyoshilover/src/cloud_run_persistence.py:308) |
| `cloud_run_persistence.run_publish_notice_entrypoint` | runtime wrapper | `subprocess.run(command, env=runner_env)` | no | clean | [src/cloud_run_persistence.py:335](/home/fwns6/code/wordpressyoshilover/src/cloud_run_persistence.py:335) |
| `run_publish_notice_email_dry_run.main` | runner main | `scan`, `send`, `send_summary`, `send_alert`, `_emit_notice_ledger` | yes | clean | [src/tools/run_publish_notice_email_dry_run.py:217](/home/fwns6/code/wordpressyoshilover/src/tools/run_publish_notice_email_dry_run.py:217) |
| `publish_notice_scanner.scan` | produce per-post + review requests | `_default_fetch`, `scan_guarded_publish_history`, `scan_post_gen_validate_history`, `scan_preflight_skip_history` | no | clean | [src/publish_notice_scanner.py:2665](/home/fwns6/code/wordpressyoshilover/src/publish_notice_scanner.py:2665) |
| `publish_notice_scanner.scan_guarded_publish_history` | guarded-review request builder | `_default_fetch_post_detail` | no | clean | [src/publish_notice_scanner.py:1649](/home/fwns6/code/wordpressyoshilover/src/publish_notice_scanner.py:1649) |
| `publish_notice_scanner.scan_post_gen_validate_history` | post-gen-validate review request builder | history/GCS sync helpers | no | clean | [src/publish_notice_scanner.py:1974](/home/fwns6/code/wordpressyoshilover/src/publish_notice_scanner.py:1974) |
| `publish_notice_scanner.scan_preflight_skip_history` | preflight-skip review request builder | history/GCS sync helpers | no | clean | [src/publish_notice_scanner.py:2170](/home/fwns6/code/wordpressyoshilover/src/publish_notice_scanner.py:2170) |
| `publish_notice_email_sender.send` | per-post mail adapter | `_classify_mail`, `build_body_text`, `_deliver_mail` | no | clean | [src/publish_notice_email_sender.py:2085](/home/fwns6/code/wordpressyoshilover/src/publish_notice_email_sender.py:2085) |
| `publish_notice_email_sender.send_summary` | summary mail adapter | `build_summary_body_text`, `_deliver_mail` | no | clean | [src/publish_notice_email_sender.py:2167](/home/fwns6/code/wordpressyoshilover/src/publish_notice_email_sender.py:2167) |
| `publish_notice_email_sender.send_alert` | alert mail adapter | `build_alert_body_text`, `_deliver_mail` | no | clean | [src/publish_notice_email_sender.py:2192](/home/fwns6/code/wordpressyoshilover/src/publish_notice_email_sender.py:2192) |
| `publish_notice_email_sender._deliver_mail` | mail gate + bridge handoff | `bridge_send_default -> mail_delivery_bridge.send` | no | clean | [src/publish_notice_email_sender.py:2017](/home/fwns6/code/wordpressyoshilover/src/publish_notice_email_sender.py:2017) |
| `mail_delivery_bridge.send` | actual SMTP send | `load_credentials_from_env`, `smtplib.SMTP_SSL`, `smtp.send_message` | no | clean | [src/mail_delivery_bridge.py:250](/home/fwns6/code/wordpressyoshilover/src/mail_delivery_bridge.py:250) |
| `run_publish_notice_email_dry_run._emit_notice_ledger` | sidecar ledger write after mail result | `runner_ledger_integration.build_entry`, `.persist` | yes | clean | [src/tools/run_publish_notice_email_dry_run.py:177](/home/fwns6/code/wordpressyoshilover/src/tools/run_publish_notice_email_dry_run.py:177) |

## Keyword hits and disposition

| Grep hit | Classification | Why it is not LLM contamination |
|---|---|---|
| [src/tools/run_publish_notice_email_dry_run.py:191](/home/fwns6/code/wordpressyoshilover/src/tools/run_publish_notice_email_dry_run.py:191) `provider="gemini"` | metadata-only | passed into `runner_ledger_integration.build_entry(...)` as a ledger field, not to a model SDK; `build_entry` only constructs a `RepairLedgerEntry` with `input_tokens=0`, `output_tokens=0` and hashes at [src/runner_ledger_integration.py:68](/home/fwns6/code/wordpressyoshilover/src/runner_ledger_integration.py:68) |
| [src/repair_provider_ledger.py:29](/home/fwns6/code/wordpressyoshilover/src/repair_provider_ledger.py:29) `_ALLOWED_PROVIDERS = {"gemini", "codex", "openai_api"}` | schema enum only | allowed provider labels for ledger validation; no OpenAI / Gemini / Anthropic client import or invocation in this module |

## Import analysis summary

- No imports of `openai`, `anthropic`, `google.generativeai`, or `vertexai` were found in the audited publish-notice mail path.
- Deterministic helper only:
  - [src.publish_notice_email_sender.py](/home/fwns6/code/wordpressyoshilover/src/publish_notice_email_sender.py:17) imports `check_consistency` from [src/baseball_numeric_fact_consistency.py](/home/fwns6/code/wordpressyoshilover/src/baseball_numeric_fact_consistency.py:1), which is regex/date/numeric validation only and contains no LLM SDK imports.
- Non-LLM cloud SDK imports observed:
  - [src/mail_delivery_bridge.py:80](/home/fwns6/code/wordpressyoshilover/src/mail_delivery_bridge.py:80) dynamically imports `google.cloud.secretmanager` to load SMTP credentials.
  - [src/publish_notice_scanner.py:491](/home/fwns6/code/wordpressyoshilover/src/publish_notice_scanner.py:491) imports `google.cloud.storage` for history sync.
- These cloud SDK imports do not cross into `generateContent`, `genai`, `OpenAI`, `Anthropic`, or `Vertex AI` usage.

## Excluded from the publish-notice runtime path

- `src/publish_notice_cron_health.py` and `src/tools/run_publish_notice_cron_health_check.py`
  - health-check tooling only; not imported from the publish-notice runtime chain.
- `src/x_draft_email_sender.py`, `src/ops_status_email_sender.py`, `src/morning_analyst_email_sender.py`
  - separate mail sender modules that share `mail_delivery_bridge`, but no import edge from the publish-notice runtime path was found.
- Evidence for the import boundary:
  - [src/tools/run_publish_notice_email_dry_run.py:20](/home/fwns6/code/wordpressyoshilover/src/tools/run_publish_notice_email_dry_run.py:20)
  - [src/publish_notice_scanner.py:23](/home/fwns6/code/wordpressyoshilover/src/publish_notice_scanner.py:23)
  - [src/publish_notice_email_sender.py:18](/home/fwns6/code/wordpressyoshilover/src/publish_notice_email_sender.py:18)

## Final judgment

- **CLEAN**
- Evidence supports the invariant: `publish_notice` mail send path has **0 LLM calls**.
- Remaining nuance:
  - the runner writes ledger metadata containing provider labels (`gemini`, `openai_api`), but those strings do not trigger any model request in the audited path.
