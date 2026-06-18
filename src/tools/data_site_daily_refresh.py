"""巨人データ 毎朝自動更新 (Cloud Run Job entrypoint)。

外部 source 由来のページを、当年分だけ軽く取り直して再公開する:
- /data/rotation/      先発ローテ一覧
- /data/roster-moves/  出場選手登録・抹消
- /data/open-games/    オープン戦結果
- /data/interleague/   セ・パ交流戦成績 (当年分は NPB公式 順位表から)

各ページは独立 (片方が失敗しても他方は更新)。LLM 不使用。
publisher 本体 (別作業の WIP) には依存しない。他のデータページにも触らない。

認証: 環境変数 WP_URL / WP_USER / WP_APP_PASSWORD (Cloud Run は Secret Manager 注入)。
ローカル実行時は .env を fallback。
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests
from requests.auth import HTTPBasicAuth

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src import (  # noqa: E402
    interleague_scraper,
    open_games_scraper,
    roster_moves_scraper,
    starter_rotation_scraper,
)
from src.data_site_template_rotation import (  # noqa: E402
    render_rotation_excerpt,
    render_rotation_html,
    render_rotation_title,
)
from src.data_site_template_roster_moves import (  # noqa: E402
    render_roster_moves_excerpt,
    render_roster_moves_html,
    render_roster_moves_title,
)
from src.data_site_template_open_games import (  # noqa: E402
    render_open_games_excerpt,
    render_open_games_html,
    render_open_games_title,
)
from src.data_site_template_interleague import (  # noqa: E402
    render_interleague_excerpt,
    render_interleague_html,
    render_interleague_title,
)

ROTATION_DATA = ROOT / "config" / "starter_rotation_2007_2026.json"
ROSTER_MOVES_DATA = ROOT / "config" / "giants_roster_moves.json"
OPEN_GAMES_DATA = ROOT / "config" / "giants_open_games.json"
INTERLEAGUE_DATA = ROOT / "config" / "giants_interleague.json"


def _creds() -> tuple[str, HTTPBasicAuth]:
    base = (os.environ.get("WP_URL") or "").strip().rstrip("/")
    user = (os.environ.get("WP_USER") or "").strip()
    pw = (os.environ.get("WP_APP_PASSWORD") or "").strip()
    if not (base and user and pw):
        try:
            from dotenv import dotenv_values
            env = dotenv_values(ROOT / ".env")
            base = base or (env.get("WP_URL") or "").strip().rstrip("/")
            user = user or (env.get("WP_USER") or "").strip()
            pw = pw or (env.get("WP_APP_PASSWORD") or "").strip()
        except Exception:
            pass
    if not (base and user and pw):
        raise SystemExit("WP_URL / WP_USER / WP_APP_PASSWORD required (env or .env)")
    return base, HTTPBasicAuth(user, pw)


def _find_page_id(base: str, auth: HTTPBasicAuth, slug: str, parent: int = 0) -> int:
    r = requests.get(
        base + "/wp-json/wp/v2/pages",
        params={"slug": slug, "status": "any", "context": "edit",
                "per_page": 10, "_fields": "id,slug,parent,status"},
        auth=auth, timeout=20,
    )
    r.raise_for_status()
    for p in (r.json() or []):
        if str(p.get("slug", "")) == slug:
            if parent and int(p.get("parent") or 0) != parent:
                continue
            return int(p.get("id") or 0)
    return 0


def _load(path: Path) -> dict:
    if path.is_file():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"WARN: read {path.name} failed: {exc!r}", file=sys.stderr)
    return {"years": []}


def _page_raw_content(base, auth, page_id: int) -> str | None:
    """既存ページの保存済み raw content (取得失敗時は None = 比較スキップ)。"""
    try:
        r = requests.get(
            base + f"/wp-json/wp/v2/pages/{page_id}",
            params={"context": "edit", "_fields": "id,content"},
            auth=auth, timeout=30,
        )
        r.raise_for_status()
        return (r.json() or {}).get("content", {}).get("raw")
    except Exception as exc:  # noqa: BLE001
        print(f"WARN: raw fetch page_id={page_id} failed: {exc!r}", file=sys.stderr)
        return None


def _upsert(base, auth, *, slug, title, content, excerpt, parent) -> bool:
    payload = {"slug": slug, "title": title, "content": content,
               "status": "publish", "parent": parent, "excerpt": excerpt}
    existing = _find_page_id(base, auth, slug, parent=parent)
    if existing:
        # 動かないデータを毎日上げ直さない: 内容が前回と同一なら POST しない
        # (revision 肥大と無駄 write 防止。取得失敗時は従来どおり update に進む)
        if _page_raw_content(base, auth, existing) == content:
            print(f"[{slug}] unchanged; skip page_id={existing}")
            return True
    url = base + (f"/wp-json/wp/v2/pages/{existing}" if existing
                 else "/wp-json/wp/v2/pages")
    action = "updated" if existing else "created"
    r = requests.post(url, json=payload, auth=auth, timeout=60)
    if not r.ok:
        print(f"[{slug}] upsert FAILED status={r.status_code} body={r.text[:300]}",
              file=sys.stderr)
        return False
    page = r.json() or {}
    print(f"[{slug}] {action} page_id={page.get('id')} status={page.get('status')} "
          f"bytes={len(content)}")
    return True


def refresh_rotation(base, auth, cluster_id, cur) -> bool:
    data = _load(ROTATION_DATA)
    fresh = starter_rotation_scraper.scrape_year(cur)
    if fresh:
        data["years"] = starter_rotation_scraper.upsert_year(data.get("years") or [], fresh)
        print(f"[rotation] refreshed {cur}: {len(fresh['games'])} games")
    else:
        print(f"[rotation] WARN: {cur} fetch empty; using baked data", file=sys.stderr)
    if not (data.get("years")):
        print("[rotation] no data; skip", file=sys.stderr)
        return False
    return _upsert(base, auth, slug="rotation", title=render_rotation_title(),
                   content=render_rotation_html(data),
                   excerpt=render_rotation_excerpt(data), parent=cluster_id)


def refresh_roster_moves(base, auth, cluster_id, cur) -> bool:
    data = _load(ROSTER_MOVES_DATA)
    fresh = roster_moves_scraper.scrape_year(cur)
    if fresh:
        data["years"] = roster_moves_scraper.upsert_year(data.get("years") or [], fresh)
        print(f"[roster-moves] refreshed {cur}: roster={len(fresh['roster'])} "
              f"moves={len(fresh['moves'])}")
    else:
        print(f"[roster-moves] WARN: {cur} fetch empty; using baked data", file=sys.stderr)
    if not (data.get("years")):
        print("[roster-moves] no data; skip", file=sys.stderr)
        return False
    return _upsert(base, auth, slug="roster-moves", title=render_roster_moves_title(data),
                   content=render_roster_moves_html(data),
                   excerpt=render_roster_moves_excerpt(data), parent=cluster_id)


def refresh_open_games(base, auth, cluster_id, cur) -> bool:
    data = _load(OPEN_GAMES_DATA)
    fresh = open_games_scraper.scrape_year(cur)
    if fresh:
        data["years"] = open_games_scraper.upsert_year(data.get("years") or [], fresh)
        print(f"[open-games] refreshed {cur}: {len(fresh['games'])} games")
    else:
        print(f"[open-games] WARN: {cur} fetch empty; using baked data", file=sys.stderr)
    if not (data.get("years")):
        print("[open-games] no data; skip", file=sys.stderr)
        return False
    return _upsert(base, auth, slug="open-games", title=render_open_games_title(data),
                   content=render_open_games_html(data),
                   excerpt=render_open_games_excerpt(data), parent=cluster_id)


def refresh_interleague(base, auth, cluster_id, cur) -> bool:
    data = _load(INTERLEAGUE_DATA)
    if not (data.get("years")):
        print("[interleague] no baked data; skip", file=sys.stderr)
        return False
    # 当年が baked (final) 済みなら scrape 不要。未確定なら NPB公式から live 注入。
    baked_years = {int(y.get("year") or 0) for y in data["years"] if y.get("final")}
    if cur not in baked_years:
        live = interleague_scraper.scrape_current(cur)
        if live:
            data["live"] = live
            g = live["giants"]
            print(f"[interleague] refreshed {cur}: {g['w']}勝{g['l']}敗{g['d']}分 "
                  f"暫定{g['rank']}位")
        else:
            print(f"[interleague] {cur} live なし (期間外 or fetch 失敗); baked のみ")
    return _upsert(base, auth, slug="interleague", title=render_interleague_title(data),
                   content=render_interleague_html(data),
                   excerpt=render_interleague_excerpt(data), parent=cluster_id)


def refresh_salary_value(base, auth, cluster_id, cur) -> bool:
    """年俸コスパ分析 (1ページ、 salary 一覧の子)。 2026-06-12 user GO。

    insight.db (GCS cache) が取れない日は skip (他ページ更新を止めない)。
    規定到達者が少なすぎる時期も skip = 薄いまま公開しない (品質基準⑤)。
    """
    from src import manual_intake_insight_query as miq
    from src.data_site_template_salary_value import (
        is_thin,
        load_salary_value_data,
        render_salary_value_excerpt,
        render_salary_value_html,
        render_salary_value_title,
    )
    db_info = miq.ensure_local_db()
    if not db_info.get("ok"):
        print(f"[salary-value] insight.db unavailable; skip: {db_info}", file=sys.stderr)
        return False
    data = load_salary_value_data(str(db_info.get("path")))
    if not data or is_thin(data):
        print(f"[salary-value] thin data (batters={len((data or {}).get('batters') or [])}); "
              "skip (低品質のまま出さない)", file=sys.stderr)
        return False
    parent = _find_page_id(base, auth, "salary", parent=cluster_id) or cluster_id
    print(f"[salary-value] batters={len(data['batters'])} pitchers={len(data['pitchers'])}")
    return _upsert(base, auth, slug="salary-value",
                   title=render_salary_value_title(data),
                   content=render_salary_value_html(data),
                   excerpt=render_salary_value_excerpt(data), parent=parent)


def refresh_standings(base, auth, cluster_id, cur) -> bool:
    """セ・リーグ順位表データページ (/data/standings/) を NPB 公式から自動更新。

    取得=既存テスト済み経路(interleague_scraper.fetch_standings_html +
    source_npb_standings_extractor.parse_npb_standings_html)。描画=standings_article
    (LLM不使用・数字そのまま)。試合日程に連動する本日次ジョブに相乗りして自動更新する。
    fetch 失敗は skip(他ページ更新を止めない)。"""
    from src import interleague_scraper as ils
    from src import source_npb_standings_extractor as sne
    from src import standings_article as sa

    try:
        html = ils.fetch_standings_html(cur, "c")
    except Exception as exc:  # noqa: BLE001
        print(f"[standings] fetch failed; skip: {exc!r}", file=sys.stderr)
        return False
    rows = sne.parse_npb_standings_html(html)
    if not rows:
        print("[standings] no rows parsed; skip", file=sys.stderr)
        return False

    standings = []
    for i, r in enumerate(rows, start=1):
        try:
            standings.append({
                "rank": int(r.get("rank") or i),
                "team": sa.short_team_name(r.get("team") or ""),
                "g": int(r.get("games") or 0),
                "w": int(r["wins"]),
                "l": int(r["losses"]),
                "t": int(r.get("draws") or 0),
                "pct": (r.get("win_pct") or "").strip(),
            })
        except (KeyError, ValueError, TypeError):
            continue
    if not standings:
        print("[standings] rows unusable; skip", file=sys.stderr)
        return False

    # 個人ランキング(打撃=打率 / 投手=防御率)も NPB 公式から取得。
    # 取れない時は順位表だけで公開(止めない)。
    from src import source_npb_leaders_extractor as nle

    leader_tables = []
    for kind, heading in (("bat", "セ・リーグ 個人打撃成績ランキング(打率)"),
                          ("pit", "セ・リーグ 個人投手成績ランキング(防御率)")):
        try:
            parsed = nle.parse_leaders_table(nle.fetch_leaders_html(cur, kind, "c"))
            if parsed and parsed[1]:
                leader_tables.append({"heading": heading, "headers": parsed[0], "rows": parsed[1]})
        except Exception as exc:  # noqa: BLE001
            print(f"[standings] leaders({kind}) fetch failed; skip section: {exc!r}", file=sys.stderr)

    date_label = datetime.now(timezone(timedelta(hours=9))).strftime("%Y年%-m月%-d日")
    title, content, excerpt = sa.render_standings_article(
        standings, date_label=date_label, source="NPB公式 順位表・個人成績",
        leader_tables=leader_tables,
    )
    return _upsert(base, auth, slug="standings", title=title,
                   content=content, excerpt=excerpt, parent=cluster_id)


def _report_player_class_drift() -> None:
    """登録ポジション分類 (data_site_player_class.json) が giants_roster.json に
    追従しているかを read-only で確認し、drift があればログに出すだけ。

    config は git 正本で、この job のコンテナ FS は ephemeral なため、ここでは
    **書き込まない / job を失敗させない**。drift が出たらローカルで
    ``python3 -m src.tools.sync_player_class_from_roster --write`` を回して
    commit する合図とする。"""
    try:
        from src.tools import sync_player_class_from_roster as sync

        roster = json.loads(sync.ROSTER_PATH.read_text(encoding="utf-8"))
        player_class = json.loads(sync.CLASS_PATH.read_text(encoding="utf-8"))
        additions, unresolved = sync.plan(roster, player_class)
        if not additions and not unresolved:
            print("[player-class] 分類は名簿に追従済み (drift なし)")
            return
        if additions:
            detail = ", ".join(f"{n}->{g}.{p}" for n, g, p in additions)
            print(f"[player-class] WARN: {len(additions)} 名が未分類 "
                  f"(sync_player_class_from_roster --write で反映): {detail}",
                  file=sys.stderr)
        if unresolved:
            detail = ", ".join(n for n, _ in unresolved)
            print(f"[player-class] WARN: {len(unresolved)} 名は position 不明で "
                  f"手動分類が必要: {detail}", file=sys.stderr)
    except Exception as exc:  # noqa: BLE001
        print(f"[player-class] drift check skipped: {exc!r}", file=sys.stderr)


def main() -> int:
    _report_player_class_drift()
    base, auth = _creds()
    cluster_id = _find_page_id(base, auth, "data", parent=0)
    cur = datetime.now(timezone.utc).year
    ok = []
    for fn in (refresh_rotation, refresh_roster_moves, refresh_open_games,
               refresh_interleague, refresh_salary_value, refresh_standings):
        try:
            ok.append(fn(base, auth, cluster_id, cur))
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR in {fn.__name__}: {exc!r}", file=sys.stderr)
            ok.append(False)
    # 1 つでも成功すれば 0 (両方失敗のみ非ゼロ)
    return 0 if any(ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
