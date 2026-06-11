"""巨人 年俸ページ publisher (一覧 + 選手別)。

config/giants_salary.json (検証済 baked データ) から
- /data/salary/            年俸ランキング一覧 (parent = data cluster)
- /data/salary/<slug>/     選手別 年俸推移 (parent = salary 一覧ページ)
を upsert する。年俸は契約更改期にしか動かないため定期 Job には載せず、
データ追加・更新時に手動 (またはアドホック Job) で実行する。

LLM 不使用。daily_refresh と同じ WP 認証 (.env fallback) と差分 skip を使う。

usage:
  python -m src.tools.data_site_salary_publish            # 全選手 + 一覧
  python -m src.tools.data_site_salary_publish <slug>...  # 指定選手 + 一覧
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.data_site_template_salary import (  # noqa: E402
    load_salary_data,
    render_salary_index_excerpt,
    render_salary_index_html,
    render_salary_index_title,
    render_salary_player_excerpt,
    render_salary_player_html,
    render_salary_player_title,
)
from src.tools.data_site_daily_refresh import (  # noqa: E402
    _creds,
    _find_page_id,
    _upsert,
)


def main() -> int:
    only = set(sys.argv[1:])
    data = load_salary_data()
    players = [p for p in (data.get("players") or [])
               if not only or p["slug"] in only]
    if not (data.get("players")):
        print("no salary data; abort", file=sys.stderr)
        return 1

    base, auth = _creds()
    cluster_id = _find_page_id(base, auth, "data", parent=0)
    if not cluster_id:
        print("data cluster page not found; abort", file=sys.stderr)
        return 1

    ok = []
    # 一覧 (選手ページの parent になるため先に upsert)
    ok.append(_upsert(
        base, auth, slug="salary",
        title=render_salary_index_title(data),
        content=render_salary_index_html(data),
        excerpt=render_salary_index_excerpt(data),
        parent=cluster_id,
    ))
    salary_id = _find_page_id(base, auth, "salary", parent=cluster_id)
    if not salary_id:
        print("salary index page not found after upsert; abort", file=sys.stderr)
        return 1

    for p in players:
        try:
            ok.append(_upsert(
                base, auth, slug=p["slug"],
                title=render_salary_player_title(p),
                content=render_salary_player_html(p),
                excerpt=render_salary_player_excerpt(p),
                parent=salary_id,
            ))
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR publishing {p['slug']}: {exc!r}", file=sys.stderr)
            ok.append(False)
    print(f"done: {sum(1 for x in ok if x)}/{len(ok)} pages ok")
    return 0 if all(ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
