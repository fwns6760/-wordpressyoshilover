"""392: ヨシラバー branding X 投稿案を Gemma 4 + Tavily HTTP REST で生成。

391 (Phase 1 CLI) で smoke 確認した方法を本番 ``x-post-mail-lane`` に
組み込むための core モジュール。 stdio MCP ではなく **Tavily REST direct**
を採用 (既存 ``Dockerfile.x_post_mail`` に Node を追加せず、 image / cold
start 不変)。

設計方針 (2026-05-19 user lock):

- 検索は ``POST https://api.tavily.com/search`` で HTTP REST 直叩き。
  fastmcp / Node は使わない。
- 生成は Gemini API 経由 Gemma 4 31B (free tier)。 paid 切替禁止。
- spec 382 hard rule (URL / hashtag / 未検証数字 / 引用 / 媒体名 禁止) を
  system prompt + post-gen regex validator の二段で gate。
- 失敗時は ``None`` 返却 (silent skip)。 caller (``run_x_post_mail.py``) は
  既存 mail を絶対に止めない。
- 任意で ``insight.db`` 由来の DB 照合済み数字を RAG として注入できる。
"""

from __future__ import annotations

import hashlib as _hashlib
import logging as _logging
import re as _re
from typing import Optional

# 既存 ``x_post_mail_lane`` の Candidate / 共通 helper を再利用する。
from src.x_post_mail_lane import (
    Candidate,
    X_CHAR_LIMIT,
    _finalize_post_text,
    _is_safe_post_text,
    _is_verified_full_giants_player_name,
)


# Gemini API 経由 Gemma 4 31B model id (391 smoke で動作確認済)
_GEMMA_BRANDING_METRIC = "GEMMA_BRANDING"
_GEMMA_BRANDING_MODEL = "gemma-4-31b-it"


# spec 382 hard rule の追加 gate (既存 ``_FORBIDDEN_POST_TERMS`` の上に積む)
_GEMMA_BRANDING_FORBIDDEN_PATTERNS = (
    _re.compile(r"https?://"),
    _re.compile(r"#\S+"),
    _re.compile(r"ヨシラバー(で|を|に)?整理しました"),
    _re.compile(r"Xでは|X上では|みんなの声"),
)


_SYSTEM_PROMPT_BASE = """あなたは巨人を主題にした野球メディアの編集者です。
Tavily で巨人関連トピックを web 検索し、 X 投稿案を 1 件生成してください。

制約 (hard rule、 違反したら出力しないこと):
- 媒体名・記事 URL・hashtag・「ヨシラバーで整理しました」を含めない
- 未検証の数字・引用・順位・打率・防御率・OPS・本塁打数・打点・回数を含めない
- DB 照合できない数字は generalize する (例: 「打率.160」→「打率の数字」)
- 記事タイトルのコピー禁止、 独自の視点で書く
- 280 文字以内
- 巨人以外の球団選手の話題は除外
- 公開済み MLB の元巨人 OB (菅野・岡本等) は OK、 非元巨人 MLB は NG

トーン制約 (重要):
- 巨人ファンの自然な voice は OK: 連勝の喜び、 優勝争いへの期待、 特定選手への信頼、 悔しさ、 「噛み締める」 テンション、 ガチで凄い・とんでもない 等の素直な熱量、 内輪ネタ (栄冠は君に輝く 等) は自然に書いてよい
- 一方、 編集者が装ったファンっぽい煽り定型語は禁止: 「ついに」「我が軍」「連覇のピース」「待ち望んでいた」「物語がここから始まる」「その時が来た」「核心に迫る」「いよいよ」 は使わない
- 具体観点を 2〜3 個 厚く入れる (打撃の質、 守備位置の意味、 起用法、 対戦相手との相性、 数字の傾向、 直近の成績推移 等)。 1 軸だけの薄い post は避ける
- 結論を急がない。 観点を提示して読み手に考えさせる

時系列制約 (重要):
- Tavily snippet の日付を必ず確認する。 1 週間以上前 / 日付不明 / 復帰前提・開幕直後 など過去文脈の snippet では、 「ついに」「これから」「もうすぐ」「いよいよ」 等の未来形・直近形を使わない
- 古い snippet しか無い場合は、 一般的な傾向 / 過去の経緯 / 起用の文脈 として淡々と書く。 現在進行形・直近形で書かない
- 季節 / 開幕 / 復帰 等の文脈は snippet 日付と現在 ({today_jst}) の差を踏まえて慎重に扱う

時間帯トーン ({hour_jst} 時 JST):
{time_tone_hint}

出力形式: post 本文のみ。 説明や前置きは書かない。
"""


def _build_system_prompt(now_jst_hour: int, today_jst: str) -> str:
    if 5 <= now_jst_hour < 11:
        hint = (
            "- 朝なので落ち着いた分析調 + 静かな熱量で書く\n"
            "- 朝の落ち着きの中で観点を厚く提示する。 騒がしい表現は控える"
        )
    else:
        hint = (
            "- 昼以降なので試合・話題に応じてファンの自然な熱量で書いてよい\n"
            "- 喜び・悔しさ・期待・信頼 を素直に出してよいが、 cheerleading 定型語は禁止のまま\n"
            "- 観点の厚みは維持する。 熱量だけで観点が薄い post は避ける"
        )
    return _SYSTEM_PROMPT_BASE.format(
        hour_jst=now_jst_hour,
        today_jst=today_jst,
        time_tone_hint=hint,
    )


def _tavily_search(
    query: str,
    api_key: str,
    *,
    max_results: int = 3,
    timeout_seconds: int = 30,
    same_day_only: bool = True,
) -> list[dict]:
    """Tavily REST API 検索。

    成功時は result dict list を返す。 network / 4xx / 5xx / JSON parse 失敗
    時は空 list 返却 (caller は no context として skip 判断する)。

    same_day_only=True の場合、 published_date が JST 当日のものだけ残す
    (post-filter)。 当日 0 件なら caller は no context として silent skip する。
    """
    if not query or not api_key:
        return []
    try:
        import requests
        resp = requests.post(
            "https://api.tavily.com/search",
            json={
                "api_key": api_key,
                "query": query,
                "max_results": max_results,
                "search_depth": "basic",
                "topic": "news",
                "days": 1,
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


def _gemma_branding_safety_check(text: str) -> bool:
    """spec 382 hard rule gate for Gemma branding output.

    True = safe (pass). False = violation (caller drops the candidate)。
    """
    if not text or not text.strip():
        return False
    if len(text) > X_CHAR_LIMIT:
        return False
    for pattern in _GEMMA_BRANDING_FORBIDDEN_PATTERNS:
        if pattern.search(text):
            return False
    if not _is_safe_post_text(text):
        return False
    return True


def build_db_fact_line(
    player_canonical: str,
    db_path: str,
    *,
    target_date: Optional[str] = None,
    streak_window: int = 5,
) -> str:
    """``insight.db`` から today の試合 / player stat / 直近連勝 を 1 fact line に。

    Read-only SELECT only。 DB に該当 record が無ければ各 line を skip、
    全件無ければ空 string を返す (Gemma 側で「DB fact 注入: なし」 扱い)。

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
                "FROM games WHERE game_date = ? "
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

            if streak_window > 0:
                cur.execute(
                    "SELECT game_date, result FROM games "
                    "WHERE game_date <= ? AND result IN ('win', 'loss', 'draw') "
                    "ORDER BY game_date DESC LIMIT ?",
                    (today, streak_window),
                )
                recent = cur.fetchall()
                if recent:
                    marks = []
                    wins = losses = draws = 0
                    for _, r in recent:
                        rl = (r or "").lower()
                        if rl == "win":
                            marks.append("○")
                            wins += 1
                        elif rl == "loss":
                            marks.append("●")
                            losses += 1
                        else:
                            marks.append("△")
                            draws += 1
                    streak_parts = [f"直近{len(recent)}試合: " + "".join(marks)]
                    summary = []
                    if wins:
                        summary.append(f"{wins}勝")
                    if losses:
                        summary.append(f"{losses}敗")
                    if draws:
                        summary.append(f"{draws}分")
                    if summary:
                        streak_parts.append("(" + "".join(summary) + ")")
                    lines.append("- " + " ".join(streak_parts))
        finally:
            con.close()
    except Exception:
        return ""
    return "\n".join(lines)


def _format_tavily_context(results: list[dict], *, snippet_len: int = 300) -> str:
    lines = []
    for r in results:
        title = str(r.get("title") or "").strip()
        content = str(r.get("content") or "").strip()
        if not title and not content:
            continue
        lines.append(f"- {title}: {content[:snippet_len]}")
    return "\n".join(lines)


def build_gemma_branding_candidate(
    player_name: str,
    *,
    gemini_api_key: str,
    tavily_api_key: str,
    db_fact_line: str = "",
    max_tavily_results: int = 3,
    timeout_seconds: int = 30,
    model_id: str = _GEMMA_BRANDING_MODEL,
    temperature: float = 0.6,
    logger: Optional[_logging.Logger] = None,
) -> Optional[Candidate]:
    """Tavily REST 検索 + Gemma 4 31B 生成で 1 件の Candidate を返す。

    silent skip 条件 (``None`` 返却):
    - player_name 不正 / 巨人 roster 不一致
    - API key 不足
    - Tavily 失敗 (factual ground 無し → hallucination 抑制のため生成しない)
    - Gemma 失敗 (rate limit / network 等)
    - 空生成 / spec 382 hard rule 違反 (validator drop)
    """
    log = logger or _logging.getLogger("x_post_branding_gen")
    player = str(player_name or "").strip()
    if not player or not gemini_api_key or not tavily_api_key:
        log.info("gemma_branding_skip reason=missing_input player=%r", player)
        return None
    if not _is_verified_full_giants_player_name(player):
        log.info("gemma_branding_skip reason=not_verified_giants_player player=%r", player)
        return None

    # 1. Tavily 検索 (factual ground)
    query = f"巨人 {player} 最新"
    results = _tavily_search(
        query,
        tavily_api_key,
        max_results=max_tavily_results,
        timeout_seconds=timeout_seconds,
    )
    if not results:
        log.warning(
            "gemma_branding_skip reason=no_tavily_results query=%r player=%s",
            query,
            player,
        )
        return None
    context = _format_tavily_context(results)
    if not context:
        log.warning(
            "gemma_branding_skip reason=empty_tavily_context query=%r player=%s",
            query,
            player,
        )
        return None

    # 2. Gemma 4 生成 (時間帯 tone hint を含む system prompt)
    from datetime import datetime, timezone, timedelta
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst)
    system_prompt = _build_system_prompt(
        now_jst_hour=now_jst.hour,
        today_jst=now_jst.strftime("%Y-%m-%d"),
    )
    prompt = (
        f"{system_prompt}\n\n"
        f"対象選手: {player}\n\n"
        f"DB 照合済み数字 (使ってよい数字): {db_fact_line or 'なし'}\n\n"
        f"Tavily 検索結果 (context、 ここから不検証数字 / 引用 / 媒体名 / URL は使わない):\n"
        f"{context}\n\n"
        "上記情報を踏まえて、 独自の視点で X 投稿案を 1 件、 本文のみ書いてください。"
    )
    try:
        from google import genai
        client = genai.Client(api_key=gemini_api_key)
        response = client.models.generate_content(
            model=model_id,
            contents=prompt,
            config={"temperature": temperature},
        )
        text = (getattr(response, "text", None) or "").strip()
    except Exception as exc:  # noqa: BLE001 - silent skip is the fault-tolerance contract
        log.warning(
            "gemma_branding_skip reason=gemini_error player=%s err=%r",
            player,
            exc,
        )
        return None

    text = _finalize_post_text(text)

    # 3. spec 382 hard rule validator
    if not _gemma_branding_safety_check(text):
        log.warning(
            "gemma_branding_skip reason=safety_check_failed player=%s text_preview=%r",
            player,
            text[:60],
        )
        return None

    # 4. Candidate dataclass
    signature_hash = _hashlib.sha1(
        f"gemma_branding|{player}|{text[:80]}".encode("utf-8")
    ).hexdigest()[:16]
    draft_lines = [
        "【根拠: Gemma 4 + Tavily HTTP REST + 任意 DB 参照】",
        f"対象選手: {player}",
        f"検索 query: {query}",
        f"Tavily 結果数: {len(results)}",
        f"DB fact 注入: {'あり' if db_fact_line else 'なし'}",
        f"model: {model_id}",
        "",
        "【Tavily 検索結果 snippet】",
        context,
    ]
    if db_fact_line:
        draft_lines.extend(["", "【DB fact line】", db_fact_line])
    log.info(
        "gemma_branding_candidate_built player=%s tavily_results=%d text_len=%d",
        player,
        len(results),
        len(text),
    )
    return Candidate(
        title=f"Gemma 4 branding｜{player}",
        metric=_GEMMA_BRANDING_METRIC,
        period_label="LLM 生成",
        draft_text="\n".join(draft_lines),
        post_text=text,
        char_count=len(text),
        signature=f"gemma_branding|{signature_hash}|False|None",
        focus_player=player,
        source_material_type="gemma_branding",
    )
