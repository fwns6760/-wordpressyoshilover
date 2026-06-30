"""data-site publisher main module (ticket 443/444 Phase 1.0).

実行 flow:
1. config から Phase 1.0 対象 player name 取得 (吉川尚輝 / 坂本勇人 / 丸佳浩)
2. 各 player について:
   - roster から position / jersey / role
   - WP REST で featured_media URL + 関連 Topic link 10-20 件
   - Pillar HTML render
   - WP REST `/pages` upsert (slug=player-slug, parent=cluster_page_id)
3. 全 player 終了後、 Cluster HTML render → WP REST `/pages` upsert (slug=data)
4. log + summary 出力

冪等性: WP page を slug で find_existing → 存在すれば PUT update、 無ければ POST。
URL 増加なし、 同 URL 上書き daily upsert。

Cloud Run Job entrypoint = `python -m src.data_site_publisher`。
env:
  - WP_URL / WP_USER / WP_APP_PASSWORD (WP REST 認証)
  - DATA_SITE_DRY_RUN=1 で WP upsert を skip (rendering と log 出力のみ)
"""

from __future__ import annotations

import hashlib as _hashlib
import json as _json
import logging
import os
import re
import sys
from dataclasses import dataclass

import requests
from requests.auth import HTTPBasicAuth

from src.data_site_query import (
    fetch_batting_stats_season,
    fetch_contribution_streak,
    fetch_hit_streak,
    fetch_lineup_slot_stats,
    fetch_opponent_split_stats,
    fetch_venue_split_stats,
    fetch_inning_split_stats,
    fetch_weekday_split_stats,
    fetch_month_split_stats,
    fetch_interleague_split_stats,
    fetch_giants_schedule,
    fetch_team_leaders,
    build_career_leaders,
    build_alltime_leaders,
    build_record_room,
    fetch_team_rankings,
    fetch_giants_team_record,
    fetch_giants_upcoming,
    fetch_npb_cl_standings,
    fetch_latest_giants_game_date,
    fetch_player_latest_game_date,
    fetch_surprise_stats,
    fetch_player_npb_ranks,
    fetch_pitcher_npb_ranks,
    fetch_pitching_stats_season,
    fetch_pitcher_opponent_split_stats,
    fetch_pitcher_venue_split_stats,
    fetch_pitcher_weekday_split_stats,
    fetch_pitcher_month_split_stats,
    fetch_pitcher_interleague_split_stats,
    fetch_recent_games,
    fetch_recent_pitching_games,
    fetch_risp_split_stats,
    fetch_sabermetrics,
    fetch_vs_lr_split_stats,
    fetch_related_topic_links,
    find_player_featured_image_url,
    find_player_featured_media_id,
    load_phase1_player_names,
    load_data_site_target_names,
    mapped_player_media_id,
    load_ikusei_entries,
    shihai_position_group,
    related_shihai_players,
    staff_military_level,
    coach_career_stat,
    load_ob_names,
    ob_legend,
    load_ob_legend_entries,
    load_roster_player,
)
from src.data_site_slug import player_slug
from src.data_site_template_cluster import (
    ClusterPlayerEntry,
    render_cluster_html,
    render_notable_data_excerpt,
    render_notable_data_page_html,
    render_notable_data_title,
    render_cluster_title,
)
from src.data_site_template_schedule import (
    render_schedule_html,
    render_schedule_title,
    render_schedule_excerpt,
)
from src.data_site_template_leaders import (
    render_leaders_html,
    render_leaders_title,
    render_leaders_excerpt,
)
from src.data_site_template_cleanup_hitters import (
    load_cleanup_hitters_data,
    render_cleanup_hitters_html,
    render_cleanup_hitters_title,
    render_cleanup_hitters_excerpt,
)
from src.data_site_jersey_source import fetch_jersey_rows
from src.mlb_alumni_fetch import MLB_ALUMNI, fetch_mlb_alumni_data, fetch_mlb_player_detail
from src.data_site_template_mlb import (
    render_mlb_html,
    render_mlb_title,
    render_mlb_excerpt,
)
from src.data_site_template_mlb_player import (
    render_mlb_player_html,
    render_mlb_player_title,
    render_mlb_player_excerpt,
)
from src.data_site_template_jersey import (
    render_jersey_numbers_excerpt,
    render_jersey_numbers_html,
    render_jersey_numbers_title,
)
from src.data_site_template_draft import (
    load_draft_data,
    render_draft_html,
    render_draft_title,
    render_draft_excerpt,
)
from src.data_site_template_rotation import (
    load_rotation_data,
    render_rotation_html,
    render_rotation_title,
    render_rotation_excerpt,
)
from src.data_site_template_walkoff import (
    load_walkoff_data,
    render_walkoff_html,
    render_walkoff_title,
    render_walkoff_excerpt,
)
from src.data_site_template_fa import (
    load_fa_data,
    render_fa_html,
    render_fa_title,
    render_fa_excerpt,
)
from src.data_site_template_trade import (
    load_trade_data,
    render_trade_html,
    render_trade_title,
    render_trade_excerpt,
)
from src.data_site_template_foreign import (
    load_foreign_players_data,
    render_foreign_players_html,
    render_foreign_players_title,
    render_foreign_players_excerpt,
)
from src.data_site_farm_stats import giants_farm_map
from src.data_site_farm_source import (
    fetch_farm_game_rows,
    fetch_farm_generic_rows,
    farm_player_stats,
)
from src.data_site_template_farm import (
    render_farm_child_excerpt,
    render_farm_child_title,
    render_farm_championship_html,
    render_farm_education_html,
    render_farm_excerpt,
    render_farm_hub_html,
    render_farm_players_html,
    render_farm_schedule_html,
    render_farm_team_html,
    render_farm_title,
    render_farm_titles_html,
)
from src.data_site_template_legends import (
    render_legends_html,
    render_legends_title,
    render_legends_excerpt,
)
from src.data_site_template_team import (
    render_team_html,
    render_team_title,
    render_team_excerpt,
    render_ranking_html,
    render_ranking_title,
    render_ranking_excerpt,
    render_batting_ranking_html,
    render_batting_ranking_title,
    render_batting_ranking_excerpt,
    render_pitching_ranking_html,
    render_pitching_ranking_title,
    render_pitching_ranking_excerpt,
    render_record_html,
    render_record_title,
    render_record_excerpt,
)
from src.data_site_template_pillar import (
    PillarPlayerInfo,
    render_pillar_html,
    render_pillar_title,
    render_pillar_excerpt,
)
from src import npb_career_ingest


LOG = logging.getLogger("data_site_publisher")

# 467: NPB career cache (publish_phase1 開始時に日次 1 回だけ load_or_refresh で満たす)。
# 各 _build_pillar_info が name -> payload を引く。 publish をブロックしない (失敗時は空)。
_CAREER_CACHE: dict = {}

# OB 年度別 (ベンチマーク由来、 config/ob_career_yearly_full.json)。 slug -> npb_career payload。
# 現役は NPB cache、 引退 OB はこちらで年度別フル表を populate する。
_OB_YEARLY_CACHE: dict | None = None


def _ob_yearly_payload(slug: str) -> dict | None:
    """OB の npb_career payload (slug 引き)。 無ければ None。 publish をブロックしない。"""
    global _OB_YEARLY_CACHE
    if _OB_YEARLY_CACHE is None:
        path = os.path.join(os.path.dirname(__file__), "..", "config", "ob_career_yearly_full.json")
        try:
            with open(path, encoding="utf-8") as fh:
                _OB_YEARLY_CACHE = _json.load(fh)
        except Exception:
            _OB_YEARLY_CACHE = {}
    return _OB_YEARLY_CACHE.get(slug)


@dataclass
class UpsertResult:
    slug: str
    page_id: int
    action: str  # "created" / "updated" / "skipped"
    url: str


def _dry_run_enabled() -> bool:
    return str(os.environ.get("DATA_SITE_DRY_RUN", "")).strip().lower() in {"1", "true", "yes", "on"}


_PROSPORTS_MAP_CACHE: dict | None = None


def _prosports_link_map() -> dict:
    """config/prosports_link_map.json の by_slug を返す (data_slug -> [{url,title,...}])。失敗時は空。"""
    global _PROSPORTS_MAP_CACHE
    if _PROSPORTS_MAP_CACHE is None:
        path = os.path.join(os.path.dirname(__file__), "..", "config", "prosports_link_map.json")
        try:
            with open(path, encoding="utf-8") as fh:
                _PROSPORTS_MAP_CACHE = (_json.load(fh) or {}).get("by_slug") or {}
        except Exception as exc:  # noqa: BLE001
            LOG.warning("prosports link map load failed: %r", exc)
            _PROSPORTS_MAP_CACHE = {}
    return _PROSPORTS_MAP_CACHE


# ── 差分更新 (incremental publish) ──────────────────────────────────────────
# 約 970 ページを毎回まるごと WP upsert すると 1 回 ~15 分かかり Cloud Run コストの主因。
# 試合で実際に変わるのは数選手だけなので、描画 HTML の SHA256 を GCS 台帳
# (slug -> {sig,page_id,url}) と照合し、変化なしのページは GET/POST を完全 skip する。
# 台帳は実行開始で download、終了で upload。download/upload 失敗 (初回 / 権限欠如) 時は
# 例外を握って全件 upsert にフォールバックするため、最悪でも従来挙動 = フェイルセーフ。
_HASH_BUCKET = os.environ.get("DATA_SITE_HASH_BUCKET", "baseballsite-yoshilover-state")
_HASH_PREFIX = os.environ.get("DATA_SITE_HASH_PREFIX", "data_site_publisher")
_HASH_REMOTE = "page_hashes.json"
# 親ページ (cluster=data / farm hub) は page_id を子の parent に使うため常に実 upsert
_ALWAYS_FRESH_SLUGS = {"data", "farm"}

_HASH_LEDGER: dict[str, dict] | None = None
_HASH_LEDGER_DIRTY = False
_HASH_SKIPPED = 0
_FORCE_FULL_RUN = False  # canary など、その run だけ全件にしたい時 True


def _incremental_enabled() -> bool:
    if _FORCE_FULL_RUN or _dry_run_enabled():
        return False
    if str(os.environ.get("DATA_SITE_FORCE_FULL", "")).strip().lower() in {"1", "true", "yes", "on"}:
        return False
    return str(os.environ.get("DATA_SITE_INCREMENTAL", "1")).strip().lower() in {"1", "true", "yes", "on"}


# コンテナに gcloud CLI は無いため、GCS は metadata トークン + REST (requests) で直接叩く。
_GCS_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
)


def _gcs_token() -> str:
    r = requests.get(_GCS_TOKEN_URL, headers={"Metadata-Flavor": "Google"}, timeout=5)
    r.raise_for_status()
    return str(r.json()["access_token"])


def _gcs_object_name() -> str:
    return f"{_HASH_PREFIX}/{_HASH_REMOTE}" if _HASH_PREFIX else _HASH_REMOTE


def _gcs_download_text() -> str | None:
    from urllib.parse import quote

    obj = quote(_gcs_object_name(), safe="")
    url = f"https://storage.googleapis.com/storage/v1/b/{_HASH_BUCKET}/o/{obj}?alt=media"
    r = requests.get(url, headers={"Authorization": f"Bearer {_gcs_token()}"}, timeout=20)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.text


def _gcs_upload_text(text: str) -> None:
    from urllib.parse import quote

    obj = quote(_gcs_object_name(), safe="")
    url = f"https://storage.googleapis.com/upload/storage/v1/b/{_HASH_BUCKET}/o?uploadType=media&name={obj}"
    r = requests.post(
        url,
        data=text.encode("utf-8"),
        headers={"Authorization": f"Bearer {_gcs_token()}", "Content-Type": "application/json"},
        timeout=30,
    )
    r.raise_for_status()


def _load_hash_ledger() -> dict[str, dict]:
    global _HASH_LEDGER
    if _HASH_LEDGER is not None:
        return _HASH_LEDGER
    _HASH_LEDGER = {}
    if not _incremental_enabled():
        return _HASH_LEDGER
    try:
        text = _gcs_download_text()
        data = _json.loads(text) if text else {}
        if isinstance(data, dict):
            _HASH_LEDGER = {str(k): v for k, v in data.items() if isinstance(v, dict)}
        LOG.info("incremental: hash ledger loaded entries=%d", len(_HASH_LEDGER))
    except Exception as exc:  # noqa: BLE001 - 初回 / file 無し / 権限欠如 → 全件 upsert
        LOG.info("incremental: no hash ledger (%s) — 初回は全件 upsert", exc)
        _HASH_LEDGER = {}
    return _HASH_LEDGER


def _save_hash_ledger() -> None:
    if _HASH_LEDGER is None or not _HASH_LEDGER_DIRTY or not _incremental_enabled():
        return
    try:
        _gcs_upload_text(_json.dumps(_HASH_LEDGER, ensure_ascii=False))
        LOG.info("incremental: hash ledger saved entries=%d skipped=%d", len(_HASH_LEDGER), _HASH_SKIPPED)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("incremental: hash ledger save fail: %s", exc)


def _content_sig(slug: str, title: str, content_html: str, excerpt: str, featured_media_id) -> str:
    h = _hashlib.sha256()
    for part in (slug, title, content_html, excerpt, str(featured_media_id or "")):
        h.update((part or "").encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def _record_hash(slug: str, sig: str, page_id: int, url: str) -> None:
    global _HASH_LEDGER_DIRTY
    if not _incremental_enabled() or not page_id:
        return
    led = _load_hash_ledger()
    led[slug] = {"sig": sig, "page_id": int(page_id), "url": str(url or f"/data/{slug}")}
    _HASH_LEDGER_DIRTY = True


def _draft_page_enabled() -> bool:
    """巨人ドラフト史ページ /data/draft の本番公開ゲート。

    全年代（1965-2024）のデータ整備が完了するまで本番公開しない（user 確定 2026-06-05）。
    既定 OFF。データ完成後に ENABLE_DATA_SITE_DRAFT=1 で点灯。
    """
    return str(os.environ.get("ENABLE_DATA_SITE_DRAFT", "")).strip().lower() in {"1", "true", "yes", "on"}


def _wp_creds() -> tuple[str, HTTPBasicAuth]:
    base = os.environ.get("WP_URL", "").strip().rstrip("/")
    user = os.environ.get("WP_USER", "").strip()
    pw = os.environ.get("WP_APP_PASSWORD", "").strip()
    if not (base and user and pw):
        raise RuntimeError("WP_URL / WP_USER / WP_APP_PASSWORD env required")
    return base, HTTPBasicAuth(user, pw)


def _find_page_id_by_slug(slug: str, *, parent: int = 0) -> int | None:
    """WP REST /pages を slug で検索 → 存在すれば page id を返す.

    Draft/trash pages can still reserve page slugs in WordPress.  Use edit
    context + status=any so upsert updates the reserved page instead of
    accidentally creating `slug-2`.
    """
    base, auth = _wp_creds()
    try:
        r = requests.get(
            base + "/wp-json/wp/v2/pages",
            params={
                "slug": slug,
                "status": "any",
                "context": "edit",
                "per_page": 10,
                "_fields": "id,slug,parent,status",
            },
            auth=auth,
            timeout=15,
        )
        if not r.ok:
            return None
        for p in (r.json() or []):
            if str(p.get("slug", "")) == slug:
                if parent and int(p.get("parent") or 0) != parent:
                    continue
                return int(p.get("id"))
        return None
    except Exception as exc:  # noqa: BLE001
        LOG.warning("find_page_id_by_slug err slug=%s: %r", slug, exc)
        return None


def _upsert_page(
    *,
    slug: str,
    title: str,
    content_html: str,
    parent: int = 0,
    featured_media_id: int | None = None,
    excerpt: str = "",
) -> UpsertResult:
    """WP page を upsert (slug 一致なら PUT、 無ければ POST)."""
    if _dry_run_enabled():
        LOG.info("DRY_RUN upsert skipped slug=%s title=%s bytes=%d", slug, title, len(content_html))
        return UpsertResult(slug=slug, page_id=0, action="skipped", url=f"/data/{slug}")

    # 差分更新: 描画内容が前回と同じページは GET/POST を skip (親ページは常に実 upsert)
    sig = _content_sig(slug, title, content_html, excerpt, featured_media_id)
    if slug not in _ALWAYS_FRESH_SLUGS and _incremental_enabled():
        cached = _load_hash_ledger().get(slug)
        if cached and cached.get("sig") == sig and cached.get("page_id"):
            global _HASH_SKIPPED
            _HASH_SKIPPED += 1
            return UpsertResult(
                slug=slug,
                page_id=int(cached["page_id"]),
                action="unchanged",
                url=str(cached.get("url") or f"/data/{slug}"),
            )

    base, auth = _wp_creds()
    payload: dict[str, object] = {
        "slug": slug,
        "title": title,
        "content": content_html,
        "status": "publish",
        "parent": parent,
        # index 方針 (2026-05-29 user 確定): データページ + SNS リアルタイムは index、
        # 速報 post のみ noindex。 旧「Yoast noindex meta」指定は no-op だった (本サイトの
        # 有効 SEO plugin は SEO SIMPLE PACK + yoshilover-post-noindex で、 どちらも
        # 投稿(is_single)対象・固定ページは noindex 対象外。 Yoast meta は無視される)。
        # 実態として data ページは index 済のため、 コードを方針に一致させ no-op meta を除去。
    }
    if featured_media_id:
        payload["featured_media"] = featured_media_id
    if excerpt:
        payload["excerpt"] = excerpt

    existing_id = _find_page_id_by_slug(slug, parent=parent)
    try:
        if existing_id:
            r = requests.post(
                base + f"/wp-json/wp/v2/pages/{existing_id}",
                json=payload,
                auth=auth,
                timeout=30,
            )
            action = "updated"
        else:
            r = requests.post(
                base + "/wp-json/wp/v2/pages",
                json=payload,
                auth=auth,
                timeout=30,
            )
            action = "created"
        if not r.ok:
            LOG.warning("upsert fail slug=%s status=%d body=%s", slug, r.status_code, r.text[:300])
            return UpsertResult(slug=slug, page_id=0, action="error", url=f"/data/{slug}")
        page = r.json() or {}
        result = UpsertResult(
            slug=slug,
            page_id=int(page.get("id") or 0),
            action=action,
            url=str(page.get("link") or f"/data/{slug}"),
        )
        _record_hash(slug, sig, result.page_id, result.url)
        return result
    except Exception as exc:  # noqa: BLE001
        LOG.exception("upsert exception slug=%s: %r", slug, exc)
        return UpsertResult(slug=slug, page_id=0, action="error", url=f"/data/{slug}")


def _build_pillar_info(player_name: str) -> PillarPlayerInfo | None:
    """1 player の Pillar 用 info をまとめ作る。 roster 未一致は None."""
    # OB・レジェンドは roster に居ない (退団/引退済)。 config 由来の profile で構築し、
    # live stats query は行わない (関連記事 + 写真のみ取得)。
    # 現役roster(現役選手・監督・コーチ)に在籍する名前は OB 扱いしない。
    # 退団した過去選手が現コーチを兼ねる場合 (内海哲也=投手コーチ 等)、 OB として
    # 解決すると監督・コーチ表から消え、 position 表へ誤混入するため現役を優先。
    ob = ob_legend(player_name) if not load_roster_player(player_name) else None
    if ob:
        slug = ob.get("slug") or player_slug(player_name)
        return PillarPlayerInfo(
            name=ob.get("display_name", player_name),
            slug=slug,
            position="",
            jersey_number="",
            role="ob",
            featured_image_url=find_player_featured_image_url(player_name),
            featured_media_id=find_player_featured_media_id(player_name),
            short_review="",
            related_topic_links=fetch_related_topic_links(player_name, limit=3),
            ob_profile=ob,
            # OB の年度別フル表 (ベンチマーク由来、 slug 引き)。 無ければ None で安全。
            npb_career=_ob_yearly_payload(slug),
            # prosports 人物記事の相互リンクは OB (原辰徳/桑田 等) こそ多い
            prosports_links=[
                (e.get("url"), e.get("title"))
                for e in (_prosports_link_map().get(slug) or [])
                if e.get("url") and e.get("title")
            ],
        )
    roster = load_roster_player(player_name)
    if not roster:
        LOG.warning("roster miss player=%s — skip", player_name)
        return None
    slug = player_slug(player_name)
    related = fetch_related_topic_links(player_name, limit=3)
    image_url = find_player_featured_image_url(player_name)
    media_id = find_player_featured_media_id(player_name)
    # 登録ポジションは NPB 公式分類を優先 (roster.position は stale: 例 石川達也は
    # roster「打者」だが公式「投手」)。 支配下でなければ roster.position に fallback。
    official_pos = shihai_position_group(player_name)
    info = PillarPlayerInfo(
        name=roster.name,
        slug=slug,
        position=official_pos or roster.position,
        jersey_number=roster.jersey_number,
        role=roster.role,
        featured_image_url=image_url,
        featured_media_id=media_id,
        short_review="",  # Phase 1.0 は AI 短評 未接続、 後 phase で追加
        related_topic_links=related,
    )
    # 関連選手 (同登録ポジションの他選手) への spoke↔spoke 内部リンク。
    # staff は shihai_position_group=None → [] (related_shihai_players 内で空)。
    info.related_players = [
        (player_slug(n), n) for n in related_shihai_players(player_name)
    ]
    # prosports.yoshilover.com の同一選手 人物・家族記事への相互リンク (config 正本)。
    info.prosports_links = [
        (e.get("url"), e.get("title"))
        for e in (_prosports_link_map().get(slug) or [])
        if e.get("url") and e.get("title")
    ]
    # 467: NPB career page 由来の網羅データ (年度別+通算+プロフィール)。 cache 由来、 無ければ None。
    info.npb_career = npb_career_ingest.career_payload_for(_CAREER_CACHE, player_name)
    # 現役 cache に無い (= 引退 OB) なら、 ベンチマーク由来の年度別フル表で populate。
    # これで OB ページも「年度ごと」詳細表 (打率/出塁率/長打率/OPS or 防御率/WHIP) を持つ。
    if not (info.npb_career and (info.npb_career.get("batting") or info.npb_career.get("pitching"))):
        info.npb_career = _ob_yearly_payload(player_slug(player_name)) or info.npb_career
    # 二軍（ファーム）今季成績を NPB 公式から付与（無ければ None で安全）。
    try:
        _frec = giants_farm_map().get(player_name.replace(" ", "").replace("　", ""))
        if _frec:
            info.farm_batting = _frec.get("batting")
            info.farm_pitching = _frec.get("pitching")
    except Exception as _farm_exc:  # noqa: BLE001
        LOG.warning("farm stats attach failed player=%s: %r", player_name, _farm_exc)
    # 監督・コーチ は当年 stats を持たない (insight.db join しても空)。 当年 stats query は
    # 全 skip し、 現役時代の通算成績 (config 由来) + profile + 関連記事の page にする。
    if (roster.role or "").strip() in ("manager", "coach"):
        info.career_stats = coach_career_stat(player_name)
        return info
    season = fetch_batting_stats_season(player_name)
    # 2026-06-30 user: 選手ページは直近5試合ではなく当季 (2026) 全試合を表示する。
    recent_games_raw = fetch_recent_games(player_name, limit=None)
    if season:
        info.has_stats = True
        info.season_games = season.games
        info.season_ab = season.ab
        info.season_hits = season.hits
        info.season_rbi = season.rbi
        info.season_runs = season.runs
        info.season_sb = season.sb
        info.season_hr = season.hr
        info.season_avg = season.avg
    if recent_games_raw:
        info.recent_games = [
            (g.game_date, g.opponent, g.ab, g.hits, g.rbi)
            for g in recent_games_raw
        ]
    # Phase 1.0a 大手未掲載 metric pack
    info.lineup_slot_stats = [
        (s.slot_order, s.games, s.ab, s.hits, s.rbi, s.avg)
        for s in fetch_lineup_slot_stats(player_name)
    ]
    info.opponent_split_stats = [
        (o.opponent, o.games, o.ab, o.hits, o.rbi, o.avg)
        for o in fetch_opponent_split_stats(player_name)
    ]
    info.venue_split_stats = [
        (v.venue, v.games, v.ab, v.hits, v.rbi, v.avg)
        for v in fetch_venue_split_stats(player_name)
    ]
    info.inning_split_stats = [
        (i.phase, i.ab, i.hits, i.avg)
        for i in fetch_inning_split_stats(player_name)
    ]
    # Phase B (452): 曜日別 / 月別 / 交流戦別
    info.weekday_split_stats = [
        (s.label, s.games, s.ab, s.hits, s.avg) for s in fetch_weekday_split_stats(player_name)
    ]
    info.month_split_stats = [
        (s.label, s.games, s.ab, s.hits, s.avg) for s in fetch_month_split_stats(player_name)
    ]
    info.interleague_split_stats = [
        (s.label, s.games, s.ab, s.hits, s.avg) for s in fetch_interleague_split_stats(player_name)
    ]
    # 453: NPB 全12球団内 順位バッジ。投手は防御率/奪三振/勝利、打者は打点/安打/打率。
    info.metric_ranks = (
        fetch_pitcher_npb_ranks(player_name)
        if (info.position or "").strip() == "投手"
        else fetch_player_npb_ranks(player_name)
    )
    # Phase 1.0b1 streak
    hit_streak = fetch_hit_streak(player_name)
    info.hit_streak_active = hit_streak.active
    info.hit_streak_season_max = hit_streak.season_max
    contrib_streak = fetch_contribution_streak(player_name)
    info.contribution_streak_active = contrib_streak.active
    info.contribution_streak_season_max = contrib_streak.season_max
    # Phase 1.5+α 投手 stats (position=投手 のみ実際表示されるが、 全 player で
    # query して dataclass に詰めておく — 投手じゃない player は値 0 で template
    # 側で section omit される)
    # 457: 得点圏 (RISP) / 対左右投手 split (打者向け、 投手 pillar では非表示)
    info.risp_split_stats = fetch_risp_split_stats(player_name)
    info.vs_lr_split_stats = fetch_vs_lr_split_stats(player_name)
    # 461: セイバーメトリクス (打者/投手 両対応、 site はライバル超えで全指標表示)
    info.sabermetric_stats = fetch_sabermetrics(player_name, (info.position or "").strip() == "投手")
    pitching = fetch_pitching_stats_season(player_name)
    if pitching:
        info.has_pitching_stats = True
        info.pitch_games = pitching.games
        info.pitch_wins = pitching.wins
        info.pitch_losses = pitching.losses
        info.pitch_ip = pitching.ip
        info.pitch_k = pitching.k
        info.pitch_bb = pitching.bb
        info.pitch_h_allowed = pitching.h_allowed
        info.pitch_hr_allowed = pitching.hr_allowed
        info.pitch_er = pitching.er
        info.pitch_era = pitching.era
        info.pitch_whip = pitching.whip
        info.pitch_k_per_9 = pitching.k_per_9
        info.pitch_bb_per_9 = pitching.bb_per_9
    # 2026-06-30 user: 投手ページも当季 (2026) 全登板を表示する。
    pitching_recent = fetch_recent_pitching_games(player_name, limit=None)
    if pitching_recent:
        info.recent_pitching_games = [
            (p.game_date, p.opponent, p.result_mark, p.ip, p.h_allowed, p.k, p.bb, p.er)
            for p in pitching_recent
        ]
    # 456: 投手 split 5種 (非投手は pitching_logs 行ゼロで [] を返す)
    info.pitch_opponent_split_stats = fetch_pitcher_opponent_split_stats(player_name)
    info.pitch_venue_split_stats = fetch_pitcher_venue_split_stats(player_name)
    info.pitch_weekday_split_stats = fetch_pitcher_weekday_split_stats(player_name)
    info.pitch_month_split_stats = fetch_pitcher_month_split_stats(player_name)
    info.pitch_interleague_split_stats = fetch_pitcher_interleague_split_stats(player_name)
    return info


def _name_to_slug(name: str) -> str:
    """player_name -> URL slug。 OB は ob_profile.slug、 現役は player_slug。 (config のみ、 network 無し)"""
    ob = ob_legend(name)
    if ob and ob.get("slug"):
        return ob["slug"]
    return player_slug(name)


# /data/notable に出す好調指標は「読者がすぐ分かる指標」のみ(BABIP/FIP 等のサバメ指数は出さない)
_NOTABLE_CLEAR_METRIC_TOKENS = ("OPS", "出塁率", "長打率", "防御率", "K/9", "守備率")


def _notable_featured_media_id() -> int | None:
    """notable page の eyecatch。X 固定ポスト導線用に坂本勇人 (user 指定 2026-06-12)。"""
    try:
        return mapped_player_media_id("坂本勇人") or None
    except Exception:  # noqa: BLE001
        return None


def _serialize_notable_leaders(top_n: int = 3) -> dict[str, list[dict]]:
    """チーム内リーダー上位を notable page 用に軽量 serialize する。"""
    try:
        leaders = fetch_team_leaders(top_n=top_n)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("notable leaders fetch failed: %r", exc)
        return {}
    if not leaders:
        return {}
    targets = set(load_data_site_target_names())
    out: dict[str, list[dict]] = {}
    for stat, entries in (leaders or {}).items():
        rows = []
        for entry in entries:
            rows.append({
                "player": entry.player,
                "display": entry.display,
                "slug": _name_to_slug(entry.player) if entry.player in targets else "",
            })
        if rows:
            out[stat] = rows
    return out


def _build_notable_data(
    cluster_entries: list[ClusterPlayerEntry],
    limit: int = 16,
    *,
    latest_game_only: bool = True,
) -> dict[str, object]:
    """Build metric-first notable data items for the dedicated page and hub teaser.

    ``latest_game_only`` keeps the public /data/notable page focused on players
    who appeared in the latest Giants game. Callers that need a wider, more
    diverse candidate pool (e.g. the YouTube Shorts selector, which must avoid
    surfacing the same hot player every run) pass ``False`` to also include
    season-to-date leaders who did not play the most recent game.
    """
    latest_game_date = fetch_latest_giants_game_date()
    if not latest_game_date:
        return {"as_of": "", "items": []}
    items: list[dict] = []
    seen: set[tuple[str, str]] = set()

    def add(player: str, slug: str, label: str, value: str, note: str, priority: float,
            category: str = "form") -> None:
        key = (player, label)
        if not player or not label or not value or key in seen:
            return
        seen.add(key)
        items.append({
            "player": player,
            "slug": slug,
            "label": label,
            "value": value,
            "note": note,
            "priority": priority,
            "category": category,
        })

    for entry in cluster_entries:
        if entry.role in ("manager", "coach") or "投手" in (entry.position_group or entry.position):
            continue
        if latest_game_only:
            player_game_date = fetch_player_latest_game_date(entry.name, "batting_logs")
            if latest_game_date and player_game_date != latest_game_date:
                continue
        try:
            hit = fetch_hit_streak(entry.name)
            contrib = fetch_contribution_streak(entry.name)
        except Exception as exc:  # noqa: BLE001
            LOG.warning("notable streak fetch failed player=%s: %r", entry.name, exc)
            continue
        if hit.active >= 3:
            add(
                entry.name, entry.slug, "連続試合安打", f"{hit.active}試合",
                f"今季最長{hit.season_max}試合", 120 + hit.active,
                category="streak",
            )
        if contrib.active >= 3:
            add(
                entry.name, entry.slug, "連続得点関与", f"{contrib.active}試合",
                f"今季最長{contrib.season_max}試合", 110 + contrib.active,
                category="streak",
            )

    if len(items) < limit:
        pitcher_labels = {
            "失点抑止（防御率）",
            "走者を出さない力（WHIP）",
            "投球内容（FIP）",
            "奪三振力（K/9）",
            "制球と奪三振（K/BB）",
        }
        for row in fetch_surprise_stats(top_n=limit * 3):
            if not any(tok in row.label for tok in _NOTABLE_CLEAR_METRIC_TOKENS):
                continue
            table = "pitching_logs" if row.label in pitcher_labels else "batting_logs"
            if latest_game_only:
                player_game_date = fetch_player_latest_game_date(row.player, table)
                if latest_game_date and player_game_date != latest_game_date:
                    continue
            # 表示は短く: label は指標名のみ、 note は「今季・リーグN位」だけに圧縮
            label_m = re.search(r"（(.+?)）", row.label)
            rank_m = re.search(r"リーグ(\d+)/\d+位", row.note or "")
            scope = (row.note or "").split("・", 1)[0]
            add(
                row.player,
                _name_to_slug(row.player),
                label_m.group(1) if label_m else row.label,
                row.value,
                f"{scope}・リーグ{rank_m.group(1)}位" if rank_m and scope else "",
                row.priority,
            )
            if len(items) >= limit:
                break

    items.sort(key=lambda item: (-float(item.get("priority") or 0), item.get("player") or ""))
    for item in items:
        item.pop("priority", None)
    try:
        standings = fetch_npb_cl_standings()
    except Exception as exc:  # noqa: BLE001
        LOG.warning("notable standings fetch failed: %r", exc)
        standings = []
    return {
        "as_of": latest_game_date,
        "items": items[:limit],
        "leaders": _serialize_notable_leaders(top_n=3),
        "standings": standings,
    }


def _build_notable_data_from_targets(
    limit: int = 16,
    *,
    latest_game_only: bool = True,
) -> dict[str, object]:
    """Build notable data without building or updating player pages."""
    entries: list[ClusterPlayerEntry] = []
    for name in load_data_site_target_names():
        roster = load_roster_player(name)
        if not roster or roster.role in ("manager", "coach"):
            continue
        entries.append(
            ClusterPlayerEntry(
                name=roster.name,
                slug=_name_to_slug(roster.name),
                position=roster.position,
                jersey_number=roster.jersey_number,
                role=roster.role,
                position_group=shihai_position_group(roster.name) or "",
            )
        )
    return _build_notable_data(entries, limit=limit, latest_game_only=latest_game_only)


def _get_page_for_edit_by_slug(slug: str, *, parent: int = 0) -> dict | None:
    page_id = _find_page_id_by_slug(slug, parent=parent)
    if not page_id:
        return None
    base, auth = _wp_creds()
    try:
        r = requests.get(
            base + f"/wp-json/wp/v2/pages/{page_id}",
            params={"context": "edit", "_fields": "id,slug,parent,status,title,content,excerpt"},
            auth=auth,
            timeout=20,
        )
        if not r.ok:
            LOG.warning("get page for edit failed slug=%s status=%d body=%s", slug, r.status_code, r.text[:300])
            return None
        return r.json() or {}
    except Exception as exc:  # noqa: BLE001
        LOG.warning("get page for edit err slug=%s: %r", slug, exc)
        return None


def _page_field_text(page: dict, field: str) -> str:
    value = page.get(field) or {}
    if isinstance(value, dict):
        return str(value.get("raw") or value.get("rendered") or "")
    return str(value or "")


_NOTABLE_SECTION_RE = re.compile(
    r'<section\b[^>]*\bid=["\']ys-notable-data["\'][\s\S]*?</section>',
    re.IGNORECASE,
)
_LEGACY_NOTABLE_HREF_RE = re.compile(
    r'href=(["\'])(?:https?://(?:www\.)?yoshilover\.com)?/data/?#ys-notable-data\1|href=(["\'])#ys-notable-data\2',
    re.IGNORECASE,
)


def _replace_legacy_notable_data_links(content_html: str) -> str:
    """Point old in-page notable links at the dedicated notable-data page."""
    updated = _LEGACY_NOTABLE_HREF_RE.sub(
        lambda match: f'href={match.group(1) or match.group(2)}/data/notable{match.group(1) or match.group(2)}',
        content_html,
    )
    return updated.replace("驚き・注目選手", "注目データ")


def _remove_notable_data_section(content_html: str) -> str:
    """Remove legacy in-page notable-data section from /data/.

    /data/ is the player personal-stats hub. The notable data content belongs
    only on /data/notable/.
    """
    return _NOTABLE_SECTION_RE.sub("", content_html, count=1)


def _update_page_content(page_id: int, content_html: str) -> UpsertResult:
    if _dry_run_enabled():
        LOG.info("DRY_RUN notable data content update skipped page_id=%s bytes=%d", page_id, len(content_html))
        return UpsertResult(slug="data", page_id=page_id, action="skipped", url="/data/")
    base, auth = _wp_creds()
    try:
        r = requests.post(
            base + f"/wp-json/wp/v2/pages/{int(page_id)}",
            json={"content": content_html},
            auth=auth,
            timeout=30,
        )
        if not r.ok:
            LOG.warning("notable data update fail page_id=%s status=%d body=%s", page_id, r.status_code, r.text[:300])
            return UpsertResult(slug="data", page_id=0, action="error", url="/data/")
        page = r.json() or {}
        return UpsertResult(
            slug="data",
            page_id=int(page.get("id") or page_id),
            action="updated",
            url=str(page.get("link") or "/data/"),
        )
    except Exception as exc:  # noqa: BLE001
        LOG.exception("notable data update exception page_id=%s: %r", page_id, exc)
        return UpsertResult(slug="data", page_id=0, action="error", url="/data/")


def _update_page_status(page_id: int, slug: str, status: str) -> UpsertResult:
    if _dry_run_enabled():
        LOG.info("DRY_RUN page status update skipped page_id=%s slug=%s status=%s", page_id, slug, status)
        return UpsertResult(slug=slug, page_id=page_id, action="skipped", url=f"/data/{slug}")
    base, auth = _wp_creds()
    try:
        r = requests.post(
            base + f"/wp-json/wp/v2/pages/{int(page_id)}",
            json={"status": status},
            auth=auth,
            timeout=30,
        )
        if not r.ok:
            LOG.warning("page status update fail page_id=%s slug=%s status=%d body=%s", page_id, slug, r.status_code, r.text[:300])
            return UpsertResult(slug=slug, page_id=0, action="error", url=f"/data/{slug}")
        page = r.json() or {}
        return UpsertResult(
            slug=slug,
            page_id=int(page.get("id") or page_id),
            action="updated",
            url=str(page.get("link") or f"/data/{slug}"),
        )
    except Exception as exc:  # noqa: BLE001
        LOG.exception("page status update exception page_id=%s slug=%s: %r", page_id, slug, exc)
        return UpsertResult(slug=slug, page_id=0, action="error", url=f"/data/{slug}")


def retire_legacy_notable_page() -> dict[str, object]:
    """Deprecated no-op.

    /data/notable/ is now the canonical notable-data page again. Keep this CLI
    harmless so an old runbook invocation cannot draft the page by mistake.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    summary = {
        "status": "ok",
        "dry_run": _dry_run_enabled(),
        "mode": "retire_legacy_notable",
        "action": "canonical_page_kept",
        "page_id": 0,
    }
    LOG.info("legacy notable retire no-op: %s", _json.dumps(summary, ensure_ascii=False))
    return summary


def publish_notable_data_only() -> dict[str, object]:
    """Update only the notable-data page and clean /data/ legacy links.

    This path intentionally does not upsert player pages, rankings, farm pages,
    or any other data-site child pages.
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    notable_data = _build_notable_data_from_targets()
    if not notable_data.get("as_of"):
        return {"status": "abort", "reason": "latest_game_date_unavailable", "mode": "notable_data_only"}
    page = _get_page_for_edit_by_slug("data", parent=0)
    if not page:
        return {"status": "abort", "reason": "data_page_not_found"}
    page_id = int(page.get("id") or 0)
    notable_result = _upsert_page(
        slug="notable",
        title=render_notable_data_title(),
        featured_media_id=_notable_featured_media_id(),
        content_html=render_notable_data_page_html(notable_data),
        parent=page_id,
        excerpt=render_notable_data_excerpt(notable_data),
    )
    current = _page_field_text(page, "content")
    next_content = _replace_legacy_notable_data_links(
        _remove_notable_data_section(current)
    )
    result = _update_page_content(page_id, next_content)
    ok = result.action in {"updated", "skipped", "unchanged"} and notable_result.action not in {"error"}
    summary = {
        "status": "ok" if ok else "error",
        "dry_run": _dry_run_enabled(),
        "mode": "notable_data_only",
        "page_id": result.page_id,
        "notable_page_id": notable_result.page_id,
        "notable_action": notable_result.action,
        "action": result.action,
        "items": len(notable_data.get("items") or []),
    }
    _save_hash_ledger()
    LOG.info("notable data only publisher done: %s", _json.dumps(summary, ensure_ascii=False))
    return summary


def _upsert_mlb_page(parent_page_id: int) -> UpsertResult | None:
    """巨人発メジャーリーガー hub + 選手別 page。 取得 0 人なら skip して前回内容を維持する。"""
    mlb_data = fetch_mlb_alumni_data()
    if not mlb_data.get("players"):
        LOG.warning("mlb alumni data empty; skip /data/mlb upsert")
        return None
    hub_result = _upsert_page(
        slug="mlb",
        title=render_mlb_title(),
        content_html=render_mlb_html(mlb_data),
        parent=parent_page_id,
        excerpt=render_mlb_excerpt(mlb_data),
    )
    mlb_page_id = hub_result.page_id or (_find_page_id_by_slug("mlb", parent=parent_page_id) or 0)
    if not mlb_page_id:
        LOG.warning("mlb hub page_id unresolved; skip player pages")
        return hub_result
    for spec in MLB_ALUMNI:
        detail = fetch_mlb_player_detail(spec)
        if not detail:
            LOG.warning("mlb player detail empty; skip slug=%s", spec.get("slug"))
            continue
        result = _upsert_page(
            slug=spec["slug"],
            title=render_mlb_player_title(detail),
            content_html=render_mlb_player_html(detail),
            parent=mlb_page_id,
            excerpt=render_mlb_player_excerpt(detail),
        )
        LOG.info("mlb player upsert slug=%s page_id=%s action=%s games=%d",
                 spec["slug"], result.page_id, result.action,
                 sum(len(s.get("games") or []) for s in detail.get("seasons") or []))
    return hub_result


def publish_mlb_only() -> dict[str, object]:
    """Update only the /data/mlb page (巨人発メジャーリーガー)."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    page = _get_page_for_edit_by_slug("data", parent=0)
    if not page:
        return {"status": "abort", "reason": "data_page_not_found", "mode": "mlb_only"}
    result = _upsert_mlb_page(int(page.get("id") or 0))
    if result is None:
        return {"status": "abort", "reason": "mlb_data_unavailable", "mode": "mlb_only"}
    summary = {
        "status": "ok" if result.action != "error" else "error",
        "dry_run": _dry_run_enabled(),
        "mode": "mlb_only",
        "mlb_page_id": result.page_id,
        "mlb_action": result.action,
    }
    _save_hash_ledger()
    LOG.info("mlb only publisher done: %s", _json.dumps(summary, ensure_ascii=False))
    return summary


def publish_phase1(only_slugs: set[str] | None = None) -> dict[str, object]:
    """Phase 1.0 main: 3 Pillar + 1 Cluster upsert.

    only_slugs 指定時は **canary モード**: 指定 slug の pillar ページだけ upsert し、
    cluster / schedule / leaders / legends / team / ranking / record の hub は触らない。
    """
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    LOG.info("data-site Phase 1.0 publisher start dry_run=%s only=%s", _dry_run_enabled(), sorted(only_slugs) if only_slugs else None)

    target_names = load_data_site_target_names()
    if not target_names:
        LOG.error("no data-site target players in roster — abort")
        return {"status": "abort", "reason": "no_target_players"}
    if only_slugs:
        target_names = [n for n in target_names if _name_to_slug(n) in only_slugs]
        # canary は指定ページを必ず再公開したいので差分 skip を無効化
        global _FORCE_FULL_RUN
        _FORCE_FULL_RUN = True

    LOG.info("phase1 target players: %s", target_names)

    # 467: NPB career cache を日次 1 回 refresh (staleness gate)。 publish 非ブロック。
    global _CAREER_CACHE
    try:
        _CAREER_CACHE = npb_career_ingest.load_or_refresh(list(target_names))
        LOG.info("career cache loaded: players=%d", len((_CAREER_CACHE or {}).get("players") or {}))
    except Exception as exc:  # noqa: BLE001
        LOG.warning("career cache load failed (continue without): %r", exc)
        _CAREER_CACHE = {}

    # Cluster page 先に upsert (parent=0、 top-level)、 page id を取得して Pillar parent に使う
    cluster_entries: list[ClusterPlayerEntry] = []
    pillar_infos: list[PillarPlayerInfo] = []
    for name in target_names:
        info = _build_pillar_info(name)
        if not info:
            continue
        pillar_infos.append(info)
        cluster_entries.append(
            ClusterPlayerEntry(
                name=info.name,
                slug=info.slug,
                position=info.position,
                jersey_number=info.jersey_number,
                role=info.role,
                position_group=shihai_position_group(name) or "",
                military=staff_military_level(info.position) if (info.role or "") in ("manager", "coach") else "",
                season_games=info.season_games,
                season_ab=info.season_ab,
                season_hits=info.season_hits,
                season_rbi=info.season_rbi,
                season_hr=info.season_hr,
                season_avg=info.season_avg,
                has_stats=info.has_stats,
                pitch_games=info.pitch_games,
                pitch_wins=info.pitch_wins,
                pitch_losses=info.pitch_losses,
                pitch_ip=info.pitch_ip,
                pitch_k=info.pitch_k,
                pitch_era=info.pitch_era,
                has_pitching_stats=info.has_pitching_stats,
            )
        )

    # OB・レジェンド: 個別 profile ページを作る (cluster の position/staff 表には入れず、
    # OB 枠 chip リンクに集約)。 roster 不在のため _build_pillar_info が ob_profile で構築。
    ob_entries: list[tuple[str, str]] = []
    ob_source = load_ob_names()
    if only_slugs:
        ob_source = [n for n in ob_source if _name_to_slug(n) in only_slugs]
    for name in ob_source:
        info = _build_pillar_info(name)
        if not info:
            continue
        pillar_infos.append(info)
        ob_entries.append((info.slug, info.name))

    if not pillar_infos:
        LOG.error("no eligible pillar infos — abort")
        return {"status": "abort", "reason": "no_pillar_infos"}

    # canary モード: hub を一切触らず、 既存 /data 親の下に対象 pillar だけ upsert して return。
    if only_slugs:
        cluster_page_id = _find_page_id_by_slug("data", parent=0) or 0
        canary_results: list[UpsertResult] = []
        for info in pillar_infos:
            result = _upsert_page(
                slug=info.slug,
                title=render_pillar_title(info),
                content_html=render_pillar_html(info),
                parent=cluster_page_id,
                featured_media_id=info.featured_media_id,
                excerpt=render_pillar_excerpt(info),
            )
            LOG.info("CANARY pillar upsert slug=%s page_id=%s action=%s", result.slug, result.page_id, result.action)
            canary_results.append(result)
        return {
            "status": "ok", "mode": "canary", "dry_run": _dry_run_enabled(),
            "pillars": [{"slug": r.slug, "page_id": r.page_id, "action": r.action, "url": r.url} for r in canary_results],
            "pillar_count": len(canary_results),
        }

    # Cluster upsert (parent=0)。 育成=一覧のみ、 OB=chip リンク (個別ページあり)。
    notable_data = _build_notable_data(cluster_entries)
    cluster_html = render_cluster_html(
        cluster_entries,
        load_ikusei_entries(),
        ob_entries,
        notable_data=notable_data,
    )
    cluster_title = render_cluster_title()
    cluster_result = _upsert_page(
        slug="data",
        title=cluster_title,
        content_html=cluster_html,
        parent=0,
    )
    LOG.info(
        "cluster upsert slug=data page_id=%s action=%s",
        cluster_result.page_id, cluster_result.action,
    )

    # Pillar upsert (parent=cluster_page_id) — dry-run 時は parent=0 (cluster_page_id=0)
    cluster_page_id = cluster_result.page_id if cluster_result.action != "skipped" else 0

    # 注目データ page — parent=cluster → /data/notable/
    notable_result = _upsert_page(
        slug="notable",
        title=render_notable_data_title(),
        featured_media_id=_notable_featured_media_id(),
        content_html=render_notable_data_page_html(notable_data),
        parent=cluster_page_id,
        excerpt=render_notable_data_excerpt(notable_data),
    )
    LOG.info("notable data upsert slug=notable page_id=%s action=%s items=%d",
             notable_result.page_id, notable_result.action, len(notable_data.get("items") or []))

    # 巨人発メジャーリーガー page — parent=cluster → /data/mlb/ (取得失敗時は skip)
    try:
        mlb_result = _upsert_mlb_page(cluster_page_id)
        if mlb_result:
            LOG.info("mlb upsert slug=mlb page_id=%s action=%s", mlb_result.page_id, mlb_result.action)
    except Exception as exc:  # noqa: BLE001
        LOG.warning("mlb upsert failed (continue): %r", exc)

    pillar_results: list[UpsertResult] = []
    for info in pillar_infos:
        html = render_pillar_html(info)
        title = render_pillar_title(info)
        result = _upsert_page(
            slug=info.slug,
            title=title,
            content_html=html,
            parent=cluster_page_id,
            featured_media_id=info.featured_media_id,
            excerpt=render_pillar_excerpt(info),
        )
        LOG.info(
            "pillar upsert slug=%s page_id=%s action=%s related=%d image=%s",
            result.slug, result.page_id, result.action,
            len(info.related_topic_links), "yes" if info.featured_image_url else "no",
        )
        pillar_results.append(result)

    # schedule ページ upsert (日程・結果カレンダー、Phase B 452) — parent=cluster → /data/schedule/
    sched_rows = fetch_giants_schedule()
    sched_result = _upsert_page(
        slug="schedule",
        title=render_schedule_title(),
        content_html=render_schedule_html(sched_rows, upcoming=fetch_giants_upcoming()),
        parent=cluster_page_id,
        excerpt=render_schedule_excerpt(sched_rows),
    )
    LOG.info("schedule upsert slug=schedule page_id=%s action=%s games=%d",
             sched_result.page_id, sched_result.action, len(sched_rows))

    # farm topic cluster: /data/farm/ + child pages (user request 2026-06-07).
    # 1軍 schedule と混ざらないよう /data/farm/ 配下に複数枚で分ける。
    farm_rows = fetch_farm_game_rows()
    farm_batting, farm_pitching = farm_player_stats()
    farm_result = _upsert_page(
        slug="farm",
        title=render_farm_title(),
        content_html=render_farm_hub_html(farm_rows, farm_batting, farm_pitching),
        parent=cluster_page_id,
        excerpt=render_farm_excerpt(farm_rows),
    )
    farm_page_id = farm_result.page_id if farm_result.action not in ("skipped", "error") else 0
    LOG.info(
        "farm hub upsert slug=farm page_id=%s action=%s games=%d bat=%d pit=%d",
        farm_result.page_id, farm_result.action, len(farm_rows), len(farm_batting), len(farm_pitching),
    )
    farm_children = [
        ("schedule", render_farm_schedule_html(farm_rows)),
        ("spring-education", render_farm_education_html(farm_rows, kind="spring")),
        ("autumn-education", render_farm_education_html(farm_rows, kind="autumn")),
        ("team", render_farm_team_html(farm_rows, fetch_farm_generic_rows("team_history"))),
        ("players", render_farm_players_html(farm_batting, farm_pitching)),
        ("titles", render_farm_titles_html(
            farm_batting, farm_pitching, fetch_farm_generic_rows("titles"),
        )),
        ("championship", render_farm_championship_html(fetch_farm_generic_rows("championship"))),
    ]
    for child_slug, child_html in farm_children:
        child_result = _upsert_page(
            slug=child_slug,
            title=render_farm_child_title(child_slug),
            content_html=child_html,
            parent=farm_page_id,
            excerpt=render_farm_child_excerpt(child_slug),
        )
        LOG.info("farm child upsert slug=%s page_id=%s action=%s",
                 child_slug, child_result.page_id, child_result.action)

    # leaders ページ upsert (選手別ランキング、Phase B 452) — parent=cluster → /data/leaders/
    leaders = fetch_team_leaders()
    leaders_result = _upsert_page(
        slug="leaders",
        title=render_leaders_title(),
        content_html=render_leaders_html(leaders),
        parent=cluster_page_id,
        excerpt=render_leaders_excerpt(leaders),
    )
    LOG.info("leaders upsert slug=leaders page_id=%s action=%s stats=%d",
             leaders_result.page_id, leaders_result.action, len(leaders))

    # legends ページ upsert (OB・レジェンド hub、Phase B 452) — parent=cluster → /data/legends/
    ob_list = load_ob_legend_entries()
    legends_result = _upsert_page(
        slug="legends",
        title=render_legends_title(),
        content_html=render_legends_html(ob_list),
        parent=cluster_page_id,
        excerpt=render_legends_excerpt(ob_list),
    )
    LOG.info("legends upsert slug=legends page_id=%s action=%s ob=%d",
             legends_result.page_id, legends_result.action, len(ob_list))

    # team ページ upsert (球団成績・セ内順位、Phase B 452) — parent=cluster → /data/team/
    team_rankings = fetch_team_rankings()
    team_record = fetch_giants_team_record()
    cl_standings = fetch_npb_cl_standings()
    team_result = _upsert_page(
        slug="team",
        title=render_team_title(),
        content_html=render_team_html(team_rankings, team_record=team_record, standings=cl_standings),
        parent=cluster_page_id,
        excerpt=render_team_excerpt(team_rankings),
    )
    LOG.info("team upsert slug=team page_id=%s action=%s metrics=%d",
             team_result.page_id, team_result.action, len(team_rankings))

    # 成績ランキング upsert (462/468)。
    # /data/ranking/ は旧URLの受け皿だけにし、実データは打撃/投手の直接ページへ分離。
    leaders = fetch_team_leaders()
    try:
        career_leaders = build_career_leaders(_CAREER_CACHE)
        LOG.info("career leaders cats=%d", len(career_leaders))
    except Exception as exc:  # noqa: BLE001
        LOG.warning("build_career_leaders failed (continue without): %r", exc)
        career_leaders = {}
    # Phase1: 全史(OB684 + 現役)NPB通算ランキング(共有部品 alltime_ranking 由来)。
    try:
        alltime_leaders = build_alltime_leaders(_CAREER_CACHE)
        LOG.info("alltime leaders cats=%d", len(alltime_leaders))
    except Exception as exc:  # noqa: BLE001
        LOG.warning("build_alltime_leaders failed (continue without): %r", exc)
        alltime_leaders = {}
    ranking_result = _upsert_page(
        slug="ranking",
        title=render_ranking_title(),
        content_html=render_ranking_html(leaders, career_leaders, alltime_leaders),
        parent=cluster_page_id,
        excerpt=render_ranking_excerpt(leaders),
    )
    LOG.info("ranking gateway upsert slug=ranking page_id=%s action=%s cats=%d career=%d alltime=%d",
             ranking_result.page_id, ranking_result.action, len(leaders), len(career_leaders), len(alltime_leaders))
    batting_ranking_result = _upsert_page(
        slug="batting-ranking",
        title=render_batting_ranking_title(),
        content_html=render_batting_ranking_html(leaders, career_leaders, alltime_leaders),
        parent=cluster_page_id,
        excerpt=render_batting_ranking_excerpt(leaders),
    )
    LOG.info("batting ranking upsert slug=batting-ranking page_id=%s action=%s",
             batting_ranking_result.page_id, batting_ranking_result.action)
    pitching_ranking_result = _upsert_page(
        slug="pitching-ranking",
        title=render_pitching_ranking_title(),
        content_html=render_pitching_ranking_html(leaders, career_leaders, alltime_leaders),
        parent=cluster_page_id,
        excerpt=render_pitching_ranking_excerpt(leaders),
    )
    LOG.info("pitching ranking upsert slug=pitching-ranking page_id=%s action=%s",
             pitching_ranking_result.page_id, pitching_ranking_result.action)

    # Phase2: 記録室ハブ /data/record(共有部品 alltime_ranking を閾値 filter)。
    try:
        record_room = build_record_room(_CAREER_CACHE)
        LOG.info("record room clubs=%d", len(record_room))
    except Exception as exc:  # noqa: BLE001
        LOG.warning("build_record_room failed (continue without): %r", exc)
        record_room = {}
    record_result = _upsert_page(
        slug="record",
        title=render_record_title(),
        content_html=render_record_html(record_room),
        parent=cluster_page_id,
        excerpt=render_record_excerpt(record_room),
    )
    LOG.info("record upsert slug=record page_id=%s action=%s clubs=%d",
             record_result.page_id, record_result.action, len(record_room))

    # 468-7: 歴代4番打者ページ (半静的 history spoke) — parent=cluster → /data/cleanup-hitters/
    cleanup_data = load_cleanup_hitters_data()
    cleanup_result = _upsert_page(
        slug="cleanup-hitters",
        title=render_cleanup_hitters_title(),
        content_html=render_cleanup_hitters_html(cleanup_data),
        parent=cluster_page_id,
        excerpt=render_cleanup_hitters_excerpt(cleanup_data),
    )
    LOG.info("cleanup hitters upsert slug=cleanup-hitters page_id=%s action=%s rows=%d",
             cleanup_result.page_id, cleanup_result.action,
             len(cleanup_data.get("alltime") or []))

    # 先発ローテ一覧 (2007-2026, 試合ごとログ) — parent=cluster → /data/rotation/
    # data: config/starter_rotation_2007_2026.json (scripts/scrape_starter_rotation.py 生成)
    rotation_data = load_rotation_data()
    rotation_result = _upsert_page(
        slug="rotation",
        title=render_rotation_title(),
        content_html=render_rotation_html(rotation_data),
        parent=cluster_page_id,
        excerpt=render_rotation_excerpt(rotation_data),
    )
    LOG.info("rotation upsert slug=rotation page_id=%s action=%s years=%d",
             rotation_result.page_id, rotation_result.action,
             len(rotation_data.get("years") or []))

    # 468 parity: 歴代背番号 page — parent=cluster → /data/jersey-numbers/
    jersey_rows = fetch_jersey_rows()
    jersey_result = _upsert_page(
        slug="jersey-numbers",
        title=render_jersey_numbers_title(),
        content_html=render_jersey_numbers_html(jersey_rows),
        parent=cluster_page_id,
        excerpt=render_jersey_numbers_excerpt(jersey_rows),
    )
    LOG.info("jersey numbers upsert slug=jersey-numbers page_id=%s action=%s rows=%d",
             jersey_result.page_id, jersey_result.action, len(jersey_rows))

    # draft ページ upsert（巨人ドラフト史 hub、user 指定 2026-06-05）— parent=cluster → /data/draft/
    # 全年代整備完了まで本番非公開: ENABLE_DATA_SITE_DRAFT=1 のときだけ upsert。
    if _draft_page_enabled():
        draft_data = load_draft_data()
        draft_result = _upsert_page(
            slug="draft",
            title=render_draft_title(),
            content_html=render_draft_html(draft_data),
            parent=cluster_page_id,
            excerpt=render_draft_excerpt(draft_data),
        )
        LOG.info("draft upsert slug=draft page_id=%s action=%s picks=%d",
                 draft_result.page_id, draft_result.action,
                 len(draft_data.get("draft_picks") or []))
    else:
        LOG.info("draft page gated OFF (ENABLE_DATA_SITE_DRAFT not set) — skip upsert")

    # FA ページ upsert（FA獲得選手 + FA有資格選手、user 指定 2026-06-05）— parent=cluster → /data/fa/
    fa_data = load_fa_data()
    fa_result = _upsert_page(
        slug="fa",
        title=render_fa_title(),
        content_html=render_fa_html(fa_data),
        parent=cluster_page_id,
        excerpt=render_fa_excerpt(fa_data),
    )
    LOG.info("fa upsert slug=fa page_id=%s action=%s acq=%d elig=%d",
             fa_result.page_id, fa_result.action,
             len(fa_data.get("fa_acquisitions") or []),
             len(fa_data.get("fa_eligible") or []))

    # サヨナラ本塁打 ページ upsert（歴代全記録、user 指定 2026-06-19）— parent=cluster → /data/walkoff-homerun/
    walkoff_data = load_walkoff_data()
    walkoff_result = _upsert_page(
        slug="walkoff-homerun",
        title=render_walkoff_title(),
        content_html=render_walkoff_html(walkoff_data),
        parent=cluster_page_id,
        excerpt=render_walkoff_excerpt(walkoff_data),
    )
    LOG.info("walkoff upsert slug=walkoff-homerun page_id=%s action=%s hr=%d",
             walkoff_result.page_id, walkoff_result.action,
             len(walkoff_data.get("homeruns") or []))

    # trade ページ upsert（トレード/入退団、user 指定 2026-06-05）— parent=cluster → /data/trade/
    trade_data = load_trade_data()
    trade_result = _upsert_page(
        slug="trade",
        title=render_trade_title(),
        content_html=render_trade_html(trade_data),
        parent=cluster_page_id,
        excerpt=render_trade_excerpt(trade_data),
    )
    LOG.info("trade upsert slug=trade page_id=%s action=%s exchange=%d all=%d",
             trade_result.page_id, trade_result.action,
             len(trade_data.get("trades_exchange") or []),
             len(trade_data.get("transactions_all") or []))

    # foreign-players ページ upsert（歴代外国人選手、user 指定 2026-06-10）— parent=cluster → /data/foreign-players/
    foreign_data = load_foreign_players_data()
    foreign_result = _upsert_page(
        slug="foreign-players",
        title=render_foreign_players_title(),
        content_html=render_foreign_players_html(foreign_data),
        parent=cluster_page_id,
        excerpt=render_foreign_players_excerpt(foreign_data),
    )
    LOG.info("foreign-players upsert slug=foreign-players page_id=%s action=%s ob=%d active=%d",
             foreign_result.page_id, foreign_result.action,
             len(foreign_data.get("ob") or []),
             len(foreign_data.get("active") or []))

    summary = {
        "status": "ok",
        "dry_run": _dry_run_enabled(),
        "cluster": {
            "slug": cluster_result.slug,
            "page_id": cluster_result.page_id,
            "action": cluster_result.action,
            "url": cluster_result.url,
        },
        "pillars": [
            {
                "slug": r.slug,
                "page_id": r.page_id,
                "action": r.action,
                "url": r.url,
            }
            for r in pillar_results
        ],
        "pillar_count": len(pillar_results),
    }
    _save_hash_ledger()
    LOG.info("data-site Phase 1.0 publisher done: %s", _json.dumps(summary, ensure_ascii=False))
    return summary


def main() -> int:
    argv = sys.argv[1:]
    if "--only-notable-data" in argv:
        try:
            summary = publish_notable_data_only()
        except Exception as exc:  # noqa: BLE001
            LOG.exception("publisher fatal: %r", exc)
            return 1
        return 0 if summary.get("status") == "ok" else 1
    if "--only-mlb" in argv:
        try:
            summary = publish_mlb_only()
        except Exception as exc:  # noqa: BLE001
            LOG.exception("publisher fatal: %r", exc)
            return 1
        return 0 if summary.get("status") == "ok" else 1
    if "--retire-legacy-notable" in argv:
        try:
            summary = retire_legacy_notable_page()
        except Exception as exc:  # noqa: BLE001
            LOG.exception("publisher fatal: %r", exc)
            return 1
        return 0 if summary.get("status") == "ok" else 1
    only_slugs: set[str] | None = None
    if "--only" in argv:
        only_slugs = {s for s in argv[argv.index("--only") + 1:] if not s.startswith("--")}
    try:
        summary = publish_phase1(only_slugs=only_slugs)
    except Exception as exc:  # noqa: BLE001
        LOG.exception("publisher fatal: %r", exc)
        return 1
    return 0 if summary.get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
