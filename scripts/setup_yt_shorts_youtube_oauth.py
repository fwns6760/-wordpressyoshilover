#!/usr/bin/env python3
"""Set up YouTube OAuth secrets for the yt-shorts semi-automatic flow.

This script performs live GCP mutation when run from an authenticated shell:

1. Enable YouTube Data API v3 on the target project.
2. Run a loopback OAuth flow with a Desktop OAuth client created in Console.
3. Store client id, client secret, refresh token, and approval token in Secret
   Manager without printing secret values.

The OAuth client itself is still created in Google Cloud Console because normal
API OAuth clients are not reliably creatable with gcloud.
"""

from __future__ import annotations

import argparse
from getpass import getpass
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import secrets
import subprocess
import sys
import time
from typing import Iterable
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen
import webbrowser


YOUTUBE_SCOPE = "https://www.googleapis.com/auth/youtube"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
DEFAULT_PROJECT = "baseballsite"
DEFAULT_PORT = 8765
DEFAULT_CLIENT_ID_SECRET = "yt-shorts-youtube-client-id"
DEFAULT_CLIENT_SECRET_SECRET = "yt-shorts-youtube-client-secret"
DEFAULT_REFRESH_TOKEN_SECRET = "yt-shorts-youtube-refresh-token"
DEFAULT_APPROVAL_TOKEN_SECRET = "yt-shorts-approval-token-secret"


def build_authorization_url(client_id: str, redirect_uri: str, state: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": YOUTUBE_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def _run(cmd: list[str], *, input_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        input=input_text.encode("utf-8") if input_text is not None else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def enable_youtube_api(project_id: str) -> None:
    _run(["gcloud", "services", "enable", "youtube.googleapis.com", "--project", project_id])


def secret_exists(project_id: str, secret_name: str) -> bool:
    result = _run(
        ["gcloud", "secrets", "describe", secret_name, "--project", project_id],
        check=False,
    )
    return result.returncode == 0


def write_secret(project_id: str, secret_name: str, value: str) -> None:
    if not value:
        raise ValueError(f"secret value is empty: {secret_name}")
    if secret_exists(project_id, secret_name):
        _run(
            ["gcloud", "secrets", "versions", "add", secret_name, "--project", project_id, "--data-file=-"],
            input_text=value,
        )
        return
    _run(
        [
            "gcloud",
            "secrets",
            "create",
            secret_name,
            "--project",
            project_id,
            "--replication-policy=automatic",
            "--data-file=-",
        ],
        input_text=value,
    )


class OAuthCallback:
    code: str = ""
    state: str = ""
    error: str = ""


def _callback_handler(expected_state: str):
    callback = OAuthCallback()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A003
            return

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            callback.error = (query.get("error", [""])[0] or "").strip()
            callback.code = (query.get("code", [""])[0] or "").strip()
            callback.state = (query.get("state", [""])[0] or "").strip()
            if callback.error:
                status = 400
                body = "OAuth failed. You can close this tab."
            elif callback.state != expected_state:
                status = 400
                body = "OAuth state mismatch. You can close this tab."
            elif callback.code:
                status = 200
                body = "OAuth completed. You can close this tab and return to the terminal."
            else:
                status = 400
                body = "OAuth code missing. You can close this tab."
            encoded = body.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return Handler, callback


def receive_authorization_code(client_id: str, *, port: int, timeout_seconds: int) -> tuple[str, str]:
    state = secrets.token_urlsafe(24)
    handler, callback = _callback_handler(state)
    server = HTTPServer(("127.0.0.1", port), handler)
    server.timeout = 1
    redirect_uri = f"http://127.0.0.1:{server.server_port}/callback"
    auth_url = build_authorization_url(client_id, redirect_uri, state)
    print("Open this URL in the Google account that owns the YouTube channel:")
    print(auth_url)
    try:
        webbrowser.open(auth_url)
    except Exception:
        pass
    deadline = time.time() + timeout_seconds
    while time.time() < deadline and not callback.code and not callback.error:
        server.handle_request()
    server.server_close()
    if callback.error:
        raise RuntimeError(f"OAuth error: {callback.error}")
    if callback.state and callback.state != state:
        raise RuntimeError("OAuth state mismatch")
    if not callback.code:
        raise TimeoutError("OAuth callback timed out")
    return callback.code, redirect_uri


def exchange_code_for_refresh_token(
    *,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
) -> str:
    body = urlencode(
        {
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        }
    ).encode("utf-8")
    request = Request(
        TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    refresh_token = str(payload.get("refresh_token") or "").strip()
    if not refresh_token:
        raise RuntimeError(
            "OAuth succeeded but refresh_token was not returned. Re-run after revoking app access, "
            "or ensure prompt=consent and access_type=offline are honored."
        )
    return refresh_token


def _prompt_nonempty(label: str, provided: str = "") -> str:
    value = provided.strip() if provided else input(f"{label}: ").strip()
    if not value:
        raise ValueError(f"{label} is required")
    return value


def _secret_summary(secret_names: Iterable[str]) -> str:
    return "\n".join(f"- {name}" for name in secret_names)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Set up yt-shorts YouTube OAuth secrets.")
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--client-id", default="")
    parser.add_argument("--client-secret", default="")
    parser.add_argument("--client-id-secret-name", default=DEFAULT_CLIENT_ID_SECRET)
    parser.add_argument("--client-secret-secret-name", default=DEFAULT_CLIENT_SECRET_SECRET)
    parser.add_argument("--refresh-token-secret-name", default=DEFAULT_REFRESH_TOKEN_SECRET)
    parser.add_argument("--approval-token-secret-name", default=DEFAULT_APPROVAL_TOKEN_SECRET)
    parser.add_argument("--skip-api-enable", action="store_true")
    parser.add_argument("--skip-secret-write", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    client_id = _prompt_nonempty("OAuth Desktop client_id", args.client_id)
    client_secret = args.client_secret.strip() or getpass("OAuth Desktop client_secret: ").strip()
    if not client_secret:
        raise ValueError("OAuth Desktop client_secret is required")

    if not args.skip_api_enable:
        print(f"Enabling YouTube Data API v3 on project={args.project} ...")
        enable_youtube_api(args.project)

    code, redirect_uri = receive_authorization_code(
        client_id,
        port=args.port,
        timeout_seconds=args.timeout_seconds,
    )
    refresh_token = exchange_code_for_refresh_token(
        client_id=client_id,
        client_secret=client_secret,
        code=code,
        redirect_uri=redirect_uri,
    )
    approval_token_secret = secrets.token_urlsafe(48)

    secret_names = [
        args.client_id_secret_name,
        args.client_secret_secret_name,
        args.refresh_token_secret_name,
        args.approval_token_secret_name,
    ]
    if not args.skip_secret_write:
        print("Writing Secret Manager values. Secret values will not be printed.")
        write_secret(args.project, args.client_id_secret_name, client_id)
        write_secret(args.project, args.client_secret_secret_name, client_secret)
        write_secret(args.project, args.refresh_token_secret_name, refresh_token)
        write_secret(args.project, args.approval_token_secret_name, approval_token_secret)

    print("Done. Secret names:")
    print(_secret_summary(secret_names))
    print("")
    print("Use these runtime secret mappings later:")
    print(f"YT_SHORTS_YOUTUBE_CLIENT_ID={args.client_id_secret_name}:latest")
    print(f"YT_SHORTS_YOUTUBE_CLIENT_SECRET={args.client_secret_secret_name}:latest")
    print(f"YT_SHORTS_YOUTUBE_REFRESH_TOKEN={args.refresh_token_secret_name}:latest")
    print(f"YT_SHORTS_APPROVAL_TOKEN_SECRET={args.approval_token_secret_name}:latest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
