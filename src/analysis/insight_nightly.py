"""INSIGHT-003 — nightly orchestrator.

Binds INSIGHT-001 (ETL) + INSIGHT-002 (fetcher / multi-game / lineup) into
a single CLI that:

  1. Resolves the NPB box HTML for ``--slug`` via cache-first fetch.
     Default ``allow_live=False`` so Claude / tests cannot trigger real
     HTTP; user passes ``--live`` to enable the actual network call.
  2. Ingests the HTML through :func:`insight_etl.etl_from_html` —
     inserts game / batting_logs / pitching_logs / single-game signals
     into the shared SQLite (``data/insight/insight.db``).
  3. Upserts lineups via :func:`insight_lineup_history.upsert_lineup_from_parsed_box`.
  4. Runs :func:`insight_multi_game_detector.run_all_detectors` and
     :func:`insight_lineup_history.run_all_lineup_detectors` across the
     full accumulated history.
  5. Persists the freshly emitted candidates and exports a markdown
     digest via :mod:`insight_markdown_summary`.

Production touch surface:

* Reads / writes ``data/insight/insight.db`` and
  ``data/insight/article_candidates.csv``.
* Reads / writes ``data/insight/raw_html/<slug>.html`` (cache).
* Writes a markdown digest to ``data/insight/digest/<date>.md``.
* **No WP REST, no Gemini, no X API, no Scheduler / env change.**
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.analysis import (  # noqa: E402
    insight_defense_proxy,
    insight_etl,
    insight_fetcher,
    insight_gcs_sync,
    insight_lineup_history,
    insight_markdown_summary,
    insight_multi_game_detector,
    insight_schedule,
)
from src.source_npb_postgame_extractor import parse_npb_box_html  # noqa: E402

DEFAULT_DIGEST_DIR = ROOT / "data" / "insight" / "digest"


class NoScheduledGames(RuntimeError):
    """Schedule page was readable, but no target game exists for this lane."""

    def __init__(self, *, target_date: dt.date, scope: str, reason: str):
        super().__init__(reason)
        self.target_date = target_date
        self.scope = scope
        self.reason = reason


# issue #44 G: counting metric ranking publish 対象。 batting_logs schema は
# AB, R, H, RBI, SB のみで HR 列が無い (HR は atbats_json 内) が、
# ranking_article_publisher.aggregate_player_counting_stat が stat_col="HR"
# を検出して atbats_json 経由の集計 (aggregate_player_hr_from_atbats) に
# dispatch するため、 HR row も COUNTING_METRICS に含める (本塁打数 ranking
# 記事を publish するため)。
COUNTING_METRICS: tuple[dict[str, str], ...] = (
    {"stat_col": "H", "table": "batting_logs",
     "metric_label_jp": "安打数"},
    {"stat_col": "HR", "table": "batting_logs",
     "metric_label_jp": "本塁打数"},
    {"stat_col": "RBI", "table": "batting_logs",
     "metric_label_jp": "打点"},
    {"stat_col": "SB", "table": "batting_logs",
     "metric_label_jp": "盗塁"},
    {"stat_col": "K", "table": "pitching_logs",
     "metric_label_jp": "奪三振数"},
)


def _data_insight_auto_draft_enabled() -> bool:
    return os.environ.get("ENABLE_DATA_INSIGHT_AUTO_DRAFT", "0").strip() == "1"


def _data_insight_no_game_day_publish_enabled() -> bool:
    return os.environ.get("ENABLE_DATA_INSIGHT_NO_GAME_DAY_PUBLISH", "0").strip() == "1"


def _run_data_insight_auto_publish(*, db_path: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run the DATA-INSIGHT article publish lane from the current DB state."""
    anomaly_publish_summary = {"skipped": True, "reason": "default_disabled"}
    ranking_publish_summary = {"skipped": True, "reason": "default_disabled"}
    if not _data_insight_auto_draft_enabled():
        return anomaly_publish_summary, ranking_publish_summary

    try:
        from src.analysis import insight_anomaly_detector as anomaly_det
        from src.analysis import anomaly_article_publisher as anomaly_pub
        from src.analysis import ranking_article_publisher as ranking_pub
        from src import wp_client as wp_mod
        conn = insight_etl.open_db(
            db_path=db_path,
            schema_path=insight_etl.DEFAULT_SCHEMA,
        )
        try:
            auto_draft_max_per_run = int(
                os.environ.get("DATA_INSIGHT_PUBLISH_MAX_PER_RUN", "3") or "3"
            )
            # 1. anomaly signal を detect (article_candidates に insert)
            try:
                anomaly_detect_summary = anomaly_det.run_all_anomaly_detectors(conn)
                detector_errors = anomaly_detect_summary.get(
                    anomaly_det.DETECTOR_ERROR_KEY, []
                )
                if detector_errors:
                    print(json.dumps({
                        "warn": "anomaly_detector_partial_failures",
                        "errors": detector_errors,
                    }, ensure_ascii=False))
            except Exception as exc:  # noqa: BLE001
                print(json.dumps({
                    "warn": "anomaly_detect_failed",
                    "error": f"{type(exc).__name__}:{exc}",
                }, ensure_ascii=False))
            # 2. WP draft publish (best-effort)
            try:
                wp = wp_mod.WPClient()
                # 2026-05-16 user feedback: same-player / same-metric
                # articles and mails were too frequent. Keep the default
                # cap conservative; callers can override by env.
                anomaly_publish_summary = {
                    "results": anomaly_pub.publish_anomaly_drafts(
                        conn, wp, max_per_run=auto_draft_max_per_run,
                    ),
                }
                ranking_publish_summary = {
                    "results": ranking_pub.publish_default_set(
                        conn, wp, max_per_run=auto_draft_max_per_run,
                    ),
                }
                # team ranking 記事 (球団 metric、user 指示で追加)
                # 2026-05-21 user feedback「6球団横並びをもう少し増やしていい」:
                # 個別 cap を分離。 default_jobs (HR/AVG/ERA) 3 + streak 1 +
                # RUN_DIFF 1 + vs opponent 5 = 最大 10 可能、 cap=8 で広めに
                # 出す (実 fire 数は dedup cooldown で半分以下に落ち着く想定)。
                team_max_per_run = int(
                    os.environ.get("DATA_INSIGHT_TEAM_PUBLISH_MAX_PER_RUN", "8")
                    or "8"
                )
                try:
                    from src.analysis import team_ranking_publisher as team_pub
                    team_summary = team_pub.publish_team_default_set(
                        conn, wp, max_per_run=team_max_per_run
                    )
                    ranking_publish_summary["team_results"] = team_summary
                except Exception as exc:  # noqa: BLE001
                    ranking_publish_summary["team_error"] = (
                        f"{type(exc).__name__}:{exc}"
                    )
                # ③ 今日は何の日(OB 誕生日)。新タイプのため env flag gate
                # (DATA_INSIGHT_OB_ANNIVERSARY=1)+ 既定 draft。X 解放は §11 user 判断。
                try:
                    from src.analysis import ob_anniversary as ob_anniv
                    if ob_anniv.enabled():
                        ranking_publish_summary["ob_anniversary"] = (
                            ob_anniv.publish_today_birthday_articles(wp)
                        )
                except Exception as exc:  # noqa: BLE001
                    ranking_publish_summary["ob_anniversary_error"] = (
                        f"{type(exc).__name__}:{exc}"
                    )
                # ② 節目カウントダウン(現役の通算記録接近)。新タイプのため env
                # flag gate(DATA_INSIGHT_CAREER_MILESTONE=1)+ 既定 draft。X 解放は §11。
                try:
                    from src.analysis import career_milestone as career_ms
                    if career_ms.enabled():
                        ranking_publish_summary["career_milestone"] = (
                            career_ms.publish_approaching_milestone_articles(wp)
                        )
                except Exception as exc:  # noqa: BLE001
                    ranking_publish_summary["career_milestone_error"] = (
                        f"{type(exc).__name__}:{exc}"
                    )
                # 348 step 3 part 2 D-1: player counting stats ranking
                # title variation のため multi-scope 投入
                # (season / last_30d / monthly / weekly)、 step 3 part 1
                # で追加した新 scope を実 publish で使う。
                try:
                    # issue #44 C: COUNTING_METRICS は module
                    # 定数化、 HR 行除外 (batting_logs に HR 列無し)
                    counting_metrics = list(COUNTING_METRICS)
                    # 2026-05-16 user feedback: one-week /
                    # one-month / season variants of the same
                    # metric firing together is noisy. Auto
                    # publish only the most time-sensitive
                    # counting window here; longer windows need
                    # a separate change gate before re-emitting.
                    # 403 (2026-05-20): weekly (calendar 月-日) も試合
                    # のない日に sample 不足、 試合数 base last_5_games に
                    # cutover (audit 確定)。
                    counting_scopes = ["last_5_games"]
                    counting_published = 0
                    for metric in counting_metrics:
                        for scope in counting_scopes:
                            if counting_published >= auto_draft_max_per_run:
                                break
                            try:
                                counting_result = ranking_pub.publish_player_counting_draft(
                                    conn, wp, scope=scope, **metric,
                                )
                                if counting_result.get("status") in (
                                    "published", "published_draft", "dry_run",
                                ):
                                    counting_published += 1
                            except Exception as exc:  # noqa: BLE001
                                print(json.dumps({
                                    "warn": "player_counting_publish_failed",
                                    "metric": metric.get("stat_col"),
                                    "scope": scope,
                                    "error": f"{type(exc).__name__}:{exc}",
                                }, ensure_ascii=False))
                        if counting_published >= auto_draft_max_per_run:
                            break
                    # 348 step 3 完全達成: ホーム/アウェイ + 対戦相手別 grouping
                    home_away_splits = [
                        ("home_away", "home", "ホーム"),
                        ("home_away", "away", "アウェイ"),
                    ]
                    opp_splits = [
                        ("opponent", "t", "vs 阪神"),
                        ("opponent", "s", "vs ヤクルト"),
                        ("opponent", "c", "vs 広島"),
                        ("opponent", "db", "vs DeNA"),
                        ("opponent", "d", "vs 中日"),
                    ]
                    # split は H/HR/RBI のみ × weekly。
                    # 2026-05-16 user feedback: 大手が出す
                    # season / full-period は auto publish から
                    # 外す。長期 split は別 gate で再導入判断。
                    split_metrics = [m for m in counting_metrics
                                     if m["stat_col"] in ("H", "HR", "RBI")]
                    split_published = 0
                    for metric in split_metrics:
                        for sf, sv, sl in home_away_splits + opp_splits:
                            if split_published >= auto_draft_max_per_run:
                                break
                            try:
                                # 403 (2026-05-20): weekly → last_5_games cutover
                                split_result = ranking_pub.publish_player_counting_split_draft(
                                    conn, wp, scope="last_5_games",
                                    split_field=sf, split_value=sv,
                                    split_label_jp=sl, **metric,
                                )
                                if split_result.get("status") in (
                                    "published", "published_draft", "dry_run",
                                ):
                                    split_published += 1
                            except Exception as exc:  # noqa: BLE001
                                print(json.dumps({
                                    "warn": "player_counting_split_publish_failed",
                                    "metric": metric.get("stat_col"),
                                    "split": f"{sf}={sv}",
                                    "error": f"{type(exc).__name__}:{exc}",
                                }, ensure_ascii=False))
                        if split_published >= auto_draft_max_per_run:
                            break
                    # 2026-05-25 user 確定: 打順 band 別 publish (上位 /
                    # クリーンナップ / 下位) は disable。 「下位打線 打点 2」
                    # 「クリーンナップ 安打数 5」 等の slice metric は ファン
                    # 興味の薄い niche metric で interesting でない判定。
                    # 関数 (publish_player_counting_by_slot_band_draft /
                    # render_player_counting_by_slot_band_article /
                    # aggregate_player_counting_stat_by_slot_band) は
                    # `ranking_article_publisher.py` 内に残置 (test 互換)、
                    # nightly 自動 publish trigger のみここで disable。
                    slot_band_published = 0  # noqa: F841 — disable 後も summary 用に変数維持
                    # 404 (2026-05-20): 登板 inning 別 publisher。 リリーフ
                    # role split (7 回 setup / 8 回 setup / 9 回 closer)。
                    # start_inning 列は 404 で derive、 backfill_pitcher_innings
                    # で既存 row も populate 済 (open_db 経由 idempotent migration)。
                    inning_published = 0
                    for inning in (9, 8, 7):  # closer > setup の順で fan 訴求高
                        if inning_published >= auto_draft_max_per_run:
                            break
                        try:
                            inning_result = ranking_pub.publish_pitcher_inning_split_draft(
                                conn, wp, scope="last_5_games", inning=inning,
                            )
                            if inning_result.get("status") in (
                                "published", "published_draft", "dry_run",
                            ):
                                inning_published += 1
                        except Exception as exc:  # noqa: BLE001
                            print(json.dumps({
                                "warn": "pitcher_inning_split_publish_failed",
                                "inning": inning,
                                "error": f"{type(exc).__name__}:{exc}",
                            }, ensure_ascii=False))
                    # 415 MVP (2026-05-20): vs 左右投手 split (approach (a) approx)。
                    # starter 限定 platoon、 NPB roster scrape の throws data 利用。
                    # last_10_games scope (last_5 では starter 対戦 sample 不足)。
                    lr_published = 0
                    for hand in ("L", "R"):
                        if lr_published >= auto_draft_max_per_run:
                            break
                        try:
                            lr_result = ranking_pub.publish_batter_vs_lr_split_draft(
                                conn, wp, scope="last_10_games", pitcher_hand=hand,
                            )
                            if lr_result.get("status") in (
                                "published", "published_draft", "dry_run",
                            ):
                                lr_published += 1
                        except Exception as exc:  # noqa: BLE001
                            print(json.dumps({
                                "warn": "batter_vs_lr_split_publish_failed",
                                "pitcher_hand": hand,
                                "error": f"{type(exc).__name__}:{exc}",
                            }, ensure_ascii=False))
                    # 405 (2026-05-21) Phase 2c + 3a/3b/3c: NPB playbyplay
                    # ingest + 走者状況別 / 打席内カウント別 / vs 球団別
                    # publisher。 ingest はベストエフォート (失敗時 publisher
                    # 側で no_data skip)。
                    try:
                        from src.analysis import insight_etl as _etl
                        ingest_stats = _etl.ingest_giants_playbyplay_recent_games(
                            conn, last_n_games=10,
                        )
                        print(json.dumps({
                            "event": "playbyplay_ingest",
                            "attempted": ingest_stats.get("games_attempted", 0),
                            "succeeded": ingest_stats.get("games_succeeded", 0),
                            "pa_rows": ingest_stats.get("pa_rows_upserted", 0),
                            "errors": len(ingest_stats.get("errors", [])),
                        }, ensure_ascii=False))
                    except Exception as exc:  # noqa: BLE001
                        print(json.dumps({
                            "warn": "playbyplay_ingest_failed",
                            "error": f"{type(exc).__name__}:{exc}",
                        }, ensure_ascii=False))
                    # 走者状況別 publisher (満塁 / 1・3塁 / 2・3塁 = 得点機 3 種)
                    runner_state_published = 0
                    for r_state in ("満塁", "1・3塁", "2・3塁"):
                        if runner_state_published >= auto_draft_max_per_run:
                            break
                        try:
                            r_result = ranking_pub.publish_giants_batter_runner_state_split_draft(
                                conn, wp, runner_state=r_state, last_n_games=10,
                            )
                            if r_result.get("status") in (
                                "published", "published_draft", "dry_run",
                            ):
                                runner_state_published += 1
                        except Exception as exc:  # noqa: BLE001
                            print(json.dumps({
                                "warn": "runner_state_split_publish_failed",
                                "runner_state": r_state,
                                "error": f"{type(exc).__name__}:{exc}",
                            }, ensure_ascii=False))
                    # 打席内カウント別 publisher
                    count_filter_published = 0
                    for cf in ("first_pitch", "two_strike"):
                        if count_filter_published >= auto_draft_max_per_run:
                            break
                        try:
                            cf_result = ranking_pub.publish_giants_batter_count_filter_draft(
                                conn, wp, count_filter=cf, last_n_games=10,
                            )
                            if cf_result.get("status") in (
                                "published", "published_draft", "dry_run",
                            ):
                                count_filter_published += 1
                        except Exception as exc:  # noqa: BLE001
                            print(json.dumps({
                                "warn": "count_filter_publish_failed",
                                "count_filter": cf,
                                "error": f"{type(exc).__name__}:{exc}",
                            }, ensure_ascii=False))
                    # vs 球団別 publisher (5 セ・リーグ相手)
                    vs_opp_published = 0
                    for opp in ("ヤクルト", "阪神", "DeNA", "中日", "広島"):
                        if vs_opp_published >= auto_draft_max_per_run:
                            break
                        try:
                            opp_result = ranking_pub.publish_giants_batter_vs_opponent_draft(
                                conn, wp, opponent=opp, last_n_games=10,
                            )
                            if opp_result.get("status") in (
                                "published", "published_draft", "dry_run",
                            ):
                                vs_opp_published += 1
                        except Exception as exc:  # noqa: BLE001
                            print(json.dumps({
                                "warn": "vs_opponent_publish_failed",
                                "opponent": opp,
                                "error": f"{type(exc).__name__}:{exc}",
                            }, ensure_ascii=False))
                    # 415 (b) strict (2026-05-21): per-PA throws lookup で対 L/R
                    # 高精度集計。 既存 (a) approx (publish_batter_vs_lr_split_draft、
                    # starter 限定) と並列稼働、 dedup metric_name は別 key
                    # (VS_LR_STRICT:L vs VS_LR:L) なので同 dedup window でも
                    # 競合しない。
                    lr_strict_published = 0
                    for hand in ("L", "R"):
                        if lr_strict_published >= auto_draft_max_per_run:
                            break
                        try:
                            ls_result = ranking_pub.publish_giants_batter_vs_lr_strict_draft(
                                conn, wp, pitcher_hand=hand, last_n_games=10,
                            )
                            if ls_result.get("status") in (
                                "published", "published_draft", "dry_run",
                            ):
                                lr_strict_published += 1
                        except Exception as exc:  # noqa: BLE001
                            print(json.dumps({
                                "warn": "vs_lr_strict_publish_failed",
                                "pitcher_hand": hand,
                                "error": f"{type(exc).__name__}:{exc}",
                            }, ensure_ascii=False))
                except Exception as exc:  # noqa: BLE001
                    ranking_publish_summary["counting_error"] = (
                        f"{type(exc).__name__}:{exc}"
                    )
            except Exception as exc:  # noqa: BLE001
                anomaly_publish_summary = {
                    "skipped": True,
                    "reason": f"publish_error:{type(exc).__name__}",
                }
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        anomaly_publish_summary = {
            "skipped": True,
            "reason": f"import_error:{type(exc).__name__}",
        }
    return anomaly_publish_summary, ranking_publish_summary


def _run_no_game_day_publish_if_enabled(*, args: argparse.Namespace) -> dict[str, Any]:
    """Optionally publish DATA-INSIGHT articles when the schedule has no games."""
    if not getattr(args, "all_teams", False):
        return {"enabled": False, "reason": "single_game_mode"}
    if not _data_insight_auto_draft_enabled():
        return {"enabled": False, "reason": "auto_draft_disabled"}
    if not _data_insight_no_game_day_publish_enabled():
        return {"enabled": False, "reason": "flag_disabled"}

    db_path = Path(args.db)
    try:
        gcs_pull_summary = insight_gcs_sync.download_state(
            base_dir=db_path.parent,
        )
    except Exception as exc:  # noqa: BLE001
        gcs_pull_summary = {"skipped": True, "reason": f"download_error:{exc!r}"}

    anomaly_publish_summary, ranking_publish_summary = _run_data_insight_auto_publish(
        db_path=db_path,
    )
    try:
        gcs_push_summary = insight_gcs_sync.upload_state(
            base_dir=db_path.parent,
            digest_dir=None,
        )
    except Exception as exc:  # noqa: BLE001
        gcs_push_summary = {"skipped": True, "reason": f"upload_error:{exc!r}"}
    return {
        "enabled": True,
        "gcs_pull": gcs_pull_summary,
        "anomaly_publish": anomaly_publish_summary,
        "ranking_publish": ranking_publish_summary,
        "gcs_push": gcs_push_summary,
    }


def resolve_all_slugs_auto(
    *,
    target_date: dt.date,
    allow_live: bool = False,
    http_get=None,
    cache_dir: Path = insight_fetcher.DEFAULT_CACHE_DIR,
) -> list[str]:
    """指定日の **全 NPB 試合** slug をまとめて返す。schedule HTML を 1 度
    だけ fetch (cache-first)、その上で parse。"""
    candidates_urls = [
        (
            insight_schedule.npb_monthly_schedule_url(target_date.year, target_date.month),
            f"schedule_{target_date.year}_{target_date.month:02d}.html",
        ),
        (
            insight_schedule.npb_daily_schedule_url(target_date),
            f"schedule_{target_date.isoformat()}_daily.html",
        ),
    ]
    target_str = target_date.isoformat()
    last_error: Exception | None = None
    parsed_schedule_seen = False
    for url, cache_filename in candidates_urls:
        try:
            html, _meta = insight_fetcher.fetch_html_polite(
                url,
                cache_filename=cache_filename,
                http_get=http_get,
                cache_dir=cache_dir,
                allow_live=allow_live,
            )
        except insight_fetcher.FetchBlocked as exc:
            last_error = exc
            continue
        if insight_schedule.parse_npb_schedule_html(html):
            parsed_schedule_seen = True
        slugs = insight_schedule.resolve_all_slugs_for_date(html, target_str)
        if slugs:
            return slugs
    if parsed_schedule_seen:
        raise NoScheduledGames(
            target_date=target_date,
            scope="npb",
            reason=f"no scheduled NPB games for {target_str}",
        )
    raise insight_fetcher.FetchBlocked(
        f"auto_resolve_all_failed: no slugs found for {target_str} "
        f"(last error: {last_error!r})"
    )


def resolve_slug_auto(
    *,
    target_date: dt.date,
    allow_live: bool = False,
    http_get=None,
    cache_dir: Path = insight_fetcher.DEFAULT_CACHE_DIR,
) -> str:
    """指定日の Giants slug を NPB schedule から自動解決する。

    Polite fetch is cache-first; ``allow_live=True`` で実 HTTP を許可。
    schedule HTML を 2 段で試す: 月別 schedule → 日次 schedule。
    どちらでも見つからなければ ``FetchBlocked`` を raise。
    """
    candidates_urls = [
        (
            insight_schedule.npb_monthly_schedule_url(target_date.year, target_date.month),
            f"schedule_{target_date.year}_{target_date.month:02d}.html",
        ),
        (
            insight_schedule.npb_daily_schedule_url(target_date),
            f"schedule_{target_date.isoformat()}_daily.html",
        ),
    ]
    last_error: Exception | None = None
    target_str = target_date.isoformat()
    parsed_schedule_seen = False
    for url, cache_filename in candidates_urls:
        try:
            html, _meta = insight_fetcher.fetch_html_polite(
                url,
                cache_filename=cache_filename,
                http_get=http_get,
                cache_dir=cache_dir,
                allow_live=allow_live,
            )
        except insight_fetcher.FetchBlocked as exc:
            last_error = exc
            continue
        if insight_schedule.parse_npb_schedule_html(html):
            parsed_schedule_seen = True
        slug = insight_schedule.resolve_giants_slug_for_date(html, target_str)
        if slug:
            return slug
    if parsed_schedule_seen:
        raise NoScheduledGames(
            target_date=target_date,
            scope="giants",
            reason=f"no scheduled Giants game for {target_str}",
        )
    raise insight_fetcher.FetchBlocked(
        f"auto_resolve_failed: no Giants slug found for {target_str} "
        f"(last error: {last_error!r})"
    )


def _default_slug_game_id(slug: str) -> str:
    """``2026/0510/d-g-08`` → ``2026-05-10:d-g-08``"""
    parts = slug.strip("/").split("/")
    if len(parts) != 3:
        return slug.replace("/", "-")
    year, mmdd, code = parts
    mm = mmdd[:2]
    dd = mmdd[2:]
    return f"{year}-{mm}-{dd}:{code}"


def _default_game_date(slug: str) -> str:
    parts = slug.strip("/").split("/")
    if len(parts) != 3:
        return ""
    year, mmdd, _ = parts
    return f"{year}-{mmdd[:2]}-{mmdd[2:]}"


def run_nightly(
    *,
    slug: str,
    game_id: Optional[str] = None,
    game_date: Optional[str] = None,
    allow_live: bool = False,
    http_get=None,
    db_path: Path = insight_etl.DEFAULT_DB_PATH,
    schema_path: Path = insight_etl.DEFAULT_SCHEMA,
    csv_path: Path = insight_etl.DEFAULT_CSV,
    cache_dir: Path = insight_fetcher.DEFAULT_CACHE_DIR,
    digest_dir: Path = DEFAULT_DIGEST_DIR,
    write_digest: bool = True,
    fetched_html: Optional[str] = None,
) -> dict:
    """Orchestrate one nightly run for a single game ``slug``.

    Parameters
    ----------
    slug:
        NPB scores slug, e.g. ``"2026/0510/d-g-08"``.
    game_id / game_date:
        Optional overrides; default derived from ``slug``.
    allow_live:
        ``True`` to permit real HTTP on cache miss. ``False`` (default)
        is safe for tests / Claude — cache miss raises ``FetchBlocked``.
    http_get:
        Optional :func:`requests.get` substitute for tests.
    fetched_html:
        Optional pre-fetched HTML (bypasses the fetcher entirely).
        Used in tests / when caller already has the HTML in memory.
    write_digest:
        ``False`` skips the markdown digest step (still returns the
        candidate summary). Useful for tests.
    """
    game_id = game_id or _default_slug_game_id(slug)
    game_date = game_date or _default_game_date(slug)
    if not game_date:
        raise ValueError(f"could not derive game_date from slug={slug!r}")

    # GCS pull (INSIGHT-005): hydrate DB / CSV before ETL so multi-game
    # detectors have history. No-op when INSIGHT_GCS_BUCKET unset.
    gcs_pull_summary = None
    try:
        gcs_pull_summary = insight_gcs_sync.download_state(
            base_dir=db_path.parent,
        )
    except Exception as exc:  # noqa: BLE001 - download failure must not block pipeline
        gcs_pull_summary = {"skipped": True, "reason": f"download_error:{exc!r}"}

    if fetched_html is None:
        html, fetch_meta = insight_fetcher.cache_or_fetch(
            slug,
            allow_live=allow_live,
            http_get=http_get,
            cache_dir=cache_dir,
        )
    else:
        html = fetched_html
        fetch_meta = {"from_cache": False, "status_code": 200, "url": None,
                      "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat()}

    # Step 2 — single-game ETL (also inserts single-game candidates).
    etl_summary = insight_etl.etl_from_html(
        html,
        game_id=game_id,
        game_date=game_date,
        db_path=db_path,
        schema_path=schema_path,
        csv_path=csv_path,
        source_url=fetch_meta.get("url"),
        source_kind="live" if not fetch_meta.get("from_cache") else "cache",
        notes=f"nightly slug={slug}",
    )

    # Step 3 — lineup upsert (post-game lineup from the same parsed box).
    parsed = parse_npb_box_html(html, allow_non_giants=True)
    conn = insight_etl.open_db(db_path=db_path, schema_path=schema_path)
    try:
        lineup_rows = insight_lineup_history.upsert_lineup_from_parsed_box(
            conn, game_id=game_id, parsed=parsed,
        )

        # INSIGHT-007: defense_opportunities を atbats から再構築。
        # 失敗しても pipeline は止めない (best-effort)。
        try:
            insight_defense_proxy.rebuild_defense_for_game(conn, game_id=game_id)
        except Exception:  # noqa: BLE001
            pass

        # 343-INSIGHT-007 follow-up: 12 team team-aware roster resolution。
        # npb_12team_roster.json を使って batting_logs / pitching_logs の
        # player_canonical NULL 行を team_name 経由で fill (Giants 戦の
        # opponent player や パ・リーグ player の canonical を遡って解決)。
        # seed_players_from_logs より前に呼ぶことで、解決した canonical が
        # players table の seed 対象に入る。
        try:
            insight_etl.fill_canonical_team_aware(conn)
        except Exception:  # noqa: BLE001
            pass

        # 343-INSIGHT-007 backfill: teams / players / advanced_metric_snapshots。
        # defense_proxy と同 best-effort pattern、いずれの失敗も pipeline は止めない。
        try:
            insight_etl.seed_teams(conn)
            insight_etl.seed_players_from_logs(conn)
        except Exception:  # noqa: BLE001
            pass
        try:
            today_iso = dt.date.today().isoformat()
            # 343-INSIGHT-007 scope-aware threshold:
            # season 早期は data sparse (5月時点で 1 player ~10 AB)、後半は
            # 充足するため scope 別に最小 sample 閾値を変える。
            #   last_7d:    PA >= 5  / IP >= 1.0  (週次 hot/cold 用、緩め)
            #   last_30d:   PA >= 15 / IP >= 5.0  (月次 ranking 用、中庸)
            #   season:     PA >= 50 / IP >= 15.0 (年間 ranking 用、厳しめ)
            # 348 step 3 拡張:
            #   last_5_games:  PA >= 3 / IP >= 0.0 (直近 5 試合 rolling)
            #   last_10_games: PA >= 6 / IP >= 0.0 (直近 10 試合 rolling)
            #   weekly:        PA >= 5 / IP >= 1.0 (ISO 週、 last_7d と類似)
            #   monthly:       PA >= 15 / IP >= 5.0 (当月 1 日〜snapshot 日)
            # issue #44 #1: season scope は規定打席 (試合数 × 3.1) /
            # 規定投球回 (試合数 × 1.0) の動的閾値に切替。 短期 scope は
            # 公式記録ではない (= 規定到達は意味なし) ため現状の固定値
            # 維持。 詳細は ``insight_etl.team_games_for_qualified_thresholds``
            # docstring。
            team_games = insight_etl.team_games_for_qualified_thresholds(conn)
            qualified_pa = int(team_games * 3.1)
            qualified_ip = float(team_games * 1.0)
            scope_thresholds: tuple[tuple[str, int, float], ...] = (
                ("last_7d", 5, 1.0),
                ("last_30d", 15, 5.0),
                ("season", qualified_pa, qualified_ip),
                # 直近 N 試合 rolling (user 2026-05-20: calendar scope 廃止、
                # 投手 / 打者 / 守備 全て 直近 3/5/10/20試合 に統一)
                ("last_3_games", 2, 0.0),
                ("last_5_games", 3, 0.0),
                ("last_10_games", 6, 0.0),
                ("last_20_games", 12, 0.0),
                ("weekly", 5, 1.0),
                ("monthly", 15, 5.0),
            )
            for snapshot_scope, min_pa, min_ip in scope_thresholds:
                insight_etl.compute_advanced_metric_snapshots(
                    conn, scope=snapshot_scope, snapshot_date=today_iso,
                    min_pa=min_pa, min_ip=min_ip,
                )
        except Exception:  # noqa: BLE001
            pass

        conn.commit()

        # Step 4 — multi-game + lineup detectors against full history.
        now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
        multi_run_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO insight_runs (run_id, run_ts, window_start, window_end, n_candidates, notes) "
            "VALUES (?,?,?,?,?,?)",
            (multi_run_id, now_iso, None, game_date, 0,
             f"nightly multi-game/lineup pass for slug={slug}"),
        )

        multi_candidates = insight_multi_game_detector.run_all_detectors(
            conn, run_id=multi_run_id, created_at=now_iso,
        )
        lineup_candidates = insight_lineup_history.run_all_lineup_detectors(
            conn, run_id=multi_run_id, created_at=now_iso,
        )
        all_candidates = list(multi_candidates) + list(lineup_candidates)
        if all_candidates:
            insight_etl.insert_candidates(conn, all_candidates)
        conn.execute(
            "UPDATE insight_runs SET n_candidates=? WHERE run_id=?",
            (len(all_candidates), multi_run_id),
        )
        conn.commit()

        csv_rows = insight_etl.export_candidates_csv(conn, csv_path)
    finally:
        conn.close()

    summary: dict[str, Any] = {
        "slug": slug,
        "game_id": game_id,
        "game_date": game_date,
        "fetch_meta": fetch_meta,
        "etl": etl_summary,
        "lineup_rows": lineup_rows,
        "multi_run_id": multi_run_id,
        "multi_game_candidates": len(multi_candidates),
        "lineup_candidates": len(lineup_candidates),
        "csv_rows_total": csv_rows,
        "digest_path": None,
    }

    if write_digest:
        digest_path = digest_dir / f"{game_date}.md"
        n_digest_rows = insight_markdown_summary.write_digest(
            db_path=db_path,
            game_date=game_date,
            out_path=digest_path,
        )
        summary["digest_path"] = str(digest_path)
        summary["digest_rows"] = n_digest_rows

    summary["gcs_pull"] = gcs_pull_summary

    # GCS push (INSIGHT-005): persist DB / CSV / digest for next run.
    try:
        summary["gcs_push"] = insight_gcs_sync.upload_state(
            base_dir=db_path.parent,
            digest_dir=digest_dir if write_digest else None,
        )
    except Exception as exc:  # noqa: BLE001 - surface but don't fail
        summary["gcs_push"] = {"skipped": True, "reason": f"upload_error:{exc!r}"}

    return summary


# ─── CLI ───────────────────────────────────────────────────────────────────


def _parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="INSIGHT-003/004 nightly orchestrator (cache-first, --live opt-in)."
    )
    p.add_argument("--slug", default=None, help="NPB scores slug (omit with --auto)")
    p.add_argument(
        "--auto", action="store_true",
        help="auto-resolve slug from NPB schedule (uses --date, default = JST yesterday)",
    )
    p.add_argument(
        "--all-teams", action="store_true",
        help="INSIGHT-007: ingest ALL 12-team NPB games for the date (default: Giants only). Requires --auto.",
    )
    p.add_argument(
        "--date", default=None,
        help="game date YYYY-MM-DD (default = JST yesterday when --auto)",
    )
    p.add_argument("--game-id", default=None, help="override (default derived from slug)")
    p.add_argument("--game-date", default=None, help="override (default derived from slug)")
    p.add_argument("--live", action="store_true",
                   help="permit real HTTP on cache miss (default: cache-only)")
    p.add_argument("--no-digest", action="store_true",
                   help="skip markdown digest generation")
    p.add_argument("--db", default=str(insight_etl.DEFAULT_DB_PATH))
    p.add_argument("--csv", default=str(insight_etl.DEFAULT_CSV))
    p.add_argument("--cache-dir", default=str(insight_fetcher.DEFAULT_CACHE_DIR))
    p.add_argument("--digest-dir", default=str(DEFAULT_DIGEST_DIR))
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    if not args.slug and not args.auto:
        print(json.dumps({"status": "blocked", "reason": "must pass --slug or --auto"}, ensure_ascii=False))
        return 2
    if args.all_teams and not args.auto:
        print(json.dumps({"status": "blocked", "reason": "--all-teams requires --auto"}, ensure_ascii=False))
        return 2

    try:
        if args.all_teams:
            target = (
                dt.date.fromisoformat(args.date)
                if args.date else insight_schedule.auto_target_jst_date()
            )
            slugs = resolve_all_slugs_auto(
                target_date=target,
                allow_live=args.live,
                cache_dir=Path(args.cache_dir),
            )
            per_game: list[dict] = []
            for s in slugs:
                try:
                    s_summary = run_nightly(
                        slug=s,
                        allow_live=args.live,
                        db_path=Path(args.db),
                        csv_path=Path(args.csv),
                        cache_dir=Path(args.cache_dir),
                        digest_dir=Path(args.digest_dir),
                        write_digest=False,  # 個別 digest はまとめない
                    )
                    per_game.append({"slug": s, "ok": True, "etl": s_summary.get("etl")})
                except insight_fetcher.FetchBlocked as exc:
                    per_game.append({"slug": s, "ok": False, "reason": str(exc)})
                except Exception as exc:  # noqa: BLE001
                    per_game.append({"slug": s, "ok": False, "reason": f"unexpected:{exc!r}"})
            # 最終的に digest を 1 回だけ書く
            digest_path = None
            if not args.no_digest:
                digest_target = Path(args.digest_dir) / f"{target.isoformat()}.md"
                digest_rows = insight_markdown_summary.write_digest(
                    db_path=Path(args.db),
                    game_date=target.isoformat(),
                    out_path=digest_target,
                )
                digest_path = str(digest_target)

            # DATA-INSIGHT-continuous: anomaly detect + draft publish (Iteration B)
            # 全 slug ETL 完了後に 1 回だけ実行、env flag で完全 disable 可能。
            # 失敗しても pipeline 止めない (best-effort)。
            anomaly_publish_summary, ranking_publish_summary = _run_data_insight_auto_publish(
                db_path=Path(args.db),
            )
            summary = {
                "mode": "all_teams",
                "game_date": target.isoformat(),
                "slugs": slugs,
                "per_game": per_game,
                "digest_path": digest_path,
                # issue #44 H: per-candidate publish 結果 / gate skip 理由を
                # Cloud Logging に流すために summary に格納する。
                # auto-draft default disabled 時も
                # {"skipped": True, "reason": "default_disabled"} が見える。
                "anomaly_publish": anomaly_publish_summary,
                "ranking_publish": ranking_publish_summary,
            }
            # GCS push after all games processed
            try:
                summary["gcs_push"] = insight_gcs_sync.upload_state(
                    base_dir=Path(args.db).parent,
                    digest_dir=Path(args.digest_dir) if not args.no_digest else None,
                )
            except Exception as exc:  # noqa: BLE001
                summary["gcs_push"] = {"skipped": True, "reason": f"upload_error:{exc!r}"}
            print(json.dumps({"status": "ok", **summary}, ensure_ascii=False))
            return 0

        slug = args.slug
        if args.auto:
            target = (
                dt.date.fromisoformat(args.date)
                if args.date else insight_schedule.auto_target_jst_date()
            )
            slug = resolve_slug_auto(
                target_date=target,
                allow_live=args.live,
                cache_dir=Path(args.cache_dir),
            )
        summary = run_nightly(
            slug=slug,
            game_id=args.game_id,
            game_date=args.game_date,
            allow_live=args.live,
            db_path=Path(args.db),
            csv_path=Path(args.csv),
            cache_dir=Path(args.cache_dir),
            digest_dir=Path(args.digest_dir),
            write_digest=not args.no_digest,
        )
    except insight_fetcher.FetchBlocked as exc:
        print(json.dumps({"status": "blocked", "reason": str(exc)}, ensure_ascii=False))
        return 2
    except NoScheduledGames as exc:
        no_game_publish = _run_no_game_day_publish_if_enabled(args=args)
        print(json.dumps({
            "status": "no_game_day",
            "game_date": exc.target_date.isoformat(),
            "scope": exc.scope,
            "reason": exc.reason,
            "data_insight_no_game_publish": no_game_publish,
        }, ensure_ascii=False))
        return 0
    print(json.dumps({"status": "ok", **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
