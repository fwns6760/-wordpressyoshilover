"""YouTube Data API helpers for the YouTube Shorts approval flow.

Runtime calls use plain HTTPS via ``requests`` so the existing Cloud Run images
do not need the heavier google-api-python-client dependency.  The functions are
only called from live mode.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from typing import Any, Mapping

import requests


TOKEN_URL = "https://oauth2.googleapis.com/token"
YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
YOUTUBE_UPLOAD_URL = f"{YOUTUBE_API_BASE.replace('/youtube/v3', '/upload/youtube/v3')}/videos"
DEFAULT_CATEGORY_ID = "17"  # Sports
DEFAULT_UPLOAD_PRIVACY = "private"
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_UPLOAD_TIMEOUT_SECONDS = 900
DEFAULT_CONTAINS_SYNTHETIC_MEDIA = False
SETTABLE_STATUS_KEYS = {
    "embeddable",
    "license",
    "privacyStatus",
    "publicStatsViewable",
    "selfDeclaredMadeForKids",
    "containsSyntheticMedia",
}


@dataclass(frozen=True)
class YouTubeOAuthConfig:
    client_id: str
    client_secret: str
    refresh_token: str
    token_uri: str = TOKEN_URL


@dataclass(frozen=True)
class YouTubeUploadResult:
    video_id: str
    privacy_status: str
    watch_url: str
    studio_url: str


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _project_id() -> str:
    return (
        os.environ.get("GOOGLE_CLOUD_PROJECT", "").strip()
        or os.environ.get("GCP_PROJECT", "").strip()
        or os.environ.get("GCLOUD_PROJECT", "").strip()
        or ""
    )


def _load_secret(secret_name: str) -> str:
    try:
        from google.cloud import secretmanager
    except ImportError as exc:
        raise RuntimeError("google.cloud.secretmanager is not available") from exc

    project_id = _project_id()
    if not project_id:
        raise RuntimeError("secret manager project id is not available")
    client = secretmanager.SecretManagerServiceClient()
    resource = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(name=resource)
    data = getattr(getattr(response, "payload", None), "data", b"")
    if not data:
        raise RuntimeError(f"secret {secret_name} latest version is empty")
    return data.decode("utf-8") if isinstance(data, bytes) else str(data)


def _config_value(env_name: str, secret_env_name: str) -> str:
    value = os.environ.get(env_name, "").strip()
    if value:
        return value
    secret_name = os.environ.get(secret_env_name, "").strip()
    if not secret_name:
        return ""
    return _load_secret(secret_name).strip()


def load_oauth_config() -> YouTubeOAuthConfig:
    config = YouTubeOAuthConfig(
        client_id=_config_value(
            "YT_SHORTS_YOUTUBE_CLIENT_ID",
            "YT_SHORTS_YOUTUBE_CLIENT_ID_SECRET_NAME",
        ),
        client_secret=_config_value(
            "YT_SHORTS_YOUTUBE_CLIENT_SECRET",
            "YT_SHORTS_YOUTUBE_CLIENT_SECRET_NAME",
        ),
        refresh_token=_config_value(
            "YT_SHORTS_YOUTUBE_REFRESH_TOKEN",
            "YT_SHORTS_YOUTUBE_REFRESH_TOKEN_SECRET_NAME",
        ),
        token_uri=os.environ.get("YT_SHORTS_YOUTUBE_TOKEN_URI", TOKEN_URL).strip() or TOKEN_URL,
    )
    missing = [
        name
        for name, value in (
            ("client_id", config.client_id),
            ("client_secret", config.client_secret),
            ("refresh_token", config.refresh_token),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(f"YouTube OAuth config is incomplete: missing {', '.join(missing)}")
    return config


def refresh_access_token(
    config: YouTubeOAuthConfig | None = None,
    *,
    session: Any = requests,
) -> str:
    cfg = config or load_oauth_config()
    response = session.post(
        cfg.token_uri,
        data={
            "client_id": cfg.client_id,
            "client_secret": cfg.client_secret,
            "refresh_token": cfg.refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("YouTube OAuth refresh did not return access_token")
    return token


def _json_response(response: Any) -> dict[str, Any]:
    try:
        payload = response.json()
    except Exception as exc:
        text = getattr(response, "text", "")
        raise RuntimeError(f"YouTube API returned non-JSON response: {str(text)[:200]}") from exc
    return payload if isinstance(payload, dict) else {}


def _authorization_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _watch_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def _studio_url(video_id: str) -> str:
    return f"https://studio.youtube.com/video/{video_id}/edit"


def upload_private_video(
    video_path: str | Path,
    *,
    title: str,
    description: str,
    tags: tuple[str, ...] = (),
    category_id: str = DEFAULT_CATEGORY_ID,
    privacy_status: str = DEFAULT_UPLOAD_PRIVACY,
    contains_synthetic_media: bool | None = None,
    config: YouTubeOAuthConfig | None = None,
    session: Any = requests,
) -> YouTubeUploadResult:
    path = Path(video_path)
    if not path.is_file():
        raise FileNotFoundError(str(path))
    if privacy_status not in {"private", "unlisted"}:
        raise ValueError("approval upload privacy_status must be private or unlisted")

    synthetic = _env_flag(
        "YT_SHORTS_YOUTUBE_CONTAINS_SYNTHETIC_MEDIA",
        DEFAULT_CONTAINS_SYNTHETIC_MEDIA,
    )
    if contains_synthetic_media is not None:
        synthetic = bool(contains_synthetic_media)
    access_token = refresh_access_token(config, session=session)
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "categoryId": str(category_id or DEFAULT_CATEGORY_ID),
            "tags": list(tags),
        },
        "status": {
            "privacyStatus": privacy_status,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": synthetic,
        },
    }
    init_response = session.post(
        YOUTUBE_UPLOAD_URL,
        params={
            "uploadType": "resumable",
            "part": "snippet,status",
            "notifySubscribers": "false",
        },
        headers={
            **_authorization_headers(access_token),
            "Content-Type": "application/json; charset=utf-8",
            "X-Upload-Content-Type": "video/mp4",
            "X-Upload-Content-Length": str(path.stat().st_size),
        },
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    init_response.raise_for_status()
    upload_location = init_response.headers.get("Location", "")
    if not upload_location:
        raise RuntimeError("YouTube resumable upload did not return Location header")

    with path.open("rb") as fh:
        upload_response = session.put(
            upload_location,
            headers={
                **_authorization_headers(access_token),
                "Content-Type": "video/mp4",
            },
            data=fh,
            timeout=DEFAULT_UPLOAD_TIMEOUT_SECONDS,
        )
    upload_response.raise_for_status()
    payload = _json_response(upload_response)
    video_id = str(payload.get("id") or "").strip()
    if not video_id:
        raise RuntimeError("YouTube upload response did not include video id")
    actual_privacy = str(payload.get("status", {}).get("privacyStatus") or privacy_status)
    return YouTubeUploadResult(
        video_id=video_id,
        privacy_status=actual_privacy,
        watch_url=_watch_url(video_id),
        studio_url=_studio_url(video_id),
    )


def _status_for_update(current_status: Mapping[str, Any], privacy_status: str) -> dict[str, Any]:
    status = {
        key: value
        for key, value in dict(current_status or {}).items()
        if key in SETTABLE_STATUS_KEYS and value is not None
    }
    status["privacyStatus"] = privacy_status
    if privacy_status != "private":
        status.pop("publishAt", None)
    return status


def set_video_privacy(
    video_id: str,
    privacy_status: str,
    *,
    config: YouTubeOAuthConfig | None = None,
    session: Any = requests,
) -> YouTubeUploadResult:
    if privacy_status not in {"private", "unlisted", "public"}:
        raise ValueError("privacy_status must be private, unlisted, or public")
    vid = str(video_id or "").strip()
    if not vid:
        raise ValueError("video_id is required")

    access_token = refresh_access_token(config, session=session)
    list_response = session.get(
        f"{YOUTUBE_API_BASE}/videos",
        params={"part": "status", "id": vid},
        headers=_authorization_headers(access_token),
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    list_response.raise_for_status()
    items = _json_response(list_response).get("items") or []
    if not items:
        raise RuntimeError(f"YouTube video not found: {vid}")
    current_status = items[0].get("status") or {}
    update_body = {"id": vid, "status": _status_for_update(current_status, privacy_status)}
    update_response = session.put(
        f"{YOUTUBE_API_BASE}/videos",
        params={"part": "status"},
        headers={
            **_authorization_headers(access_token),
            "Content-Type": "application/json; charset=utf-8",
        },
        data=json.dumps(update_body, ensure_ascii=False).encode("utf-8"),
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )
    update_response.raise_for_status()
    payload = _json_response(update_response)
    actual_privacy = str(payload.get("status", {}).get("privacyStatus") or privacy_status)
    return YouTubeUploadResult(
        video_id=vid,
        privacy_status=actual_privacy,
        watch_url=_watch_url(vid),
        studio_url=_studio_url(vid),
    )


__all__ = [
    "YouTubeOAuthConfig",
    "YouTubeUploadResult",
    "load_oauth_config",
    "refresh_access_token",
    "set_video_privacy",
    "upload_private_video",
]
