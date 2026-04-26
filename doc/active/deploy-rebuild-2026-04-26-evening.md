# deploy rebuild 2026-04-26 evening

## scope

Ticket scope was deploy-only for the three existing Cloud Run Jobs below so they pick up the `src/` changes already landed in:

- `181` / `5b21543`
- `182 v2` / `2cabfcd`

Targets:

- `draft-body-editor`
- `guarded-publish`
- `publish-notice`

Out of scope:

- `src/`, `tests/`, `requirements*.txt`, `.env`, WSL cron
- Dockerfile or Cloud Build YAML edits
- `codex-shadow`
- Secret Manager / GCS / Scheduler mutations
- `git push`

## baseline

- repo: `/home/fwns6/code/wordpressyoshilover`
- deploy baseline time: `2026-04-26 22:45 JST`
- repo HEAD used for all images: `b389f20`
- dispatch board checked at start: `doc/README.md`

## cloud build results

All three builds completed successfully in `asia-northeast1`.

| image | build id | status | digest |
|---|---|---|---|
| `draft-body-editor:b389f20` | `faf38121-e098-4097-91d4-3ed5f1207e4f` | `SUCCESS` | `sha256:4980216ad19cc0c689a7f5b791fcb1d1adbbe7d00b7e285d610fc1b6ab1845e9` |
| `guarded-publish:b389f20` | `4640159f-4a81-4873-ad63-572892b66e84` | `SUCCESS` | `sha256:cecb683fce604901aad60584475b8929eadc6882f920daaa736e69f1508e84eb` |
| `publish-notice:b389f20` | `eef25f5a-58ef-4643-94df-30bc607f7dd5` | `SUCCESS` | `sha256:09dec1e91a7ef46b39b39925ee903c339a11d010f802c85a6f533f705d060dfe` |

Artifact Registry verify:

- `draft-body-editor:b389f20` -> `sha256:4980216ad19cc0c689a7f5b791fcb1d1adbbe7d00b7e285d610fc1b6ab1845e9`
- `guarded-publish:b389f20` -> `sha256:cecb683fce604901aad60584475b8929eadc6882f920daaa736e69f1508e84eb`
- `publish-notice:b389f20` -> `sha256:09dec1e91a7ef46b39b39925ee903c339a11d010f802c85a6f533f705d060dfe`

## cloud run job updates

All three jobs were updated successfully.

`gcloud run jobs describe ... --format='value(spec.template.spec.template.spec.containers[0].image)'`

- `draft-body-editor` -> `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/draft-body-editor:b389f20`
- `guarded-publish` -> `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish:b389f20`
- `publish-notice` -> `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/publish-notice:b389f20`

## guarded-publish smoke

Manual smoke was run once after the image update:

- command: `gcloud run jobs execute guarded-publish --region=asia-northeast1 --project=baseballsite --wait`
- execution: `guarded-publish-z9k2t`
- completion: `EXECUTION_SUCCEEDED`
- execution image digest: `asia-northeast1-docker.pkg.dev/baseballsite/yoshilover/guarded-publish@sha256:cecb683fce604901aad60584475b8929eadc6882f920daaa736e69f1508e84eb`
- execution window: `2026-04-26T14:00:18.693359Z` -> `2026-04-26T14:00:53.223609Z`

Execution log summary:

- `would_publish=0`
- `refused_count=0`
- `would_skip=0`
- `executed=[]`
- `put_ok=0` (derived: no sent/executed rows were produced)

Interpretation:

- publish runner started and completed successfully on the rebuilt image
- publish did **not** revive during this smoke because no candidate was proposed in this run
- no additional refusal wave occurred in this smoke

Recent `would_publish` log check after the smoke:

- `2026-04-26T14:00:44.893352Z` -> `"would_publish": 0`

## safety

- changed repo file for this ticket: `doc/active/deploy-rebuild-2026-04-26-evening.md` only
- no source code, tests, env, secret values, scheduler definitions, or WSL cron were edited
- no secret value was printed into chat, commit text, or this note
- `codex-shadow` was not touched
- `git push`: not run
