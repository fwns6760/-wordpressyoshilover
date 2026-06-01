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
import html as _htmllib
import logging
import os
import re
import sqlite3
import sys
import urllib.parse
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
    """投稿候補。post は「検証事実(数字/文脈/引用)+ 願望(主張しない)」だけで組む。

    LLM 不使用 = ハルシネーションゼロ。生成系の意味/一言(埋め草)は廃止し、
    number/context/quote は全て DB照合 or 記事literal、reaction は願望のみ。
    """
    bucket: str          # 順位・記録型 / 直近変化型 / 起用・昇格理由型
    player: str
    number: str          # 核となる検証数字(hook、必須)
    source: str          # 出典(DB scope / 記事URL)
    context: str = ""    # 追加の検証事実(今季比 等、任意・空可)
    reaction: str = ""   # 締めの願望(事実主張を含まない)
    quote: str = ""      # 記事の実発言(主は記事で要確認)
    article_url: str = ""
    note: str = ""
    polished: str = ""   # Flash Lite で引きつけた本文(数字検証通過時のみ。空=fact版)

    def fact_text(self) -> str:
        """検証事実のみで組んだ本文(LLMなし fallback)。全行 検証 or 願望。"""
        lines = [self.number]
        if self.context:
            lines.append(self.context)
        if self.quote:
            lines.append("")
            lines.append(f"「{self.quote}」")
        if self.reaction:
            lines.append("")
            lines.append(self.reaction)
        return "\n".join(lines)

    def post_text(self) -> str:
        """X に貼れる本文。LLM polish 通過分はそれを、無ければ fact 版。"""
        return self.polished or self.fact_text()

    def render(self) -> str:
        lines = [
            f"【{self.bucket}】{_short_name(self.player)}",
            "",
            self.post_text(),
            "",
            f"出典：{self.source}",
        ]
        if self.quote:
            lines.append("※ 発言の主は記事で確認(他者の発言の可能性)")
        if self.note:
            lines.append(f"※ {self.note}")
        return "\n".join(lines)


def _short_name(player: str) -> str:
    """表示用の短い選手名(記事注記やスペースを除く)。"""
    return player.split("(")[0].replace(" ", "").strip()


def _reaction(number: str) -> str:
    """締めの願望を返す(事実主張を含まない=ハルシネーション不可)。

    number の型でトーンだけ寄せ、選手名+数字長で deterministic に variant 選択。
    """
    if any(k in number for k in ("防御率", "勝利", "昇格", "登録")):
        pool = ["1軍でどう使われるか楽しみ。", "次の登板に期待。", "結果を出してほしい。"]
    elif any(k in number for k in ("連続", "本", "号", "猛打賞")):
        pool = ["このまま止まらず続けてほしい。", "どこまで伸びるか楽しみ。"]
    elif "番" in number:  # 起用・打順
        pool = ["今日のスタメン、楽しみ。", "チャンスで回ってきてほしい。"]
    else:  # rate / hot
        pool = ["ここから乗っていってほしい。", "この調子で頼む。", "今日も期待したい。"]
    return pool[len(number) % len(pool)]


def _has_hook(c: "Candidate") -> bool:
    """投稿に値する具体 hook があるか(薄い候補=打順だけ等を除外)。"""
    n = c.number
    if any(k in n for k in (".", "防御率", "連続", "本", "号", "昇格", "登録", "勝利", "猛打賞")):
        return True
    return bool(c.quote)  # 数字 hook が弱くても実発言があれば可


# ── Flash Lite polish(安価LLM。数字はコードロック、rate数字の捏造は却下)──
_GEMINI_MODEL = os.environ.get("DAILY_X_CANDIDATES_GEMINI_MODEL", "gemini-3.1-flash-lite")
# rate 数字: 「.412」(先頭0なし野球表記)も「1.65」「0.412」も捕捉
_RATE_RE = re.compile(r"\d*\.\d+")


def _llm_enabled() -> bool:
    if str(os.environ.get("DAILY_X_CANDIDATES_USE_LLM", "")).strip().lower() in {"0", "false", "no", "off"}:
        return False
    return bool(os.environ.get("GEMINI_API_KEY", "").strip())


def _allowed_rate_tokens(c: "Candidate") -> set[str]:
    """事実(number/context/quote)に含まれる rate 数字。出力はこれ以外の rate を持てない。"""
    src = " ".join([c.number, c.context, c.quote])
    return set(_RATE_RE.findall(src))


def _llm_polish(c: "Candidate", *, now_hint: str = "") -> str:
    """Flash Lite で「データ+文字で引きつける」本文に。数字検証 NG / 失敗時は ""。

    数字はプロンプトで固定 + 出力 rate 数字が事実外なら却下(数字ハルシネーション不可)。
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return ""
    facts = [c.number]
    if c.context:
        facts.append(c.context)
    if c.quote:
        facts.append(f"発言(主は本人とは限らない):「{c.quote}」")
    prompt = "\n".join([
        "あなたは巨人ファン向け速報メディア「ヨシラバー」の中の人。",
        "下の検証済みデータだけを使い、巨人ファンが思わず読みたくなる短いX投稿を書く。",
        "",
        "# 使える事実(これ以外の数字・順位・成績・固有名を足さない)",
        *facts,
        "",
        "# ルール",
        "- 上の数字はそのまま使い、新しい数字/順位/割合を絶対に作らない",
        "- 選手はフルネーム・敬称なし、短い行を改行で並べる",
        "- データ → ファンの実感 の流れ。120-160字で熱く、でも断定しすぎない",
        "- 煽り・誇張・未確定の予言はしない。事実は事実、気持ちは気持ち",
        "- 出力は投稿本文のみ(説明や前置きなし)",
    ])
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=_GEMINI_MODEL, contents=prompt, config={"temperature": 0.75},
        )
        text = (getattr(resp, "text", None) or "").strip()
    except Exception as exc:  # noqa: BLE001 - 失敗は fact 版に fallback
        LOG.warning("llm_polish skip player=%s err=%r", c.player, exc)
        return ""
    if not text or len(text) < 30:
        return ""
    # ① 数字ハルシネーション guard: 出力の rate 数字は事実内のものだけ
    allowed = _allowed_rate_tokens(c)
    if any(tok not in allowed for tok in _RATE_RE.findall(text)):
        LOG.warning("llm_polish rejected (rate hallucination) player=%s", c.player)
        return ""
    # ② データ保持 guard: 元の数字/記録を落としたふわふわ文は却下(データで引きつけ強制)
    if not _keeps_data(c, text):
        LOG.warning("llm_polish rejected (data dropped) player=%s", c.player)
        return ""
    # ③ 最小 inflammatory guard
    if any(w in text for w in ("死ね", "クビ", "戦犯", "最低", "引退しろ")):
        LOG.warning("llm_polish rejected (inflammatory) player=%s", c.player)
        return ""
    return text


def _keeps_data(c: "Candidate", text: str) -> bool:
    """polish 出力が元データ(数字/記録)を保持しているか。ふわふわ文を弾く。"""
    rates = _allowed_rate_tokens(c)
    if rates:
        return any(r in text for r in rates)
    keys = re.findall(r"\d+|連続|防御率|安打|昇格|本塁打|猛打賞|勝利", c.number)
    return any(k in text for k in keys) if keys else True


_QUOTE_BAN = ("vs", "ニュース20", "カレンダー", "万年", "第2章", "門下生", "ファイターズ",
              "読売ジャイアンツ", "プロ野球ニュース", "中継情報", "テレビ", "ラジオ")
_SPEECH_END = ("た", "たい", "ない", "思う", "いく", "ます", "です", "だ", "！", "。",
               "ね", "よ", "しい", "れる", "った", "たな", "ある")


def _quote_keys(player: str) -> set[str]:
    """選手名の照合 key(フル / 空白なし / 姓)。近接マッチ用。"""
    n = _short_name(player)
    keys = {n}
    if " " in player:
        keys.add(player.split(" ")[0])
    if len(n) >= 2:
        keys.add(n[:2])  # 姓近似
    return {k for k in keys if len(k) >= 2}


def _extract_quote(content_html: str, player: str = "") -> str:
    """記事本文 HTML から「発言らしい」引用を1つ拾う(LLM不使用)。

    番組名/対戦カード/カレンダー等のノイズは除外。player 指定時は **その選手名の近く
    (±150字)にある引用だけ**を採る(誤帰属防止)。近くに無ければ空(引用なし)。
    player 無指定時は最長の speech-like を返す。
    """
    if not content_html:
        return ""
    txt = _htmllib.unescape(re.sub(r"<[^>]+>", " ", content_html))
    valid: list[tuple[int, str]] = []
    for m in re.finditer(r"[「『]([^」』]{8,80})[」』]", txt):
        q = m.group(1).strip()
        if not (8 <= len(q) <= 70):
            continue
        if any(b in q for b in _QUOTE_BAN):
            continue
        if not q.endswith(_SPEECH_END):
            continue
        valid.append((m.start(), q))
    if not valid:
        return ""
    if player:
        # 選手名の出現位置に最も近い引用(±150字以内)だけ採用
        positions: list[int] = []
        for k in _quote_keys(player):
            i = txt.find(k)
            while i != -1:
                positions.append(i)
                i = txt.find(k, i + 1)
        if not positions:
            return ""
        best, best_d = "", 10 ** 9
        for pos, q in valid:
            d = min(abs(pos - p) for p in positions)
            if d < best_d:
                best, best_d = q, d
        return best if best_d <= 150 else ""
    return max((q for _, q in valid), key=len, default="")


def _x_intent_url(text: str) -> str:
    """X(Twitter)の投稿 intent URL。クリックで本文 prefill された compose が開く。"""
    return "https://x.com/intent/post?text=" + urllib.parse.quote(text)


def _search_player_quote(player: str) -> tuple[str, str]:
    """WP を選手名で read-only 検索し、直近記事から引用1つ + 記事URLを返す。

    creds 無し / hit 無しなら ("", "")。hidden_hot(ニュース外の選手)の材料補完用。
    """
    base = os.environ.get("WP_URL", "").strip().rstrip("/")
    user = os.environ.get("WP_USER", "").strip()
    pw = os.environ.get("WP_APP_PASSWORD", "").strip()
    if not (base and user and pw):
        return "", ""
    name = _short_name(player)
    try:
        r = requests.get(
            base + "/wp-json/wp/v2/posts",
            params={"search": name, "per_page": 3, "_fields": "link,content",
                    "orderby": "date", "order": "desc"},
            auth=HTTPBasicAuth(user, pw),
            timeout=20,
        )
        if not r.ok:
            return "", ""
        for p in (r.json() or []):
            q = _extract_quote((p.get("content", {}) or {}).get("rendered", ""), name)
            if q:
                return q, p.get("link", "")
    except Exception as exc:  # noqa: BLE001
        LOG.warning("_search_player_quote err %s: %r", player, exc)
    return "", ""


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
    number = f"{_short_name(player)} 直近7日 {label}{val_s}({n}打席){rank_s}"
    return number, "insight.db last_7d(日付ベース)"


def _season_recent_context(cur: sqlite3.Cursor, player: str, snap: str) -> str:
    """今季通算 AVG を文脈として返す(検証事実、sample>=40 のみ)。空可。

    例「今季通算は打率.270」。直近数字との対比はファンが読み取るので断定しない。
    """
    r = cur.execute(
        """SELECT metric_value, sample_size FROM advanced_metric_snapshots
           WHERE team_code='g' AND player_canonical=? AND snapshot_date=? AND scope='season' AND metric_name='AVG'""",
        (player, snap),
    ).fetchone()
    if r and r[0] is not None and (r[1] or 0) >= 40:
        return f"今季通算は打率{f'{r[0]:.3f}'.lstrip('0')}({r[1]}打席)"
    return ""


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
        is_pitcher = _is_pitcher(cur, player)
        num = _player_number(cur, player, snap)  # 投手→防御率 / 野手→打率(型出し分け)
        context = ""
        if num and _is_positive_hook(num[0], is_pitcher=is_pitcher):
            number, source = num
            note = ""
            context = "" if is_pitcher else _season_recent_context(cur, player, snap)
        else:
            # rate が凡庸/不調 or 無し → 正のシグナル文(連続安打等)を hook にする
            number = f"{_short_name(player)} {cur_val}"
            source = f"signal:{sig}"
            note = f"最終出場 {last_app} を確認の上で使用"
        is_streak = sig in ("batter_hit_streak", "batter_multi_hit", "anomaly_milestone_crossed")
        bucket = "順位・記録型" if is_streak else "直近変化型"
        out.append(Candidate(bucket, player, number, source, context=context,
                             reaction=_reaction(number), note=note))
    return out


def _fetch_recent_posts(limit_posts: int = 30) -> list[dict]:
    """直近 WP 記事(title/link)を read-only GET。creds 無しなら []。"""
    base = os.environ.get("WP_URL", "").strip().rstrip("/")
    user = os.environ.get("WP_USER", "").strip()
    pw = os.environ.get("WP_APP_PASSWORD", "").strip()
    if not (base and user and pw):
        LOG.info("WP creds 無し → ニュース連動は skip")
        return []
    try:
        r = requests.get(
            base + "/wp-json/wp/v2/posts",
            params={"per_page": limit_posts, "_fields": "title,link,date,content",
                    "orderby": "date", "order": "desc"},
            auth=HTTPBasicAuth(user, pw),
            timeout=25,
        )
        if not r.ok:
            LOG.warning("WP posts fetch fail status=%d", r.status_code)
            return []
        return r.json() or []
    except Exception as exc:  # noqa: BLE001
        LOG.warning("WP posts fetch err: %r", exc)
        return []


def _giants_match_map(cur: sqlite3.Cursor) -> dict[str, str]:
    """記事タイトル照合用 key→canonical。full(空白有/無)優先、姓は fallback。"""
    roster = _giants_roster(cur)
    full_keys: dict[str, str] = {}
    surname_keys: dict[str, str] = {}
    for n in roster:
        full_keys[n.replace(" ", "")] = n
        full_keys[n] = n
        sur = n.split(" ")[0] if " " in n else n[:2]
        surname_keys.setdefault(sur, n)  # 先勝ち(姓衝突は full 優先で吸収)
    # full を優先するため後ろに surname を merge(full に無い key のみ)
    for k, v in surname_keys.items():
        full_keys.setdefault(k, v)
    return full_keys


def _pitching_number(cur: sqlite3.Cursor, player: str, snap: str) -> Optional[tuple[str, str]]:
    """投手の数字(防御率)。last_7d → season の順。微小サンプルは誇張防止で除外。

    sample_size < 3 の scope は採用しない(防御率0.00・セ1位 のような 1-2 回の
    誇張を避け、 記事テキストの二軍成績 fallback に回す)。 セ順位は sample>=10 のみ。
    """
    for scope in ("last_7d", "season"):
        r = cur.execute(
            """SELECT metric_value, sample_size, league_rank FROM advanced_metric_snapshots
               WHERE team_code='g' AND player_canonical=? AND snapshot_date=? AND scope=? AND metric_name='ERA'""",
            (player, snap, scope),
        ).fetchone()
        if r and r[0] is not None and (r[1] or 0) >= 3:
            rank_s = f"・セ{r[2]}位" if r[2] and r[2] <= 10 and (r[1] or 0) >= 10 else ""
            label = "直近7日" if scope == "last_7d" else "今季"
            return f"{_short_name(player)} {label} 防御率{r[0]:.2f}(投球回基準{r[1]}){rank_s}", f"insight.db {scope}"
    return None


def _is_pitcher(cur: sqlite3.Cursor, player: str) -> bool:
    """投手か(pitching_logs に登板記録があれば投手)。"""
    r = cur.execute(
        "SELECT COUNT(*) FROM pitching_logs WHERE player_canonical=?", (player,)
    ).fetchone()
    return bool(r and r[0])


def _player_number(cur: sqlite3.Cursor, player: str, snap: str) -> Optional[tuple[str, str]]:
    """ポジションに応じた数字を返す。投手→防御率 / 野手→打率。型違いは出さない。"""
    if _is_pitcher(cur, player):
        return _pitching_number(cur, player, snap)
    return _fresh_number(cur, player, snap)


_PITCH_WORDS = ("投球", "マウンド", "完投", "完封", "奪三振", "三振", "抑え",
                "リリーフ", "先発", "防御率", "制球", "球威", "ストレート", "変化球", "投げ")


def _quote_fits_position(quote: str, is_pitcher: bool) -> bool:
    """引用が選手のポジションと矛盾しないか(投手発言を野手に付けない)。"""
    if not quote:
        return True
    has_pitch_talk = any(w in quote for w in _PITCH_WORDS)
    if has_pitch_talk and not is_pitcher:
        return False  # 野手に投手発言=誤帰属の使い回し → 捨てる
    return True


def _is_positive_hook(number: str, *, is_pitcher: bool) -> bool:
    """投稿に値する「良い/注目」数字か。不調(.000 等)・凡庸は除外。

    セ/順位が付いていれば無条件 OK(記録系・連続・本塁打・昇格も OK)。
    率のみの時: 野手は打率 >= .270、投手は防御率 <= 3.00 を目安に。
    """
    if any(k in number for k in ("セ", "位", "連続", "本塁打", "猛打賞", "昇格", "登録", "勝利", "号")):
        return True
    rates = _RATE_RE.findall(number)
    if not rates:
        return True  # 数字が rate でない(記事数字等)はここで弾かない
    try:
        val = float(rates[0] if rates[0].startswith("0") or "." != rates[0][0] else "0" + rates[0])
    except ValueError:
        return True
    if is_pitcher:
        return val <= 3.00          # 防御率は低いほど良い
    return val >= 0.270             # 打率 .270 未満は出さない(不調除外)


def _article_number(title: str) -> Optional[str]:
    """記事タイトルから数字を抽出(二軍/昇格の fallback、出典=記事)。"""
    nums: list[str] = []
    for pat in NUM_PATTERNS:
        nums.extend(pat.findall(title))
    if not nums:
        return None
    cleaned = [n.replace("『", "").replace("」", "").replace("「", "").strip() for n in nums]
    return " / ".join(dict.fromkeys(cleaned))[:60]


def collect_news_anchored(cur: sqlite3.Cursor, posts: list[dict]) -> list[Candidate]:
    """ニュース起点: 各記事の関連巨人選手にデータを紐付ける(RSS=鮮度ゲート内蔵)。

    一軍打者→last_7d打率 / 投手→防御率 / 二軍・DB不在→記事タイトル内の数字。
    自前の【巨人データ】post はデータ連動が冗長なので除外。
    """
    snap = cur.execute("SELECT MAX(snapshot_date) FROM advanced_metric_snapshots").fetchone()[0]
    gmap = _giants_match_map(cur)
    out: list[Candidate] = []
    emitted: set[str] = set()  # 同一選手は最初に出た記事1本だけ(重複排除)
    for p in posts:
        title = (p.get("title", {}) or {}).get("rendered", "") or ""
        link = p.get("link", "")
        content_html = (p.get("content", {}) or {}).get("rendered", "")
        if title.startswith("【巨人データ】"):
            continue  # 自前データ post には付けない
        matched: list[str] = []
        for key, canon in gmap.items():
            if key in title and canon not in matched:
                matched.append(canon)
        if not matched:
            continue
        for player in matched[:3]:
            if player in emitted:
                continue
            emitted.add(player)
            is_pitcher = _is_pitcher(cur, player)
            article_quote = _extract_quote(content_html, player)  # 選手近接の引用のみ
            if not _quote_fits_position(article_quote, is_pitcher):
                article_quote = ""  # 投手発言を野手に付けない(誤帰属の使い回し排除)
            num = _player_number(cur, player, snap)  # 投手→防御率 / 野手→打率
            context = note = ""
            if num and _is_positive_hook(num[0], is_pitcher=is_pitcher):
                number, source = num
                context = "" if is_pitcher else _season_recent_context(cur, player, snap)
            else:
                # rate が不調/凡庸/無し → 記事数字(昇格等) or 発言を hook に。両方無ければ skip
                art = _article_number(title)
                if art:
                    number, source = f"{_short_name(player)} {art}", link
                    note = "数字は記事タイトル由来。本文で正確に確認の上で使用"
                elif article_quote:
                    number, source = _short_name(player), link  # 発言が主のポスト
                else:
                    continue  # 良い数字も記事数字も整合する発言も無い → 出さない
            out.append(Candidate(
                bucket="ニュース連動",
                player=f"{player}(記事: {title.strip()[:34]}…)",
                number=number,
                source=link if source.startswith("http") or not link else f"{source} / {link}",
                context=context,
                reaction=_reaction(number),
                quote=article_quote,
                article_url=link,
                note=note,
            ))
    return out


def generate(limit_ichigun: int = 6) -> dict:
    path = _db_path()
    posts = _fetch_recent_posts()
    news: list[Candidate] = []
    hidden_hot: list[Candidate] = []
    if path:
        with sqlite3.connect(path) as conn:
            cur = conn.cursor()
            news = [c for c in collect_news_anchored(cur, posts) if _has_hook(c)]
            news_players = {c.player.split("(")[0] for c in news}
            # ニュースに出ていない「隠れ好調」だけを DB signal から補完
            for c in collect_ichigun_candidates(cur):
                if c.player not in news_players:
                    # 記事から発言/引用を拾って材料化(ニュース外でも検索で補完)
                    q, url = _search_player_quote(c.player)
                    if _quote_fits_position(q, _is_pitcher(cur, c.player)):
                        c.quote, c.article_url = q, url
                    else:
                        c.article_url = url  # 引用は捨てるが記事リンクは残す
                    if not _has_hook(c):
                        continue  # 数字 hook も発言も無い薄い候補は出さない
                    hidden_hot.append(c)
                if len(hidden_hot) >= limit_ichigun:
                    break
    else:
        LOG.warning("insight.db 不在(INSIGHT_DB_PATH 未設定)→ DB 連動 skip")

    # 誤帰属対策: 同一引用が 2 人以上に付いたら使い回し=誤帰属とみなし全員から外す。
    from collections import Counter
    qcount = Counter(c.quote for c in news + hidden_hot if c.quote)
    for c in news + hidden_hot:
        if c.quote and qcount[c.quote] > 1:
            c.quote = ""
    # 引用を外した結果 hook(数字/発言)が無くなった候補は落とす
    news = [c for c in news if _has_hook(c)]
    hidden_hot = [c for c in hidden_hot if _has_hook(c)]

    # Flash Lite polish(安価・任意)。数字はロック済、検証通過分だけ採用。失敗は fact 版。
    if _llm_enabled():
        polished_n = 0
        for c in news + hidden_hot:
            p = _llm_polish(c)
            if p:
                c.polished = p
                polished_n += 1
        LOG.info("llm_polish applied=%d/%d (model=%s)", polished_n, len(news) + len(hidden_hot), _GEMINI_MODEL)

    return {"news": news, "hidden_hot": hidden_hot}


def flatten_candidates(result: dict) -> list[Candidate]:
    """送信順に1本のリスト化(ニュース連動 → 隠れ好調)。"""
    return list(result.get("news", [])) + list(result.get("hidden_hot", []))


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _card_html(c: Candidate, idx: int) -> str:
    """1候補のカード HTML(本文 + Xポスト/記事ボタン + 出典)。"""
    head = c.player.split("(")[0]
    x_draft = c.post_text()
    intent = _x_intent_url(x_draft)
    src = (f'<a href="{_esc(c.source)}">記事/出典を開く</a>'
           if c.source.startswith("http") else _esc(c.source))
    note = f'<div style="color:#999;font-size:12px;margin-top:6px;">※ {_esc(c.note)}</div>' if c.note else ""
    quote_caution = ('<div style="color:#999;font-size:11px;">※ 発言の主は記事で確認</div>'
                     if c.quote else "")
    btn = (
        f'<a href="{_esc(intent)}" '
        'style="display:inline-block;background:#000;color:#fff;text-decoration:none;'
        'padding:11px 20px;border-radius:9999px;font-weight:600;font-size:14px;margin:4px 8px 4px 0;">'
        '𝕏 にポストする</a>'
    )
    read_btn = (
        f'<a href="{_esc(c.article_url)}" '
        'style="display:inline-block;background:#eee;color:#333;text-decoration:none;'
        'padding:11px 18px;border-radius:9999px;font-size:14px;margin:4px 0;">記事を読む</a>'
        if c.article_url.startswith("http") else ""
    )
    return (
        '<div style="border:1px solid #eee;border-radius:8px;padding:14px;margin:0 0 16px;">'
        f'<div style="font-weight:600;color:#5d4037;margin-bottom:6px;">{idx}. 【{_esc(c.bucket)}】{_esc(head)}</div>'
        '<div style="background:#fafafa;border-radius:8px;padding:12px;margin:6px 0;">'
        f'<div style="white-space:pre-wrap;font-size:14px;line-height:1.6;">{_esc(x_draft)}</div></div>'
        f'{quote_caution}'
        f'<div style="margin-top:8px;">{btn}{read_btn}</div>'
        f'<div style="margin-top:6px;color:#888;font-size:12px;">出典：{src}</div>'
        f'{note}</div>'
    )


def _card_text(c: Candidate, idx: int) -> str:
    head = c.player.split("(")[0]
    x_draft = c.post_text()
    return "\n".join([
        f"── {idx}. 【{c.bucket}】{head} ──",
        x_draft,
        f"▶ ポスト: {_x_intent_url(x_draft)}",
        (f"出典: {c.source}" if c.source else ""),
    ])


def build_combined_mail(cands: list[Candidate], *, date_label: str) -> tuple[str, str, str]:
    """全候補を1通にまとめる(各候補=カード + Xポストボタン)。(subject, text, html)。"""
    n = len(cands)
    subject = f"【巨人Xデータ】今日の候補 {n}件 {date_label}".strip()
    text_body = "\n\n".join(
        [f"今日のX投稿候補 {n}件（手動選別用 / 投稿はされません）"]
        + [_card_text(c, i) for i, c in enumerate(cands, 1)]
        + ["─ 各ポストボタンで本文入りのX作成画面が開きます。"]
    )
    cards = "".join(_card_html(c, i) for i, c in enumerate(cands, 1))
    html_body = (
        '<div style="font-family:sans-serif;max-width:600px;">'
        f'<div style="font-size:13px;color:#666;margin-bottom:10px;">今日のX投稿候補 {n}件 / 手動選別用・投稿はされません。気に入った候補のボタンを押すと本文入りのX作成画面が開きます。</div>'
        f'{cards or "<p>候補なし</p>"}'
        '</div>'
    )
    return subject, text_body, html_body


def _print_report(result: dict) -> None:
    cands = flatten_candidates(result)
    print("=" * 60)
    print("今日のX投稿候補(449 §5 ニュース連動 / read-only / 投稿はしない)")
    print(f"news={len(result.get('news', []))} hidden_hot={len(result.get('hidden_hot', []))} 計{len(cands)}件")
    print("=" * 60)
    for i, c in enumerate(cands, 1):
        print(f"\n--- {i}/{len(cands)} ---")
        print(c.render())
    if not cands:
        print("\n候補なし(DB/WP creds を確認)")


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    result = generate()
    _print_report(result)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
