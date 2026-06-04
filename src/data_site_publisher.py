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

import json as _json
import logging
import os
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
    fetch_recent_hot,
    fetch_team_leaders,
    fetch_player_npb_ranks,
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


def _wp_creds() -> tuple[str, HTTPBasicAuth]:
    base = os.environ.get("WP_URL", "").strip().rstrip("/")
    user = os.environ.get("WP_USER", "").strip()
    pw = os.environ.get("WP_APP_PASSWORD", "").strip()
    if not (base and user and pw):
        raise RuntimeError("WP_URL / WP_USER / WP_APP_PASSWORD env required")
    return base, HTTPBasicAuth(user, pw)


def _find_page_id_by_slug(slug: str, *, parent: int = 0) -> int | None:
    """WP REST /pages を slug で検索 → 存在すれば page id を返す."""
    base, auth = _wp_creds()
    try:
        r = requests.get(
            base + "/wp-json/wp/v2/pages",
            params={"slug": slug, "per_page": 5, "_fields": "id,slug,parent"},
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
        return UpsertResult(slug=slug, page_id=0, action="skipped", url=f"/data/{slug}/")

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
            return UpsertResult(slug=slug, page_id=0, action="error", url=f"/data/{slug}/")
        page = r.json() or {}
        return UpsertResult(
            slug=slug,
            page_id=int(page.get("id") or 0),
            action=action,
            url=str(page.get("link") or f"/data/{slug}/"),
        )
    except Exception as exc:  # noqa: BLE001
        LOG.exception("upsert exception slug=%s: %r", slug, exc)
        return UpsertResult(slug=slug, page_id=0, action="error", url=f"/data/{slug}/")


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
            related_topic_links=fetch_related_topic_links(player_name, limit=20),
            ob_profile=ob,
            # OB の年度別フル表 (ベンチマーク由来、 slug 引き)。 無ければ None で安全。
            npb_career=_ob_yearly_payload(slug),
        )
    roster = load_roster_player(player_name)
    if not roster:
        LOG.warning("roster miss player=%s — skip", player_name)
        return None
    slug = player_slug(player_name)
    related = fetch_related_topic_links(player_name, limit=20)
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
    # 467: NPB career page 由来の網羅データ (年度別+通算+プロフィール)。 cache 由来、 無ければ None。
    info.npb_career = npb_career_ingest.career_payload_for(_CAREER_CACHE, player_name)
    # 現役 cache に無い (= 引退 OB) なら、 ベンチマーク由来の年度別フル表で populate。
    # これで OB ページも「年度ごと」詳細表 (打率/出塁率/長打率/OPS or 防御率/WHIP) を持つ。
    if not (info.npb_career and (info.npb_career.get("batting") or info.npb_career.get("pitching"))):
        info.npb_career = _ob_yearly_payload(player_slug(player_name)) or info.npb_career
    # 監督・コーチ は当年 stats を持たない (insight.db join しても空)。 当年 stats query は
    # 全 skip し、 現役時代の通算成績 (config 由来) + profile + 関連記事の page にする。
    if (roster.role or "").strip() in ("manager", "coach"):
        info.career_stats = coach_career_stat(player_name)
        return info
    season = fetch_batting_stats_season(player_name)
    recent_games_raw = fetch_recent_games(player_name, limit=5)
    if season:
        info.has_stats = True
        info.season_games = season.games
        info.season_ab = season.ab
        info.season_hits = season.hits
        info.season_rbi = season.rbi
        info.season_runs = season.runs
        info.season_sb = season.sb
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
    # 453: NPB 全12球団内 順位バッジ (打点/安打/打率)
    info.metric_ranks = fetch_player_npb_ranks(player_name)
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
    pitching_recent = fetch_recent_pitching_games(player_name, limit=5)
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
                season_hits=info.season_hits,
                season_rbi=info.season_rbi,
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
    cluster_html = render_cluster_html(cluster_entries, load_ikusei_entries(), ob_entries,
                                       hot=fetch_recent_hot())
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

    # ranking ページ upsert (選手別 球団内ランキング HUB、 462) — parent=cluster → /data/ranking/
    # 468-1: 現役選手の NPB 通算成績ランキングを career cache から集計して併載。
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
    LOG.info("ranking upsert slug=ranking page_id=%s action=%s cats=%d career=%d alltime=%d",
             ranking_result.page_id, ranking_result.action, len(leaders), len(career_leaders), len(alltime_leaders))

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
    LOG.info("data-site Phase 1.0 publisher done: %s", _json.dumps(summary, ensure_ascii=False))
    return summary


def main() -> int:
    argv = sys.argv[1:]
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
