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
from datetime import datetime, timezone
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


def main() -> int:
    base, auth = _creds()
    cluster_id = _find_page_id(base, auth, "data", parent=0)
    cur = datetime.now(timezone.utc).year
    ok = []
    for fn in (refresh_rotation, refresh_roster_moves, refresh_open_games,
               refresh_interleague):
        try:
            ok.append(fn(base, auth, cluster_id, cur))
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR in {fn.__name__}: {exc!r}", file=sys.stderr)
            ok.append(False)
    # 1 つでも成功すれば 0 (両方失敗のみ非ゼロ)
    return 0 if any(ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
