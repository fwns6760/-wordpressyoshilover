"""347 CLI entry — send one セ・リーグ X post candidate mail.

Default is **live send** (matches publish-notice job semantics); pass
``--dry-run`` to skip the SMTP call.

Hard constraints (mirror ticket 347):
    - LLM API never called.
    - insight.db: read-only via miq.query_rank.
    - article_candidates table: never touched (348 owns it).
    - パ・リーグ 6 teams: filtered out, only セ 6 teams reach the mail.

Cloud Run Job entrypoint: ``python -m src.tools.run_x_post_mail``.
"""

from __future__ import annotations

import argparse
import hashlib as _hashlib
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Sequence
from urllib import request as urlrequest
from urllib.error import URLError
from zoneinfo import ZoneInfo

if __package__ in {None, ""}:  # pragma: no cover - direct script execution
    REPO_ROOT = Path(__file__).resolve().parents[2]
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

from src import manual_intake_insight_query as miq  # noqa: E402
from src import mail_delivery_bridge as mdb  # noqa: E402
from src import x_post_mail_lane as lane  # noqa: E402
# 392: optional import — only used when X_POST_MAIL_GEMMA_GEN_ENABLED=1。
# 既存 (flag OFF) 経路で import 失敗時に mail を止めないため lazy import。
try:
    from src import x_post_branding_gen as _xbg  # noqa: E402
except Exception:  # noqa: BLE001 - keep mail lane working even if 392 deps missing
    _xbg = None  # type: ignore[assignment]


LOG = logging.getLogger("x_post_mail")
DEFAULT_MAX_DB_STALENESS_DAYS = 2
DEFAULT_DEDUP_MIN_CANDIDATES = 3
DEFAULT_LINEUP_FOCUS_MIN_CANDIDATES = 1
DEFAULT_NEWS_FALLBACK_SOURCE_LIMIT = 32
DEFAULT_NEWS_FALLBACK_ENTRY_LIMIT = 5
DEFAULT_NEWS_FALLBACK_TIMEOUT_SECONDS = 4
DEFAULT_NEWS_PRIORITY_CANDIDATES = 5
RSS_SOURCES_FILE = Path(__file__).resolve().parents[2] / "config" / "rss_sources.json"


def _configure_logging() -> None:
    level_name = (os.environ.get("LOG_LEVEL") or "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, level_name, logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _resolve_recipients(override: str | None) -> list[str]:
    if override:
        return [r.strip() for r in override.split(",") if r.strip()]
    raw = os.environ.get("MAIL_BRIDGE_TO") or os.environ.get("X_POST_MAIL_TO") or ""
    return [r.strip() for r in raw.split(",") if r.strip()]


def _resolve_sender() -> str | None:
    # Match the env precedence mail_delivery_bridge honours so the
    # observed From: address matches the publish-notice convention.
    return (
        os.environ.get("MAIL_BRIDGE_FROM")
        or os.environ.get("NOTIFY_FROM")
        or os.environ.get("MAIL_BRIDGE_SMTP_USERNAME")
        or None
    )


def _resolve_reply_to() -> str | None:
    return os.environ.get("MAIL_BRIDGE_REPLY_TO") or os.environ.get("NOTIFY_REPLY_TO")


def _resolve_max_db_staleness_days() -> int:
    raw = (
        os.environ.get("X_POST_MAIL_MAX_DB_STALENESS_DAYS")
        or str(DEFAULT_MAX_DB_STALENESS_DAYS)
    ).strip()
    try:
        return int(raw)
    except ValueError:
        LOG.warning(
            "Invalid X_POST_MAIL_MAX_DB_STALENESS_DAYS=%r; using default %d",
            raw,
            DEFAULT_MAX_DB_STALENESS_DAYS,
        )
        return DEFAULT_MAX_DB_STALENESS_DAYS


def _resolve_dedup_min_candidates() -> int:
    raw = (
        os.environ.get("X_POST_MAIL_DEDUP_MIN_CANDIDATES")
        or str(DEFAULT_DEDUP_MIN_CANDIDATES)
    ).strip()
    try:
        value = int(raw)
    except ValueError:
        LOG.warning(
            "Invalid X_POST_MAIL_DEDUP_MIN_CANDIDATES=%r; using default %d",
            raw,
            DEFAULT_DEDUP_MIN_CANDIDATES,
        )
        return DEFAULT_DEDUP_MIN_CANDIDATES
    if value < 0:
        LOG.warning(
            "Invalid X_POST_MAIL_DEDUP_MIN_CANDIDATES=%r; using default %d",
            raw,
            DEFAULT_DEDUP_MIN_CANDIDATES,
        )
        return DEFAULT_DEDUP_MIN_CANDIDATES
    return value


def _resolve_lineup_focus_min_candidates() -> int:
    raw = (
        os.environ.get("X_POST_MAIL_LINEUP_FOCUS_MIN_CANDIDATES")
        or str(DEFAULT_LINEUP_FOCUS_MIN_CANDIDATES)
    ).strip()
    try:
        value = int(raw)
    except ValueError:
        LOG.warning(
            "Invalid X_POST_MAIL_LINEUP_FOCUS_MIN_CANDIDATES=%r; using default %d",
            raw,
            DEFAULT_LINEUP_FOCUS_MIN_CANDIDATES,
        )
        return DEFAULT_LINEUP_FOCUS_MIN_CANDIDATES
    if value < 0:
        LOG.warning(
            "Invalid X_POST_MAIL_LINEUP_FOCUS_MIN_CANDIDATES=%r; using default %d",
            raw,
            DEFAULT_LINEUP_FOCUS_MIN_CANDIDATES,
        )
        return DEFAULT_LINEUP_FOCUS_MIN_CANDIDATES
    return value


def _lineup_focus_disabled() -> bool:
    raw = (os.environ.get("X_POST_MAIL_LINEUP_FOCUS_DISABLED") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _news_fallback_disabled() -> bool:
    raw = (os.environ.get("X_POST_MAIL_NEWS_FALLBACK_DISABLED") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _data_split_enabled() -> bool:
    """448: env flag for 差別化データ split surprise 候補 (inning/venue)。

    Default OFF。 ON 時のみ pick_candidates 後に data_split 候補を append する。
    flag OFF では既存挙動完全不変 (rollback 余地)。
    """
    raw = (os.environ.get("ENABLE_X_POST_DATA_SPLIT") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _data_split_max_per_run() -> int:
    """448: data_split 候補数 / fire の上限 (default 2)。"""
    return _resolve_int_env("X_POST_DATA_SPLIT_MAX", 2, min_value=0)


def _data_angles_enabled() -> bool:
    """2026-06-11 角度 v2 (勝利相関 / 対戦別split / 歴代通算チェイス) の env flag。

    Default OFF。 ON 時のみ pick_candidates 後に角度候補を append する。
    flag OFF では既存挙動完全不変 (rollback 余地)。
    """
    raw = (os.environ.get("ENABLE_X_POST_DATA_ANGLES") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _data_angles_max_per_run() -> int:
    """角度 v2 候補数 / fire の上限 (default 3 = 各角度 1 本)。"""
    return _resolve_int_env("X_POST_DATA_ANGLES_MAX", 3, min_value=0)


def _roster_move_enabled() -> bool:
    """2026-06-12 登録抹消速報 (Tigers型、 NPB公示) の env flag。 Default OFF。"""
    raw = (os.environ.get("ENABLE_X_POST_ROSTER_MOVES") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _milestone_enabled() -> bool:
    """2026-06-12 節目達成🎉 (chikupn型、 通算節目の跨ぎ検出) の env flag。 Default OFF。"""
    raw = (os.environ.get("ENABLE_X_POST_MILESTONE") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _rarity_enabled() -> bool:
    """2026-06-12 今季初・以来 (chikupn型、 希少事象) の env flag。 Default OFF。"""
    raw = (os.environ.get("ENABLE_X_POST_RARITY") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _salary_value_enabled() -> bool:
    """2026-06-12 年俸コスパ (データ×年俸クロス、 バーゲン型のみ) の env flag。

    Default OFF。 flag OFF では既存挙動完全不変 (rollback 余地)。
    """
    raw = (os.environ.get("ENABLE_X_POST_SALARY_VALUE") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _pregame_preview_enabled() -> bool:
    """2026-06-12 試合前見どころ (今日の試合プレビュー) の env flag。

    Default OFF。 flag OFF では既存挙動完全不変 (rollback 余地)。
    """
    raw = (os.environ.get("ENABLE_X_POST_PREGAME_PREVIEW") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _on_this_day_enabled() -> bool:
    """2026-06-12 角度③ あの日の巨人 (on this day 歴史枠) の env flag。

    Default OFF。 flag OFF では既存挙動完全不変 (rollback 余地)。
    """
    raw = (os.environ.get("ENABLE_X_POST_ON_THIS_DAY") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _legend_compare_enabled() -> bool:
    """2026-06-12 角度① 新旧比較 (同年齢レジェンド対比) の env flag。

    Default OFF。 flag OFF では既存挙動完全不変 (rollback 余地)。
    """
    raw = (os.environ.get("ENABLE_X_POST_LEGEND_COMPARE") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _weekly_mvp_enabled() -> bool:
    """2026-06-12 角度⑤ 週間MVP (月曜定番企画) の env flag。

    Default OFF。 ON でも builder 側が月曜以外は空 list を返す。
    flag OFF では既存挙動完全不変 (rollback 余地)。
    """
    raw = (os.environ.get("ENABLE_X_POST_WEEKLY_MVP") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _topical_boost_enabled() -> bool:
    """2026-06-11 ①話題選手連動: RSSHub 巨人系 X 言及数で候補を先頭寄せする env flag。

    Default OFF。 並び替えと why_now 追記のみで、 本文・数字は変えない。
    """
    raw = (os.environ.get("ENABLE_X_POST_TOPICAL_BOOST") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _video_radar_enabled() -> bool:
    """451: env flag for 動画レーダー (公式/OB/メディア YouTube の懐かし/ファン動画候補)。

    Default OFF。 ON 時のみ pick_candidates 後に video_radar 候補を append。
    flag OFF では既存挙動完全不変 (rollback 余地)。
    """
    raw = (os.environ.get("ENABLE_X_POST_VIDEO_RADAR") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _video_radar_max_per_run() -> int:
    """451: 動画候補数 / fire の上限 (default 3)。"""
    return _resolve_int_env("X_POST_VIDEO_RADAR_MAX", 3, min_value=0)


def _quote_captions_enabled() -> bool:
    """451: 「今日の動画引用キャプション」をメールに出すか (default OFF)。"""
    raw = (os.environ.get("ENABLE_X_POST_QUOTE_CAPTIONS") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _reply_candidates_enabled() -> bool:
    """451: 「リプライ候補」(大手投稿への返信、 インプ近道) をメールに出すか (default OFF)。"""
    raw = (os.environ.get("ENABLE_X_POST_REPLY_CANDIDATES") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _reply_candidates_max_per_run() -> int:
    """リプライ候補数 / fire の上限。 報知返信欄を厚くするため default 3。"""
    return _resolve_int_env("X_POST_REPLY_CANDIDATES_MAX", 3, min_value=0)


def _news_scrape_enabled() -> bool:
    """@Tigers_140609 風の速報スクレイプ型 post をメール便に出すか (default OFF)。

    ON 時、 queue 417 で drain 済みの 報知/サンスポ 記事 facts を
    news_scrape_x_post で 280 字速報に整形し、 同じメールに最大 N 件 append。
    flag OFF では既存挙動完全不変 (rollback 余地)。
    """
    raw = (os.environ.get("ENABLE_X_POST_NEWS_SCRAPE") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _news_scrape_max_per_run() -> int:
    """速報スクレイプ候補数 / fire の上限 (default 2、 LLM 費用を抑える)。"""
    return _resolve_int_env("X_POST_MAIL_NEWS_SCRAPE_MAX", 2, min_value=0)


def _x_post_player_dedup_enabled() -> bool:
    """1メール内で同一選手の候補を1つに圧縮するか (default ON)。

    user 2026-06-20: branding / 速報スクレイプ / 報知リプ が同じ主役選手 (例: 増田
    大輝の初猛打賞) を別々に拾い、1通に同一選手が2件以上載って他ニュースの枠を
    潰す問題への対策。OFF で従来挙動 (rollback)。
    """
    raw = (os.environ.get("X_POST_MAIL_PLAYER_DEDUP") or "1").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _candidate_player_key(cand) -> str:
    return lane._normalize_player_name(getattr(cand, "focus_player", "") or "")


def _dedupe_candidates_by_player(candidates, *, log=None):
    """同一メール内で focus_player が重複する候補を先頭1件に圧縮する。

    候補リストは優先度順に積まれている前提で、各選手の最初の1件を残し以降を落とす
    (branding と 速報スクレイプ が同じ選手を別経路で拾った重複を最終段で除去)。
    focus_player 不明の候補は対象外でそのまま残す。flag OFF なら素通り。
    """
    if not _x_post_player_dedup_enabled():
        return list(candidates)
    seen: set[str] = set()
    kept: list = []
    dropped: list = []
    for cand in candidates:
        key = _candidate_player_key(cand)
        if key and key in seen:
            dropped.append(cand)
            continue
        if key:
            seen.add(key)
        kept.append(cand)
    if dropped and log is not None:
        log.info(
            "player_dedup: 同一選手の重複 %d 件を除去 (残り %d 件) players=%s",
            len(dropped), len(kept),
            ",".join(sorted({_candidate_player_key(c) for c in dropped if _candidate_player_key(c)})),
        )
    return kept


def _build_news_scrape_candidates(queue_items, *, gemini_key, max_count, log, exclude_player_keys=None):
    """queue 417 で drain 済みの記事 (article_info) から @Tigers_140609 風の
    速報スクレイプ候補 (lane.Candidate) を最大 max_count 件作る。

    facts は記事の title / summary / 抽出引用のみ。 news_scrape_x_post の
    system prompt が「facts 外の数字/固有名詞/引用を作らない」を強制するため
    数字 hallucination は起きない。 加えて lane._is_safe_post_text と 280 字
    上限で二重 gate。 LLM 失敗 / 空 / unsafe は個別 skip (silent)。

    ``exclude_player_keys`` (正規化済み選手名 set) に含まれる選手、および本関数
    内で既に採用した選手は skip する。同じメール内で同一選手のポストが branding /
    別記事 経由で重複するのを防ぎ (user 2026-06-20)、空いた枠を別ニュースに回す。
    重複判定は Gemini 呼び出しの前に行うため LLM コストも無駄にしない。

    返値は ``(candidate, source_item)`` の list。 caller は source_item を
    processed_queue_items に積んで再 drain (次 fire での重複生成) を防ぐ。
    """
    out: list[tuple[lane.Candidate, object]] = []
    if max_count <= 0 or not gemini_key or not queue_items:
        return out
    try:
        from src import news_scrape_x_post as _nsx
    except Exception as exc:  # noqa: BLE001
        log.info("news_scrape skip: import failed err=%r", exc)
        return out
    seen_player_keys: set[str] = {
        k for k in (exclude_player_keys or set()) if k
    } if _x_post_player_dedup_enabled() else set()
    for item in queue_items:
        if len(out) >= max_count:
            break
        title = (getattr(item, "title", "") or "").strip()
        summary = (getattr(item, "summary", "") or "").strip()
        source_url = (getattr(item, "source_url", "") or "").strip()
        players = list(getattr(item, "player_canonical", []) or [])
        if not title:
            continue
        player_key = lane._normalize_player_name(players[0]) if players else ""
        if player_key and player_key in seen_player_keys:
            log.info(
                "news_scrape skip dup-player source_url=%s player=%s (枠を別ニュースへ)",
                source_url, player_key,
            )
            continue
        facts: dict = {"見出し": title}
        if summary:
            facts["概要"] = summary
        quotes = _nsx.extract_quotes_from_text(summary or title)
        if quotes:
            facts["コメント"] = quotes
        if players:
            facts["選手"] = "、".join(players[:3])
        try:
            text = _nsx.format_scrape_post(facts, api_key=gemini_key).strip()
        except Exception as exc:  # noqa: BLE001
            log.warning("news_scrape build skip source_url=%s err=%r", source_url, exc)
            continue
        if not text or len(text) > lane.X_CHAR_LIMIT or not lane._is_safe_post_text(text):
            log.info("news_scrape drop source_url=%s reason=empty/oversize/unsafe", source_url)
            continue
        focus = players[0] if players else ""
        sig = "news_scrape|" + _hashlib.sha1(
            (source_url or title).encode("utf-8")
        ).hexdigest()[:16]
        cand = lane.Candidate(
            title=f"速報スクレイプ｜{title[:24]}",
            metric=lane._NEWS_SCRAPE_METRIC,
            period_label="速報",
            draft_text=text,
            char_count=len(text),
            post_text=text,
            signature=sig,
            focus_player=focus,
            source_material_type="news_scrape",
        )
        out.append((cand, item))
        if player_key:
            seen_player_keys.add(player_key)
        log.info("news_scrape built source_url=%s text_len=%d", source_url, len(text))
    return out


_OFFICIAL_REPLY_HANDLE = "TokyoGiants"
_DEFAULT_REPLY_TARGET_HANDLES = ("hochi_giants",)


def _unique_reply_handles(handles: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for handle in handles:
        clean = (handle or "").strip().lstrip("@")
        if not clean:
            continue
        key = clean.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(clean)
    return out


def _reply_target_handles() -> list[str]:
    """リプライ候補の対象 X handle。

    既存 env / default はそのまま維持し、読売巨人軍公式 ``TokyoGiants`` を
    repo 側で補完する。Cloud Run env や Scheduler を変えずに、mail の手動リプ
    候補だけを追加するための narrow hook。
    """
    raw = (os.environ.get("X_POST_REPLY_TARGET_HANDLES") or "").strip()
    handles = [h.strip().lstrip("@") for h in raw.split(",") if h.strip()]
    if not handles:
        handles = list(_DEFAULT_REPLY_TARGET_HANDLES)
    return _unique_reply_handles([*handles, _OFFICIAL_REPLY_HANDLE])


def _reply_candidate_mail_labels(handle: str) -> tuple[str, str, str, str, tuple[str, ...]]:
    lower = (handle or "").strip().lstrip("@").lower()
    if lower == "hochi_giants":
        return (
            "報知リプ候補",
            "報知投稿への返信=リアルタイムの返信欄で露出",
            "hochi_reply",
            lane._HOCHI_REPLY_METRIC,
            ("reply:hochi", "manual_only"),
        )
    if lower == _OFFICIAL_REPLY_HANDLE.lower():
        return (
            "公式リプ候補",
            "読売巨人軍公式投稿への返信=公式投稿の返信欄で露出",
            "official_reply",
            lane._REPLY_CANDIDATE_METRIC,
            ("reply:official", "manual_only"),
        )
    return (
        "リプライ候補",
        "大手投稿に返信=インプ近道",
        "reply_candidate",
        lane._REPLY_CANDIDATE_METRIC,
        ("manual_only",),
    )


def _fan_reply_enabled() -> bool:
    """ファンアカ (フーガ/缶詰) 投稿へのリプ候補をメールに出すか (default OFF)。

    2026-06-05 user GO: 巨人系ファンアカの試合反応に value-add リプ (同調でなく数字/逆角度を
    1個足す) を mail で届け、 user が手動リプ。 自動投稿はしない。 LLM コストは既存の
    per-fire budget (X_POST_MAIL_MAX_LLM_PER_RUN、 報知リプ等と共有=天井を上げない)。
    """
    raw = (os.environ.get("ENABLE_X_POST_FAN_REPLY") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _fan_reply_max_per_run() -> int:
    """ファンリプ候補数 / fire の上限。 少量 試験運用なので default 2。"""
    return _resolve_int_env("X_POST_FAN_REPLY_MAX", 2, min_value=0)


def _fan_reply_target_handles() -> list[str]:
    """ファンリプの対象 X handle。 default = フーガ + 缶詰 (2026-06-05 user 指定)。"""
    raw = (
        os.environ.get("X_POST_FAN_REPLY_TARGET_HANDLES")
        or "EH87EazmV9D2eSw,kandume92"
    ).strip()
    handles = [h.strip().lstrip("@") for h in raw.split(",") if h.strip()]
    return handles or ["EH87EazmV9D2eSw", "kandume92"]


def _reply_llm_enabled() -> bool:
    """返信文の LLM 生成。 2026-06-04 user 方針で default ON (リプもヨシラバー風)。

    旧 deterministic テンプレ (「見どころありますね/意見分かれそう」 の空虚な47字) を
    廃し、 報知投稿への返信も flash-lite voice で書く。 コストは per-fire LLM budget
    (X_POST_MAIL_MAX_LLM_PER_RUN) で上限管理。 明示的に切りたい時のみ
    ENABLE_X_POST_REPLY_LLM=0 で OFF。
    """
    raw = (os.environ.get("ENABLE_X_POST_REPLY_LLM") or "").strip().lower()
    if not raw:
        return True
    return raw not in {"0", "false", "no", "off"}


def _voice_only_enabled() -> bool:
    """2026-06-04 user 方針: メールを「ヨシラバー風 voice」候補のみにする (default ON)。

    ON 時、 compose 直前に DB ランキング表 (候補1型) / data_split の生データ枠を
    出力から落とす (voice metric allowlist で残す)。 voice が 0 件に枯れた便だけ
    元候補へ fallback して scheduled mail を空にしない。 明示的に旧挙動へ戻す時のみ
    X_POST_MAIL_VOICE_ONLY=0。
    """
    raw = (os.environ.get("X_POST_MAIL_VOICE_ONLY") or "").strip().lower()
    if not raw:
        return True
    return raw not in {"0", "false", "no", "off"}


def _video_radar_llm_enabled() -> bool:
    """451: 引用RTコメントを Gemini 3.1 Flash Lite で生成するか (default OFF)。

    OFF なら LLM なしの出来事 template (¥0)。 ON で品質優先 (既存 branding と同 model、
    従量課金。 2026-05-22 ルールに従い deploy 後 billing 実測)。
    """
    raw = (os.environ.get("ENABLE_X_POST_VIDEO_RADAR_LLM") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _make_voiced_comment_fn(now_jst, subject):
    """A/B (2026-06-01): フーガ+缶詰 voice で text に反応する短文を返す closure を作る。

    news_opinion (A) / data-split (B) を全面 voice 化するための共通 factory。 key 無し /
    import 失敗 → None を返し、 caller (builder) は従来の安全テンプレに graceful fallback。
    voice は `build_quote_rt_comment` (= `_build_system_prompt` 経由の合成 voice + 時間帯トーン)。
    """
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMMA_BRANDING_GEMINI_API_KEY") or ""
    if not key:
        return None
    try:
        from src import x_post_branding_gen as _xbg
    except Exception:  # noqa: BLE001
        return None

    def _fn(text, player, _k=key, _g=_xbg, _now=now_jst, _s=subject):
        return _g.build_quote_rt_comment(text, player, gemini_api_key=_k, now=_now, subject=_s)

    return _fn


def _gemini_branding_enabled() -> bool:
    """392: env flag for Gemini Flash Lite + Tavily REST branding candidate.

    Default OFF。 ON 時のみ news_opinion fallback を skip して Gemini Flash Lite 候補
    を mail に append する。 flag OFF では既存挙動完全不変。
    """
    raw = (os.environ.get("X_POST_MAIL_GEMMA_GEN_ENABLED") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _gemini_branding_max_per_run() -> int:
    """392: Gemini Flash Lite 候補数 / fire の上限 (default 2)。"""
    return _resolve_int_env(
        "X_POST_MAIL_GEMMA_GEN_MAX",
        2,
        min_value=0,
    )


def _gemini_branding_all_mode() -> bool:
    """2026-05-22 user request: rebrand every data-ranking candidate via Gemini Flash Lite
    branding (alternating fuuga / kandume persona) instead of appending a
    fixed-count of Gemini Flash Lite posts on top. Default OFF — flag-gate so the
    append-only mode stays the rollback baseline.
    """
    raw = (os.environ.get("X_POST_MAIL_GEMMA_BRANDING_ALL") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _fan_voice_enabled() -> bool:
    """397: env flag for fan_voice (参考) candidate.

    Default OFF。 ON 時のみ x-post-mail-evening (17:30) / postgame
    (22:30) 便で fan_voice candidate を append する。 flag OFF では
    既存挙動完全不変。
    """
    raw = (os.environ.get("X_POST_MAIL_FAN_VOICE_ENABLED") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _fan_voice_max_per_run() -> int:
    """397: fan_voice 候補数 / fire の上限 (default 2)。"""
    return _resolve_int_env(
        "X_POST_MAIL_FAN_VOICE_MAX",
        2,
        min_value=0,
    )


def _is_fan_voice_fire_window(now_jst: datetime) -> bool:
    """397: 試合時間帯 (= postgame 便相当) なら True。

    2026-05-20 user 方針更新: 試合中はファンツイートがまだ熟しておらず
    (= 試合開始直後の 17:30 evening は意味薄)、 試合がある程度進んだ
    19:00 以降のツイートに価値がある。 現スケジュール 5 便 (07:00 /
    12:00 / 15:00 / 17:30 / 22:30) のうち 19:00 以降は 22:30 postgame
    のみが該当する。

    手動 fire / cron drift を考慮し 19:00-23:59 を許容レンジ。
    朝 / 昼 / 午後 / 17:30 evening は False (= fan_voice 発動なし)。
    """
    if now_jst.tzinfo is None:
        return False
    if lane.is_extra_game_window(now_jst):
        return True
    minutes_since_midnight = now_jst.hour * 60 + now_jst.minute
    # 19:00 - 23:59 を試合進行〜試合直後 window とする
    return 19 * 60 <= minutes_since_midnight <= 23 * 60 + 59


def _monday_game_window_skip_enabled() -> bool:
    """月曜の試合系 dense window を止める cost guard。

    user 2026-06-07: 「月曜日は試合がない」。祝日などで月曜開催がある時だけ
    X_POST_MAIL_ALLOW_MONDAY_GAME_WINDOWS=1 で一時解除する。
    """
    raw = (os.environ.get("X_POST_MAIL_ALLOW_MONDAY_GAME_WINDOWS") or "").strip().lower()
    return raw not in {"1", "true", "yes", "on"}


def _before_7am_skip_enabled() -> bool:
    """user-facing X post mail は 7:00 JST から。

    Scheduler 側の反映漏れや手動 fire で早朝に起動しても、通常は何も送らない。
    必要な検証時だけ X_POST_MAIL_ALLOW_BEFORE_7AM=1 で解除する。
    """
    raw = (os.environ.get("X_POST_MAIL_ALLOW_BEFORE_7AM") or "").strip().lower()
    return raw not in {"1", "true", "yes", "on"}


def _live_duplicate_player_cooldown_hours() -> int:
    """試合中15分便の同一選手重複を抑える短時間 cooldown。

    既存の 168h player history はDB候補の広い分散用。こちらは試合中の
    reply/video/fan reply だけに使い、直近便で出た同じ選手の LLM 生成を
    先に止める。0 で無効化。
    """
    return _resolve_int_env("X_POST_MAIL_LIVE_DUPLICATE_PLAYER_COOLDOWN_HOURS", 1, min_value=0)


def _live_duplicate_player_cooldown_active(now_jst: datetime) -> bool:
    return (
        lane.x_impression_timing_label(now_jst)
        == lane._X_IMPRESSION_TIMING_LABELS["in_game_strong"]
    )


def _is_before_7am_jst(now_jst: datetime) -> bool:
    if now_jst.tzinfo is None:
        now_jst = now_jst.replace(tzinfo=ZoneInfo("Asia/Tokyo"))
    else:
        now_jst = now_jst.astimezone(ZoneInfo("Asia/Tokyo"))
    return now_jst.hour < 7


def _is_monday_game_window(now_jst: datetime) -> bool:
    if now_jst.tzinfo is None:
        now_jst = now_jst.replace(tzinfo=ZoneInfo("Asia/Tokyo"))
    else:
        now_jst = now_jst.astimezone(ZoneInfo("Asia/Tokyo"))
    if now_jst.weekday() != 0:  # Monday
        return False
    label = lane.x_impression_timing_label(now_jst)
    game_labels = {
        lane._X_IMPRESSION_TIMING_LABELS["pregame_db"],
        lane._X_IMPRESSION_TIMING_LABELS["lineup"],
        lane._X_IMPRESSION_TIMING_LABELS["in_game_strong"],
        lane._X_IMPRESSION_TIMING_LABELS["postgame_peak"],
    }
    return label in game_labels


def _resolve_int_env(name: str, default: int, *, min_value: int = 0) -> int:
    raw = (os.environ.get(name) or str(default)).strip()
    try:
        value = int(raw)
    except ValueError:
        LOG.warning("Invalid %s=%r; using default %d", name, raw, default)
        return default
    if value < min_value:
        LOG.warning("Invalid %s=%r; using default %d", name, raw, default)
        return default
    return value


def _resolve_news_priority_candidates(max_candidates: int) -> int:
    value = _resolve_int_env(
        "X_POST_MAIL_NEWS_PRIORITY_CANDIDATES",
        DEFAULT_NEWS_PRIORITY_CANDIDATES,
        min_value=0,
    )
    return max(0, min(value, max_candidates))


def _fetch_today_lineup_focus_names() -> list[str]:
    """Scrape today's Giants lineup and return canonical player names.

    Failure is a soft fallback: the X post mail still works from the
    existing data-ranking pool when lineup is not published yet or Yahoo
    changes markup.
    """
    if _lineup_focus_disabled():
        LOG.info("Lineup focus disabled by X_POST_MAIL_LINEUP_FOCUS_DISABLED")
        return []
    try:
        from src.rss_fetcher import fetch_today_giants_lineup_stats_from_yahoo
    except Exception as exc:  # noqa: BLE001
        LOG.warning("Lineup focus import failed; continuing without focus: %r", exc)
        return []
    try:
        rows = fetch_today_giants_lineup_stats_from_yahoo()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("Lineup focus fetch failed; continuing without focus: %r", exc)
        return []
    names = lane.focus_player_names_from_lineup_rows(rows)
    if names:
        LOG.info("Lineup focus enabled: %d players %s", len(names), names)
    else:
        LOG.info("Lineup focus unavailable: no lineup rows returned")
    return names


def _load_news_fallback_sources(path: Path = RSS_SOURCES_FILE) -> list[dict]:
    try:
        sources = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        LOG.warning("news/opinion fallback source load failed: %r", exc)
        return []
    out: list[dict] = []
    for source in sources:
        source_type = str(source.get("type") or "")
        roles = source.get("role") or []
        if isinstance(roles, str):
            roles = [roles]
        if source_type not in {"news", "social_news", "tag_scrape"}:
            continue
        if source_type == "social_news" and "article_source" not in roles:
            continue
        if source_type == "tag_scrape" and roles and "article_source" not in roles:
            continue
        if source_type == "tag_scrape" and not str(source.get("scraper") or "").strip():
            continue
        url = str(source.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        out.append(source)
    return out


def _fetch_feed_entries(source: dict, *, timeout_seconds: int) -> list[dict]:
    if str(source.get("type") or "") == "tag_scrape":
        from src import tag_page_scraper

        article_limit = int(source.get("article_limit") or DEFAULT_NEWS_FALLBACK_ENTRY_LIMIT)
        article_limit = max(1, min(article_limit, DEFAULT_NEWS_FALLBACK_ENTRY_LIMIT))
        return tag_page_scraper.fetch_tag_page_entries(
            scraper=str(source.get("scraper") or ""),
            url=str(source.get("url") or ""),
            max_age_days=int(source.get("max_age_days") or 1),
            article_limit=article_limit,
            logger=LOG,
        )
    try:
        import feedparser
    except Exception as exc:  # noqa: BLE001
        LOG.warning("news/opinion fallback feedparser import failed: %r", exc)
        return []
    url = str(source.get("url") or "")
    req = urlrequest.Request(
        url,
        headers={
            "User-Agent": "yoshilover-x-post-mail/1.0",
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
        },
    )
    try:
        with urlrequest.urlopen(req, timeout=timeout_seconds) as response:  # noqa: S310
            data = response.read()
    except (OSError, URLError) as exc:
        LOG.warning(
            "news/opinion fallback fetch failed source=%s url=%s error=%r",
            source.get("name"),
            url,
            exc,
        )
        return []
    parsed = feedparser.parse(data)
    return list(parsed.entries or [])


def _entry_text(entry: dict) -> tuple[str, str, str]:
    title = str(entry.get("title") or "").strip()
    link = str(entry.get("link") or entry.get("id") or "").strip()
    summary = str(
        entry.get("summary")
        or entry.get("description")
        or entry.get("subtitle")
        or ""
    ).strip()
    return title, link, summary


def _entry_published_dt(entry: dict):
    """feed entry の公開日時を tz-aware datetime に。 取れなければ None。

    feedparser は ``published_parsed`` (UTC struct_time) を最優先。 無ければ
    ``published`` / ``updated`` / ``pubDate`` 文字列を RFC1123 / ISO で parse。
    """
    from datetime import datetime as _dt, timezone as _tz
    import time as _time
    from email.utils import parsedate_to_datetime as _p
    st = entry.get("published_parsed") or entry.get("updated_parsed")
    if st is not None:
        try:
            return _dt.fromtimestamp(_time.mktime(st) - _time.timezone, tz=_tz.utc)
        except (TypeError, ValueError, OverflowError):
            pass
    for k in ("published", "updated", "pubDate", "date"):
        raw = str(entry.get(k) or "").strip()
        if not raw:
            continue
        try:
            return _p(raw)
        except (TypeError, ValueError, IndexError):
            pass
        try:
            return _dt.fromisoformat(raw.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            pass
    return None


def _fetch_news_opinion_fallback_candidates(
    existing_candidates: list[lane.Candidate],
    *,
    max_candidates: int,
    now: datetime,
    recent_player_counts: dict[str, int] | None = None,
    comment_fn=None,
) -> list[lane.Candidate]:
    """Fill sparse data mails with source-backed news/opinion candidates.

    This fallback reads public RSS/Atom feeds only. It does not call WP,
    X API, LLMs, or the ``article_candidates`` table.
    """
    needed = max(0, max_candidates - len(existing_candidates))
    if needed <= 0:
        return []
    if _news_fallback_disabled():
        LOG.info("News/opinion fallback disabled by X_POST_MAIL_NEWS_FALLBACK_DISABLED")
        return []
    source_limit = _resolve_int_env(
        "X_POST_MAIL_NEWS_FALLBACK_SOURCE_LIMIT",
        DEFAULT_NEWS_FALLBACK_SOURCE_LIMIT,
        min_value=0,
    )
    entry_limit = _resolve_int_env(
        "X_POST_MAIL_NEWS_FALLBACK_ENTRY_LIMIT",
        DEFAULT_NEWS_FALLBACK_ENTRY_LIMIT,
        min_value=1,
    )
    timeout_seconds = _resolve_int_env(
        "X_POST_MAIL_NEWS_FALLBACK_TIMEOUT_SECONDS",
        DEFAULT_NEWS_FALLBACK_TIMEOUT_SECONDS,
        min_value=1,
    )
    if source_limit <= 0:
        return []
    existing_player_keys = {
        lane._normalize_player_name(c.focus_player)
        for c in existing_candidates
        if lane._normalize_player_name(c.focus_player)
    }
    history_player_counts = {
        lane._normalize_player_name(name): int(count or 0)
        for name, count in (recent_player_counts or {}).items()
        if lane._normalize_player_name(name) and int(count or 0) > 0
    }
    history_player_keys = set(history_player_counts)
    # フェーズ別鮮度窓 (試合中3h / 後6h / 前12h / 日中24h) を記事系にも統一適用。
    # 公開日時が取れない記事は「古くないと確認できない」ため strict に skip (user「古い記事はダメ」)。
    max_age_hours = lane.phase_freshness_max_age_hours(now)
    skipped_stale = 0
    skipped_no_date = 0
    seen_urls: set[str] = set()
    out: list[lane.Candidate] = []
    for source in _load_news_fallback_sources()[:source_limit]:
        if len(out) >= needed:
            break
        for entry in _fetch_feed_entries(source, timeout_seconds=timeout_seconds)[:entry_limit]:
            if len(out) >= needed:
                break
            title, link, summary = _entry_text(entry)
            if not title or not link or link in seen_urls:
                continue
            pub_dt = _entry_published_dt(entry)
            if pub_dt is None:
                skipped_no_date += 1
                continue
            if (now - pub_dt).total_seconds() / 3600.0 > max_age_hours:
                skipped_stale += 1
                continue
            # 2026-06-01 user「コーチ監督も全員名前を入れて」: 選手のみ → 全員 (player ∪ member) で検出。
            player = lane.detect_giants_player_name(
                f"{title} {summary}",
                alias_map={**lane._load_giants_player_aliases(), **lane._load_giants_member_aliases()},
            )
            player_key = lane._normalize_player_name(player)
            if not player_key or player_key in existing_player_keys:
                continue
            if player_key in history_player_keys:
                LOG.info(
                    "news_opinion_fallback_player_history_skip source=%s "
                    "player=%s previous_count=%d url=%s",
                    source.get("name"),
                    player,
                    history_player_counts.get(player_key, 0),
                    link,
                )
                continue
            cand = lane.build_news_opinion_candidate(
                source_title=title,
                source_url=link,
                source_excerpt=summary,
                source_name=str(source.get("name") or ""),
                player_name=player,
                now=now,
                comment_fn=comment_fn,  # A: フーガ+缶詰 voice (None なら従来テンプレ)
            )
            if cand is None:
                continue
            out.append(cand)
            seen_urls.add(link)
            existing_player_keys.add(player_key)
            LOG.info(
                "news_opinion_fallback_candidate_added source=%s player=%s url=%s",
                source.get("name"),
                player,
                link,
            )
            # 併産 (user 2026-06-01「値段一緒なら両方ほしい」): 記事本文から本人コメントが
            # literal で取れれば、 たんぱく①「コメント速報」も追加 (LLM不使用・¥0)。 全 graceful。
            try:
                creq = urlrequest.Request(link, headers={"User-Agent": "yoshilover-x-post-mail/1.0"})
                with urlrequest.urlopen(creq, timeout=timeout_seconds) as cresp:  # noqa: S310
                    html_text = cresp.read().decode("utf-8", errors="replace")
                ccand = lane.build_player_comment_candidate(
                    member_name=player,
                    source_title=title,
                    source_url=link,
                    html_text=html_text,
                    source_name=str(source.get("name") or ""),
                    now=now,
                )
                if ccand is not None:
                    out.append(ccand)
                    LOG.info("player_comment_candidate_added player=%s url=%s", player, link)
            except Exception as _cexc:  # noqa: BLE001
                LOG.info("player_comment_skip url=%s: %r", link, _cexc)
    LOG.info(
        "news_opinion_fallback freshness max_age_h=%.1f added=%d skipped_stale=%d skipped_no_date=%d",
        max_age_hours,
        len(out),
        skipped_stale,
        skipped_no_date,
    )
    return out


def _build_fan_voice_candidates(
    existing_candidates: list[lane.Candidate],
    *,
    bucket_name: str,
    now: datetime,
    max_count: int,
    recent_player_counts: dict[str, int] | None = None,
    lookback_hours: int = 24,
) -> list[lane.Candidate]:
    """397: build 「(参考) 巨人ファン X 投稿」 candidates from GCS-cached
    fan_voice_pool entries (uploaded by yoshilover-fetcher).

    Filters:
    - tweet text length 20-280
    - text contains a verified Giants player name (NER via
      :func:`lane.detect_giants_player_name`)
    - URL not already present in another candidate of this mail
    - player not in 24h history (``recent_player_counts``)
    - player not already in current candidate list

    Returns up to ``max_count`` candidates, newest-first (by ``pub_iso``
    if available, else by ``ts``).
    """
    if max_count <= 0 or not bucket_name:
        return []
    try:
        entries = lane.load_recent_fan_voice_pool_entries(
            bucket_name,
            now,
            lookback_hours=lookback_hours,
        )
    except Exception as exc:  # noqa: BLE001 - silent skip per fan_voice contract
        LOG.warning("fan_voice load failed (silent skip): %r", exc)
        return []
    if not entries:
        LOG.info("fan_voice: 0 entries in GCS cache within last %dh", lookback_hours)
        return []
    # newest-first sort
    def _sort_key(rec: dict) -> str:
        return str(rec.get("pub_iso") or rec.get("ts") or "")
    entries = sorted(entries, key=_sort_key, reverse=True)

    existing_urls = {
        getattr(c, "signature", "") for c in existing_candidates
    }
    existing_player_keys = {
        lane._normalize_player_name(c.focus_player)
        for c in existing_candidates
        if lane._normalize_player_name(c.focus_player)
    }
    history_player_keys = {
        lane._normalize_player_name(name)
        for name, count in (recent_player_counts or {}).items()
        if lane._normalize_player_name(name) and int(count or 0) > 0
    }
    out: list[lane.Candidate] = []
    seen_handles: set[str] = set()
    for entry in entries:
        if len(out) >= max_count:
            break
        text = str(entry.get("text") or "").strip()
        url = str(entry.get("url") or "").strip()
        handle = str(entry.get("handle") or "").strip()
        if not text or not url:
            continue
        # diversity: at most 1 candidate per handle within one mail
        if handle and handle in seen_handles:
            LOG.info(
                "fan_voice_skip reason=handle_diversity handle=%s url=%s",
                handle, url,
            )
            continue
        player = lane.detect_giants_player_name(text)
        player_key = lane._normalize_player_name(player)
        if not player_key:
            LOG.info("fan_voice_skip reason=no_giants_player_in_text url=%s", url)
            continue
        if player_key in existing_player_keys:
            LOG.info(
                "fan_voice_skip reason=player_in_current_mail player=%s url=%s",
                player, url,
            )
            continue
        if player_key in history_player_keys:
            LOG.info(
                "fan_voice_skip reason=player_in_24h_history player=%s url=%s",
                player, url,
            )
            continue
        cand = lane.build_fan_voice_candidate(entry, detected_player=player)
        if cand is None:
            continue
        if cand.signature in existing_urls:
            continue
        out.append(cand)
        existing_player_keys.add(player_key)
        if handle:
            seen_handles.add(handle)
        LOG.info(
            "fan_voice_candidate_added handle=%s player=%s url=%s",
            handle, player, url,
        )
    LOG.info("fan_voice: built %d candidates (max=%d)", len(out), max_count)
    return out


def _backfill_dedup_starved_candidates(
    candidates: list[lane.Candidate],
    relaxed_candidates: list[lane.Candidate],
    *,
    max_candidates: int,
    recent_player_counts: dict[str, int] | None = None,
    min_candidates: int = 0,
) -> list[lane.Candidate]:
    """Keep fresh dedup-safe candidates first, then fill with relaxed ones.

    The 24h dedup gate is useful while there are enough alternative
    combos. When it leaves the mail nearly empty, the operator loses the
    actual review queue, so duplicate suppression must become a soft
    preference instead of a hard skip.

    397 originally allowed a Stage B override that put history players
    back when the mail was sparse. 436 follow-up removes that override:
    the user prefers fewer candidates over seeing the same player again
    and again in pitcher-rate Top10 tables.
    """
    merged = list(candidates)
    seen_signatures = {c.signature for c in merged if c.signature}
    history_player_keys = {
        lane._normalize_player_name(name)
        for name, count in (recent_player_counts or {}).items()
        if lane._normalize_player_name(name) and int(count or 0) > 0
    }
    seen_player_keys = {
        lane._normalize_player_name(c.focus_player)
        for c in merged
        if lane._normalize_player_name(c.focus_player)
    }
    player_dedup_skipped: list[lane.Candidate] = []
    for cand in relaxed_candidates:
        if len(merged) >= max_candidates:
            break
        if cand.signature and cand.signature in seen_signatures:
            continue
        cand_key = lane._normalize_player_name(cand.focus_player)
        if cand_key and (cand_key in seen_player_keys or cand_key in history_player_keys):
            LOG.info(
                "dedup_fallback_player_skip metric=%s period=%s player=%s reason=%s",
                cand.metric,
                cand.period_label,
                cand.focus_player,
                "in_current_mail" if cand_key in seen_player_keys else "in_24h_history",
            )
            player_dedup_skipped.append(cand)
            continue
        merged.append(cand)
        if cand.signature:
            seen_signatures.add(cand.signature)
        if cand_key:
            seen_player_keys.add(cand_key)
    if min_candidates > 0 and len(merged) < min_candidates and player_dedup_skipped:
        LOG.warning(
            "dedup_fallback_player_skip_kept count=%d current=%d min=%d "
            "reason=prefer_fewer_candidates_over_repeat_players",
            len(player_dedup_skipped),
            len(merged),
            min_candidates,
        )
    return merged


def _candidate_identity(candidate: lane.Candidate) -> str:
    if candidate.signature:
        return candidate.signature
    return "|".join(
        [
            str(candidate.metric or ""),
            str(candidate.period_label or ""),
            str(candidate.title or ""),
        ]
    )


def _resolve_gemini_api_keys() -> tuple[str, str]:
    """392: env var から Gemini / Tavily API key を読む。

    Cloud Run Job では Secret Manager binding 経由で ``GEMINI_API_KEY`` と
    ``TAVILY_API_KEY`` が env として渡る前提。 未設定なら空文字を返し、
    caller (Gemini Flash Lite builder) が None 返却で silent skip する。
    """
    gemini = (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("GOOGLE_API_KEY")
        or ""
    )
    tavily = os.environ.get("TAVILY_API_KEY") or ""
    return gemini, tavily


def _pick_gemini_branding_players(
    existing_candidates: list[lane.Candidate],
    *,
    lineup_focus_names: list[str] | None,
    recent_player_counts: dict[str, int] | None,
    max_count: int,
    cooldown_players: set[str] | None = None,
) -> list[tuple[str, str]]:
    """392: Gemini Flash Lite 生成対象の player を最大 max_count 件選ぶ。

    優先順位:
        1. lineup focus names (今日のスタメン): まだ既存 candidates に居ない player
        2. 既存 candidates の focus_player で db_fact_line を持つもの
        3. 既存 candidates の focus_player (DB fact line 空でも)
        4. 既存 candidates から取れない場合は giants_roster default を使わず空返却

    返り値: ``(player_name, db_fact_line)`` の tuple list。
    """
    if max_count <= 0:
        return []
    history = {k: v for k, v in (recent_player_counts or {}).items() if v}
    cooldown = cooldown_players or set()
    # 同一選手の過剰生成を抑える 2 段 gate (LLM 費用節約):
    #   1. cooldown: 直近 X_POST_MAIL_GEMMA_PLAYER_COOLDOWN_HOURS (既定 24h)
    #      以内に投稿済みの player は skip。試合中 / 翌日に同じ選手を何度も
    #      生成して費用を捨てるのを防ぐ。
    #   2. window cap: history window (X_POST_MAIL_PLAYER_HISTORY_HOURS、
    #      既定 168h=7d) 内の既出回数が
    #      X_POST_MAIL_GEMMA_PLAYER_MAX_PER_WINDOW (既定 2、 2026-05-25
    #      user 「同一選手 最高 2 回まで」 を生成側にも適用) 以上なら skip。
    max_per_window = _resolve_int_env(
        "X_POST_MAIL_GEMMA_PLAYER_MAX_PER_WINDOW", 2, min_value=1
    )
    seen_keys: set[str] = set()
    picks: list[tuple[str, str]] = []

    def _add(name: str, fact: str) -> None:
        nonlocal picks, seen_keys
        if len(picks) >= max_count:
            return
        n = str(name or "").strip()
        if not n:
            return
        key = lane._normalize_player_name(n)
        if not key or key in seen_keys:
            return
        if key in cooldown:
            # 直近に投稿済み → 再生成は費用の無駄なので skip
            return
        if history.get(key, 0) >= max_per_window:
            return
        seen_keys.add(key)
        picks.append((n, fact))

    # 1. lineup focus (今日のスタメン)
    for name in (lineup_focus_names or []):
        _add(name, "")
    # 2-3. 既存 candidates から (db_fact_line 持ち優先)
    candidates_with_fact = [c for c in existing_candidates if (c.db_fact_line or "").strip()]
    candidates_without_fact = [c for c in existing_candidates if not (c.db_fact_line or "").strip()]
    for cand in candidates_with_fact + candidates_without_fact:
        _add(cand.focus_player, cand.db_fact_line or "")
    return picks


def _rebrand_candidates_via_gemini(
    candidates: list[lane.Candidate],
    *,
    lineup_focus_names: list[str] | None,
    db_path: str | None,
    bucket_name: str | None,
) -> list[lane.Candidate]:
    """Replace each candidate's ``post_text`` with a Gemini Flash Lite branding rewrite.

    2026-05-22 user request: instead of appending a fixed-count of branding
    posts on top of data-ranking posts, rebrand every existing candidate so
    the whole mail comes out in ヨシラバー voice. Personas are mixed (alternating
    ``fuuga`` for even indices and ``kandume`` for odd) regardless of game-day
    time-of-day — caller asked for the mix, not the time-gated auto-switch.

    Behaviour notes:
    - 24h history gate (player overuse skip in the picker) is bypassed —
      the caller has already accepted these candidates via dedup fallback,
      so Gemini Flash Lite should rewrite them too.
    - ``focus_player`` / ``title`` / ``draft_text`` / ``signature`` are kept
      from the original candidate; only ``post_text`` and ``char_count``
      are replaced. ``draft_text`` keeps the analytical proof for the mail's
      "根拠データ" disclosure block.
    - On Gemini Flash Lite / Tavily failure (any of: missing API key, no Tavily results,
      validator drop), the original candidate is kept verbatim — the mail
      never drops a line because of a branding retry.

    Cost note: Tavily runs once per player (``"巨人 {player} 最新"``). 5 fires
    × N candidates per day vs the 1,000 credit / month limit — watch for
    overrun once this lane scales beyond ~6 candidates / fire.
    """
    if _xbg is None or not candidates:
        return candidates
    gemini_key, tavily_key = _resolve_gemini_api_keys()
    if not gemini_key or not tavily_key:
        LOG.warning(
            "Gemini Flash Lite rebrand skipped: missing API key (gemini=%s tavily=%s) — keeping data-ranking text",
            bool(gemini_key),
            bool(tavily_key),
        )
        return candidates

    from datetime import datetime, timezone, timedelta
    from dataclasses import replace as _dc_replace
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)

    fan_voice_snippet = ""
    if bucket_name:
        try:
            entries = lane.load_recent_fan_voice_pool_entries(
                bucket_name, now_jst, lookback_hours=24
            )
            if entries:
                top = entries[0]
                text_preview = str(top.get("text") or "").strip()[:120]
                handle = str(top.get("handle") or "").strip()
                if text_preview:
                    fan_voice_snippet = (
                        f"@{handle}: {text_preview}" if handle else text_preview
                    )
        except Exception as exc:  # noqa: BLE001
            LOG.info("fan_voice_snippet_skip reason=%r", exc)

    starting_pitcher_today = ""
    opponent_starter = ""
    try:
        from src.analysis.pregame_themes import fetch_today_starting_pitchers
        starting_pitcher_today, opponent_starter, _ = fetch_today_starting_pitchers()
    except Exception as exc:  # noqa: BLE001
        LOG.info("starting_pitcher_fetch_skip reason=%r", exc)

    lineup_change_summary = ""
    promotion_summary = ""
    if bucket_name:
        try:
            from src.analysis.daily_snapshot import (
                build_lineup_change_string,
                build_promotion_string,
            )
            if lineup_focus_names:
                lineup_change_summary = build_lineup_change_string(
                    bucket_name,
                    list(lineup_focus_names),
                    now_jst=now_jst,
                    logger=LOG,
                )
            try:
                roster_path = Path(__file__).resolve().parent.parent.parent / "config" / "giants_roster.json"
                roster_data = json.loads(roster_path.read_text(encoding="utf-8"))
                today_active = {
                    str(p.get("name") or "").strip()
                    for p in roster_data
                    if p.get("active") and p.get("role") == "player"
                }
                today_active = {n for n in today_active if n}
                if today_active:
                    promotion_summary = build_promotion_string(
                        bucket_name, today_active, now_jst=now_jst, logger=LOG
                    )
            except Exception as roster_exc:  # noqa: BLE001
                LOG.info("roster_snapshot_skip reason=%r", roster_exc)
        except Exception as snap_exc:  # noqa: BLE001
            LOG.info("daily_snapshot_skip reason=%r", snap_exc)

    rebranded: list[lane.Candidate] = []
    success_count = 0
    for idx, cand in enumerate(candidates):
        persona = "fuuga" if idx % 2 == 0 else "kandume"
        player = (cand.focus_player or "").strip()
        if not player:
            rebranded.append(cand)
            continue
        db_fact = ""
        if db_path:
            try:
                db_fact = _xbg.build_db_fact_line(player, db_path)
            except Exception as exc:  # noqa: BLE001
                LOG.warning(
                    "build_db_fact_line failed during rebrand (player=%s err=%r)",
                    player,
                    exc,
                )
                db_fact = ""
        fact = db_fact or (cand.db_fact_line or "")
        try:
            new_cand = _xbg.build_gemini_branding_candidate(
                player,
                gemini_api_key=gemini_key,
                tavily_api_key=tavily_key,
                db_fact_line=fact,
                persona=persona,
                logger=LOG,
                db_path=db_path or "",
                focused_players=list(lineup_focus_names) if lineup_focus_names else None,
                fan_voice_snippet=fan_voice_snippet,
                starting_pitcher_today=starting_pitcher_today,
                opponent_pitcher_canonical=opponent_starter,
                lineup_change_summary=lineup_change_summary,
                promotion_summary=promotion_summary,
            )
        except Exception as exc:  # noqa: BLE001
            LOG.warning(
                "rebrand_via_gemini failed player=%s persona=%s err=%r — keep original",
                player,
                persona,
                exc,
            )
            new_cand = None
        if new_cand is not None and (new_cand.post_text or "").strip():
            rebranded.append(
                _dc_replace(
                    cand,
                    post_text=new_cand.post_text,
                    char_count=len(new_cand.post_text),
                )
            )
            success_count += 1
        else:
            LOG.info(
                "rebrand_via_gemini kept original player=%s persona=%s "
                "(Gemini Flash Lite returned no text — Tavily / safety / API failure)",
                player,
                persona,
            )
            rebranded.append(cand)
    LOG.info(
        "Gemini Flash Lite rebrand: %d/%d candidates rewritten in brand voice (alternating fuuga/kandume)",
        success_count,
        len(candidates),
    )
    return rebranded


def _build_gemini_branding_candidates(
    existing_candidates: list[lane.Candidate],
    *,
    lineup_focus_names: list[str] | None,
    recent_player_counts: dict[str, int] | None,
    max_count: int,
    db_path: str | None = None,
    bucket_name: str | None = None,
    cooldown_players: set[str] | None = None,
) -> list[lane.Candidate]:
    """392: max_count 件まで Gemini Flash Lite branding candidate を生成。

    silent skip 設計: 例外 / Tavily 失敗 / Gemini Flash Lite 失敗 / validator drop で
    None 返却された分は単に出力 list から除外。 既存 mail は止めない。

    db_path が渡された場合、 player ごとに ``build_db_fact_line()`` で
    insight.db の今日試合 / player log / 直近連勝 を fact line に整形し、
    Gemini Flash Lite 入力 prompt に注入する (RAG hallucination 抑制)。 DB 該当 record
    が無ければ空 string、 caller fact (lineup pick の補助 fact) を fallback。
    """
    if _xbg is None:
        LOG.info(
            "Gemini Flash Lite branding skipped: src.x_post_branding_gen import failed at module load"
        )
        return []
    gemini_key, tavily_key = _resolve_gemini_api_keys()
    if not gemini_key or not tavily_key:
        LOG.warning(
            "Gemini Flash Lite branding skipped: missing API key (gemini=%s tavily=%s)",
            bool(gemini_key),
            bool(tavily_key),
        )
        return []
    players = _pick_gemini_branding_players(
        existing_candidates,
        lineup_focus_names=lineup_focus_names,
        recent_player_counts=recent_player_counts,
        max_count=max_count,
        cooldown_players=cooldown_players,
    )
    if not players:
        LOG.info("Gemini Flash Lite branding skipped: no eligible players from lineup/candidates")
        return []
    out: list[lane.Candidate] = []

    # 試合 in DB + 勝利時は roundup mode を 1 件 priority で fire (時間帯
    # 問わず)。 朝 fire でも前夜の勝利 game が DB にあれば roundup 出せる。
    # roundup fact line が空 (no game / loss / draw) なら single-player のみ。
    # 今日試合が DB に無ければ昨日も試す (朝 fire で前夜試合を拾うため)。
    from datetime import datetime, timezone, timedelta
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)
    roundup_added = False
    roundup_fact = ""
    if db_path:
        for offset in (0, 1):
            target_date = (now_jst - timedelta(days=offset)).strftime("%Y-%m-%d")
            try:
                rf = _xbg.build_team_roundup_fact_line(db_path, target_date=target_date)
            except Exception as exc:  # noqa: BLE001
                LOG.warning("build_team_roundup_fact_line failed err=%r", exc)
                rf = ""
            if rf:
                roundup_fact = rf
                LOG.info("roundup fact found at offset=%d (date=%s)", offset, target_date)
                break
        if roundup_fact:
            try:
                rc = _xbg.build_team_roundup_candidate(
                    roundup_fact,
                    gemini_api_key=gemini_key,
                    tavily_api_key=tavily_key,
                    logger=LOG,
                )
            except Exception as exc:  # noqa: BLE001
                LOG.warning("build_team_roundup_candidate failed err=%r", exc)
                rc = None
            if rc is not None:
                out.append(rc)
                roundup_added = True
                LOG.info("Gemini Flash Lite roundup candidate appended (postgame win)")

    # roundup が出た時は残り枠 = max_count - 1、 出てない時は max_count 全部 single-player
    remaining = max_count - (1 if roundup_added else 0)
    if remaining <= 0:
        return out
    # 414 axis E7 wire: fan_voice_pool から直近 24h の 1 件を snippet として注入
    # (試合前 prompt themes に組み込まれる、 fault-tolerant)
    fan_voice_snippet = ""
    if bucket_name:
        try:
            entries = lane.load_recent_fan_voice_pool_entries(
                bucket_name, now_jst, lookback_hours=24
            )
            if entries:
                top = entries[0]
                text_preview = str(top.get("text") or "").strip()[:120]
                handle = str(top.get("handle") or "").strip()
                if text_preview:
                    fan_voice_snippet = (
                        f"@{handle}: {text_preview}" if handle else text_preview
                    )
        except Exception as exc:  # noqa: BLE001
            LOG.info("fan_voice_snippet_skip reason=%r", exc)

    # 414 axis E1 wire: Yahoo schedule で今日の先発を fetch、 axis E6 用 opponent
    # 先発も同時に取得 (build_pregame_themes に渡して相手投手相性 SQL 集計に活用)
    starting_pitcher_today = ""
    opponent_starter = ""
    try:
        from src.analysis.pregame_themes import fetch_today_starting_pitchers
        starting_pitcher_today, opponent_starter, _ = fetch_today_starting_pitchers()
    except Exception as exc:  # noqa: BLE001
        LOG.info("starting_pitcher_fetch_skip reason=%r", exc)

    # 414 axis E4 + E5 wire: 日次 snapshot 経由で打順変更 / 昇格 diff を計算。
    # 今日の値を save (翌日 fire の前日 snapshot として使う) + 前日 snapshot から
    # build summary を返す。 bucket_name 不在時は silent fallback (空文字)。
    lineup_change_summary = ""
    promotion_summary = ""
    if bucket_name:
        try:
            from src.analysis.daily_snapshot import (
                build_lineup_change_string,
                build_promotion_string,
                save_lineup_snapshot,
                save_roster_active_snapshot,
            )
            today_str = now_jst.strftime("%Y-%m-%d")
            if lineup_focus_names:
                lineup_change_summary = build_lineup_change_string(
                    bucket_name,
                    list(lineup_focus_names),
                    now_jst=now_jst,
                    logger=LOG,
                )
                save_lineup_snapshot(
                    bucket_name, today_str, list(lineup_focus_names), logger=LOG
                )
            try:
                roster_path = Path(__file__).resolve().parent.parent.parent / "config" / "giants_roster.json"
                roster_data = json.loads(roster_path.read_text(encoding="utf-8"))
                today_active = [
                    str(p.get("name") or "").strip()
                    for p in roster_data
                    if p.get("active") and p.get("role") == "player"
                ]
                today_active_set = {n for n in today_active if n}
                if today_active_set:
                    promotion_summary = build_promotion_string(
                        bucket_name, today_active_set, now_jst=now_jst, logger=LOG
                    )
                    save_roster_active_snapshot(
                        bucket_name, today_str, list(today_active_set), logger=LOG
                    )
            except Exception as roster_exc:  # noqa: BLE001
                LOG.info("roster_snapshot_skip reason=%r", roster_exc)
        except Exception as snap_exc:  # noqa: BLE001
            LOG.info("daily_snapshot_skip reason=%r", snap_exc)
    for player, lineup_fact in players[:remaining]:
        db_fact = ""
        if db_path:
            try:
                db_fact = _xbg.build_db_fact_line(player, db_path)
            except Exception as exc:  # noqa: BLE001 - silent skip per fault-tolerance contract
                LOG.warning(
                    "build_db_fact_line failed (player=%s err=%r); falling back to lineup fact",
                    player,
                    exc,
                )
                db_fact = ""
        fact = db_fact or lineup_fact
        # 414 axis E wire: focused_players (= 今日のスタメン focus name list) と
        # fan_voice_snippet を pass、 build_gemini_branding_candidate が
        # build_pregame_themes に転送して prompt 注入する。
        cand = _xbg.build_gemini_branding_candidate(
            player,
            gemini_api_key=gemini_key,
            tavily_api_key=tavily_key,
            db_fact_line=fact,
            logger=LOG,
            db_path=db_path or "",
            focused_players=list(lineup_focus_names) if lineup_focus_names else None,
            fan_voice_snippet=fan_voice_snippet,
            starting_pitcher_today=starting_pitcher_today,
            opponent_pitcher_canonical=opponent_starter,
            lineup_change_summary=lineup_change_summary,
            promotion_summary=promotion_summary,
        )
        if cand is not None:
            out.append(cand)
    return out


def _build_comment_numeric_priority(
    news_candidates: list[lane.Candidate],
    data_candidates: list[lane.Candidate],
) -> tuple[list[lane.Candidate], set[str], set[str]]:
    combined: list[lane.Candidate] = []
    consumed_news: set[str] = set()
    consumed_data: set[str] = set()
    for news_candidate in news_candidates:
        news_id = _candidate_identity(news_candidate)
        news_player = lane._normalize_player_name(news_candidate.focus_player)
        if not news_player:
            continue
        for data_candidate in data_candidates:
            data_id = _candidate_identity(data_candidate)
            if data_id in consumed_data:
                continue
            if lane._normalize_player_name(data_candidate.focus_player) != news_player:
                continue
            comment_db = lane.build_comment_numeric_candidate(
                news_candidate,
                data_candidate,
            )
            if comment_db is None:
                continue
            combined.append(comment_db)
            consumed_news.add(news_id)
            consumed_data.add(data_id)
            break
    return combined, consumed_news, consumed_data


def _merge_news_priority_candidates(
    news_candidates: list[lane.Candidate],
    data_candidates: list[lane.Candidate],
    *,
    max_candidates: int,
) -> list[lane.Candidate]:
    """Put source-backed news/comment candidates first, then DB data.

    This keeps the mail schedule and UI unchanged while shifting the
    content from repeated metric-only candidates toward RSS/comment
    hooks. Player diversity is enforced as a hard mail-level gate; a
    shorter mail is preferable to repeating the same player.
    """
    merged: list[lane.Candidate] = []
    seen_identities: set[str] = set()
    used_players: set[str] = set()
    comment_db_candidates, consumed_news, consumed_data = _build_comment_numeric_priority(
        news_candidates,
        data_candidates,
    )

    def add(candidate: lane.Candidate, *, enforce_player: bool) -> bool:
        if len(merged) >= max_candidates:
            return False
        identity = _candidate_identity(candidate)
        if identity in seen_identities:
            return False
        player_key = lane._normalize_player_name(candidate.focus_player)
        if enforce_player and player_key and player_key in used_players:
            return False
        merged.append(candidate)
        seen_identities.add(identity)
        if player_key:
            used_players.add(player_key)
        return True

    for candidate in comment_db_candidates:
        add(candidate, enforce_player=True)
    for candidate in news_candidates:
        if _candidate_identity(candidate) in consumed_news:
            continue
        add(candidate, enforce_player=True)
    for candidate in data_candidates:
        if _candidate_identity(candidate) in consumed_data:
            continue
        add(candidate, enforce_player=True)
    return merged[:max_candidates]


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Send one セ・リーグ X post candidate mail (347).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Compose mail and log it but do not call SMTP.",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=10,
        help="Maximum candidates to include (default 10).",
    )
    parser.add_argument(
        "--to",
        help="Override recipients (comma-separated). Defaults to MAIL_BRIDGE_TO env.",
    )
    parser.add_argument(
        "--min-sample",
        type=int,
        default=30,
        help="Minimum AB/IP/opps sample size for ranking inclusion (default 30, 350: tightened from 10).",
    )
    # 424: --mode 廃止 (on-queue / scheduled 統合 path に一本化、 2026-05-22)。
    # 旧 --mode=on-queue 互換のため argparse 受け入れは残すが、 値は無視して
    # 統合 path で fire する (scheduler body 更新を待つ間の lag tolerance)。
    parser.add_argument(
        "--mode",
        choices=("scheduled", "on-queue"),
        default="scheduled",
        help="DEPRECATED (424): mode は無視、 統合 path のみ。 引数は scheduler 移行猶予のため温存。",
    )
    return parser.parse_args(argv)


def _main_on_queue(args: argparse.Namespace, recipients: list[str]) -> int:
    """417: drain x_post_candidate_queue → Gemini Flash Lite で候補生成 → mail.

    queue 0 件なら silent skip (mail を送らない、 return 0)。
    Gemini Flash Lite 候補生成失敗 (safety_check / unverified) は個別 skip、 1 件でも候補が
    残れば mail compose、 全件 skip なら mail 送らない。
    mail 送信成功時のみ mark_processed (失敗時は次 fire で再 drain)。
    """
    LOG.info("on-queue mode: starting queue flush flow")
    try:
        from src import x_post_candidate_queue as _xpcq
    except Exception as exc:  # noqa: BLE001
        LOG.error("on-queue mode: x_post_candidate_queue import failed err=%r", exc)
        return 5
    if _xbg is None:
        LOG.error("on-queue mode: x_post_branding_gen unavailable (392 deps missing)")
        return 5

    gemini_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMMA_BRANDING_GEMINI_API_KEY")
    if not gemini_key:
        LOG.error("on-queue mode: GEMINI_API_KEY env missing")
        return 5

    # 417 follow-up (RPM safety): drain max を args.max_candidates に絞る (= 10)。
    # 旧 max_count = max_candidates * 3 (= 30) だと filter で skip された item も
    # Gemini Flash Lite call は走るため、 1 fire で 30 call → 15 RPM 上限超過 risk。 cap=10 で
    # 1 fire 最大 10 call、 ~30 sec、 < 15 RPM 安全圏。
    queue_items = _xpcq.drain(max_count=args.max_candidates)
    if not queue_items:
        LOG.info("on-queue mode: queue is empty — silent skip (no mail sent)")
        return 0
    LOG.info("on-queue mode: drained %d queue items", len(queue_items))

    # db_path (DB fact line は使わないが、 persona 自動選択 (is_giants_game_day)
    # のために必要。 利用不可なら None で渡す = persona は時刻ベース fallback)
    db_path: str | None = None
    try:
        db_info = miq.ensure_local_db()
        if db_info.get("ok"):
            db_path = db_info.get("path")
    except Exception as exc:  # noqa: BLE001
        LOG.info("on-queue mode: insight.db unavailable (persona fallback): %r", exc)

    candidates: list[lane.Candidate] = []
    processed_items: list = []
    for item in queue_items:
        try:
            cand = _xbg.build_x_post_from_article_info(
                item,
                gemini_api_key=gemini_key,
                db_path=db_path or "",
                logger=LOG,
            )
        except Exception as exc:  # noqa: BLE001
            LOG.warning(
                "on-queue mode: build_x_post_from_article_info exception source_url=%s err=%r",
                item.source_url,
                exc,
            )
            cand = None
        if cand is None:
            # silent skip — gate hit / no player / API error
            # NOTE: do NOT mark_processed; let it stay queued for next fire retry.
            # (rss_fetcher dedup will prevent re-enqueue of same source_url.)
            continue
        cand_key = _candidate_player_key(cand)
        if cand_key and _x_post_player_dedup_enabled() and any(
            _candidate_player_key(c) == cand_key for c in candidates
        ):
            # 同一選手の別記事は枠を別ニュースへ譲る (user 2026-06-20)。
            # mark_processed して次 fire での同一選手再浮上も防ぐ。
            LOG.info("on-queue skip dup-player source_url=%s player=%s", item.source_url, cand_key)
            processed_items.append(item)
            continue
        candidates.append(cand)
        processed_items.append(item)
        if len(candidates) >= args.max_candidates:
            break

    candidates = _dedupe_candidates_by_player(candidates, log=LOG)

    if not candidates:
        LOG.info(
            "on-queue mode: drained %d items but all produced 0 candidates (gate hit / no player) — skip mail",
            len(queue_items),
        )
        return 0

    LOG.info(
        "on-queue mode: composing mail with %d candidates (drained %d)",
        len(candidates),
        len(queue_items),
    )
    mail = lane.compose_mail(
        candidates,
        context_label="報知/サンスポ 直結 (queue 417)",
        context_note="",
    )

    if args.dry_run:
        LOG.info("[dry-run on-queue] subject=%s", mail.subject)
        LOG.info("[dry-run on-queue] candidate count=%d", mail.candidate_count)
        LOG.info(
            "[dry-run on-queue] text body preview (first 600 chars):\n%s",
            mail.text_body[:600],
        )
        # dry-run でも mark_processed しない (次回も同じ queue を見れるように)
        return 0

    LOG.info("on-queue mode: sending mail to %s …", recipients)
    request = mdb.MailRequest(
        to=recipients,
        subject=mail.subject,
        text_body=mail.text_body,
        html_body=mail.html_body,
        sender=_resolve_sender(),
        reply_to=_resolve_reply_to(),
        metadata={"ticket": "417", "lane": "x_post_mail", "mode": "on-queue", "candidate_count": mail.candidate_count},
        inline_images=[
            mdb.InlineImage(
                content_id=ci.cid,
                data=ci.png,
                mime_subtype="png",
                filename=f"{ci.cid}.png",
            )
            for ci in mail.candidate_images
        ],
    )
    result = mdb.send(request, dry_run=False)
    LOG.info(
        "on-queue mode: mail send result status=%s reason=%s refused=%s",
        result.status,
        result.reason,
        result.refused_recipients,
    )
    if result.status not in {"sent", "dry_run"}:
        LOG.error("on-queue mode: mail not sent (status=%s) — keep queue items for retry", result.status)
        return 4

    # mail 送信成功 → 該当 queue items を mark_processed
    marked = 0
    for item in processed_items:
        if _xpcq.mark_processed(item):
            marked += 1
    LOG.info("on-queue mode: mark_processed %d / %d items", marked, len(processed_items))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    _configure_logging()
    args = _parse_args(argv)

    # per-fire LLM 生成上限 (2026-06-03 コスト削減)。1 fire の全 Gemini 経路
    # (buzz/reply/引用RT/queue/roundup) 合算の生成回数を上限で抑える。0 = 無制限。
    # 既定 8 (実測 8-18/fire → 高い回を 8 に抑制、 出力 1-7 候補は維持余地)。
    if _xbg is not None:
        _llm_budget_max = _resolve_int_env("X_POST_MAIL_MAX_LLM_PER_RUN", 8, min_value=0)
        _xbg.set_llm_budget(_llm_budget_max)
        LOG.info("per-fire LLM budget set: max=%s", _llm_budget_max or "unlimited")

    recipients = _resolve_recipients(args.to)
    if not recipients and not args.dry_run:
        LOG.error("No recipients configured (MAIL_BRIDGE_TO env or --to). Aborting.")
        return 2

    # 424: --mode 引数は廃止扱い (lag tolerance のため argparse は残置)、
    # 全 fire を統合 path で処理する。 queue 417 drain は compose_mail 直前
    # で append される (下記)。
    if args.mode == "on-queue":
        LOG.info(
            "424: --mode=on-queue is DEPRECATED — running unified path "
            "(queue drain is inlined later in this function)."
        )

    now_jst = datetime.now(ZoneInfo("Asia/Tokyo"))
    if _before_7am_skip_enabled() and _is_before_7am_jst(now_jst):
        LOG.info(
            "x-post mail early skip: reason=before_user_morning_start now=%s "
            "override_env=X_POST_MAIL_ALLOW_BEFORE_7AM",
            now_jst.isoformat(),
        )
        return 0
    if _monday_game_window_skip_enabled() and _is_monday_game_window(now_jst):
        LOG.info(
            "x-post mail early skip: reason=monday_no_game_window now=%s "
            "timing=%s override_env=X_POST_MAIL_ALLOW_MONDAY_GAME_WINDOWS",
            now_jst.isoformat(),
            lane.x_impression_timing_label(now_jst),
        )
        return 0

    LOG.info("Downloading insight.db cache (read-only)…")
    db_path: str | None = None
    try:
        db_info = miq.ensure_local_db()
        if db_info.get("ok"):
            db_path = db_info.get("path")
    except Exception as exc:  # noqa: BLE001
        LOG.exception("ensure_local_db failed: %r", exc)
        return 3
    if not db_path:
        LOG.error("insight.db cache unavailable: %s", db_info)
        return 3
    latest_game_date = lane.query_db_latest_game_date(db_path)
    staleness_days = lane.db_staleness_days(latest_game_date, now=now_jst)
    max_staleness_days = _resolve_max_db_staleness_days()
    LOG.info(
        "insight.db freshness latest_game_date=%s staleness_days=%s max=%d path=%s",
        latest_game_date,
        staleness_days,
        max_staleness_days,
        db_path,
    )
    if max_staleness_days >= 0 and (
        staleness_days is None or staleness_days > max_staleness_days
    ):
        LOG.error(
            "insight.db stale; aborting mail latest_game_date=%s staleness_days=%s max=%d",
            latest_game_date,
            staleness_days,
            max_staleness_days,
        )
        return 4

    # 355 / 441: load rolling dedup set so combos already mailed do not
    # repeat. Window defaults to 168h (7d) and is overridable via
    # ``X_POST_MAIL_PLAYER_HISTORY_HOURS``. Disabled when
    # ``X_POST_MAIL_DEDUP_DISABLED=1`` or bucket env missing. GCS errors
    # are logged and treated as empty state (= dedup off for this run,
    # mail still sends).
    dedup_set: set[str] | None = None
    recent_player_counts: dict[str, int] = {}
    cooldown_players: set[str] = set()
    live_duplicate_players: set[str] = set()
    dedup_records: list[dict] = []
    bucket_name = os.environ.get("INSIGHT_GCS_BUCKET") or ""
    dedup_disabled = (os.environ.get("X_POST_MAIL_DEDUP_DISABLED") or "").strip()
    history_hours = _resolve_int_env(
        "X_POST_MAIL_PLAYER_HISTORY_HOURS", 168, min_value=1
    )
    gemini_player_cooldown_hours = _resolve_int_env(
        "X_POST_MAIL_GEMMA_PLAYER_COOLDOWN_HOURS", 24, min_value=0
    )
    if bucket_name and dedup_disabled not in {"1", "true", "yes"}:
        try:
            dedup_records = lane._load_recent_dedup_records(
                bucket_name, now_jst, lookback_hours=history_hours
            )
            dedup_set = {
                str(rec.get("signature") or "")
                for rec in dedup_records
                if str(rec.get("signature") or "")
            }
            LOG.info(
                "Loaded %dh dedup set: %d signatures",
                history_hours,
                len(dedup_set),
            )
            recent_player_counts = lane._player_counts_from_dedup_records(dedup_records)
            LOG.info(
                "Loaded %dh player history: %d players, %d appearances",
                history_hours,
                len(recent_player_counts),
                sum(recent_player_counts.values()),
            )
            cooldown_players = lane._players_within_cooldown(
                dedup_records, now_jst, gemini_player_cooldown_hours
            )
            LOG.info(
                "Gemini Flash Lite player cooldown (%dh): %d players blocked from re-generation",
                gemini_player_cooldown_hours,
                len(cooldown_players),
            )
            live_duplicate_cooldown_hours = _live_duplicate_player_cooldown_hours()
            if (
                live_duplicate_cooldown_hours > 0
                and _live_duplicate_player_cooldown_active(now_jst)
            ):
                live_duplicate_players = lane._players_within_cooldown(
                    dedup_records, now_jst, live_duplicate_cooldown_hours
                )
                LOG.info(
                    "Live duplicate player cooldown (%dh): %d players blocked from reply/video/fan generation",
                    live_duplicate_cooldown_hours,
                    len(live_duplicate_players),
                )
        except Exception as exc:  # noqa: BLE001
            LOG.warning("dedup load failed (continuing without dedup): %r", exc)
            dedup_set = set()
            recent_player_counts = {}
            live_duplicate_players = set()
    else:
        LOG.info("Dedup disabled (bucket=%s, disabled_env=%s)",
                 bool(bucket_name), dedup_disabled)

    LOG.info("Picking candidates (max=%d, min_sample=%d, db_path=%s, dedup=%s)…",
             args.max_candidates, args.min_sample, bool(db_path),
             len(dedup_set) if dedup_set is not None else "off")
    lineup_focus_names = _fetch_today_lineup_focus_names()
    context_label = "今日のスタメン" if lineup_focus_names else ""
    candidates = lane.pick_candidates(
        miq.query_rank,
        now=now_jst,
        max_candidates=args.max_candidates,
        min_sample=args.min_sample,
        db_path=db_path,
        dedup_set=dedup_set,
        focus_player_names=lineup_focus_names,
        context_label=context_label,
        recent_player_counts=recent_player_counts,
    )
    if lineup_focus_names and len(candidates) < _resolve_lineup_focus_min_candidates():
        LOG.warning(
            "Lineup focus produced only %d candidates; retrying without lineup "
            "focus so the scheduled mail does not disappear entirely.",
            len(candidates),
        )
        candidates = lane.pick_candidates(
            miq.query_rank,
            now=now_jst,
            max_candidates=args.max_candidates,
            min_sample=args.min_sample,
            db_path=db_path,
            dedup_set=dedup_set,
            recent_player_counts=recent_player_counts,
        )
        context_label = ""
    dedup_min_candidates = _resolve_dedup_min_candidates()
    if dedup_set is not None and len(candidates) < dedup_min_candidates:
        LOG.warning(
            "24h dedup left only %d candidates (<%d); retrying without dedup "
            "to avoid starving scheduled mail.",
            len(candidates),
            dedup_min_candidates,
        )
        relaxed_candidates = lane.pick_candidates(
            miq.query_rank,
            now=now_jst,
            max_candidates=args.max_candidates,
            min_sample=args.min_sample,
            db_path=db_path,
            dedup_set=None,
            focus_player_names=lineup_focus_names if context_label else None,
            context_label=context_label,
            recent_player_counts=recent_player_counts,
        )
        backfilled = _backfill_dedup_starved_candidates(
            candidates,
            relaxed_candidates,
            max_candidates=args.max_candidates,
            recent_player_counts=recent_player_counts,
            min_candidates=dedup_min_candidates,
        )
        if len(backfilled) > len(candidates):
            LOG.info(
                "Dedup fallback backfilled candidates: %d -> %d",
                len(candidates),
                len(backfilled),
            )
            candidates = backfilled
        else:
            LOG.info(
                "Dedup fallback found no additional candidates (relaxed=%d)",
                len(relaxed_candidates),
            )
    # Add-on candidates can intentionally increase the review mail without
    # displacing the base DB/news set. Keep the normal cap for baseline
    # candidates, then add explicit slots for reply candidates below.
    extra_policy_slots = 0

    # 448: flag ON 時、 大手未掲載の差別化 data split (序盤/中盤/終盤・本拠地/ビジター
    # 別打率の大きな差) 候補を append する。 公開 X 自動投稿はしない (候補=メールまで)。
    # flag OFF (default) では既存挙動完全不変。
    if _data_split_enabled() and db_path:
        ds_max = _data_split_max_per_run()
        if ds_max > 0:
            try:
                ds_candidates = lane.build_data_split_candidates(
                    db_path,
                    now=now_jst,
                    max_count=ds_max,
                    dedup_set=dedup_set,
                )
            except Exception as _ds_exc:  # noqa: BLE001
                LOG.warning("data_split build failed: %r", _ds_exc)
                ds_candidates = []
            # 既存候補と signature 重複しないものだけ append
            _existing_sigs = {getattr(c, "signature", "") for c in candidates}
            ds_new = [c for c in ds_candidates if c.signature not in _existing_sigs]
            if ds_new:
                before = len(candidates)
                candidates = candidates + ds_new
                LOG.info(
                    "data_split appended: base=%d data_split=%d total=%d",
                    before, len(ds_new), len(candidates),
                )

    # 2026-06-11 角度 v2 (user 全部GO): 勝利相関 (条件付き勝率) / 対戦カード別 split /
    # 歴代通算チェイス。 各角度 1 本ずつ、 カード PNG は builder 側で直接添付
    # (image_bytes)。 公開 X 自動投稿はしない (候補=メールまで)。 flag OFF で既存不変。
    # 話題選手 counts はここで 1 回だけ取得し、 角度の優先選手 (今夜の主役の驚きを
    # 先に出す、 user「色々なデータを試合あとは知りたい」) と後段 boost で共用する。
    # 2026-06-12 試合前見どころ: 今日の巨人戦 (NPB公式 日程+予告先発) に直結する
    # 数字だけのプレビュー。 builder 側 gate = 今日試合あり+開始前+数字あり、
    # 満たさなければ 0 件 (user「関係がないものを出すくらいなら出さない」)。
    # built 時は _pregame_opp を立て、 下の data_angles を今日の相手限定に切替える。
    _pregame_opp: str | None = None
    if _pregame_preview_enabled() and db_path:
        try:
            from src import x_post_data_angles as _pg_angles
            pg_candidates = _pg_angles.build_pregame_preview_candidates(
                db_path, now=now_jst, max_count=1, dedup_set=dedup_set)
        except Exception as _pg_exc:  # noqa: BLE001
            LOG.warning("pregame preview build failed: %r", _pg_exc)
            pg_candidates = []
        if pg_candidates:
            sig_parts = (pg_candidates[0].signature or "").split("|")
            _pregame_opp = sig_parts[2] if len(sig_parts) >= 3 else None
            _existing_sigs = {getattr(c, "signature", "") for c in candidates}
            pg_new = [c for c in pg_candidates if c.signature not in _existing_sigs]
            if pg_new:
                before = len(candidates)
                candidates = candidates + pg_new
                LOG.info(
                    "pregame preview appended: base=%d pregame=%d total=%d opp=%s",
                    before, len(pg_new), len(candidates), _pregame_opp,
                )

    topical_counts: dict[str, int] | None = None
    if _data_angles_enabled() and db_path:
        da_max = _data_angles_max_per_run()
        if da_max > 0:
            try:
                from src import x_post_data_angles as _angles

                if _topical_boost_enabled():
                    topical_counts = _angles.fetch_topical_counts()
                _preferred = {
                    p for p, n in (topical_counts or {}).items() if n >= 2
                }
                if _preferred:
                    LOG.info("data_angles preferred (今夜の話題): %s", sorted(_preferred))
                if _pregame_opp:
                    # 試合前枠 (2026-06-12 user「関係あるものだけ」): 汎用角度を止め、
                    # 今日の相手カードの split だけに絞る。
                    da_candidates = _angles.build_opponent_split_candidates(
                        db_path, now=now_jst, max_count=1, dedup_set=dedup_set,
                        preferred_players=_preferred,
                        opponents={_pregame_opp})[:da_max]
                else:
                    # 2026-06-12 user「手動mailを増やしたい」: 勝利相関/対戦split 各2本へ増量
                    da_candidates = (
                        _angles.build_win_correlation_candidates(
                            db_path, now=now_jst, max_count=2, dedup_set=dedup_set,
                            preferred_players=_preferred)
                        + _angles.build_opponent_split_candidates(
                            db_path, now=now_jst, max_count=2, dedup_set=dedup_set,
                            preferred_players=_preferred)
                        + _angles.build_alltime_chase_candidates(
                            now=now_jst, max_count=1, dedup_set=dedup_set)
                    )[:da_max]
                if now_jst.hour >= 21:
                    # 試合後枠 (22時便): 今夜の話題選手に関係する候補のみ。
                    # 関係ゼロなら出さない (埋め草禁止)。
                    _before_rel = len(da_candidates)
                    da_candidates = [
                        c for c in da_candidates
                        if (getattr(c, "focus_player", "") or "") in _preferred
                    ]
                    if _before_rel and len(da_candidates) < _before_rel:
                        LOG.info(
                            "postgame relevance gate: %d -> %d angle candidates "
                            "(今夜の話題選手のみ)", _before_rel, len(da_candidates))
            except Exception as _da_exc:  # noqa: BLE001
                LOG.warning("data_angles build failed: %r", _da_exc)
                da_candidates = []
            _existing_sigs = {getattr(c, "signature", "") for c in candidates}
            da_new = [c for c in da_candidates if c.signature not in _existing_sigs]
            if da_new:
                before = len(candidates)
                candidates = candidates + da_new
                LOG.info(
                    "data_angles appended: base=%d angles=%d total=%d",
                    before, len(da_new), len(candidates),
                )

    # 2026-06-12 user「試合前と試合後は今日の試合に関係あるものだけ」:
    # 試合非連動の汎用枠 (あの日の巨人 / 新旧比較 / 週間MVP) は朝〜昼便 (〜13時台)
    # のみに退避する。 15時以降の便 (試合前 15/16/17時・試合後 22時) には出さない。
    _generic_angle_window = now_jst.hour <= 13

    # 2026-06-12 角度③ あの日の巨人: 裏取り済みイベント or レジェンドの生まれた日。
    # 毎日安定供給の歴史枠。 候補=メールまで。 flag OFF で既存不変。
    if _on_this_day_enabled() and _generic_angle_window:
        try:
            from src import x_post_data_angles as _od_angles
            od_candidates = _od_angles.build_on_this_day_candidates(
                now=now_jst, max_count=1, dedup_set=dedup_set)
        except Exception as _od_exc:  # noqa: BLE001
            LOG.warning("on_this_day build failed: %r", _od_exc)
            od_candidates = []
        _existing_sigs = {getattr(c, "signature", "") for c in candidates}
        od_new = [c for c in od_candidates if c.signature not in _existing_sigs]
        if od_new:
            before = len(candidates)
            candidates = candidates + od_new
            LOG.info(
                "on_this_day appended: base=%d otd=%d total=%d",
                before, len(od_new), len(candidates),
            )

    # 2026-06-12 角度① 新旧比較: 同年齢シーズン時点の通算本塁打で若手×レジェンド対比。
    # 驚きゲート (レジェンド同年齢時点を上回る時のみ)。 候補=メールまで。 flag OFF で既存不変。
    if _legend_compare_enabled() and db_path and _generic_angle_window:
        try:
            from src import x_post_data_angles as _lc_angles
            lc_candidates = _lc_angles.build_legend_age_compare_candidates(
                db_path, now=now_jst, max_count=1, dedup_set=dedup_set)
        except Exception as _lc_exc:  # noqa: BLE001
            LOG.warning("legend_compare build failed: %r", _lc_exc)
            lc_candidates = []
        _existing_sigs = {getattr(c, "signature", "") for c in candidates}
        lc_new = [c for c in lc_candidates if c.signature not in _existing_sigs]
        if lc_new:
            before = len(candidates)
            candidates = candidates + lc_new
            LOG.info(
                "legend_compare appended: base=%d legend=%d total=%d",
                before, len(lc_new), len(candidates),
            )

    # 2026-06-12 Tigers型: 出場選手登録・抹消の速報 (公示があった日のみ、 巨人のみ)。
    if _roster_move_enabled() and _generic_angle_window:
        try:
            from src import x_post_data_angles as _rm_angles
            rm_candidates = _rm_angles.build_roster_move_candidates(
                now=now_jst, max_count=1, dedup_set=dedup_set)
        except Exception as _rm_exc:  # noqa: BLE001
            LOG.warning("roster_move build failed: %r", _rm_exc)
            rm_candidates = []
        _existing_sigs = {getattr(c, "signature", "") for c in candidates}
        rm_new = [c for c in rm_candidates if c.signature not in _existing_sigs]
        if rm_new:
            before = len(candidates)
            candidates = candidates + rm_new
            LOG.info("roster_move appended: base=%d rm=%d total=%d",
                     before, len(rm_new), len(candidates))

    # 2026-06-12 chikupn型①: 今季初・以来 (希少事象)。 直近巨人戦で事象があった時のみ。
    if _rarity_enabled() and db_path and _generic_angle_window:
        try:
            from src import x_post_data_angles as _ra_angles
            ra_candidates = _ra_angles.build_rarity_candidates(
                db_path, now=now_jst, max_count=1, dedup_set=dedup_set)
        except Exception as _ra_exc:  # noqa: BLE001
            LOG.warning("rarity build failed: %r", _ra_exc)
            ra_candidates = []
        _existing_sigs = {getattr(c, "signature", "") for c in candidates}
        ra_new = [c for c in ra_candidates if c.signature not in _existing_sigs]
        if ra_new:
            before = len(candidates)
            candidates = candidates + ra_new
            LOG.info("rarity appended: base=%d ra=%d total=%d",
                     before, len(ra_new), len(candidates))

    # 2026-06-12 chikupn型②: 通算節目達成🎉。 直近巨人戦で節目を跨いだ時のみ。
    if _milestone_enabled() and db_path and _generic_angle_window:
        try:
            from src import x_post_data_angles as _ms_angles
            ms_candidates = _ms_angles.build_milestone_candidates(
                db_path, now=now_jst, max_count=1, dedup_set=dedup_set)
        except Exception as _ms_exc:  # noqa: BLE001
            LOG.warning("milestone build failed: %r", _ms_exc)
            ms_candidates = []
        _existing_sigs = {getattr(c, "signature", "") for c in candidates}
        ms_new = [c for c in ms_candidates if c.signature not in _existing_sigs]
        if ms_new:
            before = len(candidates)
            candidates = candidates + ms_new
            LOG.info("milestone appended: base=%d ms=%d total=%d",
                     before, len(ms_new), len(candidates))

    # 2026-06-12 年俸コスパ: データ×年俸クロス (user「これいいね」)。 割安バーゲン型のみ
    # (年俸絡みの negative は炎上リスクのため出さない)。 候補=メールまで。 flag OFF で既存不変。
    if _salary_value_enabled() and db_path and _generic_angle_window:
        try:
            from src import x_post_data_angles as _sv_angles
            sv_candidates = _sv_angles.build_salary_value_candidates(
                db_path, now=now_jst, max_count=1, dedup_set=dedup_set)
        except Exception as _sv_exc:  # noqa: BLE001
            LOG.warning("salary_value build failed: %r", _sv_exc)
            sv_candidates = []
        _existing_sigs = {getattr(c, "signature", "") for c in candidates}
        sv_new = [c for c in sv_candidates if c.signature not in _existing_sigs]
        if sv_new:
            before = len(candidates)
            candidates = candidates + sv_new
            LOG.info(
                "salary_value appended: base=%d sv=%d total=%d",
                before, len(sv_new), len(candidates),
            )

    # 2026-06-12 角度⑤ 週間MVP: 月曜限定の定番企画 (先週 月〜日 の巨人打者集計トップ)。
    # 公開 X 自動投稿はしない (候補=メールまで)。 flag OFF で既存不変。
    if _weekly_mvp_enabled() and db_path and _generic_angle_window:
        try:
            from src import x_post_data_angles as _wm_angles
            wm_candidates = _wm_angles.build_weekly_mvp_candidates(
                db_path, now=now_jst, max_count=1, dedup_set=dedup_set)
        except Exception as _wm_exc:  # noqa: BLE001
            LOG.warning("weekly_mvp build failed: %r", _wm_exc)
            wm_candidates = []
        _existing_sigs = {getattr(c, "signature", "") for c in candidates}
        wm_new = [c for c in wm_candidates if c.signature not in _existing_sigs]
        if wm_new:
            before = len(candidates)
            candidates = candidates + wm_new
            LOG.info(
                "weekly_mvp appended: base=%d mvp=%d total=%d",
                before, len(wm_new), len(candidates),
            )

    # 451: flag ON 時、 公式/OB/メディア YouTube の「懐かし・ファン反応」動画候補を append。
    # 転載しない (URL 紹介のみ)、 公開 X 自動投稿はしない (候補=メールまで)。 flag OFF で既存不変。
    if _video_radar_enabled():
        vr_max = _video_radar_max_per_run()
        if vr_max > 0:
            # 451: 品質優先で引用RTコメントを Gemini 3.1 Flash Lite で生成 (flag ON 時)。
            # 失敗時は build_video_radar_candidates 内で LLM なし出来事 template に fallback。
            vr_comment_fn = None
            if _video_radar_llm_enabled():
                _vr_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMMA_BRANDING_GEMINI_API_KEY") or ""
                if _vr_key:
                    try:
                        from src import x_post_branding_gen as _vr_xbg

                        def vr_comment_fn(post_text, player, phase_hint="", *, db_fact="", _k=_vr_key, _g=_vr_xbg, _now=now_jst):  # noqa: E731
                            # voice は spec の フーガ+缶詰 合成 (_build_system_prompt)。 時間帯トーンは now から自動。
                            # 2026-06-04 user 方針「DBは使わない」: db_fact (今季数字) は渡さない。
                            # 引用RTは元投稿 (Xバズ動画) を素材にしたヨシラバー風の読みのみで書く。
                            return _g.build_quote_rt_comment(post_text, player, gemini_api_key=_k, now=_now)
                    except Exception as _vr_imp_exc:  # noqa: BLE001
                        LOG.warning("video_radar LLM comment unavailable: %r", _vr_imp_exc)
                        vr_comment_fn = None
            try:
                vr_candidates = lane.build_video_radar_candidates(
                    db_path,
                    now=now_jst,
                    max_count=vr_max,
                    dedup_set=dedup_set,
                    comment_fn=vr_comment_fn,
                    avoid_player_names=live_duplicate_players,
                )
            except Exception as _vr_exc:  # noqa: BLE001
                LOG.warning("video_radar build failed: %r", _vr_exc)
                vr_candidates = []
            _existing_sigs_vr = {getattr(c, "signature", "") for c in candidates}
            vr_new = [c for c in vr_candidates if c.signature not in _existing_sigs_vr]
            if vr_new:
                before = len(candidates)
                candidates = candidates + vr_new
                LOG.info(
                    "video_radar appended: base=%d video=%d total=%d",
                    before, len(vr_new), len(candidates),
                )

    # 451: 「今日の動画引用キャプション」(ヨシラバーコメント+データ)。 user が X で動画を
    # 長押し引用する時に貼るテキスト。 巨人選手限定。 flag ON 時のみ append。
    if _quote_captions_enabled() and db_path:
        try:
            from src import sns_topic_cards as _tc
            caps = _tc.build_quote_captions(db_path, max_captions=5)
        except Exception as _cap_exc:  # noqa: BLE001
            LOG.warning("quote_captions build failed: %r", _cap_exc)
            caps = []
        cap_cands = []
        for c in caps:
            sig = "quote_caption|" + c["player"]
            if dedup_set is not None and sig in dedup_set:
                continue
            draft = (
                f"{c['caption']}\n\n"
                "※ X で該当の動画を長押し → 引用 → このキャプションを貼って投稿。"
            )
            cap_cands.append(lane.Candidate(
                title=f"🎬 動画引用: {c['player']} {c['headline']}",
                metric="quote_caption", period_label="動画引用キャプション",
                draft_text=draft, char_count=len(c["caption"]), signature=sig,
                post_text=c["caption"], focus_player=c["player"],
                why_now="今日の話題 (動画引用用)", source_material_type="quote_caption",
            ))
        if cap_cands:
            before = len(candidates)
            candidates = candidates + cap_cands
            LOG.info("quote_captions appended: base=%d cap=%d total=%d", before, len(cap_cands), len(candidates))

    # 451: 「💬リプライ候補」(大手投稿 + 同じヨシラバー声のリプ文)。 大手投稿に返信=大観客に
    # 露出 (小規模アカウントのインプ近道)。 1タップ返信ボタン (reply intent)。 flag ON 時のみ。
    if _reply_candidates_enabled() and db_path:
        rep_max = _reply_candidates_max_per_run()
        if rep_max > 0:
            # ③ 順位燃料: default は LLM 不使用のヨシラバー風 deterministic reply。
            # 追加費用を避けるため、 Gemini は ENABLE_X_POST_REPLY_LLM=1 の時だけ使う。
            rep_comment_fn = None
            _rep_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMMA_BRANDING_GEMINI_API_KEY") or ""
            if _reply_llm_enabled() and _rep_key:
                try:
                    from src import x_post_branding_gen as _rep_xbg

                    def rep_comment_fn(parent_text, player, _k=_rep_key, _g=_rep_xbg, _now=now_jst):  # noqa: E731
                        # 親ツイート本文に対するヨシラバーボイスのリプ (= 引用RTコメントと同型)。
                        return _g.build_quote_rt_comment(parent_text, player, gemini_api_key=_k, now=_now)
                except Exception as _rep_imp_exc:  # noqa: BLE001
                    LOG.warning("reply_candidates LLM comment unavailable: %r", _rep_imp_exc)
                    rep_comment_fn = None
            target_handles = _reply_target_handles()
            try:
                from src import sns_topic_cards as _tc2
                reps = _tc2.build_reply_candidates(
                    db_path,
                    max_replies=rep_max,
                    comment_fn=rep_comment_fn,
                    handles=target_handles,
                    avoid_player_names=live_duplicate_players,
                )
            except Exception as _rep_exc:  # noqa: BLE001
                LOG.warning("reply_candidates build failed: %r", _rep_exc)
                reps = []
            rep_cands = []
            for r in reps:
                handle = str(r.get("handle") or "").strip().lstrip("@")
                sig = f"reply_cand|{handle or 'unknown'}|{r['tweet_id']}"
                if dedup_set is not None and sig in dedup_set:
                    continue
                label, why_now, source_material_type, metric, reason_tags = _reply_candidate_mail_labels(handle)
                draft = (
                    f"返信先({label}): {r['url']}\n"
                    f"対象handle: @{handle or 'unknown'}\n"
                    f"リプ文: {r['reply']}\n\n"
                    "※ ボタンで返信画面が開く(リプ文入り)→ 投稿。"
                    "大手の返信欄に露出=インプ近道。自動投稿はしない。"
                    + ("" if rep_comment_fn else "\n※ 生成: LLM不使用 (追加費用なし)。")
                )
                rep_cands.append(lane.Candidate(
                    title=f"💬 {label}: {r['player']} {r['headline']}",
                    metric=metric,
                    period_label=label,
                    draft_text=draft,
                    char_count=len(r["reply"]),
                    signature=sig,
                    post_text=r["reply"],
                    focus_player=r["player"],
                    reply_to_id=r["tweet_id"],
                    why_now=why_now,
                    source_material_type=source_material_type,
                    reason_tags=reason_tags,
                ))
            if rep_cands:
                before = len(candidates)
                candidates = candidates + rep_cands
                extra_policy_slots += len(rep_cands)
                LOG.info(
                    "reply_candidates appended: base=%d rep=%d total=%d handles=%s",
                    before,
                    len(rep_cands),
                    len(candidates),
                    ",".join(target_handles),
                )
            else:
                LOG.info(
                    "reply_candidates empty: handles=%s raw=%d reason=no_eligible_post_or_dedup",
                    ",".join(target_handles),
                    len(reps),
                )

    # 2026-06-05 user GO: ファンアカ (フーガ @EH87EazmV9D2eSw / 缶詰 @kandume92) の試合反応への
    # value-add リプ候補。 既存リプ機構 (build_reply_candidates) を流用し、 ファンのカジュアル
    # 反応文を拾うため require_event=False。 空虚な同調を送らないよう skip_on_empty_comment=True
    # (LLM voice が門番落ちした投稿はスキップ)。 巨人選手検出 + _is_giants で巨人関連のみ
    # (フーガの広島/楽天ポストは除外)。 自動投稿はしない (mail 候補まで)。 LLM は per-fire budget
    # (X_POST_MAIL_MAX_LLM_PER_RUN) を報知リプ等と共有=天井を上げない。 default OFF (flag gated)。
    if _fan_reply_enabled() and db_path:
        fan_max = _fan_reply_max_per_run()
        if fan_max > 0:
            fan_comment_fn = None
            _fan_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GEMMA_BRANDING_GEMINI_API_KEY") or ""
            if _fan_key:
                try:
                    from src import x_post_branding_gen as _fan_xbg

                    def fan_comment_fn(parent_text, player, _k=_fan_key, _g=_fan_xbg, _now=now_jst):  # noqa: E731
                        # ファン投稿への value-add リプ (同調でなく数字/逆角度を1個足す)。 subject で
                        # 「ファン投稿への反応」と枠付け。 元ネタに無い数字は門番 (_extract_unverified_numbers) で弾く。
                        return _g.build_quote_rt_comment(
                            parent_text, player, gemini_api_key=_k, now=_now, subject="巨人ファンの投稿",
                        )
                except Exception as _fan_imp_exc:  # noqa: BLE001
                    LOG.warning("fan_reply LLM comment unavailable: %r", _fan_imp_exc)
                    fan_comment_fn = None
            fan_handles = _fan_reply_target_handles()
            try:
                from src import sns_topic_cards as _tc3
                fan_reps = _tc3.build_reply_candidates(
                    db_path,
                    max_replies=fan_max,
                    comment_fn=fan_comment_fn,
                    handles=fan_handles,
                    require_event=False,
                    skip_on_empty_comment=True,
                    avoid_player_names=live_duplicate_players,
                )
            except Exception as _fan_exc:  # noqa: BLE001
                LOG.warning("fan_reply build failed: %r", _fan_exc)
                fan_reps = []
            fan_cands = []
            for r in fan_reps:
                handle = str(r.get("handle") or "").strip().lstrip("@")
                sig = f"fan_reply|{handle or 'unknown'}|{r['tweet_id']}"
                if dedup_set is not None and sig in dedup_set:
                    continue
                draft = (
                    f"返信先(ファンリプ候補): {r['url']}\n"
                    f"対象handle: @{handle or 'unknown'}\n"
                    f"リプ文: {r['reply']}\n\n"
                    "※ ボタンで返信画面が開く(リプ文入り)→ 投稿。"
                    "巨人系ファンアカの試合反応に value-add リプ=客層に露出。自動投稿はしない。"
                )
                fan_cands.append(lane.Candidate(
                    title=f"💬 ファンリプ候補: @{handle or 'unknown'} {r['player']} {r['headline']}",
                    metric=lane._REPLY_CANDIDATE_METRIC,
                    period_label="ファンリプ候補",
                    draft_text=draft,
                    char_count=len(r["reply"]),
                    signature=sig,
                    post_text=r["reply"],
                    focus_player=r["player"],
                    reply_to_id=r["tweet_id"],
                    why_now="ファンアカの試合反応に返信=客層に露出",
                    source_material_type="reply_candidate",
                    reason_tags=("reply:fan", "manual_only"),
                ))
            if fan_cands:
                before = len(candidates)
                candidates = candidates + fan_cands
                extra_policy_slots += len(fan_cands)
                LOG.info(
                    "fan_reply appended: base=%d fan=%d total=%d handles=%s",
                    before, len(fan_cands), len(candidates), ",".join(fan_handles),
                )

    # 392: flag ON 時は news_opinion fallback (template) を skip し、 Gemini Flash Lite
    # + Tavily REST で branding candidate を 1-3 件生成して append する。
    # flag OFF (default) では既存挙動を 100% 維持 (rollback 余地)。
    gemini_enabled = _gemini_branding_enabled()
    if gemini_enabled and _gemini_branding_all_mode():
        # 2026-05-22 user request: rebrand every candidate via Gemini Flash Lite (alternating
        # fuuga / kandume) so the whole mail comes out in ヨシラバー voice.
        candidates = _rebrand_candidates_via_gemini(
            candidates,
            lineup_focus_names=lineup_focus_names,
            db_path=db_path,
            bucket_name=bucket_name or None,
        )
        news_fallback_enabled = False
        fallback_candidates: list[lane.Candidate] = []
    elif gemini_enabled:
        gemini_count = _gemini_branding_max_per_run()
        if gemini_count > 0:
            gemini_candidates = _build_gemini_branding_candidates(
                candidates,
                lineup_focus_names=lineup_focus_names,
                recent_player_counts=recent_player_counts,
                max_count=gemini_count,
                db_path=db_path,
                bucket_name=bucket_name or None,
                cooldown_players=cooldown_players,
            )
            if gemini_candidates:
                before = len(candidates)
                candidates = candidates + gemini_candidates
                LOG.info(
                    "Gemini Flash Lite branding appended: data=%d gemini=%d total=%d",
                    before,
                    len(gemini_candidates),
                    len(candidates),
                )
            else:
                LOG.info(
                    "Gemini Flash Lite branding produced 0 candidates "
                    "(visible skip: Tavily / Gemini errors or validator drops)."
                )
        # flag ON ルートでは template-based news_opinion fallback を呼ばない
        news_fallback_enabled = False
        fallback_candidates: list[lane.Candidate] = []
    else:
        news_fallback_enabled = not _news_fallback_disabled()
        fallback_candidates = []
    news_priority_count = _resolve_news_priority_candidates(args.max_candidates)
    if not news_fallback_enabled and not gemini_enabled:
        LOG.info("News/opinion fallback disabled by X_POST_MAIL_NEWS_FALLBACK_DISABLED")
    if news_fallback_enabled and news_priority_count:
        fallback_candidates = _fetch_news_opinion_fallback_candidates(
            [],
            max_candidates=news_priority_count,
            now=now_jst,
            recent_player_counts=recent_player_counts,
            comment_fn=_make_voiced_comment_fn(now_jst, "ニュース記事"),  # A: フーガ+缶詰 voice
        )
        if fallback_candidates:
            before = len(candidates)
            candidates = _merge_news_priority_candidates(
                fallback_candidates,
                candidates,
                max_candidates=args.max_candidates,
            )
            LOG.info(
                "News/opinion priority merged candidates: data=%d news=%d total=%d",
                before,
                len(fallback_candidates),
                len(candidates),
            )
    if (
        news_fallback_enabled
        and not fallback_candidates
        and len(candidates) < args.max_candidates
    ):
        fallback_candidates = _fetch_news_opinion_fallback_candidates(
            candidates,
            max_candidates=args.max_candidates,
            now=now_jst,
            recent_player_counts=recent_player_counts,
            comment_fn=_make_voiced_comment_fn(now_jst, "ニュース記事"),  # A: フーガ+缶詰 voice
        )
        if fallback_candidates:
            before = len(candidates)
            candidates = candidates + fallback_candidates
            LOG.info(
                "News/opinion fallback filled candidates: %d -> %d",
                before,
                len(candidates),
            )
    # 397: fan_voice (参考) candidate append。
    # X_POST_MAIL_FAN_VOICE_ENABLED=1 で ON、 evening (17:30) / postgame
    # (22:30) 便 (= _is_fan_voice_fire_window) でのみ append。 朝 / 昼 /
    # 午後便には出さない (試合時間帯のファン熱を mail に届けるため)。
    # flag OFF or 試合時間帯外なら完全 skip (no-op、 既存挙動不変)。
    if _fan_voice_enabled() and _is_fan_voice_fire_window(now_jst):
        fan_voice_max = _fan_voice_max_per_run()
        if fan_voice_max > 0 and bucket_name:
            remaining_slots = max(0, args.max_candidates - len(candidates))
            fan_voice_count = min(fan_voice_max, remaining_slots)
            if fan_voice_count > 0:
                fan_voice_candidates = _build_fan_voice_candidates(
                    candidates,
                    bucket_name=bucket_name,
                    now=now_jst,
                    max_count=fan_voice_count,
                    recent_player_counts=recent_player_counts,
                    lookback_hours=max(1, int(lane.phase_freshness_max_age_hours(now_jst))),
                )
                if fan_voice_candidates:
                    before = len(candidates)
                    candidates = candidates + fan_voice_candidates
                    LOG.info(
                        "fan_voice appended: data=%d fan_voice=%d total=%d",
                        before,
                        len(fan_voice_candidates),
                        len(candidates),
                    )
                else:
                    LOG.info(
                        "fan_voice produced 0 candidates "
                        "(empty GCS cache / NER mismatch / dedup)."
                    )
            else:
                LOG.info(
                    "fan_voice skip: mail already full (candidates=%d, max=%d)",
                    len(candidates),
                    args.max_candidates,
                )
    elif _fan_voice_enabled():
        LOG.info(
            "fan_voice skip: not in fire window (now=%s, allowed 17:00-23:30 JST)",
            now_jst.strftime("%H:%M"),
        )

    # 424: queue 417 drain — 報知/サンスポ direct queue を統合 path に組み込む。
    # 旧 _main_on_queue を inline 化。 build_x_post_from_article_info が cand を
    # 返した item は processed_queue_items に残し、 mail 送信成功時に
    # mark_processed する (失敗時は queue に残し次 fire で再 drain)。
    processed_queue_items: list = []
    try:
        from src import x_post_candidate_queue as _xpcq
    except Exception as exc:  # noqa: BLE001
        _xpcq = None  # type: ignore[assignment]
        LOG.info("queue 417 drain skip: x_post_candidate_queue import failed err=%r", exc)
    if _xpcq is not None and _xbg is not None:
        queue_gemini_key = (
            os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GEMMA_BRANDING_GEMINI_API_KEY")
            or ""
        )
        if not queue_gemini_key:
            LOG.info("queue 417 drain skip: GEMINI_API_KEY env missing")
        else:
            queue_items = _xpcq.drain(max_count=args.max_candidates)
            if not queue_items:
                LOG.info("queue 417 drain: queue empty — 0 items")
            else:
                LOG.info("queue 417 drain: %d items", len(queue_items))
                # 同一選手の重複 Gemini 生成を抑えつつ出力は守る (LLM 費用節約 + 回帰修正)。
                # 多媒体が同じ選手を扱い queue に同 player 記事が複数入ると、昔は全件
                # 生成していた。費用のため 1 選手 1 成功 (succeeded_player_keys) に絞るが、
                # 最初の 1 本が品質ゲート (unverified_numbers 等) で落ちても次の記事を
                # 試せるよう「成功するまで最大 N 試行」(attempt_counts) にする。これで
                # 出力 (旧来の通過チャンス) を維持しつつ無駄叩きを上限で抑える。
                # cross-run cooldown/cap は skip_player_keys (env で有効化、既定は無効)。
                queue_cap = _resolve_int_env(
                    "X_POST_MAIL_GEMMA_PLAYER_MAX_PER_WINDOW", 2, min_value=1
                )
                queue_attempts_max = _resolve_int_env(
                    "X_POST_MAIL_QUEUE_PLAYER_MAX_ATTEMPTS", 3, min_value=1
                )
                queue_skip_players = set(cooldown_players) | {
                    k for k, v in (recent_player_counts or {}).items()
                    if int(v or 0) >= queue_cap
                }
                queue_succeeded_players: set[str] = set()
                queue_attempt_counts: dict[str, int] = {}
                queue_candidates: list[lane.Candidate] = []
                for item in queue_items:
                    try:
                        cand = _xbg.build_x_post_from_article_info(
                            item,
                            gemini_api_key=queue_gemini_key,
                            db_path=db_path or "",
                            logger=LOG,
                            skip_player_keys=queue_skip_players,
                            succeeded_player_keys=queue_succeeded_players,
                            attempt_counts=queue_attempt_counts,
                            max_attempts_per_player=queue_attempts_max,
                        )
                    except Exception as exc:  # noqa: BLE001
                        LOG.warning(
                            "queue 417 drain: build exception source_url=%s err=%r",
                            getattr(item, "source_url", "?"),
                            exc,
                        )
                        cand = None
                    if cand is None:
                        continue
                    queue_candidates.append(cand)
                    processed_queue_items.append(item)
                if queue_candidates:
                    before_q = len(candidates)
                    candidates = candidates + queue_candidates
                    LOG.info(
                        "queue 417 appended: data+others=%d queue=%d total=%d",
                        before_q,
                        len(queue_candidates),
                        len(candidates),
                    )
                else:
                    LOG.info(
                        "queue 417 drain: %d items drained but 0 candidates built "
                        "(safety_check / unverified_numbers / no player)",
                        len(queue_items),
                    )

                # @Tigers_140609 風 速報スクレイプ: 同じ drain 済み記事を再利用し
                # (二重 drain しない)、 重要コメント + 数字だけの速報型 post を
                # 最大 N 件 同じメールに append。 ENABLE_X_POST_NEWS_SCRAPE=1 のみ。
                if _news_scrape_enabled():
                    scrape_pairs = _build_news_scrape_candidates(
                        queue_items,
                        gemini_key=queue_gemini_key,
                        max_count=_news_scrape_max_per_run(),
                        log=LOG,
                        exclude_player_keys={
                            _candidate_player_key(c) for c in candidates
                            if _candidate_player_key(c)
                        },
                    )
                    if scrape_pairs:
                        scrape_cands = [c for c, _ in scrape_pairs]
                        # source 記事は branding と共有。 scrape が拾った item を
                        # processed に積み、 再 drain (次 fire での重複生成) を防ぐ。
                        for _c, it in scrape_pairs:
                            if it not in processed_queue_items:
                                processed_queue_items.append(it)
                        before_s = len(candidates)
                        candidates = candidates + scrape_cands
                        LOG.info(
                            "news_scrape appended: before=%d scrape=%d total=%d",
                            before_s,
                            len(scrape_cands),
                            len(candidates),
                        )

    # 441: relaxed-history fallback removed. user 方針「少なくてもよいから
    # 連発回避優先」(memory: feedback_data_insight_user_preferences_2026_05_15,
    # ticket 436 follow-up 21:20)。 0 件のままなら mail skip。
    if not candidates and recent_player_counts:
        LOG.info(
            "Player history left 0 candidates; skipping mail per user policy "
            "(no relaxed-history backfill).",
        )
    if not candidates:
        LOG.warning("No candidates generated — skip send (insight.db likely sparse).")
        return 0

    # 2026-06-04 user 方針: メールは「ヨシラバー風 voice」のみ。 DB ランキング表 (候補1型) /
    # data_split (序盤/中盤/終盤・本拠地別の生データ枠) は出力しない。 voice metric の
    # allowlist で残す。 voice が 0 件に枯れた便だけ、 scheduled mail を空にしないため
    # 元の候補へ fallback (safety、 log で可視化)。
    if _voice_only_enabled():
        _VOICE_ONLY_METRICS = {
            lane._NEWS_OPINION_METRIC, lane._FAN_VOICE_METRIC, lane._GEMINI_BRANDING_METRIC,
            lane._HOCHI_REPLY_METRIC, lane._REPLY_CANDIDATE_METRIC, lane._VIDEO_RADAR_METRIC,
            lane._PLAYER_COMMENT_METRIC, lane._COMMENT_DB_METRIC, "quote_caption",
            # @Tigers_140609 風 速報スクレイプ (報知/サンスポ facts の速報型) も
            # たんぱく事実型として許可 (voice-only filter で落とさない)。
            lane._NEWS_SCRAPE_METRIC,
            # 2026-06-11 角度 v2 (user 全部GO): たんぱく事実型 pattern① として許可。
            # 2026-06-04 の voice-only は「DB ランキング表の生データ枠」を落とす意図で、
            # 驚き角度 (勝利相関/対戦別/歴代チェイス) は 2-pattern 設計の①に該当する。
            "勝利相関", "対戦別split", "歴代通算チェイス",
            # 2026-06-12 角度①③⑤ (新旧比較/あの日の巨人/週間MVP) も同じ
            # たんぱく事実型 pattern① (驚きゲート/裏取り済み bake-in 由来)。
            "新旧比較", "あの日の巨人", "週間MVP",
            # 2026-06-12 試合前見どころ (今日の試合に直結する数字のみ)。
            "試合前見どころ",
            # 2026-06-12 年俸コスパ (データ×年俸クロス、 バーゲン型のみ)。
            "年俸コスパ",
            # 2026-06-12 chikupn型 (節目達成 / 今季初・以来) + Tigers型 (登録抹消)。
            "節目達成", "今季初・以来", "登録抹消",
        }
        _before_voice = len(candidates)
        _voice_candidates = [c for c in candidates if c.metric in _VOICE_ONLY_METRICS]
        _data_dropped = _before_voice - len(_voice_candidates)
        if _voice_candidates:
            if _data_dropped:
                LOG.info(
                    "voice-only filter: dropped %d DB-data candidates (ranking/data_split), kept %d voice",
                    _data_dropped, len(_voice_candidates),
                )
            candidates = _voice_candidates
        elif _data_dropped:
            # 2026-06-12 user「データ記事は驚きのもの以外は送らないで」: voice 0 件でも
            # 生データ候補を floor として送らない。 mail skip (「少なくてもよい」方針)。
            LOG.warning(
                "voice-only filter emptied the mail (%d data candidates, 0 voice); "
                "skipping send per user policy (no raw-data floor).",
                _before_voice,
            )
            return 0

    # 2026-06-11 ①話題選手連動 (user「その試合で話題になった選手がインプとれそう」):
    # RSSHub 巨人系 X の直近言及数で候補を先頭寄せ (本文・数字は不変、 並びと why_now のみ)。
    # 下の policy gate は順序保持で先頭から cap するため、 boost はこの位置で効く。
    if _topical_boost_enabled() and candidates:
        try:
            from src import x_post_data_angles as _angles

            # data_angles block で取得済みなら再 fetch しない (RSSHub 叩き 1 回/便)
            _buzz = topical_counts if topical_counts is not None \
                else _angles.fetch_topical_counts()
            if _buzz:
                candidates = _angles.boost_topical_candidates(candidates, _buzz)
        except Exception as _tb_exc:  # noqa: BLE001
            LOG.info("topical boost skip: %r", _tb_exc)

    # 2026-05-27 x-impression-plan: final API-free policy gate.
    # Keep the 437 media/share path unchanged; only prune same-mail
    # duplicates and annotate kept candidates with "why now" timing.
    before_policy = len(candidates)
    candidates, policy_drops = lane.apply_x_impression_policy(
        candidates,
        now=now_jst,
        max_candidates=args.max_candidates + extra_policy_slots,
    )
    for dropped, reason in policy_drops:
        LOG.info(
            "x_impression_policy_drop reason=%s title=%s player=%s metric=%s period=%s",
            reason,
            dropped.title,
            dropped.focus_player,
            dropped.metric,
            dropped.period_label,
        )
    if policy_drops:
        LOG.info(
            "x_impression_policy: dropped=%d before=%d after=%d",
            len(policy_drops),
            before_policy,
            len(candidates),
        )
    if not candidates:
        LOG.warning("X impression policy left 0 candidates — skip send.")
        return 0

    # 同一選手の重複を最終段で除去 (branding+速報スクレイプ+報知リプ が同じ主役を
    # 別経路で拾った分。user 2026-06-20: 重複が他ニュースの枠を潰すのを防ぐ)。
    candidates = _dedupe_candidates_by_player(candidates, log=LOG)
    if not candidates:
        LOG.warning("player_dedup left 0 candidates — skip send.")
        return 0

    LOG.info("Composing mail with %d candidates…", len(candidates))
    context_note = ""
    if context_label and lineup_focus_names:
        context_note = "今日のスタメン優先: " + "、".join(lineup_focus_names)
    mail = lane.compose_mail(
        candidates,
        context_label=context_label,
        context_note=context_note,
        dropped=policy_drops,
    )

    if args.dry_run:
        LOG.info("[dry-run] subject=%s", mail.subject)
        LOG.info("[dry-run] candidate count=%d", mail.candidate_count)
        LOG.info("[dry-run] text body preview (first 600 chars):\n%s",
                 mail.text_body[:600])
        return 0

    LOG.info("Sending mail to %s …", recipients)
    request = mdb.MailRequest(
        to=recipients,
        subject=mail.subject,
        text_body=mail.text_body,
        html_body=mail.html_body,
        sender=_resolve_sender(),
        reply_to=_resolve_reply_to(),
        metadata={"ticket": "347", "lane": "x_post_mail", "candidate_count": mail.candidate_count},
        inline_images=[
            mdb.InlineImage(
                content_id=ci.cid,
                data=ci.png,
                mime_subtype="png",
                filename=f"{ci.cid}.png",
            )
            for ci in mail.candidate_images
        ],
    )
    result = mdb.send(request, dry_run=False)
    LOG.info("mail send result: status=%s reason=%s refused=%s",
             result.status, result.reason, result.refused_recipients)
    if result.status not in {"sent", "dry_run"}:
        LOG.error("mail send not sent (status=%s) — exit non-zero", result.status)
        return 4
    # 424: mark queue 417 items as processed only on real send (skip dry_run).
    # 失敗時は queue に残し次 fire で再 drain (rss_fetcher dedup が再 enqueue を防ぐ)。
    if processed_queue_items and result.status == "sent":
        try:
            from src import x_post_candidate_queue as _xpcq_mark  # local re-import
            marked_q = 0
            for item in processed_queue_items:
                if _xpcq_mark.mark_processed(item):
                    marked_q += 1
            LOG.info(
                "queue 417 mark_processed: %d / %d items",
                marked_q,
                len(processed_queue_items),
            )
        except Exception as exc:  # noqa: BLE001
            LOG.warning("queue 417 mark_processed failed: %r", exc)
    # 355: record the signatures of the candidates we just shipped so
    # subsequent runs (within 24h) can dedup them. Only runs when the
    # dedup feature is enabled (bucket env present + not opted-out).
    if (
        dedup_set is not None
        and bucket_name
        and result.status == "sent"
    ):
        signatures = [c.signature for c in candidates if c.signature]
        if signatures:
            signed_candidates = [c for c in candidates if c.signature]
            ok = lane._record_dedup_signatures(
                bucket_name,
                signatures,
                now_jst,
                focus_players=[c.focus_player for c in signed_candidates],
                metrics=[c.metric for c in signed_candidates],
                period_labels=[c.period_label for c in signed_candidates],
            )
            LOG.info("Recorded %d dedup signatures (ok=%s)",
                     len(signatures), ok)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    sys.exit(main())
