"""今日のX投稿候補ジェネレータ(449 §5 RSS話題ゲート方式、read-only)。

目的:
    DB 全スキャンではなく「今日 話題になっている巨人選手・動き」を起点に、
    448 §3 の ① データ小ネタ候補を `数字 / 意味 / 一言` テンプレで出す。
    投稿はしない。WP 書き込み・env 変更・Gemini・source 拡張・X API は一切なし。

データ源2系統(449 §5):
    - 一軍で調子いい選手 → insight.db(日付ベース snapshot + 最終出場ゲート)
    - 二軍/昇格・抹消の理由 → 直近 WP 記事タイトル内の数字(出典=その記事)

必須ゲート(449 §1):
    1. 巨人ロスターで絞る(advanced_metric_snapshots team_code='g' の選手集合)
    2. 最終出場日 ≤ 直近 FRESH_DAYS 日(離脱選手を除外)
    3. scope 鮮度: 「数字」は日付ベース(last_7d)を優先。試合数ベースは decay しないので単独採用しない

実行:
    INSIGHT_DB_PATH=/path/insight.db python -m src.tools.daily_x_candidates
    (WP 記事取得は WP_URL/WP_USER/WP_APP_PASSWORD があれば read-only GET。無ければ一軍のみ)
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

import requests
from requests.auth import HTTPBasicAuth

LOG = logging.getLogger("daily_x_candidates")

FRESH_DAYS = 3  # 最終出場が「最新試合日 - FRESH_DAYS」以内のみ採用(離脱除外)

# fan が反応しやすい signal のみ(投手 rest/workload 等のノイズは除外)
FAN_SIGNAL_TYPES = (
    "batter_hit_streak",
    "batter_multi_hit",
    "batter_recent_hot",
    "batter_homerun",
    "anomaly_milestone_crossed",
    "lineup_slot_jump_up",
    "lineup_first_slot_appearance",
    "starter_quality_start",
)

# 昇格・抹消・登録系の WP タイトル keyword
ROSTER_MOVE_KEYWORDS = ("一軍登録", "1軍登録", "再昇格", "今季初昇格", "昇格", "登録抹消", "抹消", "出場選手登録")

# 記事タイトルから拾う数字 pattern(出典=記事)
NUM_PATTERNS = [
    re.compile(r"防御率[『「]?\s*[\d.]+"),
    re.compile(r"打率[『「]?\s*[\d.]+"),
    re.compile(r"\d+試合"),
    re.compile(r"\d+登板"),
    re.compile(r"防御率\d+[.．]\d+"),
    re.compile(r"プロ初勝利"),
    re.compile(r"\d+[本号]"),
]


@dataclass
class Candidate:
    bucket: str          # 順位・記録型 / 直近変化型 / 起用・昇格理由型
    player: str
    number: str          # 数字: 行
    meaning: str         # 意味: 行(データ由来の事実テンプレ)
    source: str          # 出典(DB last_7d / 記事URL)
    note: str = ""       # 補足(鮮度・要確認 等)

    def render(self) -> str:
        lines = [
            f"【{self.bucket}】{self.player}",
            f"数字：{self.number}",
            f"意味：{self.meaning}",
            "一言：(ファン向けの一言をここに / 448 テンプレ)",
            f"出典：{self.source}",
        ]
        if self.note:
            lines.append(f"※ {self.note}")
        return "\n".join(lines)


def _db_path() -> Optional[str]:
    explicit = os.environ.get("INSIGHT_DB_PATH", "").strip()
    if explicit and os.path.exists(explicit):
        return explicit
    default = "/tmp/insight_cache/insight.db"
    return default if os.path.exists(default) else None


def _giants_roster(cur: sqlite3.Cursor) -> set[str]:
    """ゲート①: 確実に巨人判別できる team_code='g' の選手集合。"""
    return {r[0] for r in cur.execute(
        "SELECT DISTINCT player_canonical FROM advanced_metric_snapshots WHERE team_code='g'"
    )}


def _latest_game_date(cur: sqlite3.Cursor) -> Optional[str]:
    r = cur.execute("SELECT MAX(game_date) FROM games").fetchone()
    return r[0] if r else None


def _last_appearance(cur: sqlite3.Cursor, player: str) -> Optional[str]:
    """打撃・投球どちらでも最後に出場した game_date。"""
    rows = cur.execute(
        """
        SELECT MAX(g.game_date) FROM (
            SELECT game_id FROM batting_logs WHERE player_canonical=?
            UNION
            SELECT game_id FROM pitching_logs WHERE player_canonical=?
        ) x JOIN games g ON x.game_id=g.game_id
        """,
        (player, player),
    ).fetchone()
    return rows[0] if rows and rows[0] else None


def _is_fresh(last_app: Optional[str], latest_game: Optional[str]) -> bool:
    """ゲート②: 最終出場が最新試合日から FRESH_DAYS 以内か。"""
    if not last_app or not latest_game:
        return False
    try:
        la = date.fromisoformat(last_app[:10])
        lg = date.fromisoformat(latest_game[:10])
    except ValueError:
        return False
    return (lg - la) <= timedelta(days=FRESH_DAYS)


def _fresh_number(cur: sqlite3.Cursor, player: str, snapshot_date: str) -> Optional[tuple[str, str]]:
    """ゲート③: 日付ベース last_7d の AVG/OPS + league_rank を「数字」化。

    返り値 = (number_text, source_text)。last_7d が無ければ None。
    """
    rows = cur.execute(
        """
        SELECT metric_name, metric_value, sample_size, league_rank, league_total
        FROM advanced_metric_snapshots
        WHERE team_code='g' AND player_canonical=? AND snapshot_date=? AND scope='last_7d'
          AND metric_name IN ('AVG','OPS','OBP')
        ORDER BY CASE metric_name WHEN 'AVG' THEN 0 WHEN 'OPS' THEN 1 ELSE 2 END
        """,
        (player, snapshot_date),
    ).fetchall()
    if not rows:
        return None
    name, val, n, rank, total = rows[0]
    label = {"AVG": "打率", "OPS": "OPS", "OBP": "出塁率"}.get(name, name)
    val_s = f"{val:.3f}".lstrip("0") if (name != "OPS" and val < 1) else f"{val:.3f}"
    rank_s = f"・セ{rank}位" if rank and rank <= 10 else ""
    number = f"{player} 直近7日 {label}{val_s}({n}打席){rank_s}"
    return number, "insight.db last_7d(日付ベース)"


def collect_ichigun_candidates(cur: sqlite3.Cursor) -> list[Candidate]:
    """一軍: 直近の fan signal を巨人ロスター ∩ 鮮度ゲートで絞り、日付ベース数字を足す。"""
    roster = _giants_roster(cur)
    latest_game = _latest_game_date(cur)
    snap = cur.execute("SELECT MAX(snapshot_date) FROM advanced_metric_snapshots").fetchone()[0]
    placeholders = ",".join("?" for _ in FAN_SIGNAL_TYPES)
    rows = cur.execute(
        f"""
        SELECT player_canonical, signal_type, current_value
        FROM article_candidates
        WHERE signal_type IN ({placeholders})
        ORDER BY created_at DESC
        LIMIT 1500
        """,
        FAN_SIGNAL_TYPES,
    ).fetchall()
    out: list[Candidate] = []
    seen: set[str] = set()
    for player, sig, cur_val in rows:
        if player not in roster or player in seen:
            continue
        last_app = _last_appearance(cur, player)
        if not _is_fresh(last_app, latest_game):
            continue  # ゲート②: 離脱・古いを除外(平山型をここで落とす)
        seen.add(player)
        fresh = _fresh_number(cur, player, snap)
        if fresh:
            number, source = fresh
            note = ""
        else:
            # 日付ベースが無い時はシグナル文 + 最終出場日を併記(鮮度明示)
            number = f"{player} {cur_val}"
            source = f"signal:{sig}"
            note = f"日付ベース stat 無し。最終出場 {last_app} を確認の上で使用"
        is_streak = sig in ("batter_hit_streak", "batter_multi_hit", "anomaly_milestone_crossed")
        bucket = "順位・記録型" if is_streak else "直近変化型"
        meaning = (
            "出塁/安打が途切れず続いている＝打線が繋がりやすい" if is_streak
            else "直近で数字が上がっている＝今が旬の選手"
        )
        out.append(Candidate(bucket, player, number, meaning, source, note))
    return out


def collect_roster_move_candidates(limit_posts: int = 40) -> list[Candidate]:
    """二軍/昇格・抹消: 直近 WP 記事タイトルから動き + 数字を拾う(出典=記事)。"""
    base = os.environ.get("WP_URL", "").strip().rstrip("/")
    user = os.environ.get("WP_USER", "").strip()
    pw = os.environ.get("WP_APP_PASSWORD", "").strip()
    if not (base and user and pw):
        LOG.info("WP creds 無し → 昇格/抹消候補は skip(一軍のみ出力)")
        return []
    try:
        r = requests.get(
            base + "/wp-json/wp/v2/posts",
            params={"per_page": limit_posts, "_fields": "title,link,date", "orderby": "date", "order": "desc"},
            auth=HTTPBasicAuth(user, pw),
            timeout=20,
        )
        if not r.ok:
            LOG.warning("WP posts fetch fail status=%d", r.status_code)
            return []
        posts = r.json() or []
    except Exception as exc:  # noqa: BLE001
        LOG.warning("WP posts fetch err: %r", exc)
        return []
    out: list[Candidate] = []
    for p in posts:
        title = (p.get("title", {}) or {}).get("rendered", "") or ""
        if not any(kw in title for kw in ROSTER_MOVE_KEYWORDS):
            continue
        nums: list[str] = []
        for pat in NUM_PATTERNS:
            nums.extend(pat.findall(title))
        if not nums:
            continue  # 数字が記事に無ければ「なぜ」を裏づけられない → skip
        dedup = list(dict.fromkeys(nums))
        number = f"{title.strip()[:60]} … {' / '.join(dedup[:3])}"
        out.append(Candidate(
            bucket="起用・昇格理由型",
            player="(記事参照)",
            number=number,
            meaning="結果を出した/整理された選手の動き＝起用の裏づけ",
            source=p.get("link", ""),
            note="数字は記事タイトル由来。本文で正確に確認の上で使用(捏造しない)",
        ))
    return out


def generate(limit_ichigun: int = 6) -> dict:
    path = _db_path()
    ichigun: list[Candidate] = []
    if path:
        with sqlite3.connect(path) as conn:
            ichigun = collect_ichigun_candidates(conn.cursor())[:limit_ichigun]
    else:
        LOG.warning("insight.db 不在(INSIGHT_DB_PATH 未設定)→ 一軍候補 skip")
    moves = collect_roster_move_candidates()
    return {"ichigun": ichigun, "roster_moves": moves}


def _print_report(result: dict) -> None:
    ichigun = result["ichigun"]
    moves = result["roster_moves"]
    print("=" * 60)
    print("今日のX投稿候補(449 §5 RSS話題ゲート / read-only / 投稿はしない)")
    print("=" * 60)
    print(f"\n■ 一軍・調子(insight.db、ロスター∩鮮度ゲート通過) {len(ichigun)}件")
    for c in ichigun:
        print("\n" + c.render())
    print(f"\n\n■ 二軍/昇格・抹消(記事タイトル由来) {len(moves)}件")
    for c in moves:
        print("\n" + c.render())
    if not ichigun and not moves:
        print("\n候補なし(DB/WP creds を確認)")


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = generate()
    _print_report(result)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
