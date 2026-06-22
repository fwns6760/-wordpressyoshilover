#!/usr/bin/env python3
"""ワンコマンドで yt-shorts の YouTube refresh token を取り直す簡易版。

引数も手入力も不要。client_id / client_secret は Secret Manager から自動取得し、
ローカル loopback で認証コードを受け取り、新しい refresh token を
``yt-shorts-youtube-refresh-token`` に保存する。

使い方:
    python3 scripts/yt_oauth_easy.py
"""

from __future__ import annotations

import subprocess
import sys

# 同ディレクトリの setup スクリプトの関数を再利用
from setup_yt_shorts_youtube_oauth import (
    DEFAULT_PROJECT,
    DEFAULT_REFRESH_TOKEN_SECRET,
    exchange_code_for_refresh_token,
    receive_authorization_code,
    write_secret,
)

PROJECT = DEFAULT_PROJECT
PORT = 8765
TIMEOUT = 600


def _secret(name: str) -> str:
    out = subprocess.run(
        ["gcloud", "secrets", "versions", "access", "latest",
         "--secret", name, "--project", PROJECT],
        capture_output=True, text=True,
    )
    return out.stdout.strip()


def main() -> int:
    client_id = _secret("yt-shorts-youtube-client-id")
    client_secret = _secret("yt-shorts-youtube-client-secret")
    if not client_id or not client_secret:
        print("ERROR: client_id / client_secret を Secret Manager から取得できませんでした。"
              " gcloud にログインしているか確認してください。")
        return 1

    print("=" * 60)
    print("下のURLをブラウザで開いて、YouTubeチャンネルのアカウントで許可してください。")
    print("（『確認されていないアプリ』→ 詳細 → 続行 → 許可）")
    print("=" * 60)

    code, redirect_uri = receive_authorization_code(
        client_id, port=PORT, timeout_seconds=TIMEOUT
    )
    refresh_token = exchange_code_for_refresh_token(
        client_id=client_id,
        client_secret=client_secret,
        code=code,
        redirect_uri=redirect_uri,
    )
    write_secret(PROJECT, DEFAULT_REFRESH_TOKEN_SECRET, refresh_token)
    print("")
    print("✅ Done. 新しい refresh token を保存しました。")
    print("   → チャットで「できた」と伝えてください。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
