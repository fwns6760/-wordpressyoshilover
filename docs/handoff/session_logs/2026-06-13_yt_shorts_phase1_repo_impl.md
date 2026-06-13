# 2026-06-13 YouTube Shorts Phase 1 repo implementation

## Summary

- Implemented Phase 1 repo path for rights-safe YouTube Shorts generation.
- Scope is repo-only: topic selection, deterministic script, numeric guard, Pillow frames, VOICEVOX/ffmpeg render path, GCS upload hook, approval mail hook, Dockerfile, Cloud Build config, tests, docs.
- No Cloud Build, Cloud Run Job mutation, Scheduler mutation, live mail, YouTube API upload, or YouTube publish was executed.
- Follow-up after user approved GCP low-cost design: `Dockerfile.yt_shorts` now derives from official `voicevox/voicevox_engine:cpu-latest` and starts VOICEVOX locally only for the Job execution. No always-on VOICEVOX service is required.

## Safety contract

- Generated video uses only self-rendered text/data cards. No game footage, broadcast screenshots, press photos, or player photos.
- `python -m src.yt_shorts_gen` defaults to dry-run.
- `--live` is required for GCS upload and real approval mail.
- Phase 1 does not upload to YouTube. User manually uploads the MP4 from the approval mail.
- `VOICEVOX_BASE_URL` is required unless local smoke explicitly passes `--allow-silent-tts`.
- In the GCP Job image, `VOICEVOX_BASE_URL` defaults to `http://127.0.0.1:50021` and `bin/run_yt_shorts_with_voicevox.sh` starts/stops VOICEVOX inside the same container.
- Numeric strings in script/title/captions must come from source topic fields. Metric labels such as `K/9` are allowed through the label field.

## Validation

Executed:

```bash
python3 -m pytest -q tests/test_yt_shorts_topic.py tests/test_yt_shorts_script.py tests/test_yt_shorts_render.py tests/test_yt_shorts_gen.py  # 18 passed
python3 -m unittest tests.test_yt_shorts_topic tests.test_yt_shorts_script tests.test_yt_shorts_render tests.test_yt_shorts_gen  # 18 tests OK
python3 -m pytest -q tests/test_data_site_publisher.py tests/test_data_site_template_cluster.py  # 40 passed
python3 -m compileall -q src/yt_shorts_topic.py src/yt_shorts_script.py src/yt_shorts_render.py src/yt_shorts_gen.py
python3 -m mkdocs build --strict
```

Follow-up validation should include:

```bash
python3 -m pytest -q tests/test_yt_shorts_gcp_job_config.py tests/test_yt_shorts_topic.py tests/test_yt_shorts_script.py tests/test_yt_shorts_render.py tests/test_yt_shorts_gen.py  # 22 passed
bash -n bin/run_yt_shorts_with_voicevox.sh
python3 -m compileall -q tests/test_yt_shorts_gcp_job_config.py
git diff --check -- .dockerignore Dockerfile.yt_shorts cloudbuild_yt_shorts.yaml bin/run_yt_shorts_with_voicevox.sh tests/test_yt_shorts_gcp_job_config.py mkdocs_docs/spec/yt-shorts-v0-design.md docs/handoff/session_logs/2026-06-13_yt_shorts_phase1_repo_impl.md doc/active/assignments.md
```

Also re-ran:

```bash
python3 -m unittest tests.test_yt_shorts_topic tests.test_yt_shorts_script tests.test_yt_shorts_render tests.test_yt_shorts_gen  # 18 tests OK
python3 -m pytest -q tests/test_data_site_publisher.py tests/test_data_site_template_cluster.py  # 40 passed
python3 -m mkdocs build --strict
```

AST parse also passed for all four `src/yt_shorts_*.py` files.

Local smoke used a temp JSON fixture:

```bash
python3 -m src.yt_shorts_gen --topic-json /tmp/yt_shorts_fixture.json --allow-silent-tts --no-mail --output-dir /tmp/yt_shorts_smoke
```

Smoke result:

- status `ok`, dry-run `true`, tts_mode `silent`
- MP4: `/tmp/yt_shorts_smoke/2026-06-13-yt_shorts-2026-06-12-7/short.mp4`
- ffprobe: width `1080`, height `1920`, video duration `60.000000`, audio duration `60.000000`
- generated 5 PNG frames, `metadata.json`, `narration.wav`, concat file, and MP4
- representative frame visually checked for text fit

## Live executor remaining

1. Build image with `cloudbuild_yt_shorts.yaml` (base image default: `voicevox/voicevox_engine:cpu-latest`).
2. Create/update Cloud Run Job `yt-shorts-gen` with existing mail bridge secrets and `YT_SHORTS_GCS_BUCKET`. A separate VOICEVOX service is not needed.
3. Execute dry-run/smoke first. Then execute `--live` once only after user approval.
4. Add Scheduler 7:30 JST only after mail approval loop is confirmed.
