"""報知ニュース記事 → 重要コメント+数値の scrape 型 X 投稿 → ワンタップ HTML メール。

@Tigers_140609 系の「重要コメントと数値だけ抜いて速報で出す」型を巨人で再現する
connector。記事(本文)は従来どおり報知ソースのまま使い、ここは **X 投稿側だけ** を作る。

流れ:
    facts(構造化) → Flash Lite で整形(format_scrape_post)
    → ワンタップ投稿リンク付き HTML メール(build_email_html)
    → mail_delivery_bridge で送信(runner 側)

事実安全(致命的 NG 回避):
    - facts は構造化で渡し、モデルには「facts 外の数字/固有名詞/日付/引用を本文に
      入れない・新しい数字を作らない」を system prompt で強制。
    - 数字と引用は facts の文字列をそのままコピーさせる。
    - 既存 format_as_x_post / x_post_gen_mcp と同じ方針。
"""

from __future__ import annotations

import html as _html
import json
import os
import re
import urllib.parse
from typing import Any, Callable, Dict, List, Optional

# X の投稿画面を本文入りで開く canonical endpoint。
# x_post_mail_lane._X_INTENT_URL_BASE と一致させる(legacy twitter.com/intent/tweet は
# 一部クライアントで ?text= を落とすため使わない)。
X_INTENT_URL_BASE = "https://x.com/intent/post"
X_CHAR_LIMIT = 280

# 既定モデル: 枠温存前提の Flash Lite(gemini_model_policy の FALLBACK と同じ)。
DEFAULT_MODEL = "gemini-3.1-flash-lite"

SCRAPE_SYSTEM_PROMPT = (
    "あなたは巨人ファンメディア『ヨシラバー』の編集アシスタント。"
    "渡す JSON の facts だけを使って日本語で出力する。"
    "【厳守】facts に無い数字・固有名詞・日付・引用・成績を一切追加/推測しない。"
    "数字と引用は facts の文字列をそのままコピーする。"
    "コードフェンス(```)やマークダウン見出しは使わない。"
)


# ---------------------------------------------------------------------------
# 1) 抽出 (v0): 報知記事テキストから引用「」を拾う簡易抽出
# ---------------------------------------------------------------------------
_QUOTE_RE = re.compile(r"「([^「」]{8,200})」")


def extract_quotes_from_text(body_text: str, *, max_quotes: int = 3) -> List[str]:
    """記事本文から「…」の発言を最大 max_quotes 本、出現順・重複除去で返す(v0)。

    数値や項目立ては記事ごとに構造が違うため、ここでは引用のみを機械抽出する。
    数字 facts は呼び出し側(報知 extractor / 手入力)から渡す前提。"""
    seen: set[str] = set()
    out: List[str] = []
    for m in _QUOTE_RE.finditer(body_text or ""):
        q = m.group(1).strip()
        if q and q not in seen:
            seen.add(q)
            out.append(q)
        if len(out) >= max_quotes:
            break
    return out


# ---------------------------------------------------------------------------
# 2) 整形: Flash Lite に facts を渡して速報ポスト本文を作る
# ---------------------------------------------------------------------------
def build_x_prompt(facts: Dict[str, Any]) -> str:
    return (
        "次の facts から、X(旧Twitter)の速報ポストを1本作る。"
        f"条件: {X_CHAR_LIMIT}字以内 / 短文で初速を狙う温度感 / 引用を1〜2本 / "
        "主要な数字を3点 / 末尾に #巨人 #ジャイアンツ。\n\nfacts:\n"
        + json.dumps(facts, ensure_ascii=False, indent=2)
    )


def _default_generate(prompt: str, *, model: str, api_key: str) -> str:
    """google.generativeai 経由で Flash Lite を 1 回叩く(SDK は遅延 import)。"""
    import google.generativeai as genai  # type: ignore[import-not-found]

    genai.configure(api_key=api_key)
    gm = genai.GenerativeModel(model_name=model, system_instruction=SCRAPE_SYSTEM_PROMPT)
    resp = gm.generate_content(prompt, generation_config={"temperature": 0.4})
    return (getattr(resp, "text", "") or "").strip()


def format_scrape_post(
    facts: Dict[str, Any],
    *,
    model: str = DEFAULT_MODEL,
    api_key: Optional[str] = None,
    generate: Optional[Callable[..., str]] = None,
) -> str:
    """facts → 速報ポスト本文。

    generate を渡すとそれを使う(テスト用 stub)。未指定なら Flash Lite を叩く。
    """
    prompt = build_x_prompt(facts)
    if generate is not None:
        return generate(prompt, model=model, api_key=api_key or "").strip()
    key = api_key or os.getenv("GEMINI_API_KEY") or ""
    if not key:
        raise RuntimeError("GEMINI_API_KEY not set (and no generate injected)")
    return _default_generate(prompt, model=model, api_key=key).strip()


# ---------------------------------------------------------------------------
# 3) ワンタップ投稿リンク + HTML メール
# ---------------------------------------------------------------------------
def build_intent_url(text: str) -> str:
    """本文入りで X の投稿画面を開く URL。"""
    return X_INTENT_URL_BASE + "?text=" + urllib.parse.quote(text, safe="")


def build_quote_intent_url(text: str, tweet_url: str) -> str:
    """引用RTで開く URL(text=コメント & url=元ツイート)。インプ近道。"""
    q = urllib.parse.quote(text, safe="")
    u = urllib.parse.quote(tweet_url, safe="")
    return f"{X_INTENT_URL_BASE}?text={q}&url={u}"


def build_email_html(
    draft_text: str,
    *,
    label: str = "X投稿 下書き",
    quote_url: Optional[str] = None,
) -> str:
    """ワンタップ投稿ボタン付きの HTML メール本文を返す。

    quote_url を渡すと「引用RTで投稿」ボタンも追加する。"""
    count = len(draft_text)
    over = count > X_CHAR_LIMIT
    intent = build_intent_url(draft_text)
    body_html = _html.escape(draft_text).replace("\n", "<br>")
    count_badge = (
        f"文字数 {count}/{X_CHAR_LIMIT} "
        + ("⚠️ 超過(短くして)" if over else "✅")
    )

    quote_btn = ""
    if quote_url:
        qurl = _html.escape(build_quote_intent_url(draft_text, quote_url))
        quote_style = (
            "display:block;text-align:center;margin:10px 0 0;padding:13px;"
            "background:#fff;color:#000;font-size:15px;font-weight:bold;"
            "text-decoration:none;border:2px solid #000;border-radius:999px;"
        )
        quote_btn = f'<a href="{qurl}" style="{quote_style}">↻ 引用RTで投稿</a>'

    return f"""<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f2f3f5;font-family:-apple-system,'Hiragino Kaku Gothic ProN',sans-serif;">
<div style="max-width:480px;margin:0 auto;padding:16px;">
  <div style="background:#fff;border-radius:14px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,.08);">
    <div style="font-size:13px;color:#ff6600;font-weight:bold;">🌙 {_html.escape(label)}</div>
    <div style="font-size:12px;color:#888;margin:2px 0 14px;">{count_badge}</div>
    <pre style="white-space:pre-wrap;word-break:break-word;font-size:15px;line-height:1.7;
                color:#15202b;background:#f7f9fa;border:1px solid #e1e8ed;border-radius:10px;
                padding:14px;margin:0;font-family:inherit;">{body_html}</pre>
    <a href="{_html.escape(intent)}"
       style="display:block;text-align:center;margin:18px 0 0;padding:15px;
              background:#000;color:#fff;font-size:17px;font-weight:bold;
              text-decoration:none;border-radius:999px;">✕ タップして投稿する</a>
    {quote_btn}
    <div style="font-size:11px;color:#999;text-align:center;margin-top:8px;">
       タップ → X が本文入りで開く → もう一度投稿で完了</div>
  </div>
</div>
</body></html>"""
