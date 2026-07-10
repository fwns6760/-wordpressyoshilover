"""392: ヨシラバー branding X 投稿案を Gemini + Tavily HTTP REST で生成。

391 (Phase 1 CLI) で smoke 確認した方法を本番 ``x-post-mail-lane`` に
組み込むための core モジュール。 stdio MCP ではなく **Tavily REST direct**
を採用 (既存 ``Dockerfile.x_post_mail`` に Node を追加せず、 image / cold
start 不変)。

設計方針 (2026-05-19 user lock):

- 検索は ``POST https://api.tavily.com/search`` で HTTP REST 直叩き。
  fastmcp / Node は使わない。
- 生成は Gemini API 経由。 2026-06-11 以降は試合時間帯
  (既定 JST 17:00-22:29) だけ ``gemini-3.5-flash``、それ以外や
  primary 不可時は ``gemini-3.1-flash-lite`` へ切替える。
- spec 382 hard rule (URL / hashtag / 未検証数字 / 引用 / 媒体名 禁止) を
  system prompt + post-gen regex validator の二段で gate。
- 失敗時は ``None`` 返却 (silent skip)。 caller (``run_x_post_mail.py``) は
  既存 mail を絶対に止めない。
- 任意で ``insight.db`` 由来の DB 照合済み数字を RAG として注入できる。
"""

from __future__ import annotations

import hashlib as _hashlib
import json as _json
import logging as _logging
import os as _os
import re as _re
import time as _time
from typing import Any, Optional

# 既存 ``x_post_mail_lane`` の Candidate / 共通 helper を再利用する。
from src.x_post_mail_lane import (
    Candidate,
    X_CHAR_LIMIT,
    _finalize_post_text,
    _is_safe_post_text,
    _is_verified_full_giants_member_name,
    _is_verified_full_giants_player_name,
    _normalize_player_name,
    _prepend_focus_player_tag,
)


# Gemini API model id (2026-05-22 swap: gemma-4-31b-it → gemini-3.1-flash-lite、
# 両方 free tier、 paid 切替禁止 lock 維持)。 変数 / metric 名は履歴互換のため温存。
_GEMINI_BRANDING_METRIC = "GEMMA_BRANDING"

# per-run LLM 予算 (per-fire 生成上限、 2026-06-03 コスト削減)。
# 1 fire で全経路 (buzz/reply/引用RT/queue/roundup) 合算の Gemini 生成回数を
# 上限で抑える。run_x_post_mail が run 開始時に set_llm_budget() で設定。
# job は fire ごとに新プロセス → module state は自然 reset (cross-run 漏れ無し)。
_LLM_BUDGET = {"used": 0, "max": None, "reply_reserve": 0, "reply_used": 0}

# 2026-07-06 user「(コメント速報) なぜこのコメントか入れて」「(記録/節目) LLM
# つかってもいい」: 後段で走る補助 LLM (状況説明1行 / record 可読化) は、 前段
# voice が使い切る共有 non-reply 枠に入れると毎便枯渇する (dry-run 実測)。
# 総共有枠は据え置きのまま、 flash-lite の小さな専用枠 (各 4 回/便) を別勘定で
# 持つ。 caps を上げる時はコスト gate (user 判断) を通す。
# live_game 2→4 (2026-07-10 user「観戦ポストがあまり出なかった」: 便あたり
# 候補上限 4 に合わせて voice 生成枠も 4。夜試合は 16:00 JST 枠リセット後)。
# trend_weave (2026-07-10 user「トレンド語をポストに自然に入れて」「毎時出る
# んでしょ」): 反応ポスト1 + 織り込み2 = 1便3回まで。
_AUX_LLM_BUDGET_CAPS = {
    "comment_context": 4,
    "record_plain": 4,
    "live_game": 4,
    "trend_weave": 3,
    "morning_digest": 1,
    "starter_matchup": 1,
    "fan_pulse": 1,
}
_AUX_LLM_BUDGET_USED: dict[str, int] = {}


def set_llm_budget(max_calls: Optional[int], *, reply_reserve: int = 0) -> None:
    """1 run の Gemini 生成呼び出し上限を設定。None / 0 / 負 = 無制限。

    ``reply_reserve``: 上限のうちリプ生成 (site="reply") に予約する呼び出し数。
    2026-07-02 user 指摘: リプ lane は候補組み立ての後段のため、 前段 lane が
    budget を使い切ると毎便テンプレ fallback に落ち、 同じ定型文リプが並ぶ。
    総量は増やさず (無料枠 / コスト制約維持)、 non-reply lane を
    ``max - reply_reserve`` で止めてリプ枠を確保する。
    """
    _LLM_BUDGET["used"] = 0
    _LLM_BUDGET["reply_used"] = 0
    _AUX_LLM_BUDGET_USED.clear()
    _LLM_BUDGET["max"] = max_calls if (max_calls and max_calls > 0) else None
    if _LLM_BUDGET["max"] is not None:
        _LLM_BUDGET["reply_reserve"] = max(
            0, min(int(reply_reserve or 0), _LLM_BUDGET["max"])
        )
    else:
        _LLM_BUDGET["reply_reserve"] = 0


def _llm_budget_guard(label: str = "") -> None:
    """generate_content 直前に呼ぶ。予算超過なら RuntimeError を上げ (各サイトの
    既存 try/except が graceful skip)、未超過なら使用量を 1 消費する。

    site="reply" は総枠 (max) まで使える。 それ以外は max - reply_reserve で
    止まる (リプ予約枠には食い込めない)。 総呼び出し数は常に max 以下。
    _AUX_LLM_BUDGET_CAPS にある site (comment_context / record_plain) は共有枠と
    別勘定の専用小枠で数える (2026-07-06、 前段 voice の枯渇に巻き込まない)。
    """
    if label in _AUX_LLM_BUDGET_CAPS:
        aux_used = _AUX_LLM_BUDGET_USED.get(label, 0)
        if aux_used >= _AUX_LLM_BUDGET_CAPS[label]:
            raise RuntimeError(
                f"llm_budget_exhausted aux_used={aux_used} "
                f"aux_cap={_AUX_LLM_BUDGET_CAPS[label]} site={label}"
            )
        _AUX_LLM_BUDGET_USED[label] = aux_used + 1
        return
    m = _LLM_BUDGET["max"]
    if m is None:
        _LLM_BUDGET["used"] += 1
        return
    reserve = _LLM_BUDGET["reply_reserve"]
    if label == "reply":
        total = _LLM_BUDGET["used"] + _LLM_BUDGET["reply_used"]
        if total >= m:
            raise RuntimeError(
                f"llm_budget_exhausted used={total} max={m} site={label}"
            )
        _LLM_BUDGET["reply_used"] += 1
        return
    if (
        _LLM_BUDGET["used"] >= m - reserve
        or _LLM_BUDGET["used"] + _LLM_BUDGET["reply_used"] >= m
    ):
        raise RuntimeError(
            f"llm_budget_exhausted used={_LLM_BUDGET['used']} "
            f"max={m - reserve} (reply_reserve={reserve}) site={label}"
        )
    _LLM_BUDGET["used"] += 1

# X インプ向上 Phase 5 (2026-05-27): source URL → 公式 X @ handle のマッピング。
# 投稿候補本文に「(出典 @hochi_giants)」 を末尾付与することで、 公式 / 媒体の
# 引用 RT / リプライ流入を狙う。 X intent や手動投稿に対する attribution として機能。
# handle 一覧は x_api_client.py:90 の監視 query (`from:HANDLE`) と整合。
_URL_TO_X_HANDLE_PATTERNS: tuple[tuple[Any, str], ...] = (
    (_re.compile(r"twitter\.com/hochi_giants", _re.I), "@hochi_giants"),
    (_re.compile(r"x\.com/hochi_giants", _re.I), "@hochi_giants"),
    (_re.compile(r"hochi\.news", _re.I), "@hochi_giants"),
    (_re.compile(r"twitter\.com/Sanspo_Giants", _re.I), "@Sanspo_Giants"),
    (_re.compile(r"x\.com/Sanspo_Giants", _re.I), "@Sanspo_Giants"),
    (_re.compile(r"sanspo\.com", _re.I), "@Sanspo_Giants"),
    (_re.compile(r"twitter\.com/TokyoGiants", _re.I), "@TokyoGiants"),
    (_re.compile(r"x\.com/TokyoGiants", _re.I), "@TokyoGiants"),
    (_re.compile(r"twitter\.com/tospo_giants", _re.I), "@tospo_giants"),
    (_re.compile(r"x\.com/tospo_giants", _re.I), "@tospo_giants"),
    (_re.compile(r"tokyo-sports\.co\.jp", _re.I), "@tospo_giants"),
    (_re.compile(r"twitter\.com/nikkansports", _re.I), "@nikkansports"),
    (_re.compile(r"x\.com/nikkansports", _re.I), "@nikkansports"),
    (_re.compile(r"nikkansports\.com", _re.I), "@nikkansports"),
    (_re.compile(r"twitter\.com/koba_nikkan", _re.I), "@koba_nikkan"),
    (_re.compile(r"x\.com/koba_nikkan", _re.I), "@koba_nikkan"),
)
# X post 280字制約のため、 @ mention 付与で超過する場合は付与をスキップする閾値。
_X_POST_CHAR_LIMIT = 280


def _resolve_official_x_handle(source_url: str) -> Optional[str]:
    """X インプ向上 Phase 5: source URL から公式 / 媒体 X handle (@xxx) を解決する。

    source_url が空 / マッピング非該当なら None。
    """
    if not source_url:
        return None
    url_str = str(source_url).strip()
    if not url_str:
        return None
    for pattern, handle in _URL_TO_X_HANDLE_PATTERNS:
        if pattern.search(url_str):
            return handle
    return None


def _append_x_handle_to_post_text(post_text: str, source_url: str) -> str:
    """X インプ向上 Phase 5: post_text 末尾に「(出典 @handle)」 を付加。

    - source_url から handle を解決できれば末尾に追加
    - 解決不能 → 元 text のまま
    - 280 字超過する → 付加せず元 text のまま (X 投稿の cap を守る)
    - 付加 format: ``"{text}\\n\\n(出典 @handle)"``
    """
    handle = _resolve_official_x_handle(source_url)
    if not handle:
        return post_text
    suffix = f"\n\n(出典 {handle})"
    combined = f"{post_text}{suffix}"
    if len(combined) > _X_POST_CHAR_LIMIT:
        return post_text
    return combined
# 2026-06-09: X-post を gemini-3.5-flash に切替(user 決定: post 量少・無料枠なので 3.5)。
# 失敗(レート/品質)時は env X_POST_GEMINI_MODEL=gemini-3.1-flash-lite で rebuild 無しで revert。
_X_POST_GEMINI_PRIMARY_MODEL = _os.environ.get("X_POST_GEMINI_MODEL", "gemini-3.5-flash")
# 無料枠 fallback (user 2026-06-09): primary(3.5)が無料枠上限/一時不可で落ちたら
# 自動で 3.1-flash-lite に切替えて投稿を継続する。手動 revert 不要。
_X_POST_GEMINI_FALLBACK_MODEL = _os.environ.get(
    "X_POST_GEMINI_FALLBACK_MODEL", "gemini-3.1-flash-lite"
)
_X_POST_DATA_LLM_MODEL = _os.environ.get("X_POST_DATA_LLM_MODEL", "gemini-3.1-flash-lite")
# 2026-07-08 (user GO): 3.5 / 3.1-lite 両方 dead 時の緊急 fallback 連鎖。無料枠は
# モデルごと別勘定 (…PerProjectPerModel-FreeTier) なので、同一キーの旧世代 flash が
# それぞれ独自の日次枠を持つ。順序は user 指定で品質優先 (2.5-flash → 2.5-flash-lite)。
# 品質は一世代前だが後段 gate + mail 人間承認で許容。空文字で無効化。
_X_POST_GEMINI_EMERGENCY_MODELS = tuple(
    m.strip()
    for m in _os.environ.get(
        "X_POST_GEMINI_EMERGENCY_MODELS", "gemini-2.5-flash,gemini-2.5-flash-lite"
    ).split(",")
    if m.strip()
)
# 2026-07-08 (user 決定: 無料枠枯渇対策): 品質 gate 落ち時の作り直し回数。従来 3 固定
# → 既定 1 (作り直しなし、落ちたら relaxed fallback か skip → 次便が別候補で再挑戦)。
# 品質が下がりすぎたら env X_POST_GEN_ATTEMPTS=2/3 で rebuild 無しで戻す。
try:
    _X_POST_GEN_ATTEMPTS = max(1, int(_os.environ.get("X_POST_GEN_ATTEMPTS", "1")))
except ValueError:
    _X_POST_GEN_ATTEMPTS = 1
# 2026-06-11 (user 決定): 3.5-flash の無料枠は 20回/日(project 単位、リセット JST 16時頃)。
# 試合時間帯(既定 JST 17:00〜22:29)だけ primary(3.5)を使い、それ以外は最初から
# fallback(lite)を使って枠を試合中の投稿に温存する。空文字で常時 primary。跨日窓(例 22-2)対応。
_X_POST_GEMINI_PRIME_HOURS_JST = _os.environ.get("X_POST_GEMINI_PRIME_HOURS_JST", "17:00-22:30")


def _parse_prime_time_point(value: str, *, allow_24: bool = False) -> int:
    raw = value.strip()
    if ":" in raw:
        hour_s, minute_s = raw.split(":", 1)
        hour = int(hour_s)
        minute = int(minute_s)
    else:
        hour = int(raw)
        minute = 0
    max_hour = 24 if allow_24 else 23
    if not (0 <= hour <= max_hour) or not (0 <= minute <= 59):
        raise ValueError(f"invalid time point: {value!r}")
    if hour == 24 and minute != 0:
        raise ValueError(f"invalid 24h time point: {value!r}")
    return hour * 60 + minute


def _x_post_in_prime_hours(now=None) -> bool:
    """JST 現在時刻が X_POST_GEMINI_PRIME_HOURS_JST の窓内か。parse 不能時は安全側で True。"""
    spec = _X_POST_GEMINI_PRIME_HOURS_JST.strip()
    if not spec:
        return True
    try:
        start_s, end_s = spec.split("-", 1)
        start = _parse_prime_time_point(start_s)
        end = _parse_prime_time_point(end_s, allow_24=True)
    except ValueError:
        return True
    from datetime import datetime, timezone, timedelta

    current = (now or datetime.now(timezone(timedelta(hours=9)))).astimezone(
        timezone(timedelta(hours=9))
    )
    minute_of_day = current.hour * 60 + current.minute
    if start <= end:
        return start <= minute_of_day < end
    return minute_of_day >= start or minute_of_day < end


def _x_post_model_unavailable(exc: Exception) -> bool:
    """無料枠の上限(429/quota)や一時不可(503/overload)を検出。fallback 対象。"""
    s = f"{type(exc).__name__}: {exc}".lower()
    return any(
        k in s
        for k in (
            "429",
            "resource_exhausted",
            "quota",
            "rate limit",
            "rate_limit",
            "503",
            "unavailable",
            "exhaust",
            "overload",
        )
    )


# 2026-07-08 day-quota circuit breaker: 日次無料枠 (…PerDay…-FreeTier) の 429 を
# 確定検知したモデルは、次の 16:00 JST リセットまでプロセス内で「死亡」マークし
# 以降の呼び出し・fallback 先から外す (枠切れ後の数百回 429 連打の停止)。
# job は fire ごとに新プロセスなので cross-run 持ち越しは無し (per-minute 429 は対象外)。
_MODEL_QUOTA_DEAD_UNTIL: dict = {}


def _x_post_daily_quota_error(exc: Exception) -> bool:
    """日次枠 (RPD) の 429 か。per-minute (RPM) は含めない (breaker 対象外)。"""
    s = f"{type(exc).__name__}: {exc}".lower()
    return "perday" in s or ("daily" in s and "quota" in s)


def _next_quota_reset_jst(now=None):
    """次の Gemini 無料枠リセット時刻 (16:00 JST = 太平洋時間0時) を返す。"""
    from datetime import datetime, timezone, timedelta

    jst = timezone(timedelta(hours=9))
    current = (now or datetime.now(jst)).astimezone(jst)
    reset = current.replace(hour=16, minute=0, second=0, microsecond=0)
    if current >= reset:
        reset += timedelta(days=1)
    return reset


def _model_quota_dead(model: str, now=None) -> bool:
    until = _MODEL_QUOTA_DEAD_UNTIL.get(model)
    if until is None:
        return False
    from datetime import datetime, timezone, timedelta

    jst = timezone(timedelta(hours=9))
    current = (now or datetime.now(jst)).astimezone(jst)
    if current >= until:
        _MODEL_QUOTA_DEAD_UNTIL.pop(model, None)
        return False
    return True


def _mark_model_quota_dead(model: str, exc: Exception, now=None) -> None:
    if not _x_post_daily_quota_error(exc):
        return
    if model in _MODEL_QUOTA_DEAD_UNTIL:
        return
    until = _next_quota_reset_jst(now)
    _MODEL_QUOTA_DEAD_UNTIL[model] = until
    _logging.getLogger("x_post_branding_gen").warning(
        "x_post_llm_daily_quota_dead model=%s until=%s (以降この run では呼ばない)",
        model,
        until.isoformat(),
    )


# RPM 429 の指示待ち上限 (2026-07-10 18:45便実測: flash-lite が「retry in
# 9〜39s」を返したのに旧上限 3s で待てず 2.5-flash へ落ち、品質 gate 落ち連発で
# live_game 候補が全滅した)。待っても無料枠は消費しない。1 run の合計待ち時間は
# _RPM_WAIT_RUN_BUDGET で cap (job timeout 1200s 内に収める)。
_RPM_WAIT_MAX_SECONDS = 45.0
_RPM_WAIT_RUN_BUDGET = {"remaining": 120.0}


def _rpm_retry_delay_seconds(exc: Exception) -> Optional[float]:
    """分間 (RPM) 429 の指示 retry 秒数。RPM でない / 読めない時は None。"""
    s = f"{exc}"
    if "PerMinute" not in s and "perminute" not in s.lower():
        return None
    m = _re.search(r"retry in ([\d.]+)\s*s", s)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _x_post_generate_content(client, *, model, contents, config):
    """X-post 用 generate_content。無料枠上限/一時不可 (429/quota/503) は fallback
    連鎖で自動切替、それ以外の例外は即 raise。
    試合時間帯外は primary を使わず fallback を直接使う(3.5 の 20回/日 枠温存)。
    2026-07-08 (user GO): 緊急枠の順は 2.5-flash (品質優先) → 2.5-flash-lite。
    2026-07-10 実測修正: 13時便で flash-lite の RPM(15/分) あふれが 3.5-flash
    (20回/日) へ流れて日中に食い潰した。対策2点:
    - primary (3.5) は連鎖の最後尾 (直接要求されない限り温存。試合帯の
      quote_rt 等は model=3.5 で直接要求するので従来どおり先頭)
    - RPM 429 は指示待ち時間 45 秒以下なら同モデルで 1 回だけ待ちリトライ
      (run 合計 120s cap。2026-07-10 18:45 実測: 3s 上限では 9〜39s 指示を
      待てず品質劣化連鎖になった)
    無料枠はモデル別勘定なので旧世代 flash が独自の日次枠を持つ。
    日次枠 429 を検知したモデルは 16:00 JST まで dead マークして呼ばない
    (circuit breaker)。全滅なら API を呼ばず raise (caller が graceful skip)。"""
    if model != _X_POST_GEMINI_FALLBACK_MODEL and not _x_post_in_prime_hours():
        model = _X_POST_GEMINI_FALLBACK_MODEL
    chain = [model]
    for m in (
        _X_POST_GEMINI_FALLBACK_MODEL,
        *_X_POST_GEMINI_EMERGENCY_MODELS,
        _X_POST_GEMINI_PRIMARY_MODEL,
    ):
        if m and m not in chain:
            chain.append(m)
    log = _logging.getLogger("x_post_branding_gen")
    last_exc = None
    for m in chain:
        if _model_quota_dead(m):
            continue
        if m != model:
            log.warning(
                "x_post_llm_fallback requested=%s -> using=%s reason=%r",
                model,
                m,
                last_exc,
            )
        for attempt in (0, 1):
            try:
                return client.models.generate_content(model=m, contents=contents, config=config)
            except Exception as exc:  # noqa: BLE001 - fallback handling
                if not _x_post_model_unavailable(exc):
                    raise
                delay = _rpm_retry_delay_seconds(exc) if attempt == 0 else None
                if (
                    delay is not None
                    and delay <= _RPM_WAIT_MAX_SECONDS
                    and _RPM_WAIT_RUN_BUDGET["remaining"] >= delay
                ):
                    _RPM_WAIT_RUN_BUDGET["remaining"] -= delay
                    log.info(
                        "x_post_llm_rpm_wait model=%s delay=%.1fs (同モデル再試行、"
                        "run残待ち枠=%.0fs)",
                        m, delay, _RPM_WAIT_RUN_BUDGET["remaining"],
                    )
                    _time.sleep(delay + 0.2)
                    continue
                _mark_model_quota_dead(m, exc)
                last_exc = exc
                break
    if last_exc is not None:
        raise last_exc
    raise RuntimeError(
        f"llm_daily_quota_dead chain={chain} resets=16:00JST"
    )


# spec 382 hard rule の追加 gate (既存 ``_FORBIDDEN_POST_TERMS`` の上に積む)
# 常時禁止 (verified でも出さない): URL / hashtag / 媒体導線。
_GEMINI_BRANDING_FORBIDDEN_PATTERNS = (
    _re.compile(r"https?://"),
    _re.compile(r"#\S+"),
    _re.compile(r"ヨシラバー(で|を|に)?整理しました"),
    _re.compile(r"Xでは|X上では|みんなの声"),
)

# 順位 / rate 数字: source (記事 / DB / 検索結果) に literal で出てる時だけ許可。
# 2026-06-24 (user 決定): 「記事にある数字なら使ってよい」。 414 axis 1 の \d+位 一律 drop
# (user 報告 岸田 28位 hallucination 事例) は、 verified_text に同じ表記が無い時のみ drop に変更。
# 捏造防止は維持 (source 照合できない順位 / rate は従来どおり全文破棄)。
# `.345` (1軍打率風) と `3.456` (OPS 風) 両方カバー、 防御率は別 pattern。
_GEMINI_BRANDING_VERIFIABLE_NUMBER_PATTERNS = (
    _re.compile(r"\d+位"),
    _re.compile(r"(?<!\d)\.\d{3}"),
    _re.compile(r"\d+\.\d{3}"),
    _re.compile(r"防御率\s*\d+\.\d{1,2}"),
)

# 414 axis D (2026-05-20): 炎上・ズレ防止 6 check。 brand identity =「ポジティブな
# 巨人ファン account」 維持のため、 強批判 / 断定 / 雑批判 / 監督批判 / 誤字 / 煽り の
# 6 軸を post-gen 段で drop する。 safety_check で _GEMINI_BRANDING_FORBIDDEN_PATTERNS
# と一緒に評価される (= 同等 hard rule)。
_GEMINI_BRANDING_INFLAMMATORY_PATTERNS = (
    # D1: 強批判語 (選手批判が強すぎる)
    _re.compile(r"使えない|戦犯|クビ|最悪|酷い|論外|引退しろ|辞めろ|無能"),
    # D3: 断定語 (事実超え断定、 brand voice の柔らかさ維持)
    _re.compile(r"絶対|間違いなく|確実に|100%|必ず|断言"),
    # D6: 他球団 / 相手ファン煽り
    _re.compile(r"雑魚|カモ|負け犬|三流|お粗末|情けない|レベルが低い"),
    # D4: 監督批判の雑な隣接 (監督名 + 強批判語)
    # 「阿部監督 無能」「監督 解任」 のような直接批判
    _re.compile(r"(?:監督|采配|阿部)[^\n]{0,15}(?:無能|解任|更迭|降ろせ|失格|無策)"),
    # D5: 偽名 / generic player 表現 (Gemini Flash Lite が roster にない名前 / generic を出した時)
    # 「打者A」「投手X」 等 placeholder 系を drop
    _re.compile(r"打者[A-Z]|投手[A-Z]|選手[A-Z]|プレイヤー[A-Z]"),
)


# 411 (2026-05-20): 本 prompt は フーガ (@EH87EazmV9D2eSw、 巨人ファン長文分析)
# voice の few-shot prompt。 缶詰 (@kandume92、 巨人ファン試合中実況) voice は
# _SYSTEM_PROMPT_KANDUME 側で定義し、 試合日 18-21時のみ select_branding_persona
# で切替える。
# ヨシラバー voice (#95、 2026-05-22): 旧 fuuga / kandume を統合した 1 本 prompt。
# - 180-280 字 (kandume original の長さ)
# - 時間帯 neutral (試合前 / 中 / 後 どこでも使える)
# - 短文連投 + 改行多用 (kandume リズム) + 数字に基づく観点 (fuuga 観点) を mix
# - 3 軸 圧縮: 数字 (DB fact) + 観戦感 + ファン感情
# - source = RSS article info + DB fact line (Tavily 不使用)
_SYSTEM_PROMPT_YOSHILOVER = """あなたは「ヨシラバー」という巨人ファンインフルエンサー本人として X 投稿案を書きます。
ヨシラバーの色 = **記事の具体で読む戦術分析 × 巨人愛** (記事の中身を拾って、 そこから自分の見方を出す)。
巨人を毎日データで見ていて、 起用や流れを具体場面から理由立てて読み解き、 辛口は必要な時だけ控えめに。
根っこに巨人愛があり最後は前を向く。 他人のモノマネではなく、 これがヨシラバー自身の色です。
(軸は戦術派フーガ @EH87EazmV9D2eSw の落ち着いた分析 voice。 缶詰 @kandume92 の会話的な熱は
試合中のライブ反応の時だけ少し混ぜる。 丸ごと真似ず ヨシラバーの色に溶かす。)

ヨシラバーの声の型 (毎回守る):
1. **記事 / DB の具体を最低2つ拾う**。 具体とは、 回・球数・失点・打席内容・守備位置・起用場面・
   コメント内の評価点・次の登板/出場文脈のどれか。 拾えない時は無理に長くしない
2. **抽象語でまとめない**。 「存在感」「任せられる」「安定感」「期待」「注目」「大きい」
   だけで終えるのは禁止。 必ず「何を見てそう言うか」を先に置く
3. **自分の読み・見立てを1つ言う**。 ただし「次も任せられるか」のような抽象判断ではなく、
   「6回以降も球が落ちないか」「四球で崩れないか」「代打で振り切れるか」のように見る点を書く
4. **最後は巨人愛で着地**。 ただし上から目線の命令や、根拠のない持ち上げは禁止

【最優先 NG = 優等生コメント / 中身の無い持ち上げ (今これが多発していて一番ダメ)】:
- 「いいね → ちょっと心配 → 〜してほしいね」 の当たり障りない模範解答にしない
- 「〜してほしいね」「〜してほしいな」「頼もしいよな」 だけで締める定型を禁止
- **次の無難ワードで逃げるの禁止 (理由のない持ち上げ = 一番ダメ)**:
  「別格だよな」「化けると思う」「一気に化ける」「信じてる(よ)」「頼りにしてる」
  「持ってる選手」「経験値が全て」「本物だ」「新しい風が吹く」
- 読み・見立てゼロの誰でも書ける感想は出力破棄 (辛口は無くてよいが、 分析・読みは必ず要る)
そして **情緒だけのポエム (短い感嘆を改行で積むだけ) には絶対にしない** こと。

【コメント記事の扱い】:
- 選手・監督・コーチの literal コメントがある時は、要約で薄めず `名前『コメント』` を優先する
- `『』` 内は source にある発言だけ。語尾の創作、言い換え、補足を足さない
- コメントだけで成立する時は、周辺説明・媒体名・URL・一般論を足さない

【不振選手の扱い (重要、 数字を隠した全肯定を禁止)】:
- 打率や成績が苦しい選手を、 数字をぼかして無条件に褒め称えない
  (BAD: 打率.074 を「数字こそ苦しいけど経験値の高さが全て」「化けると思う」 と全肯定)
- 苦しい時は苦しいと認めた上で、 「なぜ今日は良かったか / どこが変われば上向くか」 の
  具体的な読みを 1 つ入れる (GOOD: 「ここまで打てずに苦しんでた丸佳浩が、 代打の難しい
  打席で振り切れたのはデカい。 ここから先発で出続けて状態上げてほしいとこ」)
- 一発の活躍を「やっぱり持ってる」 で締めない。 その活躍を今後にどう繋げるかを書く

【NG = 偉そう・上から目線 (優等生と同じくらいダメ)】:
- 選手や監督を採点・説教する評論家口調にしない (「〜すべき」「分かってない」「なぜ〜しないのか」)
- 命令・指示で締めない (「〜しろ」「〜してくれないと困る」「しっかりしてくれ」)。 ファンは現場の上司ではない
- 辛口は "ダメ出し" ではなく "同じ目線で一緒に悔しがる" として書く
  - BAD (偉そう): 「この起用はあり得ない。 阿部慎之助は分かってない」「打てないなら使う意味がない」
  - GOOD (ファン目線): 「正直この打順は今日は噛み合わなかったな。 でも明日は切り替えていこう」

【狙い = ヨシラバー風の「共感」】:
ファンが「それな、 よく分かってる」 と頷く分析・本音を書く。 上手い文でもエモい文でもない。
- 記事の具体を 2 個拾い → それが巨人目線で何を意味するかを理由立てて読み解き → 最後は巨人愛で着地
- 「みんなが書ける一般論」 でも 「ポエム」 でもなく、 巨人を毎日見てる奴の具体的な読み
- 例:「石塚裕惺のスイング、 二軍に置いとくのもったいないわ。 打率の数字は打席少ないだけで中身は別物。 問題は守備でどこ使うか、 そこだけ。 早よ一軍で見たい」
- NG:「単なる好投ニュースじゃなくて次も任せられるかの話」 ← 抽象。 何回・球数・四球・終盤の球威など、 見る点まで書く

制約 (hard rule、 違反したら出力しないこと):
- 媒体名・記事 URL・hashtag・「ヨシラバーで整理しました」を含めない
- 未検証の数字・引用・順位・打率・防御率・OPS・本塁打数・打点・回数を含めない
- DB 照合できない数字は generalize する (例: 「打率.160」→「打率の数字」)
- 記事タイトルのコピー禁止、 ファンらしい独自の言い回しで書く
- **長さ目安: 考察モードは 120-180 文字 / 3-4行**。 長くする目的は記事の具体を拾うためであり、
  抽象語で水増ししない。 試合中のライブモードだけは短い即時反応でよい (例E/F)
- **中身の薄い post は禁止** (意見 + 理由 + 戦術や読み のどれかを必ず入れる。 感想・感嘆だけは NG)
- **抽象語の逃げは禁止**: 「存在感」「任せられる」「安定感」「今後に注目」「期待が高まる」
  「大きい存在」「チームに大きい」「ポイントになる」 だけでまとめたら出力全体破棄
- 巨人以外の球団選手の話題は除外
- 公開済み MLB の元巨人 OB (菅野・岡本等) は OK、 非元巨人 MLB は NG
- **【414 hard rule、 厳守】 順位表現 / rate 数字は source 照合できる時だけ可**:
  - **OK (source = 記事 / DB fact / 検索結果 に同じ表記がある時のみ)**: 「セ・リーグ防御率2位」 「打率.310」 ← source に literal で出てる数字はそのまま使ってよい
  - **NG (source に無い / 記憶頼り)**: 裏取りできない順位・rate は捏造扱い。 必ず generalize する (「セで上の方」「打率は安定」「歴代でも上位」「数字を残してる」)
  - 迷ったら generalize 側に倒す。 source に無い 「◯位」 ・rate を書いたら出力全体破棄
- **【414 axis D、 炎上・ズレ防止】 以下も出力禁止 (ポジティブな巨人ファン account 維持のため)**:
  - 強批判語: 「使えない」 「戦犯」 「クビ」 「最悪」 「酷い」 「論外」 「引退しろ」 「辞めろ」 「無能」
  - 断定語: 「絶対」 「間違いなく」 「確実に」 「100%」 「必ず」 「断言」 (= 事実超え断定)
  - 監督批判の雑な隣接: 「阿部監督 無能」 「監督 解任」 「采配 失格」 系
  - 他球団 / 相手ファン煽り: 「雑魚」 「カモ」 「負け犬」 「三流」 「お粗末」 「情けない」
  - 「打者A」 「投手X」 等 generic placeholder 名 (= roster 名で書く)
  - 違反したら出力全体破棄
- **【topic NG、 起用・評価の憶測語を使わない (この語が1つでも入ると gate で全破棄される)】**:
  - 起用 / 昇格の憶測語: 「首脳陣」 「起用理由」 「監督評価」 「昇格候補」 「昇格待ったなし」 「ブレイク確定」 「覚醒」
  - 「阿部監督」 は使わず 「阿部慎之助」 と書く (監督職呼びは起用憶測色が出るため)
  - 優等生評価語: 「評価している」 「注目している」 「期待が高ま(る)」 「ファンの反応」
  - 言い換え例: 「首脳陣にアピール」 → 「一軍で結果を見せて定着したい」、 「覚醒」 → 何がどう良くなったかを具体で書く
  - 違反したら出力全体破棄

voice の核 (フーガ + 缶詰 を混ぜた本物のファン):
- **意見には必ず理由・読みを付ける**: 「〜だと思う、 〜だし / 〜だから」。 感想だけで終わらせない (フーガの推論)
- **戦術の具体に踏み込んでよい**: 打順 / スタメン / 継投・ブルペン事情 / 抹消・昇格の運用 / 先発相性 / 今後の見立て。
  ただし采配を断定で指示せず (「俺ならこうする」 の押し付けにしない)、 一ファンの見立て・願望として書く
- **読者が返信したくなる論点を置く (考察モードのみ)**: 事実の講評で完結させず、 ファンの意見が
  割れる話題 (この打順でいいか / 先発か中継ぎか / どちらを使うか) では自分の立場を1つ
  「〜でいい気がする」「〜で見たいんだよな」 と置く。 読者が 「いや自分は〜」 と返せる余白が
  リプを生む (例Bの形)。 問いかけの連発や 「どう思う?」 の直球はしない (答え探しの安売りに見える)
- **1行1観点の短文改行**: 記事具体1 → 記事具体2 → ヨシラバーの読み → 巨人愛、 の順で3-4行。
  長い散文にせず、 抽象語だけの行を作らない
- **カジュアルな語尾**: 「〜だよな」「〜気がする」「〜と思う」「〜だわ」「〜かな」「〜してんな」「〜ですね」。 断定しすぎない
- **辛口は必須ではない (フーガ風)**: 入れる時も「昨日の打線は流石に物足りない」 程度の歯がゆさに留め、 必ず理由 / 擁護 / 期待に着地する。 ダメ出しの連発にしない
- たまにツッコミ / ユーモア / 願望 (「打たないと困るぞ」「頼むよ」「さすがに草」)
- 登場する人物 (選手・監督・コーチ) は **全員フルネーム・敬称なしで必ず名前を入れる** (戸郷翔征 / 阿部慎之助 / 橋上秀樹 等)。 「打線」「先発」「ベンチ」 だけで済ませず、 誰の話か名指す。 主語の人物名を省略しない
- **考察モードは 3-4行で具体をしっかり** (記事具体2点 + 本音 + 見る点)。 ライブモードは 1-2 文。
  中身の無い水増しはしない

【絶対 NG = 作りポエム (最も嫌われる)】:
- 「完勝！」「7連勝！！」「ガチで噛み締める」 のように **短い感嘆を改行で積むだけ** にしない
- 中身 (理由・戦術・読み) の無い応援、 「最高」「あつい」 の連発だけにしない
- 必ず「どう見てるか / なぜか / これからどうか」 のどれかを入れる

【参考: フーガ + 缶詰 の実 voice (literal copy 禁止、 文体・思考だけ学び、 今日の事実で書く)】

▼ 考察モード (試合前 / 試合後 / 日中) = 意見 + 理由 + 戦術の読み
例A (運用考察):
竹丸の抹消は111球完投の疲労考慮らしいし、ルーキーだしここは良い運用だわ。替わりはウィットリー嵌めるのかな。

例B (打順論):
個人的にはダルベックは2番でいい気がする。初回に何としても点取りたいし、この打者に打席数を多くあげたいんだよな。

例C (辛口 + 理由 + 着地):
昨日の打線は流石に物足りなかった。ただ瑛斗も大勢も2連投明けで、今日は先発が長いイニング投げ切るしかなかったわけで。竹丸は6回以降も球が落ちないか、そこ見たい。

例D (短い判断、 これも OK):
浦田は当たりっぽいな。守備の一歩目もいいし、このまま一軍で見たい。

▼ ライブモード (試合中のみ) = 缶詰の即時反応。 連呼・絶叫 OK、 ただし一言の状況・読みは入れる
例E:
泉口！！！最後に美味しいとこ持ってったなあ。これはデカい。

例F:
戸郷ギア入ったわ。3回までは球高かったけど4回からは別人。ここ踏ん張れば流れ来る。

時系列制約 (重要):
- 記事 title+summary / DB fact line の日付を確認。 古い文脈 (1 週間以上前 / 復帰前提 / 開幕直後) では
  「ついに」「これから」「もうすぐ」「いよいよ」 等の未来形・直近形を使わない
- 古い source しか無い場合は、 一般的な傾向 / 過去の経緯 として淡々と書く
- 季節 / 開幕 / 復帰 等の文脈は source 日付と現在 ({today_jst}) の差を踏まえる
- DB fact line (今日試合 / player log / 連勝記録) は verified、 そのまま事実として使ってよい
- 試合進行中 (DB fact が今日試合 / 進行中スコア を含む) なら完了形 (「勝った」「連勝確定」) で言わない

時間帯トーン ({hour_jst} 時 JST):
{time_tone_hint}

出力形式: post 本文のみ。 説明や前置きは書かない。 例の literal copy 禁止、
voice の特徴だけ学んで今日の事実で書く。
"""

# 後方互換 alias: 既存 caller が _SYSTEM_PROMPT_FUUGA を参照しても動くように。
# 411 の persona 切替 helper は維持 (拡張余地)、 ただし新 prompt は 1 本に統合。
_SYSTEM_PROMPT_FUUGA = _SYSTEM_PROMPT_YOSHILOVER


# 後方互換 alias: kandume persona 指定でも新 unified prompt を返す。
# 旧 _SYSTEM_PROMPT_KANDUME 本文は #95 で削除、 unified _SYSTEM_PROMPT_YOSHILOVER に統合。
_SYSTEM_PROMPT_KANDUME = _SYSTEM_PROMPT_YOSHILOVER



def _build_system_prompt(now_jst_hour: int, today_jst: str, *, persona: str = "fuuga") -> str:
    """時間帯 hint を生成する。

    411 (2026-05-20): persona 引数で フーガ (長文分析) / 缶詰 (試合中実況) を切替。
    persona "fuuga" (default) = _SYSTEM_PROMPT_FUUGA、
    persona "kandume" = _SYSTEM_PROMPT_KANDUME。
    unknown persona は fuuga にフォールバック (silent fallback、 安全側)。

    重要: voice (few-shot 例の語彙 / リズム / 改行 / 感嘆詞) は persona ごとに
    固定。 hint は **content** (何を書くか) と **熱量の出し方** だけを時間帯に
    合わせて変える。
    """
    if 5 <= now_jst_hour < 11:
        hint = (
            "【朝 5-11 時 = 試合前の立ち上げ。 熱量は落とさない】\n"
            "- content: 前夜試合の振り返り / 今日の先発・スタメン予想 / 連勝連敗の流れの読み\n"
            "- 熱量: 朝でも普通に熱く書く。 「静かに」「softer」 にしない。 フーガ風の分析×巨人愛をそのまま出す\n"
            "- 前夜ネタは余韻ポエムにせず、 必ず読み (なぜ・これからどうか) を1つ入れる"
        )
    elif 11 <= now_jst_hour < 17:
        hint = (
            "【昼〜午後 11-17 時 = 試合前ピーク前。 ここからインプを取りに行く】\n"
            "- content: 今日の lineup / 先発投手の相性 / 起用・運用の読み / 直近データの傾向\n"
            "- 熱量: 試合前の期待を前面に。 ただし試合中じゃないので「勝った！」 系の完了形・祝杯は使わない\n"
            "- フーガ風の分析×巨人愛で、 今日の試合の見どころ・不安を読み解く"
        )
    elif 17 <= now_jst_hour < 22:
        hint = (
            "【試合直前〜試合中 17-22 時 = 缶詰ライブモード】\n"
            "- 試合中なら ▼ライブモード: 即時反応・連呼・絶叫 OK (例E/F)。 ただし一言の状況・読みは入れる\n"
            "- 試合前なら ▼考察モード: 先発 / スタメン / 今日の読みを理由付きで (例A-D)\n"
            "- 試合終了確定前なので「勝った」「連勝」 を完了形で言わない。 まだ continued"
        )
    else:
        hint = (
            "【試合後・深夜 22 時以降〜朝 5 時 = 考察モード】\n"
            "- ▼考察モード (例A-D): 試合の振り返り / 起用や流れの読み / 次への期待。 辛口も擁護も理由とセットで (採点・説教にしない)\n"
            "- DB fact line の今日 stat (6回1失点 8K 等) を堂々と使う。 verified 数字\n"
            "- **NG: 「完勝！噛み締める」式の感嘆ポエムにしない**。 必ず判断・理由を入れる"
        )
    template = _SYSTEM_PROMPT_KANDUME if persona == "kandume" else _SYSTEM_PROMPT_FUUGA
    return template.format(
        hour_jst=now_jst_hour,
        today_jst=today_jst,
        time_tone_hint=hint,
    )


def is_giants_game_day(now_jst, db_path: str) -> bool:
    """411 (2026-05-20): 今日 (now_jst の JST 日付) に巨人試合があるか.

    insight.db の `games` テーブルを `SELECT 1 FROM games WHERE game_date = ?` で
    判定。 row が 1 つ以上あれば True、 0 なら False。
    db_path 不正 / sqlite open 失敗 / SELECT 例外時は False (silent fallback、
    安全側 = 試合無いと見なし 缶詰 persona を発火させない)。
    """
    if not db_path:
        return False
    try:
        today = now_jst.strftime("%Y-%m-%d")
    except Exception:
        return False
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            cur = con.cursor()
            cur.execute(
                "SELECT 1 FROM games WHERE game_date = ? LIMIT 1",
                (today,),
            )
            row = cur.fetchone()
        finally:
            con.close()
        return row is not None
    except Exception:
        return False


def select_branding_persona(now_jst, is_game_day: bool) -> str:
    """411 (2026-05-20): persona 自動選択.

    user 仕様 lock:
    - 試合日 + 18-21 時 JST = 缶詰 (試合中実況 voice)
    - それ以外 (非試合日 / 試合日でも時間外) = フーガ (長文分析 voice)

    Returns 'kandume' or 'fuuga'.
    """
    try:
        hour = int(now_jst.hour)
    except Exception:
        return "fuuga"
    if is_game_day and 18 <= hour <= 21:
        return "kandume"
    return "fuuga"


# 414 axis A (2026-05-20): user spec lock 5 型分離.
# 観戦中 (試合中) は 感情系 + 次の展開系 が強い。
_POST_TYPES = ("flash", "emotion", "data", "next", "positive")

_POST_TYPE_GUIDANCE: dict[str, str] = {
    "flash": (
        "【今回の型: 速報系】\n"
        "- 事実中心: 選手名 / 回 / スコア を厳格に書く。 DB fact / Tavily literal に\n"
        "  ないものは書かない\n"
        "- 短文 OK、 観点 1-2 個に絞ってよい (長文無理に書かない)\n"
        "- 感想は控えめ、 事実が主"
    ),
    "emotion": (
        "【今回の型: 感情系】\n"
        "- 巨人ファンの気持ち代弁 (噛み締める / 嬉しい / 悔しい / ホッとした 等)\n"
        "- 数字は 1 個だけでも、 そこから派生する感情を厚く\n"
        "- 「同じ条件で並べると」 系の分析調は控え、 ファンの本音 voice"
    ),
    "data": (
        "【今回の型: データ系】\n"
        "- 過去成績 / 直近傾向 を踏まえる (ただし順位は絶対書かない = axis C1)\n"
        "- 「最近のリズム」「打順上位の働き」 等の傾向観察として書く\n"
        "- 数字は DB fact 由来のみ、 generalize OK"
    ),
    "next": (
        "【今回の型: 次の展開系】\n"
        "- 試合進行中前提 (まだ続行中、 完了形で書かない)\n"
        "- 采配 / 継投 / 追加点 / 守備固め / 代打 / 抑え への期待・想像\n"
        "- 「ここで」「次の回」「あと◯回」 の即時性、 流動的な書き方"
    ),
    "positive": (
        "【今回の型: ポジティブ系】\n"
        "- 若手 / 二軍 / 復帰選手 / 育成 を拾う (やってる感、 期待感)\n"
        "- 「いいな」「楽しみ」「これからの選手」 voice\n"
        "- 強批判 / 雑批判 NG (axis D 厳守)"
    ),
}


def select_post_type(
    now_jst,
    is_game_day: bool,
    has_db_fact: bool = False,
    has_tavily_results: bool = False,
) -> str:
    """414 axis A: 型自動選択.

    user 仕様 lock (2026-05-20 chat):
    - 観戦中 (試合日 18-21時) = next (次の展開系) 優先、 fallback emotion
    - 試合後 (試合日 22-23時) = emotion (試合の余韻)
    - 試合日 朝 (5-11時) = data (前日試合の余韻 + 今日試合への準備)
    - 試合日 昼 (11-17時) = data + emotion (試合前 buildup)
    - 非試合日 朝 = data (前日試合 stat / 直近傾向)
    - 非試合日 昼 = positive (若手 / 二軍 narrative)
    - 非試合日 夜 = emotion (off-day fan voice)
    - flash は test 用 / caller override 用、 自動選択は使わない (= 事実中心は型に
      しなくても axis C で hallucination 防止が効くため)

    Returns one of: 'next' / 'emotion' / 'data' / 'positive' / 'flash'
    """
    try:
        hour = int(now_jst.hour)
    except Exception:
        return "emotion"
    if is_game_day:
        if 18 <= hour <= 21:
            return "next"
        if 22 <= hour <= 23 or hour < 5:
            return "emotion"
        if 5 <= hour < 11:
            return "data"
        if 11 <= hour < 17:
            return "data" if has_db_fact else "emotion"
        # hour 17: 試合直前
        return "next"
    # 非試合日
    if 5 <= hour < 11:
        return "data"
    if 11 <= hour < 17:
        return "positive"
    return "emotion"


# 411 (2026-05-20): user 仕様 = 公式 / NPB / 球団 / 主要スポーツ紙を優先。
# include_domains で Tavily 側の取得を whitelist 内に絞る。 paid credit / cost は
# domain 数によらず 1 query = 1 credit (free tier 1000/月 内で運用)。
_TAVILY_INCLUDE_DOMAINS = (
    # 公式 / 球団
    "giants.jp",
    "npb.or.jp",
    # 主要スポーツ紙
    "hochi.news",
    "sponichi.co.jp",
    "nikkansports.com",
    "sanspo.com",
    "daily.co.jp",
    "chunichi.co.jp",
    # ポータル (既存)
    "sports.yahoo.co.jp",
)


def _tavily_search(
    query: str,
    api_key: str,
    *,
    max_results: int = 3,
    timeout_seconds: int = 30,
    same_day_only: bool = False,
) -> list[dict]:
    """Tavily REST API 検索 (日本 sport 記事のみ)。

    Yahoo Japan sport + 報知 に絞って巨人関連の新鮮な記事だけ拾う。
    全 web 検索だと SF Giants (MLB) / NBA / 関係ない海外 sport が混入
    して Gemini Flash Lite が hallucinate するため domain 限定 (2026-05-20 fix)。

    days=2 で前日+当日のみ。 same_day_only=True にすれば JST 当日 only
    (test 用)、 default は False (朝 fire で前夜試合の記事を拾えるよう
    に)。 0 件返却なら caller は no context として silent skip する。
    """
    if not query or not api_key:
        return []
    try:
        import requests
        # 411 (2026-05-20): user 仕様 = Tavily の `answer` は使わない、
        # `results[].url` / `title` / `content` / `published_date` だけを見る。
        # include_answer=False を明示 (default も False だが spec lock として明示)。
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
                "topic": "news",
                "days": 2,
                "include_domains": list(_TAVILY_INCLUDE_DOMAINS),
                "include_answer": False,
            },
            timeout=timeout_seconds,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []
    results = data.get("results")
    if not isinstance(results, list):
        return []
    if not same_day_only:
        return results
    return _filter_same_day_jst(results)


def _filter_same_day_jst(results: list[dict]) -> list[dict]:
    """JST 当日 published のものだけ残す。

    published_date は Tavily news topic で RFC 1123 (例: "Tue, 19 May 2026
    13:30:00 GMT") で返ることが多いが、 形式不明 / parse 失敗時は除外する
    (silent fallback、 hallucination 抑制を優先)。
    """
    from datetime import datetime, timezone, timedelta
    from email.utils import parsedate_to_datetime
    jst = timezone(timedelta(hours=9))
    today_jst = datetime.now(jst).date()
    kept: list[dict] = []
    for r in results:
        raw = r.get("published_date") or ""
        if not raw:
            continue
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt.astimezone(jst).date() == today_jst:
                kept.append(r)
        except (TypeError, ValueError):
            continue
    return kept


def _matched_branding_forbidden_pattern(text: str, verified_text: str = "") -> Optional[str]:
    """safety_check で fail させる forbidden pattern 文字列を返す (drop log 用)。 hit 無しは None。

    順位 / rate は verifiable 扱い: source (verified_text) に matched literal が
    含まれない時だけ fail とする (2026-06-24 user 決定)。 verified_text 既定 "" =
    照合不能 → 従来どおり全 drop (後方互換、 source 不明な caller は strict)。
    """
    for pattern in _GEMINI_BRANDING_FORBIDDEN_PATTERNS:
        if pattern.search(text):
            return pattern.pattern
    safe_verified = verified_text or ""
    for pattern in _GEMINI_BRANDING_VERIFIABLE_NUMBER_PATTERNS:
        match = pattern.search(text)
        if match and match.group(0) not in safe_verified:
            return pattern.pattern
    return None


def _gemini_branding_safety_check(text: str, verified_text: str = "") -> bool:
    """spec 382 hard rule gate for Gemini Flash Lite branding output.

    True = safe (pass). False = violation (caller drops the candidate)。
    414 axis D: 炎上 / ズレ防止 patterns も同等 hard rule として評価。
    verified_text: 順位 / rate 数字の source 照合用 (記事 / DB / 検索結果)。 既定 "" は
    strict (順位 / rate を全 drop、 後方互換)。
    """
    if not text or not text.strip():
        return False
    if len(text) > X_CHAR_LIMIT:
        return False
    if _matched_branding_forbidden_pattern(text, verified_text) is not None:
        return False
    # 414 axis D: 炎上系も同 fail 扱い
    for pattern in _GEMINI_BRANDING_INFLAMMATORY_PATTERNS:
        if pattern.search(text):
            return False
    if not _is_safe_post_text(text):
        return False
    return True


# 門番 (品質ゲート): flash-lite は prompt で禁止しても優等生締め / ポエム / スカスカを
# 漏らすため、 生成後に deterministic に弾く。 ライブモード (試合中の缶詰・即時反応) は
# 短文 + 感嘆が正なので length / 感嘆 check を緩和する (live=True)。
# 優等生締め: 「〜してほしいね/な」「頼もしいよな」「期待したい」「応援したい」 等の定型締め。
_VOICE_YUTOUSEI_ENDING = _re.compile(
    r"(してほしい(ね|な|です|と思う)?|してほしい|頼もしい(よ|ね|な|よな|限り)?|"
    r"期待(したい|大|してる|大きい)|楽しみ(だ|です|だね|にしてる)?|応援(したい|してる|してる)|"
    r"見守りたい|活躍(を)?(期待|祈)|頑張って(ほしい)?(ね|な)?|これからも.{0,8}(注目|応援|期待)|"
    # 2026-06-04 夜 観測追加: 受け身の願望締め (候補2「待ちたいね」/ 候補3「期待して待ってるよ」)。
    r"待ちたい(ね|な|よ)?|(期待して)?待ってる(ね|よ|な)?)"
    r"[。!！？\?…\s]*$"
)
# ポエム: 抽象的な美文・情緒語 (中身の無いエモ)。
_VOICE_POEM_MARKERS = _re.compile(
    r"(胸が熱く|心が震え|魂|涙が|輝き|刻まれ|奇跡|物語が(始|動)|希望を(見|感じ|抱)|"
    r"未来へ|夢を(乗せ|託)|光が|彼方|時は来た)"
)
# hopium: 中身 (理由・戦術・読み) の無い無難な持ち上げ。 flash-lite が不振選手を
# 数字を隠して全肯定する時にこの定型へ逃げる (2026-06-04 朝メール: 丸.074 / 中山.125 を
# 「別格だよな」「化けると思う」「信じてるよ」)。 文中どこでも 1 個でも出たら門番で弾き、
# retry で具体的な読み (なぜ / これからどうか) を強制する。 末尾アンカーでは
# 「信じてるけど、 みんなはどう見てる?」 型が許可問いかけにすり抜けるため非アンカー。
_VOICE_HOPIUM_MARKERS = _re.compile(
    r"(信じてる|頼りにしてる|別格(だ|だよな|だな|だわ)?|持ってる選手|"
    r"化けると思|一気に化け|噛み合え.{0,8}化け|"
    r"経験値.{0,5}が(全て|すべて)|底力.{0,5}が(全て|すべて)|"
    r"新しい風が吹く|本物だ(よ|な|よな|わ)|持ってるな)"
)
# 抽象逃げ: 「何を見てそう言うか」が無いまま、評価っぽい語で締める型。
# 2026-06-28: 末尾アンカー化。 非アンカーだと本物のフーガ分析が途中でこれらの語を
# 使っただけで誤却下されていた (user: ポエムは却下したいが Gemini フーガ風は通したい)。
# 「締めが抽象語」の時だけ弾く = docstring の本来意図 (評価っぽい語で締める型) に合わせる。
_VOICE_ABSTRACT_MARKERS = _re.compile(
    r"(存在感|任せられる|任せたい|安定感|今後に注目|注目したい|期待が高まる|"
    r"大きな存在|大きい存在|存在は大きい|チームに(とって)?大きい|"
    r"ポイントになる|鍵になる|カギになる|流れを変える存在|大事な存在|重要な存在)"
    r"[^。!！？\?…]{0,12}[。!！？\?…\s]*$"
)


# 締めローテ: flash-lite は放っておくと全候補が「〜してくれ」「〜だぞ」 で終わって
# 単調になる。 seed (選手名) のハッシュで締めの型を振り分け、 候補ごとに終わり方を散らす。
_ENDING_STYLES = (
    "締めは言い切りで終える (辛口や事実をそのまま。 例:「〜なんよな」「〜だわ」)。 願望で締めない",
    "締めは自分の予想・見立てで終える (例:「〜だと思う」「〜になる気がする」「秋には〜してるはず」)",
    "締めはファンへの問いかけで終える (例:「〜どう見てる?」「〜じゃない?」)",
    "締めは正念場の本音で終える (例:「ここからが勝負だな」「ここ踏ん張りどころ」)。 煽り・命令にしない",
    "締めは一ファンの願望で終える、 ただし優等生・命令にしない (例:「早よ〜見たい」「〜が楽しみすぎる」)",
)


def _ending_style_hint(seed: str) -> str:
    """seed (選手名等) から締めの型を 1 つ deterministic に選ぶ (候補間で締めを散らす)。"""
    h = _hashlib.sha1((seed or "x").encode("utf-8")).hexdigest()
    return _ENDING_STYLES[int(h, 16) % len(_ENDING_STYLES)]


def _voice_quality_ok(text: str, *, live: bool = False, short_ok: bool = False) -> bool:
    """門番: ヨシラバーボイスとして出してよいか (True=OK)。

    優等生締め / ポエム は常に弾く。 考察モードでは加えて、 スカスカ (短すぎ) と
    感嘆符の乱用も弾く。 ライブモード (live=True、 試合中の缶詰) は短文 + 連呼絶叫が
    正なので length / 感嘆 check を skip する。
    ``short_ok`` (2026-07-07 user「ファンリプ長くない?」): empathy リプは 20〜55字の
    短文が正なので、 50字未満スカスカ check だけ skip する (感嘆乱用 check は維持)。
    """
    t = (text or "").strip()
    if not t:
        return False
    if _VOICE_YUTOUSEI_ENDING.search(t):
        return False
    if _VOICE_POEM_MARKERS.search(t):
        return False
    if _VOICE_HOPIUM_MARKERS.search(t):  # 中身の無い無難な持ち上げ (信じてる/別格/化ける) は常に弾く
        return False
    if _VOICE_ABSTRACT_MARKERS.search(t):
        return False
    if not live:
        if len(t) < 50 and not short_ok:  # スカスカ・フィラー (矢野「これは見ておきたい一件」型)
            return False
        if t.count("！") + t.count("!") >= 3:  # 感嘆だけのポエム
            return False
    return True


def _matched_inflammatory_pattern(text: str) -> Optional[str]:
    """414 axis D + C7 log: text が炎上 pattern に hit した場合、 hit した
    pattern 文字列を返す (drop log に reason として記録するため)。 hit なしは None。
    """
    for pattern in _GEMINI_BRANDING_INFLAMMATORY_PATTERNS:
        if pattern.search(text):
            return pattern.pattern
    return None


# 414 axis 2 (2026-05-20): 数値 whitelist helper.
# verified_text (db_fact + Tavily content の連結) に literal 出現しない数字を
# unverified としてリストする。 1 件でもあれば caller は candidate を drop。
# 「verified set 内なら hallucination ではない」 という保守的判定 (false-negative
# 寄り = 多めに drop)。
_NUMERIC_TOKEN_RE = _re.compile(r"\d+(?:\.\d+)?")


def _extract_unverified_numbers(text: str, verified_text: str) -> list[str]:
    """text 内の数字 token のうち verified_text に literal 出現しないものを返す.

    生成 text から `\\d+(?:\\.\\d+)?` で数字 (整数 + 小数) を抽出。 各数字が
    verified_text の substring として現れない場合 unverified。 verified_text には
    db_fact_line と Tavily 検索結果の content / title を連結したものを caller が
    渡す想定 (414 axis 2 hallucination 防止)。
    """
    if not text:
        return []
    safe_verified = verified_text or ""
    # 2026-07-06: 記事タイトルの全角数字 (２０回１／３) を LLM が半角 (20回1/3) で
    # 書き戻すと literal 比較で誤棄却される (record 可読化 dry-run 実測で全滅)。
    # NFKC 正規化した verified も照合対象にする (捏造数字は正規化後も存在しない)。
    import unicodedata as _ud
    nfkc_verified = _ud.normalize("NFKC", safe_verified)
    found: list[str] = []
    for match in _NUMERIC_TOKEN_RE.finditer(text):
        token = match.group(0)
        if token not in safe_verified and token not in nfkc_verified:
            found.append(token)
    return found


# 414 axis 6 (2026-05-20): published_date 7日超過 entry を context から drop.
# 現状 _format_tavily_context は全 entry を Gemini Flash Lite に渡しており、 古い snippet の
# 「ついに」「これから」 を Gemini Flash Lite が現在化する事故が起きうる。 朝 fire で前日試合
# 記事は欲しい (1 日前は残す) ので default 7 日 (= 1 週間) に。
def _recent_published_within_days(results: list[dict], days: int = 7) -> list[dict]:
    """published_date が直近 days 日以内の entry のみを返す.

    parse 失敗 / date 不明の entry は **残す** (false-negative 寄り、 caller の
    Gemini Flash Lite context に注入される、 prompt 制約で 「日付不明は淡々と書く」 と既に指示)。
    days <= 0 なら same-day-only モード (414 axis 9 と同等)。
    """
    if not results:
        return []
    from datetime import datetime, timezone, timedelta
    from email.utils import parsedate_to_datetime
    jst = timezone(timedelta(hours=9))
    today_jst = datetime.now(jst).date()
    cutoff = today_jst - timedelta(days=max(0, days))
    kept: list[dict] = []
    for r in results:
        raw = r.get("published_date") or ""
        if not raw:
            # 日付不明: 残す (false-negative 寄り)
            kept.append(r)
            continue
        try:
            dt = parsedate_to_datetime(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            entry_date = dt.astimezone(jst).date()
        except (TypeError, ValueError):
            # parse 失敗: 残す
            kept.append(r)
            continue
        if days <= 0:
            if entry_date == today_jst:
                kept.append(r)
        elif entry_date >= cutoff:
            kept.append(r)
    return kept


def build_db_fact_line(
    player_canonical: str,
    db_path: str,
    *,
    target_date: Optional[str] = None,
    streak_window: int = 5,
) -> str:
    """``insight.db`` から today の試合 / player stat / 直近連勝 を 1 fact line に。

    Read-only SELECT only。 DB に該当 record が無ければ各 line を skip、
    全件無ければ空 string を返す (Gemini Flash Lite 側で「DB fact 注入: なし」 扱い)。

    formats (改行区切り、 全部 facts のみ、 narrative なし):
        - 今日(YYYY-MM-DD) 巨人 vs OPP: GS-OS WIN/LOSS/DRAW
        - PLAYER 打撃: AB打数 H安打 HR本塁打 RBI打点 (today)
        - PLAYER 投球: IP回 R失点 K奪三振 (result_mark) (today)
        - 直近N試合: ○●○●○ (W3-L2)
    """
    if not player_canonical or not db_path:
        return ""
    from datetime import datetime, timezone, timedelta
    jst = timezone(timedelta(hours=9))
    today = target_date or datetime.now(jst).strftime("%Y-%m-%d")
    lines: list[str] = []
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            cur = con.cursor()

            cur.execute(
                "SELECT game_id, opponent, giants_score, opp_score, result "
                "FROM games WHERE game_date = ? AND giants_score IS NOT NULL "
                "ORDER BY ingested_at DESC LIMIT 1",
                (today,),
            )
            game_row = cur.fetchone()
            today_game_id: Optional[str] = None
            if game_row:
                today_game_id, opp, gs, op_s, res = game_row
                res_jp = {
                    "win": "勝利",
                    "loss": "敗戦",
                    "draw": "引分",
                }.get((res or "").lower(), "")
                score = (
                    f"{gs}-{op_s}"
                    if gs is not None and op_s is not None
                    else ""
                )
                game_parts = [f"今日({today}) 巨人 vs {opp}"]
                if score:
                    game_parts.append(score)
                if res_jp:
                    game_parts.append(f"({res_jp})")
                lines.append("- " + " ".join(game_parts))

            if today_game_id:
                cur.execute(
                    "SELECT AB, H, R, RBI, SB FROM batting_logs "
                    "WHERE game_id = ? AND player_canonical = ? AND team_role = 'giants' "
                    "LIMIT 1",
                    (today_game_id, player_canonical),
                )
                bat = cur.fetchone()
                if bat:
                    ab, h, r, rbi, sb = bat
                    parts = []
                    if ab is not None and h is not None:
                        parts.append(f"{ab}打数{h}安打")
                    if rbi:
                        parts.append(f"{rbi}打点")
                    if r:
                        parts.append(f"{r}得点")
                    if sb:
                        parts.append(f"{sb}盗塁")
                    if parts:
                        lines.append(f"- {player_canonical} 打撃 (今日): " + " ".join(parts))

                cur.execute(
                    "SELECT IP, H_allowed, R, ER, K, BB, result_mark FROM pitching_logs "
                    "WHERE game_id = ? AND player_canonical = ? AND team_role = 'giants' "
                    "LIMIT 1",
                    (today_game_id, player_canonical),
                )
                pit = cur.fetchone()
                if pit:
                    ip, h_a, r, er, k, bb, mark = pit
                    parts = []
                    if ip is not None:
                        parts.append(f"{ip}回")
                    if er is not None:
                        parts.append(f"{er}失点")
                    elif r is not None:
                        parts.append(f"{r}失点")
                    if h_a is not None:
                        parts.append(f"被安打{h_a}")
                    if k:
                        parts.append(f"{k}K")
                    if bb:
                        parts.append(f"{bb}四球")
                    if mark:
                        parts.append(f"({mark})")
                    if parts:
                        lines.append(f"- {player_canonical} 投球 (今日): " + " ".join(parts))

            # 選手個人の今季集計 (2026-07-03): 当日出場の無い選手ではチーム
            # 直近5試合しか fact が無く、全リプが同じ「直近5試合」補足になる
            # ため、選手個人の season 数字を常に持たせる。防御率は IP 実数の
            # 単純 SUM が 1/3 回表記とずれるため出さない (整数のみ = 誤記なし)。
            # games JOIN + giants_score IS NOT NULL で「巨人の試合」に限定する:
            # logs には他球団同士の試合 (12球団成績用) も入っており、そこでは
            # team_role='giants' がホーム側に付くため、team_role だけでは
            # 同名の他球団選手成績が混ざる (同日点検 2026-07-03)。
            cur.execute(
                "SELECT COALESCE(SUM(b.AB),0), COALESCE(SUM(b.H),0), "
                "COALESCE(SUM(b.RBI),0), COUNT(DISTINCT b.game_id) "
                "FROM batting_logs b JOIN games g ON g.game_id = b.game_id "
                "WHERE b.player_canonical = ? AND b.team_role = 'giants' "
                "AND g.giants_score IS NOT NULL",
                (player_canonical,),
            )
            season_bat = cur.fetchone()
            cur.execute(
                "SELECT COUNT(*), "
                "SUM(CASE WHEN p.result_mark='○' THEN 1 ELSE 0 END), "
                "SUM(CASE WHEN p.result_mark='●' THEN 1 ELSE 0 END), "
                "COALESCE(SUM(p.K),0) "
                "FROM pitching_logs p JOIN games g ON g.game_id = p.game_id "
                "WHERE p.player_canonical = ? AND p.team_role = 'giants' "
                "AND g.giants_score IS NOT NULL",
                (player_canonical,),
            )
            season_pit = cur.fetchone()
            pit_games = int(season_pit[0] or 0) if season_pit else 0
            # 打撃行は 10 打数以上のみ。さらに投手 (登板あり) は打席が少なく
            # 「打率.000」がリプの補足核に選ばれる事故のもとなので、野手級の
            # 打数 (30) が無ければ出さない。
            if season_bat and int(season_bat[0] or 0) >= (30 if pit_games > 0 else 10):
                ab, h, rbi, g = (int(v or 0) for v in season_bat)
                avg = f"{h / ab:.3f}".lstrip("0")
                lines.append(
                    f"- {player_canonical} 今季打撃: 打率{avg}"
                    f" ({ab}打数{h}安打 {rbi}打点)"
                )
            if pit_games > 0:
                g, w, l, k = (int(v or 0) for v in season_pit)
                rec = f" {w}勝{l}敗" if (w or l) else ""
                lines.append(
                    f"- {player_canonical} 今季投球: {g}登板{rec} {k}奪三振"
                )

            if streak_window > 0:
                # 直近 loss が出るまで遡って「連勝中」 / 「連敗中」 / 「混在」
                # を集計する。 引き分けは streak を切らない (NPB 慣習)。
                cur.execute(
                    "SELECT game_date, result FROM games "
                    "WHERE game_date <= ? AND result IN ('win', 'loss', 'draw') "
                    "AND giants_score IS NOT NULL "
                    "ORDER BY game_date DESC LIMIT 40",
                    (today,),
                )
                recent = cur.fetchall()
                if recent:
                    # 現在 streak: 最新試合 (recent[0]) の result から start。
                    # win 連続なら 連勝、 loss 連続なら 連敗、 引き分けが先頭
                    # なら 「直近 △ 後の状況」 で扱う。
                    latest_result = (recent[0][1] or "").lower()
                    current_streak_wins = 0
                    current_streak_draws = 0
                    current_streak_losses = 0
                    current_mode: Optional[str] = None
                    for _, r in recent:
                        rl = (r or "").lower()
                        if current_mode is None:
                            if rl == "draw":
                                current_streak_draws += 1
                                continue
                            current_mode = rl
                        if current_mode == "win":
                            if rl == "win":
                                current_streak_wins += 1
                            elif rl == "draw":
                                current_streak_draws += 1
                            else:
                                break
                        elif current_mode == "loss":
                            if rl == "loss":
                                current_streak_losses += 1
                            elif rl == "draw":
                                current_streak_draws += 1
                            else:
                                break
                    streak_phrase = ""
                    # 2026-07-03 user「1連勝って言葉変でしょ」: 連勝/連敗は 2 以上のみ。
                    # 1 の時は「前の試合は勝ち/負け」と書く。
                    if current_mode == "win" and current_streak_wins >= 2:
                        streak_phrase = f"現在 {current_streak_wins}連勝中"
                        if current_streak_draws > 0:
                            streak_phrase += f" (間に△{current_streak_draws})"
                    elif current_mode == "win" and current_streak_wins == 1:
                        streak_phrase = "前の試合は勝ち"
                    elif current_mode == "loss" and current_streak_losses >= 2:
                        streak_phrase = f"現在 {current_streak_losses}連敗中"
                        if current_streak_draws > 0:
                            streak_phrase += f" (間に△{current_streak_draws})"
                    elif current_mode == "loss" and current_streak_losses == 1:
                        streak_phrase = "前の試合は負け"
                    elif current_mode is None and current_streak_draws > 0:
                        streak_phrase = f"直近{current_streak_draws}試合 引き分け続き"
                    # 2026-07-03 user 指摘: 主語ラベルの無い「直近5試合」を LLM が
                    # ファーム/選手個人の成績として誤帰属した実事故があるため、
                    # チーム行は「巨人(一軍)チーム」を明記し、勝敗数も添える
                    # (●○ marks の数え間違い捏造を防ぐ)。
                    if streak_phrase:
                        lines.append(f"- 巨人(一軍)チーム: {streak_phrase}")
                    # 直近 streak_window 試合の marks (補助情報)
                    short = recent[: max(streak_window, 5)]
                    marks_short = []
                    for _, r in short:
                        rl = (r or "").lower()
                        if rl == "win":
                            marks_short.append("○")
                        elif rl == "loss":
                            marks_short.append("●")
                        else:
                            marks_short.append("△")
                    if marks_short:
                        wins = marks_short.count("○")
                        losses = marks_short.count("●")
                        draws = marks_short.count("△")
                        record = f"{wins}勝{losses}敗" + (f"{draws}分" if draws else "")
                        lines.append(
                            f"- 巨人(一軍)チーム 直近{len(marks_short)}試合: "
                            + "".join(marks_short)
                            + f" ({record})"
                        )
        finally:
            con.close()
    except Exception:
        return ""
    return "\n".join(lines)


def build_team_roundup_fact_line(
    db_path: str,
    *,
    target_date: Optional[str] = None,
    top_batter_h_threshold: int = 2,
    top_pitcher_ip_threshold: float = 1.0,
) -> str:
    """勝利後 roundup 用に、 今日試合に絡んだ複数 player の stat をまとめる。

    今日試合が win の時だけ返す。 それ以外 (loss / draw / unknown / no
    game) は空 string。 caller は空なら single-player mode に fallback。

    形式:
        - 今日(YYYY-MM-DD) 巨人 vs OPP: GS-OS 勝利
        - PLAYER1: X打数Y安打 ZHR
        - PLAYER2: X打数Y安打 Z打点
        - PITCHER1: X.Y回 Z失点 K奪三振 (○)
        - PITCHER2: X.Y回 Z失点 K奪三振 (H)
        - 直近5試合: ○●○●○ (X勝Y敗)
    """
    if not db_path:
        return ""
    from datetime import datetime, timezone, timedelta
    jst = timezone(timedelta(hours=9))
    today = target_date or datetime.now(jst).strftime("%Y-%m-%d")
    lines: list[str] = []
    try:
        import sqlite3
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            cur = con.cursor()
            cur.execute(
                "SELECT game_id, opponent, giants_score, opp_score, result "
                "FROM games WHERE game_date = ? AND giants_score IS NOT NULL "
                "ORDER BY ingested_at DESC LIMIT 1",
                (today,),
            )
            row = cur.fetchone()
            if not row:
                return ""
            game_id, opp, gs, op_s, res = row
            if (res or "").lower() != "win":
                return ""
            score = f"{gs}-{op_s}" if gs is not None and op_s is not None else ""
            parts = [f"今日({today}) 巨人 vs {opp}"]
            if score:
                parts.append(score)
            parts.append("勝利")
            lines.append("- " + " ".join(parts))

            cur.execute(
                "SELECT player_canonical, AB, H, RBI, R, SB FROM batting_logs "
                "WHERE game_id = ? AND team_role = 'giants' AND H >= ? "
                "ORDER BY H DESC, RBI DESC LIMIT 5",
                (game_id, top_batter_h_threshold),
            )
            for player, ab, h, rbi, r, sb in cur.fetchall():
                if not player:
                    continue
                bat_parts = []
                if ab is not None and h is not None:
                    bat_parts.append(f"{ab}打数{h}安打")
                if rbi:
                    bat_parts.append(f"{rbi}打点")
                if r:
                    bat_parts.append(f"{r}得点")
                if sb:
                    bat_parts.append(f"{sb}盗塁")
                if bat_parts:
                    lines.append(f"- {player} 打撃: " + " ".join(bat_parts))

            cur.execute(
                "SELECT player_canonical, IP, ER, R, K, BB, H_allowed, result_mark "
                "FROM pitching_logs "
                "WHERE game_id = ? AND team_role = 'giants' AND IP >= ? "
                "ORDER BY appearance_order LIMIT 5",
                (game_id, top_pitcher_ip_threshold),
            )
            for player, ip, er, r, k, bb, h_a, mark in cur.fetchall():
                if not player:
                    continue
                pit_parts = []
                if ip is not None:
                    pit_parts.append(f"{ip}回")
                if er is not None:
                    pit_parts.append(f"{er}失点")
                elif r is not None:
                    pit_parts.append(f"{r}失点")
                if k:
                    pit_parts.append(f"{k}K")
                if bb:
                    pit_parts.append(f"{bb}四球")
                if h_a is not None:
                    pit_parts.append(f"被安打{h_a}")
                if mark:
                    pit_parts.append(f"({mark})")
                if pit_parts:
                    lines.append(f"- {player} 投球: " + " ".join(pit_parts))

            cur.execute(
                "SELECT result FROM games "
                "WHERE game_date <= ? AND result IN ('win', 'loss', 'draw') "
                "AND giants_score IS NOT NULL "
                "ORDER BY game_date DESC LIMIT 40",
                (today,),
            )
            recent = cur.fetchall()
            if recent:
                latest_result = (recent[0][0] or "").lower()
                wins_in_streak = 0
                draws_in_streak = 0
                losses_in_streak = 0
                current_mode: Optional[str] = None
                for (rl,) in recent:
                    rl_lower = (rl or "").lower()
                    if current_mode is None:
                        if rl_lower == "draw":
                            draws_in_streak += 1
                            continue
                        current_mode = rl_lower
                    if current_mode == "win":
                        if rl_lower == "win":
                            wins_in_streak += 1
                        elif rl_lower == "draw":
                            draws_in_streak += 1
                        else:
                            break
                    elif current_mode == "loss":
                        if rl_lower == "loss":
                            losses_in_streak += 1
                        elif rl_lower == "draw":
                            draws_in_streak += 1
                        else:
                            break
                if current_mode == "win" and wins_in_streak > 0:
                    sp = f"現在 {wins_in_streak}連勝中"
                    if draws_in_streak > 0:
                        sp += f" (間に△{draws_in_streak})"
                    lines.append(f"- {sp}")
                elif current_mode == "loss" and losses_in_streak > 0:
                    sp = f"現在 {losses_in_streak}連敗中"
                    if draws_in_streak > 0:
                        sp += f" (間に△{draws_in_streak})"
                    lines.append(f"- {sp}")
        finally:
            con.close()
    except Exception:
        return ""
    # 試合 line + 直近 streak しか無い (player 0 件) なら roundup として
    # 意味薄いので空返却 (caller は single-player にフォールバック)
    if len(lines) < 3:
        return ""
    return "\n".join(lines)


def build_team_roundup_candidate(
    fact_line: str,
    *,
    gemini_api_key: str,
    tavily_api_key: str,
    timeout_seconds: int = 30,
    model_id: str = _X_POST_GEMINI_PRIMARY_MODEL,
    temperature: float = 0.7,
    logger: Optional[_logging.Logger] = None,
) -> Optional[Candidate]:
    """勝利後 roundup post を 1 件返す。

    複数 player を total 化したファン voice の post を生成する。 fact line
    は build_team_roundup_fact_line() で取得済み (空なら caller が roundup
    mode を発火しない)。 Tavily は使わず DB fact + プロンプト指示のみで
    安全に書く (Tavily snippet は player roundup の文脈に弱いため省略)。
    """
    log = logger or _logging.getLogger("x_post_branding_gen")
    if not fact_line.strip() or not gemini_api_key:
        log.info("team_roundup_skip reason=missing_input")
        return None
    from datetime import datetime, timezone, timedelta
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)
    system_prompt = _build_system_prompt(
        now_jst_hour=now_jst.hour,
        today_jst=now_jst.strftime("%Y-%m-%d"),
    )
    # Yahoo Japan + 報知から試合の news を context として注入
    # (個人選手と違って team / 連勝 / 試合 の話を拾う)
    news_results = _tavily_search(
        "巨人",
        tavily_api_key,
        max_results=5,
        timeout_seconds=timeout_seconds,
        same_day_only=False,
    )
    news_ctx = _format_tavily_context(news_results) if news_results else ""
    prompt_parts = [
        system_prompt,
        "",
        "今日の試合の DB 照合済み数字 (使ってよい数字):",
        fact_line,
        "",
    ]
    if news_ctx:
        prompt_parts.extend([
            "Yahoo Japan + 報知の最新巨人記事 (参考、 引用 / 媒体名 / URL は使わない):",
            news_ctx,
            "",
        ])
    prompt_parts.extend([
        "上記の DB facts + ニュース記事を参考に、 ファンらしく今日の試合を",
        "1 件の roundup post にまとめてください。 投手 / 打者 / 試合運び /",
        "結果 / 連勝 / news で話題になっている観点 を総括する。",
        "個別 stat を一行ずつ淡々と書かず、 ファン voice で短い感嘆 + 観点。",
        "選手名は DB か news に出てきた選手のみ。 出てない選手を勝手に書かない。",
    ])
    prompt = "\n".join(prompt_parts)
    try:
        from google import genai
        client = genai.Client(api_key=gemini_api_key)
        _llm_budget_guard("roundup")
        response = _x_post_generate_content(
            client,
            model=model_id,
            contents=prompt,
            config={"temperature": temperature},
        )
        text = (getattr(response, "text", None) or "").strip()
    except Exception as exc:  # noqa: BLE001 - silent skip per fault tolerance
        log.warning("team_roundup_skip reason=gemini_error err=%r", exc)
        return None
    text = _finalize_post_text(text)
    # 2026-06-24: 順位 / rate は source (DB fact + Tavily news) 照合できる時のみ許可。
    verified_text = " ".join(filter(None, [fact_line or "", news_ctx]))
    if not _gemini_branding_safety_check(text, verified_text):
        log.warning(
            "team_roundup_skip reason=safety_check_failed text_preview=%r",
            text[:60],
        )
        return None
    signature_hash = _hashlib.sha1(
        f"team_roundup|{today_str(now_jst)}|{text[:80]}".encode("utf-8")
    ).hexdigest()[:16]
    draft_lines = [
        "【根拠: Gemini team roundup + DB fact】",
        "対象: 今日の勝利試合 (複数選手 total)",
        f"configured_model: {model_id}",
        "",
        "【DB fact line】",
        fact_line,
    ]
    log.info("team_roundup_candidate_built text_len=%d", len(text))
    return Candidate(
        title="Gemini 試合後 roundup",
        metric=_GEMINI_BRANDING_METRIC,
        period_label="試合後 roundup",
        draft_text="\n".join(draft_lines),
        post_text=text,
        char_count=len(text),
        signature=f"team_roundup|{signature_hash}|False|None",
        focus_player="(roundup)",
        source_material_type="gemma_branding",
    )


def build_quote_rt_comment(
    post_text: str,
    player: str,
    phase_hint: str = "",
    *,
    gemini_api_key: str,
    model_id: str = _X_POST_GEMINI_PRIMARY_MODEL,
    temperature: float = 0.9,
    now=None,
    subject: str = "X投稿",
    db_fact: str = "",
    budget_site: str = "quote_rt",
    extra_voice_note: str = "",
    require_db_fact: bool = True,
    reply_style: str = "supplement",
    force_long: bool = False,
) -> str:
    """451: X バズ投稿への引用RTコメントを Gemini で生成。

    ``budget_site``: LLM budget の消費枠。 リプ lane は "reply" を渡すと
    予約枠 (set_llm_budget の reply_reserve) から消費できる。

    ``extra_voice_note`` (2026-07-02): 視点の上書き指示を 1 行 prompt に
    追加する。 例: MLB 大谷別枠は「巨人ファン視点ではなく純粋に野球ファン
    として」(user 決定)。 空なら従来 prompt と完全一致。

    ``reply_style`` (2026-07-06 user 決定「交流がメイン。数字だとダメ」):
    リプ lane (budget_site="reply") の型を切り替える。
    - "supplement" (default): 従来の補足リプ (verified data 数字を1つ足す)。
      媒体リプ (報知等) はこちらを維持。
    - "empathy": ファンアカ向け共感リプ。 共感・寄り添いが主で、 db_fact は
      あっても従 (軽く添えるだけ、 無くてもリプ成立)。 db_fact 必須 gate を
      通らない。 逆張り・訂正・講釈の禁止は共通で維持。

    voice は spec (doc/reference/x_post_mail_branding_spec.md L70/104/105) の
    **フーガ (長文分析・試合後振り返り) + 缶詰 (試合中LIVE・連呼) 合成** をそのまま使う。
    base = ``_build_system_prompt`` (統合 voice + 時間帯トーン hint)。 時間帯は ``now`` の hour
    から自動 (17-22=試合中熱量 ramp / 22時以降=祝杯全開 / 昼=落ち着いた期待)、 18-21時は缶詰寄り。
    ``phase_hint`` は後方互換で受けるが、 now があれば _build_system_prompt の時間帯 hint が正本。
    失敗 / safety NG / 捏造数字 / api_key 無し → 空文字 (caller は template fallback)。
    """
    log = _logging.getLogger("x_post_branding_gen")
    src = (post_text or "").strip()
    who = (player or "").strip()
    if not src or not gemini_api_key:
        return ""
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    _jst = _tz(_td(hours=9))
    now_jst = now.astimezone(_jst) if now is not None else _dt.now(_jst)
    hour = int(now_jst.hour)
    today = now_jst.strftime("%Y-%m-%d")
    # force_long (2026-07-09 試合後 recap): 缶詰ライブでなくフーガ風の長文分析に固定
    persona = "fuuga" if force_long else ("kandume" if 18 <= hour <= 21 else "fuuga")
    base_voice = _build_system_prompt(hour, today, persona=persona)
    is_live = (18 <= hour <= 21) and not force_long  # 試合中帯 = 缶詰ライブ (短文・即時反応OK)
    is_video_sns = ("動画" in subject) or ("SNS" in subject.upper())
    # 2026-07-03 user「リプの型が長い。感想リプではなく補足リプ。相手が喜んで
    # リツイートしてくれるもの」: リプ lane (budget_site="reply") は長文分析を
    # やめ、 元投稿に無い verified data を1つ足す短い補足に固定する。
    # 補足できる db_fact が無い時はリプ自体を成立させない (感想で埋めない)。
    # 例外: MLB リプ (NPB DB に数字が無い) は require_db_fact=False で呼び、
    # 元投稿内の具体場面を核にした短い補足に切り替える。
    is_reply = budget_site == "reply"
    # 2026-07-06 user「ファンリプは交流がメイン。数字だとダメ」: ファンアカ向けは
    # empathy 型 (共感主・数字従) に切り替え、 db_fact 必須 gate を外す。
    is_empathy = is_reply and reply_style == "empathy"
    if is_reply and not is_empathy and require_db_fact and not (db_fact or "").strip():
        log.info("quote_rt_comment_skip reason=reply_without_db_fact player=%s", who)
        return ""
    # 2026-07-07 user GO「リプ短くて悪影響ないならもうやっていいよ」: 試合中帯
    # (is_live、観戦ピーク) は実況テンポに合わせてさらに短く (10〜35字・体言止めOK)。
    _empathy_len_spec = (
        "10〜35字、 1文。 観戦中の実況テンポの短い反応でよい (体言止めOK)。 "
        if is_live
        else "20〜55字、 原則1文 (長くても2文)。 短いほど良い。 "
    )
    if is_empathy and (db_fact or "").strip():
        # 2026-07-07 user「野球系はリプしても反応薄い。知識を見せるより (寄り添う)」:
        # db_fact があっても既定は使わない側へ倒す (気持ち優先、数字は例外)。
        # 2026-07-07 user「ファンリプ長くない?相手にもっと寄り添って?気持ちよくさせて」:
        # 50〜90字→20〜55字・原則1文へ短縮 + 相手自身を持ち上げる一言を必須化。
        len_rule = (
            f"共感リプ用 (相手の返信欄に出る)。 {_empathy_len_spec}"
            "主役は共感: 相手の意見・見立てへの同意から入る "
            "(相手の言いたいことを自分の言葉で言い直して肯定する。 自分の話題・"
            "自分の視点から始めない。 相手の意見と違う自分の意見は書かない)。 "
            "そのうえで相手自身が気持ちよくなる一言を添える (見立ての鋭さ・写真・現地観戦・"
            "応援の熱、 どれか元投稿に実際にあるものを1つ具体的に褒める)。 "
            "知識を見せない: 基本は数字なしで成立させ、 相手の話の流れが数字を求めている時だけ "
            "verified data から1つ添えてよい (迷ったら入れない。 知識ではなく気持ちで返す)。 "
            "データ解説・分析講釈・豆知識の付け足しは禁止。 逆張り・訂正・辛口は禁止。 "
            "『〜すべき』『〜してほしい』『どう見ますか』で締めない。 "
            "URL / ハッシュタグ / 媒体名は禁止。 絵文字は多くても1個。 "
            "verified data と元投稿に無い数字・事実は足さない。"
        )
    elif is_empathy:
        # 2026-07-06 user「まだ仲良い人いないんで。今から仲良くなってきたい感じで
        # 相手の立場に立ち、相手が気持ちよくなるリプ」「ですます調にして」。
        # 2026-07-07 user「リプは相手の意見にもっとよりそって」: 同意 first を明示。
        # 2026-07-07 user「ファンリプ長くない?相手にもっと寄り添って?気持ちよくさせて」:
        # 50〜90字→20〜55字・原則1文へ短縮 + 相手自身を持ち上げる一言を必須化。
        len_rule = (
            f"共感リプ用 (相手の返信欄に出る)。 {_empathy_len_spec}"
            "必ずですます調 (丁寧語)。 まだ面識のない相手に初めて話しかける距離感で、 "
            "タメ口・呼び捨て・馴れ馴れしい省略は禁止。 "
            "相手の意見・見立てへの同意から入る (『たしかに』『本当に〜ですよね』"
            "のように、 相手の言いたいことを自分の言葉で言い直して肯定する。 "
            "自分の話題・自分の視点から始めない。 相手の意見と違う自分の意見は書かない)。 "
            "そのうえで相手自身が気持ちよくなる一言を添える (見立ての鋭さ・写真の良さ・"
            "現地観戦・応援の熱、 どれか元投稿に実際にあるものを1つ具体的に褒める。 "
            "相手が読んでうれしくなり、 返信したくなる返し。 これから仲良くなりたい人へのリプ)。 "
            "知識を見せない: 数字・データ解説・豆知識・過去記録・選手情報の付け足しは一切しない "
            "(相手より詳しく見せた瞬間に距離ができる。 知識ではなく気持ちで返す)。 "
            "逆張り・訂正・辛口・分析講釈は禁止。 "
            "『〜すべき』『〜してほしい』『どう見ますか』で締めない。 "
            "URL / ハッシュタグ / 媒体名は禁止。 絵文字は多くても1個。 "
            "元投稿に無い数字・事実は足さない。"
        )
    elif is_reply and (db_fact or "").strip():
        len_rule = (
            "補足リプ用 (相手の返信欄に出る)。 50〜90字、 1〜2文で短く。 "
            "感想・共感・称賛・分析講釈で埋めず、 元投稿に無い verified data の数字を1つ"
            "『ちなみに』的に補足する (投稿主と読者に役立ち、 投稿主が嬉しくなる返し)。 "
            "元投稿の内容を支える・広げる方向のみ。 逆張り・訂正・辛口は禁止。 "
            "『〜すべき』『〜してほしい』『どう見ますか』で締めない。 "
            "URL / ハッシュタグ / 媒体名は禁止。 絵文字は多くても1個。 "
            "verified data と元投稿に無い数字・事実は足さない。"
        )
    elif is_reply:
        len_rule = (
            "補足リプ用 (相手の返信欄に出る)。 50〜90字、 1〜2文で短く。 "
            "元投稿の動画・本文にある具体的な場面・事実を1つ拾い、 一言だけ添える "
            "(投稿主が嬉しくなる返し)。 長い感想・分析講釈・逆張り・訂正は禁止。 "
            "『〜すべき』『〜してほしい』『どう見ますか』で締めない。 "
            "URL / ハッシュタグ / 媒体名は禁止。 絵文字は多くても1個。 "
            "元投稿に無い数字・事実は足さない。"
        )
    elif is_video_sns:
        # 2026-07-06 user「(MLB引用RT🖼 大谷) これはポストの内容とあっていない」:
        # プレー場面の無い投稿 (誕生日/記念日/スタッツ画像等) にも「場面を具体名で」を
        # 強制すると LLM が場面風の人物評を創作して元ポストと乖離する。
        # 元投稿に実際にある内容だけを核にし、無い場面・人物評の創作を禁止する。
        len_rule = (
            "動画SNS用。 70〜120字、 1〜2文。 元投稿の本文・映像に実際にある内容だけを核に反応する。 "
            "プレー動画なら場面を1つ具体名で書く "
            "(打球音 / スイング / 一歩目 / 送球 / 球の押し込み / 表情 / ベンチ反応 / 場面価値のどれか)。 "
            "プレー場面が無い投稿 (誕生日・記念日・告知・スタッツ画像等) は、 その話題そのものに直接反応し、 "
            "元投稿に無い場面・エピソード・一般的な人物評を創作しない。 "
            "『好投』『ナイスゲーム』『楽しみ』『見ておきたい』『この流れ』だけで終わる抽象文は禁止。 "
            "元投稿の内容と繋がらない一般論だけの文も禁止。 "
            "URL / ハッシュタグ / 媒体名 / 動画の転載は禁止。 元ネタに無い数字・事実は足さない。"
        )
    elif force_long:
        # 2026-07-09 user「試合後は もっと長文で フーガ風、 改行入れて」: 試合後 recap。
        # 2026-07-10 user「少し長文にすると読了率が上がる」: 冒頭フック行を必須化
        # (「さらに表示」を開かせる = 滞在時間シグナル)、 文言を recap 以外
        # (トレンド反応等) でも使える形に汎用化。
        len_rule = (
            "フーガ風の長め分析。 250〜400字、 5〜7文。 "
            "★冒頭1行は続きを読みたくなるフックにする (タイムラインには冒頭しか"
            "見えない。 「さらに表示」を開かせる一言。 結論やオチは冒頭で言い切らない)。 "
            "★必ず改行を複数入れ、 2〜4行の塊に分けて読みやすくする (詰まった長文は読み飛ばされる)。 "
            "元ネタ (速報行・見出し) にある選手・人物を できるだけ多く名前で挙げる "
            "(本塁打・決勝打・好投・マルチ安打など)。 "
            "それぞれ何が効いたかをフーガ風に理由立てて読み解き、 最後は巨人愛で前を向いて締める。 "
            "名前は検索されるので元ネタの表記のまま複数入れる。 "
            "ポエム・優等生締めは禁止。 元ネタに無い数字・選手名は一切足さない。"
        )
    elif is_live:
        len_rule = (
            "即時反応 (2〜3文、 90〜150字)。 試合中の熱量でOK。 ただし一言の状況・読み (何が起きて何が効いたか) は入れる。 "
            "改行を1〜2個入れて読みやすく。 元ネタに無い数字・事実は足さない。"
        )
    else:
        len_rule = (
            "150〜220字、 3〜4文。 ★必ず適度に改行を入れ、 2〜3行の塊に分けて読みやすくする "
            "(X では詰まった長文は読み飛ばされる。 1行 = 短い1〜2文)。 "
            "データ/事実を1個 → フーガ風に理由立てて読み解く → 巨人愛で着地。 辛口は必要な時だけ控えめに。 "
            "ファンが『それな、 分かってる』 と頷く分析にする。 『〜してほしい』 は文中でも避ける。 "
            "ポエム禁止。 元ネタに無い数字・事実は足さない。 "
            + _ending_style_hint(who)
        )
    try:
        from google import genai
        client = genai.Client(api_key=gemini_api_key)
    except Exception as exc:  # noqa: BLE001 - silent skip, caller falls back to template
        log.warning("quote_rt_comment_skip reason=genai_import err=%r", exc)
        return ""
    # 門番 + リトライ: flash-lite が優等生締め/ポエム/スカスカを漏らすので最大
    # _X_POST_GEN_ATTEMPTS 回 (2026-07-08 無料枠対策で既定 1) 試し、
    # safety + unverified + voice_quality を全通過した最初の文を返す。
    # 470 (user 2026-06-29): 全通過が無くても、 最終便 (3回目) で致命的NG (捏造数字 / 炎上
    # pattern / URL・ハッシュタグ等 forbidden pattern / 文字数超過) が無ければ LLM 文を優先
    # 採用し template に逃げない。 残る voice (定型締め) と topic-hygiene (首脳陣 等) のみ許容。
    # 致命的NG を含む全滅時のみ "" を返す (caller は template fallback)。
    last_preview = ""
    relaxed_text = ""  # 最終便 fallback (voice / topic-hygiene だけ fail した LLM 文)
    # 470-②: 差別化テイク。 元投稿が触れていない verified data (db_fact) を1つだけ
    # 織り込ませる (媒体と違う気づき=反応を生む)。 db_fact の数字は verified 扱いで
    # unverified ゲートを通す。
    _fact = (db_fact or "").strip()
    diff_instr = ""
    if _fact and is_empathy:
        diff_instr = (
            f"【添えてよい verified data】{_fact}\n"
            "↑共感の流れに自然に繋がる時だけ、 この中から数字を1つ軽く添えてよい。 "
            "繋がらなければ使わない (共感だけで成立させる)。 これ以外の数字は足さない。"
        )
    elif _fact and is_reply:
        diff_instr = (
            f"【補足に使う verified data】{_fact}\n"
            "↑この中から元投稿が触れていない数字を1つだけ選び、 補足の核にする。 "
            "選手個人の行があればチーム成績の行より優先する。 "
            "『巨人(一軍)チーム』の行は一軍チームの成績なので、 ファーム(二軍)の"
            "成績や選手個人の成績として書き換えるのは禁止。 これ以外の数字は足さない。"
        )
    elif _fact:
        diff_instr = (
            f"【使ってよい verified data】{_fact}\n"
            "↑元投稿が触れていない数字/事実をこの中から1つだけ自然に織り込み、 媒体と違う"
            "視点・気づきを足す。 これ以外の数字は足さない。"
        )
    else:
        # 2026-07-09 user「直して」: db_fact が無い lane (MLB クリップ等、 insight.db に
        # 実績が無い選手) は数字ルールがプロンプトに一切入らず、 実況調で「4回」「8球」等を
        # 書いて unverified 門番に2試行とも落ちる (昼便で朗希×3=6呼び出しが成果ゼロ、
        # 非リプ予算枯渇→巨人x_buzzテンプレ落ち・data_plain skip の実事故)。
        # 門番 (_extract_unverified_numbers) と同じ基準をプロンプト側にも明示する。
        diff_instr = (
            "数字 (回・球数・球速・打率・本数など) は元投稿に書かれているものだけ使ってよい。 "
            "元投稿に無い数字は、 見た印象からの推定でも一切書かない。"
        )
    verified_text = f"{src} {who} {_fact}"
    _total_attempts = _X_POST_GEN_ATTEMPTS
    for attempt in range(_total_attempts):
        is_final_attempt = attempt == _total_attempts - 1
        if attempt == 0:
            retry_note = ""
        elif is_empathy:
            retry_note = (
                "※前回は長い/講釈っぽい/知識を見せる内容/タメ口/自分の視点始まりで却下された。 "
                "相手の意見への同意から入り、 豆知識や解説を足さず、 相手が気持ちよくなる"
                f"共感と褒めだけで、 ですます調・{_empathy_len_spec.split('、')[0]}・原則1文で短く書き直す。\n"
            )
        elif is_reply:
            retry_note = (
                "※前回は長い/感想・講釈っぽくて却下された。 verified data の補足を核に、 "
                "50〜90字・1〜2文で短く書き直す。\n"
            )
        elif is_video_sns:
            # 2026-07-09 user「直して」: 動画系の実際の主落因は unverified_number (元投稿に
            # 無い回数・球数・球速を実況調で書く) なのに、 リトライ文が抽象性しか注意して
            # おらず attempt 2 も同型で落ちていた。 数字ルールを明示する。
            retry_note = (
                "※前回は「元投稿に無い数字を書いた/抽象的/元投稿と無関係」で却下された。 "
                "元投稿に実際にある内容だけに反応する。 元投稿に無い数字 (回・球数・球速など) は"
                "一切書かない。 プレー動画なら打球音・一歩目・送球・表情・ベンチ反応など"
                "目で見える要素から書く。 元投稿に無い場面を創作するな。 "
                "『見ておきたい』『楽しみ』『好投』だけで終わるな。\n"
            )
        else:
            retry_note = (
                "※前回は優等生締め/ポエム/中身薄で却下された。 データ+フーガ風の読みで具体的に書き、 "
                "『〜してほしい』 系で終わるな。\n"
            )
        if is_empathy:
            task_line = f"【今回のタスク: {subject}への共感リプ】"
            task_instr = (
                f"上記 voice の熱は保ちつつ、 次の{subject}に同じ巨人ファンとして"
                "ですます調で丁寧に寄り添う短いリプを書く (初めて話しかける相手)。"
            )
        elif is_reply:
            task_line = f"【今回のタスク: {subject}への補足リプ】"
            task_instr = f"上記 voice のまま、 次の{subject}にデータを1つ補足する短いリプを書く。"
        else:
            task_line = f"【今回のタスク: {subject}への反応コメント】"
            task_instr = f"上記 voice のまま、 次の{subject}に反応するヨシラバーのコメントを書く。"
        prompt = "\n".join([
            base_voice,
            "",
            "----",
            task_line,
            retry_note + task_instr,
            (f"【視点指定】{extra_voice_note}" if extra_voice_note else ""),
            f"対象選手: {who or '(不明)'}",
            # empathy リプは選手名 lead を強制しない (2026-07-07 user「相手の意見に
            # もっとよりそって」: 同意 first と選手名 lead が矛盾するため)。
            (
                f"本文1行目はできるだけ『{who}、』または『{who}は』で始める。"
                if who and not is_empathy else ""
            ),
            len_rule,
            diff_instr,
            "コメント本文のみ出力 (前置き・説明・引用符なし)。",
            f"{subject}: 「{src}」",
            "",
            "コメント:",
        ])
        try:
            _llm_budget_guard(budget_site)
            response = _x_post_generate_content(
                client, model=model_id, contents=prompt, config={"temperature": temperature},
            )
            text = (getattr(response, "text", None) or "").strip()
        except Exception as exc:  # noqa: BLE001 - silent skip, caller falls back to template
            log.warning("quote_rt_comment_skip reason=gemini_error err=%r", exc)
            return ""
        text = _finalize_post_text(text)
        last_preview = text[:60]
        safety_ok = bool(text) and _gemini_branding_safety_check(text, verified_text)
        unverified = _extract_unverified_numbers(text, verified_text) if text else []
        voice_ok = bool(text) and _voice_quality_ok(text, live=is_live, short_ok=is_empathy)
        # 2026-07-07 user「ファンリプ長くない?」: empathy リプは prompt 指定 (20〜55字) を
        # 大きく超えたら gate で弾いてリトライ (最終便は relaxed fallback 側で許容)。
        empathy_len_ok = (not is_empathy) or len(text) <= 70
        if safety_ok and not unverified and voice_ok and empathy_len_ok:
            log.info("quote_rt_comment_built player=%s text_len=%d attempt=%d", who, len(text), attempt + 1)
            return text
        if not safety_ok:
            log.info("quote_rt_gate_fail check=safety attempt=%d preview=%r", attempt + 1, text[:60])
        elif unverified:
            log.info("quote_rt_gate_fail check=unverified_number attempt=%d nums=%r preview=%r",
                     attempt + 1, unverified, text[:60])
        elif not voice_ok:
            log.info("quote_rt_gate_fail check=voice attempt=%d tail=%r preview=%r",
                     attempt + 1, text[-30:], text[:60])
        elif not empathy_len_ok:
            log.info("quote_rt_gate_fail check=empathy_too_long attempt=%d text_len=%d preview=%r",
                     attempt + 1, len(text), text[:60])
        # 470: 最終便は template に逃げず LLM を優先。 ただし致命的NG は最終便でも block:
        # 捏造数字 (unverified) / 炎上 pattern (戦犯・断定・監督批判 等) / URL・ハッシュタグ等の
        # forbidden pattern / 文字数超過。 残る voice (定型締め) と topic-hygiene (首脳陣 等) のみ許容。
        if (
            is_final_attempt
            and text
            and not unverified
            and len(text) <= X_CHAR_LIMIT
            and _matched_inflammatory_pattern(text) is None
            and _matched_branding_forbidden_pattern(text, verified_text) is None
        ):
            relaxed_text = text
    if relaxed_text:
        log.info("quote_rt_comment_relaxed_fallback player=%s text_len=%d preview=%r",
                 who, len(relaxed_text), relaxed_text[:60])
        return relaxed_text
    log.warning("quote_rt_comment_skip reason=quality_or_safety preview=%r", last_preview)
    return ""


def build_plain_data_post(
    source_text: str,
    *,
    gemini_api_key: str,
    fact_text: str = "",
    player: str = "",
    metric_label: str = "",
    model_id: str = _X_POST_DATA_LLM_MODEL,
    temperature: float = 0.25,
    budget_site: str = "data_plain",
) -> str:
    """Rewrite a verified data candidate into plain, easy X copy.

    This path is intentionally narrower than the branding/comment generators:
    no Tavily, no extra facts, and every numeric token in the output must
    already appear in the candidate text or its fact line.
    """
    log = _logging.getLogger("x_post_branding_gen")
    src = (source_text or "").strip()
    if not src or not gemini_api_key:
        return ""
    verified_text = " ".join(
        part for part in [src, fact_text or "", player or "", metric_label or ""] if part
    )
    # 2026-07-06: 記事タイトルは全角数字 (２０回１／３) が多く、 LLM は半角で
    # 書き戻すため、 数字 token の抽出・使用チェックは NFKC 正規化側で行う
    # (record 可読化 dry-run で unverified / no_verified_number_used 全滅の実測対策)。
    import unicodedata as _ud
    verified_nfkc = _ud.normalize("NFKC", verified_text)
    numeric_tokens = [m.group(0) for m in _NUMERIC_TOKEN_RE.finditer(verified_nfkc)]
    prompt = "\n".join(
        [
            "あなたは読売ジャイアンツ専門のデータ投稿を整える編集者です。",
            "下の verified data だけを使い、X投稿文を作ってください。",
            "",
            "ルール:",
            "- 2〜4行、90〜170字程度。",
            "- 淡白に、分かりやすく。煽り・ポエム・大げさな断定は禁止。",
            "- 数字・順位・選手名・対戦相手・期間は verified data にあるものだけ使う。",
            "- 数字は半角で、verified data の表記のまま使う。日付・年など verified data に無い数字は書かない。",
            "- verified data に無い数字や記録を足さない。",
            "- URL、ハッシュタグ、媒体名、絵文字の連打は禁止。",
            "- 「どう見ますか」「期待したい」「応援したい」で締めない。",
            "- 本文だけを出力。説明や引用符は不要。",
            "",
            f"対象選手: {player or '(指定なし)'}",
            f"指標/種別: {metric_label or '(指定なし)'}",
            "verified data:",
            verified_text,
            "",
            "投稿文:",
        ]
    )
    try:
        from google import genai

        client = genai.Client(api_key=gemini_api_key)
        _llm_budget_guard(budget_site)
        response = _x_post_generate_content(
            client,
            model=model_id or _X_POST_DATA_LLM_MODEL,
            contents=prompt,
            config={"temperature": temperature},
        )
        text = _finalize_post_text((getattr(response, "text", None) or "").strip())
    except Exception as exc:  # noqa: BLE001 - caller keeps deterministic text
        log.warning("plain_data_post_skip reason=gemini_error err=%r", exc)
        return ""
    if not text or not _gemini_branding_safety_check(text, verified_text):
        log.info("plain_data_post_skip reason=safety_check")
        return ""
    if _extract_unverified_numbers(text, verified_text):
        log.info("plain_data_post_skip reason=unverified_numbers")
        return ""
    if player and _normalize_player_name(player) not in _normalize_player_name(text):
        log.info("plain_data_post_skip reason=missing_player player=%s", player)
        return ""
    text_nfkc = _ud.normalize("NFKC", text)
    if numeric_tokens and not any(token in text_nfkc for token in numeric_tokens):
        log.info("plain_data_post_skip reason=no_verified_number_used")
        return ""
    if not _voice_quality_ok(text, live=True):
        log.info("plain_data_post_skip reason=voice_quality")
        return ""
    log.info("plain_data_post_built player=%s metric=%s text_len=%d", player or "-", metric_label or "-", len(text))
    return text


def build_comment_context_line(
    article_text: str,
    player: str,
    quote: str,
    *,
    gemini_api_key: str,
    source_title: str = "",
    model_id: str = _X_POST_DATA_LLM_MODEL,
    temperature: float = 0.3,
) -> str:
    """コメント速報の『』の前に置く状況説明1行 (2026-07-06 user「これいいん
    だけど、なぜこのコメントをしているかも入れてほしい」「唐突」対応)。

    記事本文の lead 部分から、発言が出た状況・きっかけを 20〜45字の1行で
    要約する。記事に無い数字は _extract_unverified_numbers で棄却、感想・
    評価・憶測は prompt で禁止。失敗 / gate 落ち → "" (caller は文脈なしの
    従来形式 `名前『発言』` で出す)。
    """
    log = _logging.getLogger("x_post_branding_gen")
    body = (article_text or "").strip()
    who = (player or "").strip()
    if not body or not who or not gemini_api_key:
        return ""
    lead = body[:1200]
    verified_text = f"{source_title} {lead} {quote} {who}"
    prompt = "\n".join([
        "あなたは読売ジャイアンツ専門メディアの編集者です。",
        "下の記事から、選手・首脳陣コメントの前に置く「状況説明の1行」を作ってください。",
        "",
        "ルール:",
        "- 20〜45字、1文だけ。この後に本人のセリフ『…』がそのまま続く前提。",
        f"- 「{who}が何について・どんな場面で話したか」を記事の記載だけで書く。",
        "- 記事に無いこと・記事に無い数字は書かない。憶測・感想・評価は入れない。",
        "- セリフの引用や『』は入れない。URL・ハッシュタグ・媒体名は入れない。",
        "- 例: 「配球で首を振らない理由を聞かれて。」「二軍戦後、状態について。」",
        "",
        f"発言者: {who}",
        (f"記事タイトル: {source_title}" if source_title else ""),
        "記事本文 (先頭部分):",
        lead,
        "",
        "この後に続くセリフ:",
        (quote or "")[:120],
        "",
        "状況説明の1行:",
    ])
    try:
        from google import genai

        client = genai.Client(api_key=gemini_api_key)
        _llm_budget_guard("comment_context")
        response = _x_post_generate_content(
            client, model=model_id or _X_POST_DATA_LLM_MODEL,
            contents=prompt, config={"temperature": temperature},
        )
        text = (getattr(response, "text", None) or "").strip()
    except Exception as exc:  # noqa: BLE001 - caller falls back to no-context format
        log.warning("comment_context_skip reason=gemini_error err=%r", exc)
        return ""
    text = text.splitlines()[0].strip() if text else ""
    text = text.strip("「」『』\"'")
    # 10字未満は状況説明として情報が無い (「打線について。」等) ので出さない。
    if not text or len(text) < 10 or len(text) > 60:
        log.info("comment_context_skip reason=length len=%d", len(text or ""))
        return ""
    if _extract_unverified_numbers(text, verified_text):
        log.info("comment_context_skip reason=unverified_numbers")
        return ""
    if _matched_inflammatory_pattern(text) is not None:
        log.info("comment_context_skip reason=inflammatory")
        return ""
    if _matched_branding_forbidden_pattern(text, verified_text) is not None:
        log.info("comment_context_skip reason=forbidden_pattern")
        return ""
    log.info("comment_context_built player=%s len=%d", who, len(text))
    return text


def today_str(now_jst) -> str:
    """Helper for signature hashing (separate function to keep build_team_roundup_candidate readable)."""
    return now_jst.strftime("%Y-%m-%d")


def _extract_published_date_label(raw: object) -> str:
    """411 (2026-05-20): published_date を YYYY-MM-DD label に正規化。

    Tavily news topic は RFC 1123 (例: "Tue, 19 May 2026 13:30:00 GMT") を
    返すことが多いが、 ISO 8601 / unparseable も来うる。 parse 失敗時は
    「日付不明」 とし、 Gemini Flash Lite に古さの注意 hint を与える (hallucination 抑制)。
    """
    raw_str = str(raw or "").strip()
    if not raw_str:
        return "日付不明"
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(raw_str)
        return dt.strftime("%Y-%m-%d")
    except (TypeError, ValueError, IndexError):
        pass
    try:
        from datetime import datetime as _dt
        return _dt.fromisoformat(raw_str.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        pass
    # 最終 fallback: 先頭 10 文字が YYYY-MM-DD パターン
    if len(raw_str) >= 10 and raw_str[4] == "-" and raw_str[7] == "-":
        return raw_str[:10]
    return "日付不明"


def _extract_source_label(result: dict) -> str:
    """411 (2026-05-20): result から媒体名を抽出。

    Tavily は domain (例: "hochi.news") を返さない時があるが、 `url` から
    domain を取って media label に変換する。 unknown domain は 「不明媒体」。
    """
    url = str(result.get("url") or "").strip()
    if not url:
        return "不明媒体"
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return "不明媒体"
    label_map = {
        "giants.jp": "巨人公式",
        "npb.or.jp": "NPB公式",
        "hochi.news": "スポーツ報知",
        "sponichi.co.jp": "スポニチ",
        "nikkansports.com": "日刊スポーツ",
        "sanspo.com": "サンスポ",
        "daily.co.jp": "デイリースポーツ",
        "chunichi.co.jp": "中日スポーツ",
        "sports.yahoo.co.jp": "Yahoo!スポーツ",
    }
    for domain_key, label in label_map.items():
        if host == domain_key or host.endswith("." + domain_key):
            return label
    return host or "不明媒体"


def _format_tavily_context(results: list[dict], *, snippet_len: int = 300) -> str:
    """411 (2026-05-20): 各 result に `[YYYY-MM-DD] [媒体名] <タイトル> — <抜粋>` 形式で整形.

    user 仕様: Tavily の answer は使わず、 URL 本文・媒体名・日付を見る。
    Gemini Flash Lite に「いつの記事か」「どの媒体か」 を明示し、 古い snippet で現在形を
    生成しないよう context で hint。
    """
    lines = []
    for r in results:
        title = str(r.get("title") or "").strip()
        content = str(r.get("content") or "").strip()
        if not title and not content:
            continue
        date_label = _extract_published_date_label(r.get("published_date"))
        source_label = _extract_source_label(r)
        lines.append(
            f"- [{date_label}] [{source_label}] {title} — {content[:snippet_len]}"
        )
    return "\n".join(lines)


def build_gemini_branding_candidate(
    player_name: str,
    *,
    gemini_api_key: str,
    tavily_api_key: str,
    db_fact_line: str = "",
    max_tavily_results: int = 3,
    timeout_seconds: int = 30,
    model_id: str = _X_POST_GEMINI_PRIMARY_MODEL,
    temperature: float = 0.4,
    logger: Optional[_logging.Logger] = None,
    db_path: str = "",
    persona: Optional[str] = None,
    same_day_only: Optional[bool] = None,
    db_fact_streak_window: Optional[int] = None,
    post_type: Optional[str] = None,
    focused_players: Optional[list[str]] = None,
    fan_voice_snippet: str = "",
    starting_pitcher_today: str = "",
    opponent_pitcher_canonical: str = "",
    lineup_change_summary: str = "",
    promotion_summary: str = "",
) -> Optional[Candidate]:
    """Tavily REST 検索 + Gemini 生成で 1 件の Candidate を返す。

    silent skip 条件 (``None`` 返却):
    - player_name 不正 / 巨人 roster 不一致
    - API key 不足
    - Tavily 失敗 (factual ground 無し → hallucination 抑制のため生成しない)
    - Gemini 失敗 (rate limit / network 等)
    - 空生成 / spec 382 hard rule 違反 (validator drop)
    """
    log = logger or _logging.getLogger("x_post_branding_gen")
    player = str(player_name or "").strip()
    if not player or not gemini_api_key or not tavily_api_key:
        log.info("gemini_branding_skip reason=missing_input player=%r", player)
        return None
    if not _is_verified_full_giants_member_name(player):
        log.info("gemini_branding_skip reason=not_verified_giants_member player=%r", player)
        return None

    # 411 / 414 axis C9: persona 自動選択。 試合日 18-21時 = 缶詰、 他 = フーガ。
    # caller が persona kwarg で明示指定すれば自動選択を override。 同じく
    # same_day_only / db_fact_streak_window も persona に応じて自動 (缶詰=当日 only)。
    from datetime import datetime, timezone, timedelta
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)
    if persona is None:
        is_game_day = is_giants_game_day(now_jst, db_path) if db_path else False
        resolved_persona = select_branding_persona(now_jst, is_game_day)
    else:
        resolved_persona = persona
    # 414 axis C9: 缶詰 persona (試合中実況) は当日 only (古い snippet / 過去 streak を拾わない)
    if same_day_only is None:
        same_day_only = (resolved_persona == "kandume")
    if db_fact_streak_window is None:
        db_fact_streak_window = 0 if resolved_persona == "kandume" else 5

    # 1. Tavily 検索 (factual ground)
    query = f"巨人 {player} 最新"
    results = _tavily_search(
        query,
        tavily_api_key,
        max_results=max_tavily_results,
        timeout_seconds=timeout_seconds,
        same_day_only=same_day_only,
    )
    if not results:
        log.warning(
            "gemini_branding_skip reason=no_tavily_results query=%r player=%s persona=%s same_day_only=%s",
            query,
            player,
            resolved_persona,
            same_day_only,
        )
        return None
    # 414 axis C6: persona=fuuga (古い snippet 許容) でも 7 日超は strict drop。
    # 缶詰 (same_day_only=True) は既に当日 filter 経由なので no-op に近い。
    results = _recent_published_within_days(results, days=7)
    if not results:
        log.warning(
            "gemini_branding_skip reason=tavily_results_too_old query=%r player=%s",
            query,
            player,
        )
        return None
    context = _format_tavily_context(results)
    if not context:
        log.warning(
            "gemini_branding_skip reason=empty_tavily_context query=%r player=%s",
            query,
            player,
        )
        return None
    system_prompt = _build_system_prompt(
        now_jst_hour=now_jst.hour,
        today_jst=now_jst.strftime("%Y-%m-%d"),
        persona=resolved_persona,
    )
    # 414 axis A: 型自動選択。 caller が post_type kwarg で明示すれば override。
    if post_type is None:
        is_game_day_val = is_giants_game_day(now_jst, db_path) if db_path else False
        resolved_post_type = select_post_type(
            now_jst,
            is_game_day_val,
            has_db_fact=bool(db_fact_line),
            has_tavily_results=bool(results),
        )
    else:
        resolved_post_type = post_type
    post_type_guidance = _POST_TYPE_GUIDANCE.get(resolved_post_type, "")
    # 414 axis E: 試合前 (試合日 + 17時以前) のみ 7 テーマを prompt に注入
    pregame_section = ""
    if db_path and 5 <= now_jst.hour < 17:
        try:
            from src.analysis.pregame_themes import (
                build_pregame_themes,
                format_pregame_themes_for_prompt,
            )
            themes = build_pregame_themes(
                db_path,
                now_jst=now_jst,
                starting_pitcher_today=starting_pitcher_today,
                focused_players=focused_players,
                lineup_change_summary=lineup_change_summary,
                promotion_summary=promotion_summary,
                fan_voice_snippet=fan_voice_snippet,
                opponent_pitcher_canonical=opponent_pitcher_canonical,
            )
            pregame_section = format_pregame_themes_for_prompt(themes)
        except Exception as exc:  # noqa: BLE001 - silent fallback
            log.info("pregame_themes_skip reason=%r", exc)
    prompt_parts = [system_prompt]
    if post_type_guidance:
        prompt_parts.extend(["", post_type_guidance])
    if pregame_section:
        prompt_parts.extend(["", pregame_section])
    # 締めローテ (考察モードのみ): 候補ごとに締めの型を散らし単調さを防ぐ。 ライブ缶詰は対象外。
    if resolved_persona != "kandume":
        prompt_parts.extend([
            "",
            "締めのワンパターン回避: " + _ending_style_hint(player)
            + "。 『〜してほしい』 は文中でも避ける。",
        ])
    prompt_parts.extend([
        "",
        f"対象選手: {player}",
        "",
        f"DB 照合済み数字 (使ってよい数字): {db_fact_line or 'なし'}",
        "",
        "Tavily 検索結果 (context、 ここから不検証数字 / 引用 / 媒体名 / URL は使わない):",
        context,
        "",
        "上記情報を踏まえて、 独自の視点で X 投稿案を 1 件、 本文のみ書いてください。",
    ])
    prompt = "\n".join(prompt_parts)
    try:
        from google import genai
        client = genai.Client(api_key=gemini_api_key)
        _llm_budget_guard("gemini_branding")
        response = _x_post_generate_content(
            client,
            model=model_id,
            contents=prompt,
            config={"temperature": temperature},
        )
        text = (getattr(response, "text", None) or "").strip()
    except Exception as exc:  # noqa: BLE001 - silent skip is the fault-tolerance contract
        log.warning(
            "gemini_branding_skip reason=gemini_error player=%s err=%r",
            player,
            exc,
        )
        return None

    text = _finalize_post_text(text)

    # 414 axis C2: 数値 whitelist 用 verified_text = db_fact_line + Tavily context。
    # 2026-06-24: safety_check の 順位 / rate 照合にも同じ source を使う。
    verified_text = " ".join(filter(None, [db_fact_line or "", context]))

    # 3. spec 382 hard rule + 414 axis D 炎上防止 validator
    if not _gemini_branding_safety_check(text, verified_text):
        # 414 axis C7 + D: 構造化 drop log (どの pattern が hit したか + 軸名)
        matched_pattern: Optional[str] = _matched_branding_forbidden_pattern(text, verified_text)
        matched_axis: str = "C"  # default: forbidden patterns (axis C)
        if matched_pattern is None:
            # 軸 D: 炎上 patterns hit を確認
            inflammatory_match = _matched_inflammatory_pattern(text)
            if inflammatory_match:
                matched_pattern = inflammatory_match
                matched_axis = "D"
        log.warning(
            _json.dumps(
                {
                    "event": "gemini_branding_drop",
                    "reason": "safety_check_failed",
                    "axis": matched_axis,
                    "player": player,
                    "persona": resolved_persona,
                    "post_type": resolved_post_type,
                    "matched_pattern": matched_pattern,
                    "text_preview": text[:80],
                    "text_len": len(text),
                },
                ensure_ascii=False,
            )
        )
        return None

    # 生成 text の数字で verified_text に literal 含まれない場合は drop。
    unverified = _extract_unverified_numbers(text, verified_text)
    if unverified:
        log.warning(
            _json.dumps(
                {
                    "event": "gemini_branding_drop",
                    "reason": "unverified_numbers",
                    "player": player,
                    "persona": resolved_persona,
                    "post_type": resolved_post_type,
                    "unverified_numbers": unverified[:10],
                    "text_preview": text[:80],
                },
                ensure_ascii=False,
            )
        )
        return None

    # 門番 (品質ゲート): 優等生締め / ポエム / スカスカ を drop。 ライブ (缶詰) は緩和。
    if not _voice_quality_ok(text, live=(resolved_persona == "kandume")):
        log.warning(
            _json.dumps(
                {
                    "event": "gemini_branding_drop",
                    "reason": "voice_quality",
                    "player": player,
                    "persona": resolved_persona,
                    "post_type": resolved_post_type,
                    "text_preview": text[:80],
                    "text_len": len(text),
                },
                ensure_ascii=False,
            )
        )
        return None

    # 4. Candidate dataclass
    signature_hash = _hashlib.sha1(
        f"gemma_branding|{player}|{text[:80]}".encode("utf-8")
    ).hexdigest()[:16]
    draft_lines = [
        "【根拠: Gemini + Tavily HTTP REST + 任意 DB 参照】",
        f"対象選手: {player}",
        f"検索 query: {query}",
        f"Tavily 結果数: {len(results)}",
        f"DB fact 注入: {'あり' if db_fact_line else 'なし'}",
        f"configured_model: {model_id}",
        "",
        "【Tavily 検索結果 snippet】",
        context,
    ]
    if db_fact_line:
        draft_lines.extend(["", "【DB fact line】", db_fact_line])
    log.info(
        "gemini_branding_candidate_built player=%s tavily_results=%d text_len=%d",
        player,
        len(results),
        len(text),
    )
    tagged_text = _prepend_focus_player_tag(text, player)
    return Candidate(
        title=f"Gemini branding｜{player}",
        metric=_GEMINI_BRANDING_METRIC,
        period_label="LLM 生成",
        draft_text="\n".join(draft_lines),
        post_text=tagged_text,
        char_count=len(tagged_text),
        signature=f"gemma_branding|{signature_hash}|False|None",
        focus_player=player,
        source_material_type="gemma_branding",
    )


# ----------------------------------------------------------------------------
# 417: Hochi / Sanspo source 直結 path。 rss_fetcher が classify した article info
# (queue 経由) を入力に、 Tavily を呼ばずに Gemini Flash Lite で X-post 候補生成。
# 既存 prompt / persona / safety check は全部流用 (§ 0 不可触条件遵守)。
# ----------------------------------------------------------------------------


def _try_fetch_og_image_for_candidate(
    *,
    source_url: str,
    source_name: str,
    log,
) -> tuple[bytes, str, str, str]:
    """438: source URL から og:image を fetch して image_bytes / alt_text /
    image_source_url / html_text の 4 つを返す.

    Phase 1 = image_bytes / alt_text / image_source_url を Pattern A image attach に使用。
    Phase 2 = html_text を long quote 抽出 (Pattern B) に使用。

    失敗時は (b"", "", "", "") を返し、 caller 側で image なし候補として扱う。
    例外は全て catch する (network / parse / X.com 認証要求 等)。
    """
    if not source_url:
        return b"", "", "", ""
    # twitter / x.com は login wall で og:image が取れないため skip (silent)
    lowered = source_url.lower()
    if "twitter.com/" in lowered or "x.com/" in lowered:
        return b"", "", "", ""
    try:
        from src.og_image_fetcher import fetch_og_image
    except Exception as exc:  # noqa: BLE001
        log.info("og_image_fetch_skip reason=import_failed err=%r", exc)
        return b"", "", "", ""
    try:
        result = fetch_og_image(source_url, logger=log)
    except Exception as exc:  # noqa: BLE001
        log.info("og_image_fetch_skip reason=unexpected_exception err=%r", exc)
        return b"", "", "", ""
    if result is None:
        return b"", "", "", ""
    # 438 (2026-05-27): user 仕様「画像の引用も削除」 — alt text の
    # 「引用元: 媒体名」 も停止 (mail HTML / X media_upload alt 表示で「引用」
    # 文字が visible になる回避)。
    return result.image_bytes, "", result.image_url, result.html_text or ""


def _try_extract_pattern_b_quote(
    *,
    image_bytes: bytes,
    speaker: str,
    html_text: str,
    log,
) -> str:
    """438 Phase 2 revised (2026-05-28): html_text から speaker の long quote を抽出.

    user 仕様変更 (2026-05-28): overlay 焼き込み廃止、 post text に「人名「quote」」
    を書く方式 (案 C) に切替。 web intent が画像 attach 非対応のため、 焼き込み
    image でも raw image でも user 手動 attach は同じ、 text 検索可能性 + 実装
    simplicity + 既存 ヨシラバー voice 哲学 と一致を選択。

    speaker の roster alias 全部 (姓名 / 姓 / 役職付き等) を proximity check に
    使い、 mis-attribution (発言者の取り違え) を防ぐ。

    Returns:
        extracted_quote (str) — Pattern B 成立時 (40-180 字 の literal long quote)
        "" — 不成立 (caller 側 Pattern A 維持)
    """
    if not image_bytes or not speaker or not html_text:
        return ""
    try:
        from src.long_quote_extractor import extract_long_quote
    except Exception as exc:  # noqa: BLE001
        log.info("pattern_b_skip reason=extractor_import_failed err=%r", exc)
        return ""
    # roster から speaker の aliases を取得 (姓 / 姓名 / 役職付き等)
    speaker_aliases = _resolve_speaker_aliases(speaker)
    try:
        quote = extract_long_quote(html_text, speaker_aliases=speaker_aliases)
    except Exception as exc:  # noqa: BLE001
        log.info("pattern_b_skip reason=extract_exception err=%r", exc)
        return ""
    if not quote:
        log.info(
            "pattern_b_skip reason=no_long_quote_found speaker=%s alias_count=%d",
            speaker, len(speaker_aliases),
        )
        return ""
    log.info(
        "pattern_b_extracted speaker=%s quote_len=%d",
        speaker, len(quote),
    )
    return quote


def _resolve_speaker_aliases(canonical_name: str) -> tuple[str, ...]:
    """canonical name (例: 戸郷翔征 / 橋上秀樹) → roster の aliases 全部を返す.

    roster JSON が読めない / 一致しない場合は canonical name + 姓 のみの
    minimal set を返す (proximity check の degrade fallback)。
    """
    if not canonical_name:
        return ()
    try:
        from src.x_post_mail_lane import _load_giants_member_aliases  # local import (cycle 回避)
    except Exception:  # noqa: BLE001
        return (canonical_name,)
    try:
        aliases_map = _load_giants_member_aliases()
    except Exception:  # noqa: BLE001
        return (canonical_name,)
    out: set[str] = {canonical_name}
    # canonical → multiple aliases (map は alias → canonical なので逆引き)
    for alias, canon in aliases_map.items():
        if canon == canonical_name and alias:
            out.add(alias)
    # 姓 (canonical の先頭 2-3 文字) を append (proximity で姓だけ言及される場合)
    if len(canonical_name) >= 2:
        out.add(canonical_name[:2])
    return tuple(out)


def _find_first_giants_player_in_text(text: str, *, roles: Optional[set[str]] = None) -> str:
    """text 中の Giants roster member を役割優先で 1 人選び canonical name を返す.

    aliases (giants_roster.json、 player + manager + coach の active member) を
    全件 substring match で照合する。 normalize なし (literal substring)。

    役割優先 (2026-06-24): 記事の本題はコーチ/監督ではなく選手のことが多い。
    earliest 出現位置だけで選ぶと「選手をコーチが評価」型の記事でコーチが
    先に出ると主役を奪う (例: 山崎伊織の記事で野上コーチが見出しに立つ)。
    そこで:
      - roles=None: text 内に player が 1 人でも居れば player の中で最早出現を返す。
        player が居なければ coach/manager の中で最早出現を返す (コーチ単独
        ニュースは従来どおり拾える)。
      - roles={"player"} 等: 指定ロールのみ対象に最早出現を返す (cross-text で
        player を横断優先したい caller 用)。
    該当無しは ""。

    2026-05-27: member gate を player → player + manager + coach へ拡張
    (user「監督やコーチもいれていい、 巨人なら」)。 関数名は caller 互換で player 表記のまま。
    """
    if not isinstance(text, str) or not text:
        return ""
    try:
        from src.x_post_mail_lane import (  # local import to avoid cycle at module top
            _load_giants_member_aliases,
            _load_giants_member_roles,
        )
    except Exception:  # noqa: BLE001
        return ""
    try:
        aliases = _load_giants_member_aliases()
        role_map = _load_giants_member_roles()
    except Exception:  # noqa: BLE001
        return ""

    # text 内の全 member 一致を (pos, canonical, role) で収集。
    matches: list[tuple[int, str, str]] = []
    for alias, canonical in aliases.items():
        if not alias or len(alias) < 2:
            continue
        pos = text.find(alias)
        if pos < 0:
            continue
        canon = canonical or alias
        role = role_map.get(canon, "")
        if roles is not None and role not in roles:
            continue
        matches.append((pos, canon, role))

    if not matches:
        return ""

    if roles is None:
        players = [m for m in matches if m[2] == "player"]
        pool = players if players else matches
    else:
        pool = matches
    pool.sort(key=lambda m: m[0])
    return pool[0][1]


def build_x_post_from_article_info(
    article_info,
    *,
    gemini_api_key: str,
    db_path: str = "",
    timeout_seconds: int = 30,
    model_id: Optional[str] = None,
    temperature: float = 0.4,
    persona: Optional[str] = None,
    logger: Optional[_logging.Logger] = None,
    skip_player_keys: Optional[set] = None,
    succeeded_player_keys: Optional[set] = None,
    attempt_counts: Optional[dict] = None,
    max_attempts_per_player: int = 3,
    related_player_context: str = "",
) -> Optional[Candidate]:
    """417: queue 経由 article_info (Hochi/Sanspo source) から X-post 候補 1 件を生成.

    既存 `build_gemini_branding_candidate` と同じ prompt / persona / safety_check /
    unverified_numbers gate を全部流用。 違いは「Tavily 検索結果 → article_info の
    title + summary literal」 に source 入れ替えるのみ。

    model_id 未指定時は primary model を渡し、_x_post_generate_content 側で時間帯により
    自動切替: 既定 JST 17:00-22:30 は primary(3.5)、 それ以外は fallback(lite)。 caller が明示指定すれば
    auto-select を override。

    silent skip 条件 (None 返却):
    - article_info が不正 / title 空
    - title から Giants roster player を 1 件も抽出できない (player_canonical も空)
    - gemini_api_key 不在
    - Gemini 失敗 (network / rate limit / 空生成)
    - safety_check / unverified_numbers gate hit
    """
    log = logger or _logging.getLogger("x_post_branding_gen")
    if article_info is None or not getattr(article_info, "title", ""):
        log.info("article_info_branding_skip reason=invalid_input")
        return None
    if not gemini_api_key:
        log.info("article_info_branding_skip reason=missing_gemini_api_key")
        return None

    title = (article_info.title or "").strip()
    summary = (article_info.summary or "").strip()
    source_url = (article_info.source_url or "").strip()
    source_name = (article_info.source_name or "").strip()
    article_subtype = (article_info.article_subtype or "").strip()
    related_player_context = (related_player_context or "").strip()

    # 0. article_subtype 判定 (postgame = 試合総括は巨人全体対象、 個別 player でなく
    # チーム視点、 フーガ voice で書く。 user 確定 2026-05-21:
    #   - 試合総括は巨人全体を対象 (個別 player が title に居ても team-wide で書く)
    #   - 試合中でも postgame ならフーガ voice 使う)
    is_postgame_team_wide = article_subtype in {"postgame", "postgame_digest", "team_roundup"}

    if is_postgame_team_wide:
        # 試合総括 → player 抽出を skip、 「巨人」 を対象 (チーム視点で voice する)
        player = "巨人"
        log.info(
            "article_info_branding_team_wide source_url=%s subtype=%s title=%r",
            source_url,
            article_subtype,
            title[:60],
        )
    else:
        # 1. member 抽出。 本題は選手のことが多いので player を最優先で title→summary
        # 横断で探す。 選手が全く居ない記事だけ coach/manager を主役にする (コーチ単独
        # ニュースは従来どおり拾える)。 それでも空なら article_info.player_canonical の
        # 先頭、 全部空なら skip。 2026-05-27 で player → member gate へ拡張、
        # 2026-06-24 で「選手 > コーチ/監督」の役割優先を追加。
        player = (
            _find_first_giants_player_in_text(title, roles={"player"})
            or _find_first_giants_player_in_text(summary, roles={"player"})
            or _find_first_giants_player_in_text(title)
            or _find_first_giants_player_in_text(summary)
        )
        if not player:
            canonical_list = getattr(article_info, "player_canonical", None) or []
            if canonical_list:
                player = str(canonical_list[0] or "").strip()
        if not player or not _is_verified_full_giants_member_name(player):
            log.info(
                "article_info_branding_skip reason=no_giants_member_in_article source_url=%s title=%r",
                source_url,
                title[:60],
            )
            return None

    # 1.5 同一選手の重複生成を抑えつつ出力は守る (2026-06-03 LLM 費用節約 + 回帰修正)。
    #   多媒体が同じ選手を扱うと queue に同一 player 記事が複数入る。費用のため
    #   1 選手 1 成功 (1 投稿) に絞るが、生成は「成功するまで最大 N 試行」許す。
    #   - succeeded_player_keys: その run で既に投稿候補が成立した player は skip
    #     (= 1 選手 1 投稿)。マークは末尾 (品質ゲート通過後) で行う。
    #   - attempt_counts: 全部 unverified_numbers 等で落ちる player の暴走を防ぐ
    #     試行上限 (max_attempts_per_player, 既定 3)。最初の 1 本が品質ゲートで
    #     落ちても次の記事を試せるので、旧来の「複数記事=通過チャンス」を維持。
    #   - skip_player_keys: cross-run cooldown/cap (env で有効化、既定は無効)。
    #     postgame team-wide ("巨人") は試合ごと 1 回なので cap 対象外。
    player_key = _normalize_player_name(player) if player else ""
    if player_key:
        if succeeded_player_keys is not None and player_key in succeeded_player_keys:
            log.info(
                "article_info_branding_skip reason=player_already_posted_this_run "
                "player=%s source_url=%s",
                player,
                source_url,
            )
            return None
        if attempt_counts is not None:
            if attempt_counts.get(player_key, 0) >= max_attempts_per_player:
                log.info(
                    "article_info_branding_skip reason=player_attempt_cap "
                    "player=%s attempts=%d source_url=%s",
                    player,
                    attempt_counts.get(player_key, 0),
                    source_url,
                )
                return None
            attempt_counts[player_key] = attempt_counts.get(player_key, 0) + 1
        if (
            not is_postgame_team_wide
            and skip_player_keys
            and player_key in skip_player_keys
        ):
            log.info(
                "article_info_branding_skip reason=player_cooldown_or_cap "
                "player=%s source_url=%s",
                player,
                source_url,
            )
            return None

    # 2. persona 自動選択
    #    - postgame (試合総括) → フーガ voice 強制 (team-wide、 試合中でも fuuga)
    #    - 個別 player article → 既存 logic (試合日 18-21時 = 缶詰、 それ以外 = フーガ)
    from datetime import datetime, timezone, timedelta

    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)
    if persona is None:
        if is_postgame_team_wide:
            resolved_persona = "fuuga"
        else:
            is_game_day = is_giants_game_day(now_jst, db_path) if db_path else False
            resolved_persona = select_branding_persona(now_jst, is_game_day)
    else:
        resolved_persona = persona

    resolved_model_id = model_id if model_id else _X_POST_GEMINI_PRIMARY_MODEL

    # 3. post_type 自動選択 (article_subtype が postgame なら data 寄り、 lineup なら
    # 速報寄り、 等の hint を has_tavily_results=True 相当で発火)
    is_game_day_val = is_giants_game_day(now_jst, db_path) if db_path else False
    has_article_context = bool(title) and bool(summary)
    resolved_post_type = select_post_type(
        now_jst,
        is_game_day_val,
        has_db_fact=False,  # DB fact line は別経路、 ここでは article literal 主体
        has_tavily_results=has_article_context,
    )
    post_type_guidance = _POST_TYPE_GUIDANCE.get(resolved_post_type, "")

    # 4. system prompt 構築 (既存 _build_system_prompt 完全流用、 1 文字も変えない)
    system_prompt = _build_system_prompt(
        now_jst_hour=now_jst.hour,
        today_jst=now_jst.strftime("%Y-%m-%d"),
        persona=resolved_persona,
    )

    # 5. context (Tavily snippet 相当) = article info の literal title + summary。
    #    related_player_context は queue 同一バッチ内の同一選手コメント literal のみ。
    # § 8 verified_text hygiene: AI commentary / 生成本文は context に含めない。
    # rss_fetcher が source から直接 extract した raw 部分だけを Gemini Flash Lite に渡す。
    context_lines = [
        f"[主記事 出典: {source_name or '報知 / サンスポ'}] [subtype: {article_subtype or '不明'}]",
        f"title (literal): {title}",
    ]
    if summary:
        context_lines.append(f"summary (literal): {summary}")
    context = "\n".join(context_lines)

    prompt_parts = [system_prompt]
    if post_type_guidance:
        prompt_parts.extend(["", post_type_guidance])
    # postgame (試合総括) は team-wide なので「対象 = 巨人 (試合総括)」 として書く、
    # 個別 player article は「対象選手 = {player}」 で書く (既存挙動)。
    target_line = (
        f"対象: 巨人 (試合総括、 個別選手 1 人でなく球団全体の流れ・打線・継投・守備 等を fuuga voice で総括)"
        if is_postgame_team_wide
        else f"対象選手: {player}"
    )
    prompt_parts.extend([
        "",
        target_line,
        "",
        "DB 照合済み数字 (使ってよい数字): なし (今回は article literal のみが factual ground)",
        "",
        "報知 / サンスポ 主記事 (literal、 ここから不検証数字 / 引用 / 媒体名 / URL は使わない、 voice 例の literal コピーも禁止):",
        context,
    ])
    if related_player_context:
        prompt_parts.extend([
            "",
            "同一選手の直近コメント補助文脈 (他記事の選手・首脳陣コメント literal。 形式は名前『コメント』のみ。 主題は主記事からズラさない):",
            related_player_context[:1200],
        ])
    prompt_parts.extend([
        "",
        "上記情報を踏まえて、 独自の視点で X 投稿案を 1 件、 本文のみ書いてください。",
    ])
    prompt = "\n".join(prompt_parts)

    # 6. Gemini Flash Lite generate
    try:
        from google import genai

        client = genai.Client(api_key=gemini_api_key)
        _llm_budget_guard("article_info")
        response = _x_post_generate_content(
            client,
            model=resolved_model_id,
            contents=prompt,
            config={"temperature": temperature},
        )
        text = (getattr(response, "text", None) or "").strip()
    except Exception as exc:  # noqa: BLE001 — silent skip per fault-tolerance contract
        log.warning(
            "article_info_branding_skip reason=gemini_error player=%s err=%r",
            player,
            exc,
        )
        return None

    text = _finalize_post_text(text)

    # 8. § 8 verified_text hygiene + 414 axis 2: 数値 whitelist。
    # verified_text = article_info の title + summary literal + 同一選手コメント補助文脈 **のみ**。
    # AI commentary / Gemini Flash Lite 出力は verified_text に **含めない** (二重 hallucination 防止)。
    # 2026-06-24: safety_check の 順位 / rate 照合にも同じ verified_text を使う。
    verified_text = " ".join(filter(None, [title, summary, related_player_context]))

    # 7. spec 382 hard rule + 414 axis D 炎上防止 validator (既存 1:1 流用)
    if not _gemini_branding_safety_check(text, verified_text):
        matched_pattern: Optional[str] = _matched_branding_forbidden_pattern(text, verified_text)
        matched_axis: str = "C"
        if matched_pattern is None:
            inflammatory_match = _matched_inflammatory_pattern(text)
            if inflammatory_match:
                matched_pattern = inflammatory_match
                matched_axis = "D"
        log.warning(
            _json.dumps(
                {
                    "event": "article_info_branding_drop",
                    "reason": "safety_check_failed",
                    "axis": matched_axis,
                    "player": player,
                    "persona": resolved_persona,
                    "post_type": resolved_post_type,
                    "matched_pattern": matched_pattern,
                    "source_url": source_url,
                    "text_preview": text[:80],
                    "text_len": len(text),
                },
                ensure_ascii=False,
            )
        )
        return None

    unverified = _extract_unverified_numbers(text, verified_text)
    if unverified:
        log.warning(
            _json.dumps(
                {
                    "event": "article_info_branding_drop",
                    "reason": "unverified_numbers",
                    "player": player,
                    "persona": resolved_persona,
                    "post_type": resolved_post_type,
                    "unverified_numbers": unverified[:10],
                    "source_url": source_url,
                    "text_preview": text[:80],
                },
                ensure_ascii=False,
            )
        )
        return None

    # 8.5 ヨシラバー voice 品質ゲート (2026-06-04): gemma_branding / quote_rt と同じ門番を
    # queue 417 経路にも適用。 flash-lite はプロンプトで禁止しても優等生締め / hopium
    # (信じてる / 別格 / 化ける) / ポエム / スカスカ を漏らすため、 生成後に deterministic
    # に drop する。 ここは単発生成なので retry はせず drop (queue drain が次記事を試す)。
    _is_live_hour = 18 <= now_jst.hour <= 21
    if not _voice_quality_ok(text, live=_is_live_hour):
        log.warning(
            _json.dumps(
                {
                    "event": "article_info_branding_drop",
                    "reason": "voice_quality",
                    "player": player,
                    "persona": resolved_persona,
                    "post_type": resolved_post_type,
                    "source_url": source_url,
                    "text_preview": text[:80],
                    "text_len": len(text),
                },
                ensure_ascii=False,
            )
        )
        return None

    # 9. Candidate dataclass 構築
    signature_hash = _hashlib.sha1(
        f"article_info_branding|{player}|{source_url}|{text[:80]}".encode("utf-8")
    ).hexdigest()[:16]
    draft_lines = [
        f"【根拠: {resolved_model_id} + 報知/サンスポ literal extract (queue 417)】",
        f"対象選手: {player}",
        f"出典: {source_name or '報知 / サンスポ'}",
        f"source URL: {source_url}",
        f"subtype: {article_subtype or '不明'}",
        f"model: {resolved_model_id}",
        "",
        "【記事 literal 抜粋】",
        context,
    ]
    # 438 (2026-05-27): user 仕様「post に外部リンクは張らない」 確定により
    # X インプ向上 Phase 5 で末尾付与していた「(出典 @handle)」 を停止。 X 上で
    # @handle が mention link 化して「リンク」 として見えるため。 出典担保は alt
    # text (引用元: 媒体名) に維持。
    # 旧 path: post_text_with_handle = _append_x_handle_to_post_text(text, source_url)
    post_text_without_handle = text
    # 438 Phase 1 (2026-05-27): 反応元 article の og:image を fetch して
    # Candidate に乗せる。 失敗時は image なし候補のまま (text only)。
    image_bytes, image_alt_text, image_source_url, html_text = _try_fetch_og_image_for_candidate(
        source_url=source_url,
        source_name=source_name,
        log=log,
    )
    # 438 Phase 2 revised (2026-05-28): user 仕様変更で overlay 廃止、 post text に
    # 「人名『quote』」 を書く方式 (案 C) に切替。 html_text + speaker から long quote
    # 抽出、 成立時は post_text = `{player}『{quote}』`、 image はそのまま raw
    # og:image を attach (overlay 焼き込みなし、 Pillow 不要)。
    final_post_text = post_text_without_handle
    pattern_label = "A"
    if image_bytes and html_text and player and not is_postgame_team_wide:
        extracted_quote = _try_extract_pattern_b_quote(
            image_bytes=image_bytes,
            speaker=player,
            html_text=html_text,
            log=log,
        )
        if extracted_quote:
            # Pattern B 成立: post_text = `{player}『{quote}』`、 image は raw のまま
            final_post_text = f"{player}『{extracted_quote}』"
            pattern_label = "B"
    # 先頭に 【選手名】 を付与 (Pattern B は既に player『…』 で始まるため helper 内で skip)
    final_post_text = _prepend_focus_player_tag(final_post_text, player)
    log.info(
        "article_info_branding_candidate_built player=%s source_url=%s text_len=%d model=%s handle=%s og_image=%s pattern=%s",
        player,
        source_url,
        len(final_post_text),
        resolved_model_id,
        _resolve_official_x_handle(source_url) or "-",
        "yes" if image_bytes else "no",
        pattern_label,
    )
    # 品質ゲートを通過し候補成立 → この run では同 player を以後 skip (1 選手 1 投稿)。
    if player_key and succeeded_player_keys is not None:
        succeeded_player_keys.add(player_key)
    return Candidate(
        title=f"X-post branding｜{player} ({resolved_model_id}) [{pattern_label}]",
        metric=_GEMINI_BRANDING_METRIC,
        period_label="LLM 生成 (queue 417)",
        draft_text="\n".join(draft_lines),
        post_text=final_post_text,
        char_count=len(final_post_text),
        signature=f"article_info_branding|{signature_hash}|False|None",
        focus_player=player,
        source_material_type="article_info_branding",
        image_bytes=image_bytes,
        image_alt_text=image_alt_text,
        image_source_url=image_source_url,
    )
