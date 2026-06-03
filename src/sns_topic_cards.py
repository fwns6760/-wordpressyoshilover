"""451/SNS: RSS/Xバズの「今日の話題キーワード」→ 該当カード型を自動選択 → カードHTML生成。

flow: RSS(巨人系X media)→ (選手, 出来事) キーワード抽出 → カード型ルーティング →
insight.db データ充填 → sns_card テンプレで HTML。 描画(PNG)は別 (sns_card と同様 HTML まで)。

X API 不使用 (自前 RSSHub)。 Gemini 不使用 (ルーティングは keyword)。
"""
from __future__ import annotations

import re as _re
import sqlite3 as _sqlite3
from typing import Callable, Optional

from src import sns_card as _card
from src import video_radar as _vr  # RSSHub fetch + item 抽出を再利用

# 巨人系 media / 公式 X (RSSHub handle)。 sns_realtime_topic と同じ系。
# 旧 yomiuri_giants は RSSHub 死にハンドルのため除外 (実feed検証済 2026-06-01、 公式= TokyoGiants)。
# リプ先の優先度 = 親ツイートの閲覧が多い順 (公式 → 報知 → サンスポ)。
# extract_rss_keywords はこの順で走査し、 build_reply_candidates は先頭から採るので
# でかいアカの返信欄を優先して borrow する (インプ原理 ①: 親の大きさ)。
_MEDIA_HANDLES = ["yomiuri_giants", "TokyoGiants", "hochi_giants", "Sanspo_Giants"]

# 出来事キーワード (検出対象)
_EVENT_WORDS = (
    "完投", "完封", "ホームラン", "本塁打", "アーチ", "一発", "サヨナラ", "猛打賞",
    "タイムリー", "適時", "好投", "無失点", "奪三振", "ファインプレー", "好守",
    "初", "プロ初", "昇格", "復帰", "勝利", "連勝", "二軍", "ファーム", "誕生日", "号",
)


def extract_rss_keywords(
    *,
    detect_player_fn: Callable[[str], str],
    fetch_fn: Optional[Callable[[str], str]] = None,
    handles: Optional[list[str]] = None,
    limit: int = 15,
) -> list[dict]:
    """RSS(巨人系X)から {player, events, title} を抽出。 選手 + 出来事語の両方ある投稿のみ。"""
    fetch = fetch_fn or _vr._default_fetch
    handles = handles or _MEDIA_HANDLES
    out: list[dict] = []
    seen: set[tuple] = set()
    for h in handles:
        try:
            xml = fetch(f"{_vr._RSSHUB_BASE}/twitter/user/{h}?limit={limit}")
        except Exception:  # noqa: BLE001
            continue
        for item in _vr._extract_rss_items(xml):
            title = item.get("text", "")
            if not title:
                continue
            try:
                player = detect_player_fn(title) or ""
            except Exception:  # noqa: BLE001
                player = ""
            if not player:
                continue
            events = [e for e in _EVENT_WORDS if e in title]
            if not events:
                continue
            key = (player, tuple(events))
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "player": player,
                "events": events,
                "title": title,
                "url": item.get("url", ""),
                "handle": h,
            })
    return out


def headline_from_events(events: list[str]) -> str:
    """出来事語 → キャッチーな見出し。 優先順で 1 つ。"""
    e = set(events or [])
    if "完封" in e:
        return "プロ初完封！" if "初" in e else "完封！"
    if "完投" in e:
        return "プロ初完投！" if ("初" in e or "プロ初" in e) else "完投！"
    if "サヨナラ" in e:
        return "サヨナラ！"
    if e & {"ホームラン", "本塁打", "アーチ", "一発", "号"}:
        if "復帰" in e:
            return "復帰即アーチ！"
        if "初" in e:
            return "初アーチ！"
        return "一発！"
    if "勝利" in e and "初" in e:
        return "今季初勝利！"
    if e & {"好投", "無失点", "奪三振"}:
        return "好投！"
    if e & {"猛打賞", "タイムリー", "適時"}:
        return "勝負強打！"
    if "復帰" in e:
        return "実戦復帰！"
    if "昇格" in e:
        return "一軍昇格！"
    if e & {"二軍", "ファーム"}:
        return "ファームで躍動！"
    return "注目！"


def _player_batting(db_path: str, name: str) -> Optional[dict]:
    with _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        r = conn.execute(
            "SELECT COALESCE(SUM(AB),0), COALESCE(SUM(H),0), COALESCE(SUM(RBI),0), COUNT(DISTINCT game_id) "
            "FROM batting_logs WHERE player_canonical=?", (name,),
        ).fetchone()
    if not r or int(r[0]) <= 0:
        return None
    ab, h, rbi, g = int(r[0]), int(r[1]), int(r[2]), int(r[3])
    return {"ab": ab, "h": h, "rbi": rbi, "games": g, "avg": (h / ab) if ab else None}


def _player_pitching(db_path: str, name: str) -> Optional[dict]:
    with _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
        r = conn.execute(
            "SELECT COUNT(*), "
            "SUM(CASE WHEN result_mark='○' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN result_mark='●' THEN 1 ELSE 0 END), "
            "COALESCE(SUM(K),0), COALESCE(SUM(IP),0.0), COALESCE(SUM(ER),0) "
            "FROM pitching_logs WHERE player_canonical=?", (name,),
        ).fetchone()
    if not r or int(r[0]) <= 0:
        return None
    g, w, l, k, ip, er = int(r[0]), int(r[1] or 0), int(r[2] or 0), int(r[3]), float(r[4]), int(r[5])
    era = (er * 9.0 / ip) if ip > 0 else None
    return {"games": g, "w": w, "l": l, "k": k, "ip": ip, "er": er, "era": era}


def _is_giants(db_path: str, name: str) -> bool:
    """insight.db で team_name='巨人' として実在する選手か (NER 誤検出=他球団を除外)。"""
    try:
        with _sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            for tbl in ("batting_logs", "pitching_logs"):
                r = conn.execute(
                    f"SELECT 1 FROM {tbl} WHERE player_canonical=? AND team_name='巨人' LIMIT 1",
                    (name,),
                ).fetchone()
                if r:
                    return True
    except Exception:  # noqa: BLE001
        return False
    return False


def build_quote_captions(
    db_path: str,
    *,
    fetch_fn: Optional[Callable[[str], str]] = None,
    max_captions: int = 5,
    detect_player_fn: Optional[Callable[[str], str]] = None,
) -> list[dict]:
    """今日の『動画引用キャプション』(ヨシラバーコメント + データ) を返す。

    user が X で動画を長押し引用する時に貼るテキスト。 RSS の出来事キーワードで選手を拾い、
    **巨人選手に限定** (NER 誤検出=他球団を除外) し、 insight.db の今季実数字を 1 行足す。
    Returns [{player, headline, caption}]。 描画/画像 不要 (テキストのみ)。
    """
    if detect_player_fn is None:
        from src.x_post_mail_lane import detect_giants_player_name, _load_giants_player_aliases
        _am = _load_giants_player_aliases()

        def detect_player_fn(t: str) -> str:  # noqa: E731
            return detect_giants_player_name(t, alias_map=_am)

    kws = extract_rss_keywords(detect_player_fn=detect_player_fn, fetch_fn=fetch_fn)
    out: list[dict] = []
    used: set[str] = set()
    for kw in kws:
        if len(out) >= max_captions:
            break
        player, events = kw["player"], kw["events"]
        if player in used or not _is_giants(db_path, player):
            continue
        headline = headline_from_events(events)
        stem = headline.rstrip("！!")
        pit = _player_pitching(db_path, player)
        bat = _player_batting(db_path, player)
        is_pitcher = bool(
            pit and (not bat or any(w in events for w in ("完投", "完封", "好投", "奪三振", "勝利")))
        )
        if is_pitcher and pit:
            era = f"・防御率{pit['era']:.2f}" if pit["era"] is not None else ""
            data = f"今季{pit['games']}登板{era}・{pit['k']}K"
        elif bat and bat["avg"] is not None:
            avg = f"{bat['avg']:.3f}".lstrip("0")
            data = f"今季打率{avg}・{bat['h']}安打{bat['rbi']}打点"
        else:
            continue
        used.add(player)
        out.append({
            "player": player,
            "headline": headline,
            "caption": f"{player}、{stem}…！{data}。",
        })
    return out


def _caption_for(db_path: str, player: str, events: list) -> Optional[str]:
    """player + events → ヨシラバー声のコメント+データ 1 行 (quote/reply 共通)。"""
    headline = headline_from_events(events)
    stem = headline.rstrip("！!")
    pit = _player_pitching(db_path, player)
    bat = _player_batting(db_path, player)
    is_pitcher = bool(pit and (not bat or any(w in events for w in ("完投", "完封", "好投", "奪三振", "勝利"))))
    if is_pitcher and pit:
        era = f"・防御率{pit['era']:.2f}" if pit["era"] is not None else ""
        data = f"今季{pit['games']}登板{era}・{pit['k']}K"
    elif bat and bat["avg"] is not None:
        avg = f"{bat['avg']:.3f}".lstrip("0")
        data = f"今季打率{avg}・{bat['h']}安打{bat['rbi']}打点"
    else:
        return None
    return f"{player}、{stem}…！{data}。"


def _yoshilover_reply_fallback(db_path: str, player: str, events: list, parent_text: str) -> str:
    """LLM を使わず、報知リプ向けの短いヨシラバー風返信文を作る。

    返信欄で読まれる前提なので、URL / hashtag / 媒体名を本文に入れず、
    「事実の反応 + 次に見るポイント」に絞る。
    """
    fact = (_caption_for(db_path, player, events) or "").strip()
    if fact:
        stem = fact.rstrip("。")
        text = (
            f"{stem}。\n"
            "ここは結果だけでなく、次にどう任されるかまで見たいですね。"
        )
    else:
        headline = headline_from_events(events).rstrip("！!")
        if headline and headline != "注目":
            text = (
                f"{player}の{headline}、ここは流れを変える材料として見たいです。\n"
                "次の場面で同じ形を出せるかまで追いたいですね。"
            )
        else:
            text = (
                f"{player}のこの話題、結果だけでなく立ち位置まで含めて見たいです。\n"
                "次の出番でどうつながるかですね。"
            )
    # 返信本文には親投稿 URL / hashtag / 媒体名を混ぜない。
    for ng in ("http", "#", "@", "報知", "スポーツ報知"):
        if ng in text:
            return ""
    # 親投稿の数字を広げないため、 fallback は 2 行・280 字以内に収める。
    if len(text) <= 279:
        return text.strip()
    return text[:279].rstrip("、。 \n") + "…"


def build_reply_candidates(
    db_path: str,
    *,
    fetch_fn: Optional[Callable[[str], str]] = None,
    max_replies: int = 5,
    detect_player_fn: Optional[Callable[[str], str]] = None,
    comment_fn: Optional[Callable[[str, str], str]] = None,
    handles: Optional[list[str]] = None,
) -> list[dict]:
    """大手巨人アカ投稿への『リプライ候補』。 ヨシラバーボイスのリプ文 + 大手投稿URL/tweet_id。

    user が大手投稿にリプ → 大手の客層に露出 (小規模アカウントのインプ近道)。 巨人選手限定。

    インプ原理 ③ (順位燃料): 公式/報知の返信欄は数百件で溢れるため、 数字の羅列リプは
    埋もれてインプを borrow できない。 ``comment_fn(parent_tweet_text, player)`` を渡すと
    親ツイートに「データ気づき + 辛口読み」を足したヨシラバーボイスのリプ文を生成し、
    いいねで上位に浮かせる。 comment_fn 無し / 生成失敗時は _caption_for の数字 1 行へ fallback。
    Returns [{player, reply, url, tweet_id, headline}]。
    """
    import re as _re2
    if detect_player_fn is None:
        from src.x_post_mail_lane import detect_giants_player_name, _load_giants_player_aliases
        _am = _load_giants_player_aliases()

        def detect_player_fn(t: str) -> str:  # noqa: E731
            return detect_giants_player_name(t, alias_map=_am)

    kws = extract_rss_keywords(
        detect_player_fn=detect_player_fn,
        fetch_fn=fetch_fn,
        handles=handles,
    )
    out: list[dict] = []
    used: set[str] = set()
    for kw in kws:
        if len(out) >= max_replies:
            break
        player, events, url = kw["player"], kw["events"], kw.get("url", "")
        title = kw.get("title", "")
        if player in used or not url or not _is_giants(db_path, player):
            continue
        m = _re2.search(r"/status/(\d+)", url)
        if not m:
            continue
        # ③ 順位燃料: まずヨシラバーボイスでリプ文を生成。 失敗時は数字 1 行へ fallback。
        reply = ""
        if comment_fn is not None and title:
            try:
                reply = (comment_fn(title, player) or "").strip()
            except Exception:  # noqa: BLE001
                reply = ""
        if not reply:
            reply = _yoshilover_reply_fallback(db_path, player, events, title)
        if not reply:
            continue
        used.add(player)
        out.append({
            "player": player, "reply": reply, "url": url,
            "tweet_id": m.group(1), "headline": headline_from_events(events),
            "handle": kw.get("handle", ""),
        })
    return out


def build_topic_cards(
    db_path: str,
    *,
    fetch_fn: Optional[Callable[[str], str]] = None,
    max_cards: int = 3,
    detect_player_fn: Optional[Callable[[str], str]] = None,
) -> list[dict]:
    """今日の話題カードを生成。 Returns [{player, kind, headline, html, title}]。

    RSS キーワード → 投手なら投手カード / それ以外は選手カード、 見出しに出来事を反映。
    """
    if detect_player_fn is None:
        from src.x_post_mail_lane import detect_giants_player_name, _load_giants_player_aliases
        _am = _load_giants_player_aliases()

        def detect_player_fn(t: str) -> str:  # noqa: E731
            return detect_giants_player_name(t, alias_map=_am)

    kws = extract_rss_keywords(detect_player_fn=detect_player_fn, fetch_fn=fetch_fn)
    out: list[dict] = []
    used: set[str] = set()
    for kw in kws:
        if len(out) >= max_cards:
            break
        player, events = kw["player"], kw["events"]
        if player in used:
            continue
        headline = headline_from_events(events)
        pit = _player_pitching(db_path, player)
        bat = _player_batting(db_path, player)
        is_pitcher = bool(pit and (not bat or pit["games"] >= 1 and ("完投" in events or "好投" in events or "奪三振" in events or "勝利" in events or "登板" in events)))
        if is_pitcher and pit:
            html = _card.render_pitcher_card_html(
                name=player, headline=headline, era=pit["era"], wins=pit["w"],
                losses=pit["l"], k=pit["k"], ip=pit["ip"], games=pit["games"],
                point_line=f"今日の話題: {kw['title'][:42]}",
            )
            kind = "pitcher"
        elif bat:
            html = _card.render_player_card_html(
                name=player, season_avg=bat["avg"], hits=bat["h"], rbi=bat["rbi"],
                games=bat["games"], point_line=headline,
            )
            kind = "batting"
        else:
            continue
        used.add(player)
        out.append({"player": player, "kind": kind, "headline": headline, "html": html, "title": kw["title"]})
    return out
