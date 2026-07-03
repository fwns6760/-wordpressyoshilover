from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_yt_shorts_dockerfile_embeds_voicevox_engine() -> None:
    dockerfile = (ROOT / "Dockerfile.yt_shorts").read_text(encoding="utf-8")

    assert "voicevox/voicevox_engine:cpu-latest" in dockerfile
    assert "YT_SHORTS_EMBEDDED_VOICEVOX=1" in dockerfile
    assert "VOICEVOX_BASE_URL=http://127.0.0.1:50021" in dockerfile
    assert 'ENTRYPOINT ["/app/bin/run_yt_shorts_with_voicevox.sh"]' in dockerfile


def test_yt_shorts_entrypoint_starts_voicevox_locally() -> None:
    entrypoint = (ROOT / "bin/run_yt_shorts_with_voicevox.sh").read_text(encoding="utf-8")

    assert "/opt/voicevox_engine/run" in entrypoint
    assert "--host \"${vv_host}\"" in entrypoint
    assert "--port \"${vv_port}\"" in entrypoint
    assert "--disable_mutable_api" in entrypoint
    assert "python3 -m src.yt_shorts_gen" in entrypoint
    assert "VOICEVOX did not become ready" in entrypoint


def test_dockerignore_keeps_yt_shorts_build_inputs() -> None:
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "!Dockerfile.yt_shorts" in dockerignore
    assert "!bin/" in dockerignore
    assert "!bin/**" in dockerignore


def test_cloudbuild_allows_voicevox_base_image_override() -> None:
    cloudbuild = (ROOT / "cloudbuild_yt_shorts.yaml").read_text(encoding="utf-8")

    assert "_VOICEVOX_ENGINE_IMAGE: voicevox/voicevox_engine:cpu-latest" in cloudbuild
    assert "VOICEVOX_ENGINE_IMAGE=${_VOICEVOX_ENGINE_IMAGE}" in cloudbuild


def test_phase15_gcp_setup_script_wires_private_upload_and_approval_flow() -> None:
    script = (ROOT / "scripts/setup_yt_shorts_phase15_gcp.sh").read_text(encoding="utf-8")

    assert "cloudbuild_yt_shorts.yaml" in script
    assert "gcloud builds submit" in script
    assert "gcloud run services update" in script
    assert "gcloud run jobs update" in script
    assert "YT_SHORTS_YOUTUBE_PRIVATE_UPLOAD=1" in script
    assert "YT_SHORTS_YOUTUBE_CLIENT_ID=yt-shorts-youtube-client-id:latest" in script
    assert "YT_SHORTS_APPROVAL_TOKEN_SECRET=yt-shorts-approval-token-secret:latest" in script
    assert "--args=--live,--youtube-private-upload" in script
    assert "CREATE_SCHEDULER" in script
    assert "Scheduler skipped" in script
