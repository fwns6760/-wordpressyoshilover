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
    "起用", "スタメン", "打順", "代打", "守備", "継投", "先発", "ローテ",
)


def extract_rss_keywords(
    *,
    detect_player_fn: Callable[[str], str],
    fetch_fn: Optional[Callable[[str], str]] = None,
    handles: Optional[list[str]] = None,
    limit: int = 15,
    require_event: bool = True,
    max_age_hours: float = 0.0,
    now=None,
) -> list[dict]:
    """RSS(巨人系X)から {player, events, title} を抽出。 選手 + 出来事語の両方ある投稿のみ。

    ``require_event=False`` のとき、 出来事語ゲートを外し **巨人選手を含む投稿は全部** 拾う
    (default True で既存挙動=媒体見出し向け不変)。 ファンアカ (フーガ/缶詰) の反応文は
    「泉口！！！復活の一打！！！」 のように媒体見出し語を持たないため、 リプ候補化には
    選手検出のみで通す (巨人関連性は detect_player_fn + 後段 ``_is_giants`` で担保)。

    ``max_age_hours`` (2026-07-03 user「リプは相手の新しいポストに付けたい」):
    0 より大きい時、 pubDate がそれより古い item と pubDate 不明の item を落とし、
    handle 内は新しい順に並べる (handle 間の優先順は維持)。 0 (default) は従来挙動。
    """
    fetch = fetch_fn or _vr._default_fetch
    handles = handles or _MEDIA_HANDLES
    now_utc = None
    if max_age_hours > 0:
        from datetime import datetime as _dt, timezone as _tz
        now_utc = (now or _dt.now(_tz.utc)).astimezone(_tz.utc)
    out: list[dict] = []
    seen: set[tuple] = set()
    # 2026-07-07: handle 直列 fetch だと 16 handle × 未キャッシュ 22s で 6 分弱
    # かかり (旧 12s timeout では全滅)、リプ親ポストが取れなかった。並列 prefetch
    # (video_radar と同じ、失敗分 1 回再試行込み) へ。handle 間の優先順は維持。
    feed_urls = {h: f"{_vr._RSSHUB_BASE}/twitter/user/{h}?limit={limit}" for h in handles}
    fetched = _vr.prefetch_feeds(list(feed_urls.values()), fetch)
    for h in handles:
        xml = fetched.get(feed_urls[h])
        if not isinstance(xml, str):
            continue
        handle_out: list[dict] = []
        for item in _vr._extract_rss_items(xml):
            title = item.get("text", "")
            if not title:
                continue
            published_at = item.get("published_at")
            if now_utc is not None:
                if published_at is None:
                    continue  # 日付不明 = 古い可能性があるので安全側で除外
                try:
                    age_h = (now_utc - published_at).total_seconds() / 3600.0
                except (TypeError, ValueError):
                    continue
                if age_h > max_age_hours:
                    continue
            try:
                player = detect_player_fn(title) or ""
            except Exception:  # noqa: BLE001
                player = ""
            if not player:
                continue
            events = [e for e in _EVENT_WORDS if e in title]
            if require_event and not events:
                continue
            key = (player, tuple(events))
            if key in seen:
                continue
            seen.add(key)
            handle_out.append({
                "player": player,
                "events": events,
                "title": title,
                "url": item.get("url", ""),
                "handle": h,
                "published_at": published_at,
            })
        if now_utc is not None and len(handle_out) > 1:
            # 鮮度ゲート有効時は published_at 必須なので None は残っていない
            handle_out.sort(key=lambda kw: kw["published_at"], reverse=True)
        out.extend(handle_out)
    return out


def _normalize_name_for_dedupe(value: object) -> str:
    return _re.sub(r"\s+", "", str(value or "")).lower()


def headline_from_events(events: list[str], source_text: str = "") -> str:
    """出来事語 → キャッチーな見出し。 優先順で 1 つ。

    2026-06-11: 「初」+「勝利」等の token 袋合成が事実誤認を起こした
    (報知「古巣楽天と初対決 勝てば…12球団勝利」→「今季初勝利！」、田中将大は
    当時すでに今季3勝)。 複合 claim (初勝利/プロ初完封/初アーチ 等) は
    ``source_text`` に literal 連続語がある時だけ出す。 token 単独で安全な
    見出し (完封！/サヨナラ！/一発！ 等) は従来どおり。
    """
    e = set(events or [])
    s = source_text or ""
    if "完封" in e:
        return "プロ初完封！" if ("初完封" in s or "プロ初" in s) else "完封！"
    if "完投" in e:
        return "プロ初完投！" if ("初完投" in s or "プロ初" in s) else "完投！"
    if "サヨナラ" in e:
        return "サヨナラ！"
    if e & {"ホームラン", "本塁打", "アーチ", "一発", "号"}:
        if "復帰" in e and "復帰" in s:
            return "復帰即アーチ！"
        if _re.search(r"初(ホームラン|本塁打|アーチ)|[1１]号", s):
            return "初アーチ！"
        return "一発！"
    if "初勝利" in s:
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
    if e & {"起用", "スタメン", "打順", "代打", "守備", "継投", "先発", "ローテ"}:
        return "起用の話題！"
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
        headline = headline_from_events(events, kw.get("title", ""))
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


def _caption_for(db_path: str, player: str, events: list, source_text: str = "") -> Optional[str]:
    """player + events → ヨシラバー声のコメント+データ 1 行 (quote/reply 共通)。"""
    headline = headline_from_events(events, source_text)
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
    if stem == "注目":
        # 出来事が確定できない時は見出し語を入れず、 数字だけで返す (誤認防止)
        return f"{player}、{data}。"
    return f"{player}、{stem}…！{data}。"


def _pick_variant(pool: list[str], player: str, parent_text: str) -> str:
    """投稿ごとに決定的 (再現可能) に文案プールから 1 つ選ぶ。

    2026-06-11 user「同じような文章が多い。AIっぽい」: 固定テンプレ 1 本/分岐
    だと毎便同じ語尾が並ぶため、 分岐ごとに 4 案のプールを hash 選択で回す。
    乱数は使わない (同じ親投稿には常に同じ文 = テスト可能・dedup 安定)。
    """
    import hashlib as _hashlib
    digest = _hashlib.md5(f"{player}|{parent_text}".encode("utf-8")).hexdigest()
    return pool[int(digest, 16) % len(pool)]


def _yoshilover_reply_fallback(db_path: str, player: str, events: list, parent_text: str) -> str:
    """LLM を使わず、報知リプ向けの短いヨシラバー風返信文を作る。

    返信欄で読まれる前提なので、URL / hashtag / 媒体名を本文に入れず、
    「事実の反応 + 断定の読み」に絞る。 様子見ヘッジ (「見方が分かれそう」
    「〜見たいです」連発) は AI 臭の元なので使わない (2026-06-11 user 指摘)。
    """
    haystack = f"{parent_text or ''} {' '.join(str(e) for e in events or [])}"
    fact = (_caption_for(db_path, player, events, parent_text) or "").strip().rstrip("。")
    headline = headline_from_events(events, parent_text).rstrip("！!")
    if any(t in haystack for t in ("起用", "スタメン", "打順", "代打", "守備", "継投", "捕手", "先発", "ローテ")):
        text = _pick_variant([
            f"{player}のこの起用、ハマればデカいと思うんよな。\n一回きりで終わらせず固定で見たい。",
            f"{player}のこの起用は賛成。流れを変えられる側の選手。",
            f"{player}をここで使う采配、嫌いじゃない。\n結果が出たら一気に固定だろうな。",
            f"{player}起用の意図ははっきりしてる。あとは本人が応えるかどうか。",
        ], player, parent_text)
    elif any(t in haystack for t in ("若手", "昇格", "一軍", "2軍", "２軍", "二軍", "ファーム", "育成")):
        text = _pick_variant([
            f"{player}、ここからどれだけ出番を掴むか。\n一試合の結果より使われ方に注目してる。",
            f"{player}の名前が挙がるの、補強より効くパターンある。",
            f"{player}、こういう時に名前が出る若手は強い。掴んでこい。",
            f"{player}、ここは数字で黙らせる番。",
        ], player, parent_text)
    elif any(t in haystack for t in ("復帰", "復活", "再合流", "実戦復帰")):
        text = _pick_variant([
            f"{player}、まず戻ってきたのがデカい。",
            f"{player}の復帰でベンチの空気が変わる。\nここからどこまで戻すか。",
            f"{player}、待ってた。居るだけで相手の警戒が変わる。",
            f"{player}、復帰即結果なら一気に流れが来る。",
        ], player, parent_text)
    elif any(t in haystack for t in ("完投", "完封", "好投", "無失点", "奪三振", "勝利")) and fact:
        text = _pick_variant([
            f"{fact}。\n数字は嘘をつかない。次の登板も軸はこの人。",
            f"{fact}。\nこの数字に文句を言える人はいない。",
            f"{fact}。\n先発の柱って、こういう数字のことを言う。",
            f"{fact}。\nローテの軸。異論は認めない。",
        ], player, parent_text)
    elif any(t in haystack for t in ("ホームラン", "本塁打", "アーチ", "一発", "サヨナラ", "タイムリー", "適時", "猛打賞")) and fact:
        text = _pick_variant([
            f"{fact}。\n次の打席も同じ形でいける。",
            f"{fact}。\nこの数字は本物。相手バッテリーは嫌だろうな。",
            f"{fact}。\n勝負どころで回ってくるのが楽しみになってきた。",
            f"{fact}。\nいま一番バットが振れてる。",
        ], player, parent_text)
    elif headline and headline != "注目":
        text = _pick_variant([
            f"{player}の{headline}、流れを変える一手になる。",
            f"{player}の{headline}、これは効く。\n次の試合の入りが変わる。",
            f"{player}の{headline}、いま数字で追うと一番面白い。",
            f"{player}の{headline}。こういう日を待ってた。",
        ], player, parent_text)
    else:
        text = _pick_variant([
            f"{player}、ここで名前が出るのは偶然じゃない。",
            f"{player}の話題、数字で追うと面白い局面に入ってる。",
            f"{player}、流れを持ってる選手の動きは追っておきたい。",
            f"{player}、ここからの数字に注目してる。",
        ], player, parent_text)
    # 返信本文には親投稿 URL / hashtag / 媒体名を混ぜない。
    for ng in ("http", "#", "@", "報知", "スポーツ報知"):
        if ng in text:
            return ""
    # 親投稿の数字を広げないため、 fallback は 2 行・180 字以内に収める。
    if len(text) <= 180:
        return text.strip()
    return text[:179].rstrip("、。 \n") + "…"


def build_reply_candidates(
    db_path: str,
    *,
    fetch_fn: Optional[Callable[[str], str]] = None,
    max_replies: int = 5,
    detect_player_fn: Optional[Callable[[str], str]] = None,
    comment_fn: Optional[Callable[[str, str], str]] = None,
    handles: Optional[list[str]] = None,
    require_event: bool = True,
    skip_on_empty_comment: bool = False,
    avoid_player_names: Optional[set[str]] = None,
    max_age_hours: float = 0.0,
) -> list[dict]:
    """大手巨人アカ投稿への『リプライ候補』。 ヨシラバーボイスのリプ文 + 大手投稿URL/tweet_id。

    user が大手投稿にリプ → 大手の客層に露出 (小規模アカウントのインプ近道)。 巨人選手限定。

    インプ原理 ③ (順位燃料): 公式/報知の返信欄は数百件で溢れるため、 数字の羅列リプは
    埋もれてインプを borrow できない。 ``comment_fn(parent_tweet_text, player)`` を渡すと
    親ツイートに「データ気づき + 辛口読み」を足したヨシラバーボイスのリプ文を生成し、
    いいねで上位に浮かせる。 comment_fn 無し / 生成失敗時は deterministic なヨシラバー風
    短文 reply へ fallback。

    ``require_event=False``: 出来事語ゲートを外す (ファンアカ フーガ/缶詰 のカジュアル反応文用)。
    ``skip_on_empty_comment=True``: comment_fn (LLM voice) が空/門番落ちした投稿は
    deterministic テンプレ fallback を使わず候補ごとスキップ (空虚な同調リプを送らない)。
    ``avoid_player_names``: 正規化済み/未正規化どちらでも可。直近便に出た選手を
    Gemini comment_fn 実行前に除外し、試合中15分便の重複と無駄な LLM 呼び出しを抑える。
    Returns [{player, reply, url, tweet_id, headline}]。
    """
    import re as _re2
    avoid_players = {
        _normalize_name_for_dedupe(name)
        for name in (avoid_player_names or set())
        if _normalize_name_for_dedupe(name)
    }
    if detect_player_fn is None:
        from src.x_post_mail_lane import detect_giants_player_name, _load_giants_player_aliases
        _am = _load_giants_player_aliases()

        def detect_player_fn(t: str) -> str:  # noqa: E731
            return detect_giants_player_name(t, alias_map=_am)

    kws = extract_rss_keywords(
        detect_player_fn=detect_player_fn,
        fetch_fn=fetch_fn,
        handles=handles,
        require_event=require_event,
        # 2026-07-03 user「リプは相手の新しいポストに付けたい」: 古い親ポストへの
        # リプは返信欄でも埋もれる。鮮度ゲート + handle 内新しい順。
        max_age_hours=max_age_hours,
    )
    out: list[dict] = []
    used: set[str] = set()
    for kw in kws:
        if len(out) >= max_replies:
            break
        player, events, url = kw["player"], kw["events"], kw.get("url", "")
        title = kw.get("title", "")
        if _normalize_name_for_dedupe(player) in avoid_players:
            continue
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
        if not reply and not skip_on_empty_comment:
            reply = _yoshilover_reply_fallback(db_path, player, events, title)
        if not reply:
            continue
        used.add(player)
        out.append({
            "player": player, "reply": reply, "url": url,
            "tweet_id": m.group(1), "headline": headline_from_events(events, title),
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
        headline = headline_from_events(events, kw.get("title", ""))
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
