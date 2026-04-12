#!/bin/bash
# Secret ManagerからGemini認証情報をセットアップ
mkdir -p /root/.gemini

if [ -n "$GEMINI_OAUTH_CREDS" ]; then
    echo "$GEMINI_OAUTH_CREDS" > /root/.gemini/oauth_creds.json
fi

if [ -n "$GEMINI_GOOGLE_ACCOUNTS" ]; then
    echo "$GEMINI_GOOGLE_ACCOUNTS" > /root/.gemini/google_accounts.json
fi

exec python3 src/server.py
