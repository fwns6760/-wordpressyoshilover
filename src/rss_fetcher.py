"""
rss_fetcher.py — RSSHub経由でXアカウント投稿を自動取得してWP下書き生成

使用例:
    python3 src/rss_fetcher.py --dry-run   # 取得確認のみ（WP投稿しない）
    python3 src/rss_fetcher.py             # 実行（WP下書き生成）
"""

import sys
import os
import json
import logging
import argparse
import subprocess
from collections import Counter
from datetime import datetime, timezone, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

# vendorディレクトリをパスに追加（サーバー環境用）
ROOT = Path(__file__).parent.parent
_vendor = str(ROOT / 'vendor')
if os.path.isdir(_vendor) and _vendor not in sys.path:
    sys.path.insert(0, _vendor)
sys.path.insert(0, str(Path(__file__).parent))

import feedparser
import re as _re
import html as _html
from html.parser import HTMLParser

from article_parts_renderer import ArticleParts, render_postgame
from body_validator import validate_body_candidate as _validate_body_candidate
from body_validator import is_supported_subtype as _body_validator_supports_subtype
from fact_conflict_guard import (
    detect_game_result_conflict as _detect_game_result_conflict,
    detect_no_game_but_result as _detect_no_game_but_result,
    detect_title_body_entity_mismatch as _detect_title_body_entity_mismatch,
)
from title_player_name_backfiller import backfill_title_player_name
from title_validator import build_reroll_title as _build_title_reroll_title
from title_validator import is_non_name_speaker_label
from title_validator import is_weak_generated_title
from title_validator import is_weak_subject_title
from title_validator import title_has_person_name_candidate
from title_validator import validate_title_candidate as _validate_title_candidate
from title_validator import is_supported_subtype as _title_validator_supports_subtype
from wp_client import WPClient
from media_xpost_selector import evaluate_media_quote_selection
from wp_draft_creator import build_oembed_block, load_posted_urls, save_posted_url
from x_post_generator import (
    build_post as build_x_post_text,
    build_post_with_meta as build_x_post_text_with_meta,
    resolve_effective_x_post_ai_mode,
)
from src.source_trust import (
    classify_url as _source_trust_classify_url,
    classify_handle as _source_trust_classify_handle,
    classify_url_family as _source_trust_classify_url_family,
    get_family_trust_level as _source_trust_get_family_trust_level,
)
from src.source_id import source_id as _source_id_key
from src.tag_category_guard import validate_tags as _tc_validate_tags, validate_category as _tc_validate_category
from src.postgame_strict_template import (
    is_strict_enabled as _postgame_strict_enabled,
    POSTGAME_STRICT_PROMPT as _postgame_strict_prompt,
    parse_postgame_strict_json as _postgame_strict_parse,
    validate_postgame_strict_payload as _postgame_strict_validate,
    has_sufficient_for_render as _postgame_strict_has_sufficient_for_render,
    render_postgame_strict_body as _postgame_strict_render,
)
from src.gemini_cache import (
    DEFAULT_MODEL_NAME as GEMINI_CACHE_MODEL_NAME,
    GeminiCacheBackendError,
    GeminiCacheKey,
    GeminiCacheManager,
    GeminiCacheValue,
    compute_content_hash as _compute_gemini_content_hash,
)


TRUE_VALUES = {"1", "true", "yes", "on"}
HTTP_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
DEFAULT_LOW_COST_AI_CATEGORIES = {"試合速報", "選手情報", "首脳陣"}
DEFAULT_AUTO_TWEET_CATEGORIES = {"試合速報", "選手情報", "首脳陣", "ドラフト・育成"}
AUTO_POST_CATEGORY_ID = 673
DRAFT_CATEGORY_FALLBACK_NAME = "コラム"
PUBLISH_SUBTYPE_ENV_MAP = {
    "postgame": "ENABLE_PUBLISH_FOR_POSTGAME",
    "lineup": "ENABLE_PUBLISH_FOR_LINEUP",
    "manager": "ENABLE_PUBLISH_FOR_MANAGER",
    "notice": "ENABLE_PUBLISH_FOR_NOTICE",
    "pregame": "ENABLE_PUBLISH_FOR_PREGAME",
    "recovery": "ENABLE_PUBLISH_FOR_RECOVERY",
    "farm": "ENABLE_PUBLISH_FOR_FARM",
    "farm_lineup": "ENABLE_PUBLISH_FOR_FARM",
    "social": "ENABLE_PUBLISH_FOR_SOCIAL",
    "player": "ENABLE_PUBLISH_FOR_PLAYER",
    "general": "ENABLE_PUBLISH_FOR_GENERAL",
    "game_note": "ENABLE_PUBLISH_FOR_GENERAL",
    "roster": "ENABLE_PUBLISH_FOR_GENERAL",
}
X_POST_SUBTYPE_ENV_MAP = {
    "postgame": "ENABLE_X_POST_FOR_POSTGAME",
    "lineup": "ENABLE_X_POST_FOR_LINEUP",
    "manager": "ENABLE_X_POST_FOR_MANAGER",
    "notice": "ENABLE_X_POST_FOR_NOTICE",
    "pregame": "ENABLE_X_POST_FOR_PREGAME",
    "recovery": "ENABLE_X_POST_FOR_RECOVERY",
    "farm": "ENABLE_X_POST_FOR_FARM",
    "farm_lineup": "ENABLE_X_POST_FOR_FARM",
    "social": "ENABLE_X_POST_FOR_SOCIAL",
    "player": "ENABLE_X_POST_FOR_PLAYER",
    "general": "ENABLE_X_POST_FOR_GENERAL",
    "game_note": "ENABLE_X_POST_FOR_GENERAL",
    "roster": "ENABLE_X_POST_FOR_GENERAL",
}
JST = timezone(timedelta(hours=9))
ENABLE_LIVE_UPDATE_ARTICLES = os.getenv("ENABLE_LIVE_UPDATE_ARTICLES", "0").strip().lower() in TRUE_VALUES
SCORE_TOKEN_RE = _re.compile(r"\d{1,2}\s*[－\-–]\s*\d{1,2}")
NUMERIC_TOKEN_RE = _re.compile(r"\d+(?:\.\d+)?(?:[%％]|本|打点|勝|敗|回|失点|奪三振|号|位|年|月|日|人|円|試合|打席|安打|点|本塁打|打率|防御率|OPS|WHIP|WAR|wRC\+?|K/9)?")
SCORE_VS_TOKEN_RE = _re.compile(r"\d{1,2}\s*対\s*\d{1,2}")
DATE_JP_TOKEN_RE = _re.compile(r"(?:\d{4}年)?\d{1,2}月\d{1,2}日")
DATE_SLASH_TOKEN_RE = _re.compile(r"(?:\d{4}/)?\d{1,2}/\d{1,2}")
TIME_TOKEN_RE = _re.compile(r"\d{1,2}:\d{2}")
RECORD_TOKEN_RE = _re.compile(r"\d+勝\d+敗(?:\d+分)?")
LABELED_DECIMAL_TOKEN_RE = _re.compile(r"(?:打率|防御率|出塁率|長打率|OPS|WHIP|WAR|wRC\+?|K/9)\s*[.:：・]?\s*\d+\.\d+")
LEADING_DECIMAL_TOKEN_RE = _re.compile(r"(?<!\d)\.\d{2,3}")
STRUCTURED_NUMBER_TOKEN_RES = (
    DATE_JP_TOKEN_RE,
    DATE_SLASH_TOKEN_RE,
    TIME_TOKEN_RE,
    SCORE_TOKEN_RE,
    SCORE_VS_TOKEN_RE,
    RECORD_TOKEN_RE,
    LABELED_DECIMAL_TOKEN_RE,
    LEADING_DECIMAL_TOKEN_RE,
)
NON_GAME_RESULT_WORDS = ("勝利", "敗戦", "白星", "黒星", "引き分け", "サヨナラ勝", "連勝", "連敗", "スコア")
RESULT_MILESTONE_RE = _re.compile(r"(?:(?:今季|通算|日米通算)\d+勝目|\d+勝目|初勝利|勝ち星|敗戦投手)")
FAKE_CITATION_MARKERS = ("npb.jp", "スポーツナビ", "1point02.jp", "Baseball Reference", "baseball.yahoo.co.jp")
GAME_ARTICLE_KEYWORDS = ("試合結果", "スタメン", "先発", "登板", "白星", "黒星", "勝利", "敗戦", "引き分け", "サヨナラ", "試合")
LINEUP_ARTICLE_KEYWORDS = ("スタメン", "スターティングメンバー", "オーダー", "打順", "1番", "2番", "3番", "4番")
LINEUP_CORE_KEYWORDS = ("スタメン", "スターティングメンバー", "オーダー")
FARM_LINEUP_MARKERS = ("二軍", "2軍", "ファーム", "イースタン", "三軍")
LIVE_UPDATE_KEYWORDS = ("途中経過", "試合中", "回表", "回裏", "勝ち越し", "同点", "逆転")
LIVE_UPDATE_FRAGMENT_KEYWORDS = LIVE_UPDATE_KEYWORDS + ("継投", "満塁", "3者凡退", "サイクル", "サイクル安打", "王手")
LINEUP_ORDER_SLOT_RE = _re.compile(r"(?<![0-9０-９])[1-9１-９]番(?!手)")
LIVE_UPDATE_PITCHER_ORDER_RE = _re.compile(r"(?<![0-9０-９])[2-9２-９]番手")
LIVE_UPDATE_INNING_RE = _re.compile(r"(?<![0-9０-９])(?:[1-9]|1\d|[１-９])回(?:表|裏|終了|途中|で)?")
NPB_TEAM_MARKERS = (
    "巨人",
    "読売ジャイアンツ",
    "阪神",
    "中日",
    "広島",
    "DeNA",
    "ヤクルト",
    "ソフトバンク",
    "日本ハム",
    "ロッテ",
    "楽天",
    "オリックス",
    "西武",
)
GIANTS_YAHOO_TEAM_ID = 1
STRICT_PROMPT_SUMMARY_MAX_CHARS = 800
DEFAULT_PROMPT_SUMMARY_MAX_CHARS = 400
STRICT_PROMPT_MAX_SOURCE_FACTS = 8
STRICT_PROMPT_MAX_QUOTES = 2
THIN_SOURCE_FACT_BLOCK_MIN_CHARS_DEFAULT = 100
THIN_SOURCE_FACT_BLOCK_MIN_CHARS_SOCIAL_NEWS = 40
RSS_DUPLICATE_COOLDOWN_HOURS_DEFAULT = 6
GEMINI_CACHE_COOLDOWN_HOURS_DEFAULT = 24
GEMINI_CACHE_COOLDOWN_HOURS_ENV = "GEMINI_CACHE_COOLDOWN_HOURS"
GEMINI_POSTGAME_STRICT_SLOTFILL_TEMPLATE_ID = "postgame_strict_slotfill_v1"
GEMINI_POSTGAME_PARTS_TEMPLATE_ID = "postgame_article_parts_v1"
GEMINI_STRICT_PROMPT_TEMPLATE_VERSION = "v1"
PUBLISH_QUALITY_MIN_CHARS_BY_SUBTYPE = {
    "postgame": 280,
    "lineup": 280,
    "manager": 350,
    "pregame": 350,
    "farm": 350,
    "farm_lineup": 350,
}
PUBLISH_QUALITY_DEFAULT_MIN_CHARS = 350
PUBLISH_QUALITY_LEAK_MARKERS = (
    "があれば必ず整理する",
    "を押さえておきたい話題です",
    "の要点を、まず押さえておきたい",
    "試合前後の流れ、スタメン、先発、スコアなど",
    "どうつながるかが見どころです",
)
LIVE_UPDATE_LINEUP_TITLE_PREFIX = "巨人スタメン"
LIVE_UPDATE_LINEUP_HEADING_KEYWORDS = ("打順", "スタメン", "先発メンバー")
CORE_SUBTYPES = ("pregame", "live_anchor", "postgame", "fact_notice", "farm")
NON_LINEUP_STARMEN_GUARD_SUBTYPES = {
    "pregame",
    "postgame",
    "farm",
    "live_update",
    "live_anchor",
    "fact_notice",
    "player_notice",
}
NON_LINEUP_STARMEN_PROMPT_GUARD = (
    f"・タイトル先頭や見出しで「{LIVE_UPDATE_LINEUP_TITLE_PREFIX}」を使わない。"
    "「打順」「スタメン」「先発メンバー」を section heading にしない"
)
PROMPT_ROLE_ECHO_PREFIXES = (
    "あなたは読売ジャイアンツ専門ブログの編集者です。",
    "読売ジャイアンツ専門ブログの編集者です。",
)
GEMINI_FLASH_THINKING_BUDGET = 0
MANAGER_BODY_TEMPLATE_VERSION = "manager_v1"
MANAGER_REQUIRED_HEADINGS = (
    "【発言の要旨】",
    "【発言内容】",
    "【文脈と背景】",
    "【次の注目】",
)
GAME_BODY_TEMPLATE_VERSION = "game_v1"
GAME_REQUIRED_HEADINGS = {
    "lineup": (
        "【試合概要】",
        "【スタメン一覧】",
        "【先発投手】",
        "【注目ポイント】",
    ),
    "live_anchor": (
        "【時点】",
        "【現在スコア】",
        "【直近のプレー】",
        "【ファン視点】",
    ),
    "postgame": (
        "【試合結果】",
        "【ハイライト】",
        "【選手成績】",
        "【試合展開】",
    ),
    "pregame": (
        "【変更情報の要旨】",
        "【具体的な変更内容】",
        "【この変更が意味すること】",
    ),
    "live_update": (
        "【いま起きていること】",
        "【流れが動いた場面】",
        "【次にどこを見るか】",
    ),
}
FARM_BODY_TEMPLATE_VERSION = "farm_v1"
FARM_REQUIRED_HEADINGS = {
    "farm": (
        "【二軍結果・活躍の要旨】",
        "【ファームのハイライト】",
        "【二軍個別選手成績】",
        "【一軍への示唆】",
    ),
    "farm_lineup": (
        "【二軍試合概要】",
        "【二軍スタメン一覧】",
        "【注目選手】",
    ),
}
NOTICE_BODY_TEMPLATE_VERSION = "notice_v1"
NOTICE_REQUIRED_HEADINGS = (
    "【公示の要旨】",
    "【対象選手の基本情報】",
    "【公示の背景】",
    "【今後の注目点】",
)
RECOVERY_BODY_TEMPLATE_VERSION = "recovery_v1"
RECOVERY_REQUIRED_HEADINGS = (
    "【故障・復帰の要旨】",
    "【故障の詳細】",
    "【リハビリ状況・復帰見通し】",
    "【チームへの影響と今後の注目点】",
)
SOCIAL_BODY_TEMPLATE_VERSION = "social_v1"
SOCIAL_REQUIRED_HEADINGS = (
    "【話題の要旨】",
    "【発信内容の要約】",
    "【文脈と背景】",
    "【ファンの関心ポイント】",
)
MEDIA_XPOST_POSITION = "before_ai_body"
DEFAULT_NOTICE_FALLBACK_IMAGE_URL = "https://yoshilover.com/wp-content/uploads/2025/07/j_RlNtbr_400x400-300x300-1.webp"
DEFAULT_GENERIC_FEATURED_FALLBACK_IMAGE_URL = DEFAULT_NOTICE_FALLBACK_IMAGE_URL
FEATURED_FALLBACK_STORY_TARGETS = {
    ("試合速報", "pregame"),
    ("試合速報", "lineup"),
    ("選手情報", "player"),
    ("首脳陣", "manager"),
}
NOTICE_RECORD_MARKERS = (
    "打率",
    "防御率",
    "OPS",
    "本塁打",
    "打点",
    "安打",
    "登板",
    "試合",
    "勝",
    "敗",
    "奪三振",
    "WHIP",
)
NOTICE_BACKGROUND_MARKERS = (
    "故障",
    "コンディション",
    "特例",
    "二軍",
    "２軍",
    "2軍",
    "ファーム",
    "育成",
    "リハビリ",
    "再調整",
    "ブルペン",
    "出場",
    "登録",
    "抹消",
    "復帰",
    "昇格",
    "合流",
)
RECOVERY_STRONG_MARKERS = (
    "離脱",
    "故障",
    "怪我",
    "ケガ",
    "負傷",
    "リハビリ",
    "回復",
    "再起",
    "戦列復帰",
    "IL入り",
    "手術",
    "診断",
    "療養",
    "コンディション不良",
    "患部",
)
RECOVERY_RETURN_MARKERS = (
    "実戦復帰",
    "戦列復帰",
    "復帰",
    "再起",
    "回復",
)
RECOVERY_PROGRESS_MARKERS = (
    "リハビリ",
    "調整",
    "ブルペン",
    "キャッチボール",
    "打撃練習",
    "ノック",
    "再開",
    "段階",
    "前進",
    "見通し",
    "予定",
    "時期",
    "メド",
    "目安",
    "未定",
    "来月",
    "今月",
    "今季中",
    "数週間",
)
RECOVERY_IMPACT_MARKERS = (
    "代役",
    "代替",
    "先発",
    "ローテ",
    "スタメン",
    "外野手争い",
    "内野手争い",
    "ベンチ入り",
    "一軍",
    "二軍",
    "チーム事情",
)
FARM_DRAFTED_PLAYER_MARKERS = (
    "ドラフト",
    "ルーキー",
    "新人",
    "支配下",
    "育成",
    "ドラ１",
    "ドラ２",
    "ドラ３",
    "ドラ４",
    "ドラ５",
    "ドラ６",
    "ドラ７",
)
RECOVERY_PART_PATTERNS = (
    r"(?:右|左)?(?:肩|肘|膝|足首|足|腰|背中|脇腹|太もも|ふくらはぎ|手首|指|股関節|首|腹斜筋|前腕|下半身|上半身)(?:の(?:違和感|張り|炎症|損傷))?(?:痛|違和感|張り|炎症|損傷|骨折|肉離れ)?",
)
CONFIRMED_RESULT_MARKERS = ("勝利した", "勝利を飾", "白星を挙げ", "敗れた", "敗戦", "黒星", "引き分け", "サヨナラ勝", "サヨナラ負", "連勝", "連敗", "完封勝", "完封負")
FACT_NOTICE_PRIMARY_MARKERS = ("訂正", "誤報", "取り下げ")
DEFINITE_RESULT_MARKERS = ("勝利しました", "勝利を飾りました", "白星を挙げました", "敗れました", "敗戦でした", "黒星を喫しました", "引き分けました")
GENERIC_REACTION_TERMS = {
    "巨人", "ジャイアンツ", "読売", "投手", "選手", "監督", "コーチ", "ファーム", "二軍", "2軍",
    "先発", "登板", "試合", "練習", "参加", "心境", "前日", "好投", "球場", "ジャイアンツ球場",
    "重要", "取り組み", "最新", "今後", "今回", "状態", "起用", "注目", "話題",
}
TOPICAL_REACTION_KEYWORDS = (
    "フォーム", "改造", "助言", "久保", "采配", "起用", "補強", "移籍", "トレード",
    "復帰", "昇格", "抹消", "スタメン", "登録", "甲子園", "東京ドーム", "誕生日",
)
GENERIC_PLAYER_ARTICLE_MARKERS = (
    "今後も継続してその効果を見極める必要があります",
    "今後どのような進化を遂げるのか",
    "期待の声が上がっています",
    "重要な焦点",
    "重要なポイント",
    "示唆していると言えるでしょう",
    "言えるでしょう",
    "ことがうかがえます",
    "注目すべき点",
    "可能性を秘めている",
    "重要です",
)
PLAYER_MECHANICS_SPECIFIC_MARKERS = (
    "フォーム",
    "フォーム変更",
    "投げ方",
    "リリース",
    "腕の振り",
    "球筋",
    "制球",
    "球種",
    "スイング",
    "スイング軌道",
    "打撃フォーム",
    "構え",
    "タイミング",
    "トップ",
    "打球方向",
    "コンタクト",
    "捕球",
    "送球",
    "送球動作",
    "二塁送球",
    "ブロッキング",
    "フレーミング",
    "キャッチング",
    "初動",
    "ステップ",
    "守備範囲",
    "打球判断",
)
PLAYER_MECHANICS_CHANGE_MARKERS = (
    "修正",
    "改善",
    "見直し",
    "改造",
    "変更",
    "取り組み",
    "助言",
)
PLAYER_STATUS_MARKERS = (
    "昇格",
    "一軍",
    "復帰",
    "登録",
    "抹消",
    "合流",
    "別メニュー",
    "二軍戦",
    "2軍戦",
    "先発へ",
    "先発予定",
    "先発見込み",
    "実戦復帰",
    "出場見込み",
)
PLAYER_NOTICE_ROUTE_MARKERS = (
    "復帰",
    "合流",
    "初合流",
    "初１軍",
    "初一軍",
    "一軍登録",
    "出場選手登録",
    "出場選手登録を抹消",
    "登録抹消",
    "抹消",
    "戦力外",
    "戦力外通告",
    "自由契約",
    "契約解除",
    "戦力構想外",
    "来季構想外",
    "来年構想外",
    "構想外",
    "現役引退",
    "引退会見",
    "引退",
    "昇格",
    "再登録",
    "実戦復帰",
    "再出発",
)
PLAYER_DISMISSAL_CATEGORY_MARKERS = (
    "戦力外通告",
    "戦力外",
    "自由契約",
    "契約解除",
    "戦力構想外",
    "来季構想外",
    "来年構想外",
    "現役引退",
    "引退会見",
)
PLAYER_DISMISSAL_EXCLUDE_MARKERS = ("元巨人", "OB", "球団OB", "巨人OB")
PLAYER_RECOVERY_ROUTE_MARKERS = (
    "離脱",
    "故障",
    "怪我",
    "ケガ",
    "負傷",
    "リハビリ",
    "回復",
    "復帰",
    "再起",
    "戦列復帰",
    "IL入り",
    "手術",
    "診断",
    "療養",
    "コンディション不良",
)
PLAYER_QUOTE_CONTEXT_MARKERS = (
    "甲子園",
    "東京ドーム",
    "相手打線",
    "打線",
    "配球",
    "立ち上がり",
    "先発",
    "登板",
    "阪神戦",
    "広島戦",
    "中日戦",
    "DeNA戦",
    "ヤクルト戦",
    "交流戦",
)
PLAYER_ROLE_SUFFIXES = ("投手", "捕手", "内野手", "外野手", "選手")
PLAYER_PITCHER_HINT_MARKERS = ("投手", "先発", "登板", "マウンド", "打線", "好投", "ローテ")
PLAYER_CATCHER_HINT_MARKERS = ("捕手", "配球", "マスク", "送球", "二塁送球", "リード")
PLAYER_INFIELDER_HINT_MARKERS = ("内野手", "遊撃", "二塁", "三塁", "一塁")
PLAYER_OUTFIELDER_HINT_MARKERS = ("外野手", "中堅", "左翼", "右翼")
PLAYER_MECHANICS_TOPIC_PATTERNS = (
    r"(フォーム(?:修正|改造|変更|見直し))",
    r"(投げ方(?:の修正|の見直し|変更))",
    r"(スイング軌道(?:の修正|の見直し))",
    r"(打撃フォーム(?:の修正|の見直し))",
    r"(送球動作の改善)",
    r"(二塁送球(?:につながる)?送球動作の改善)",
    r"(守備範囲(?:の改善|の見直し))",
)
PLAYER_STATUS_TOPIC_PATTERNS = (
    (r"一軍に?合流", "一軍合流"),
    (r"二軍戦(?:で)?実戦復帰|二軍戦復帰", "二軍戦復帰"),
    (r"出場選手登録を抹消|登録抹消", "登録抹消"),
    (r"一軍昇格|昇格", "一軍昇格"),
    (r"復帰", "復帰"),
    (r"別メニュー", "別メニュー"),
    (r"出場見込み", "出場見込み"),
)
PLAYER_QUOTE_SCENE_PATTERNS = (
    r"(移籍後初の[^。、「」 ]+戦)",
    r"([^。、「」 ]+戦)に向け",
    r"(甲子園での登板)",
    r"(東京ドームでの登板)",
    r"(試合前)",
)
MEDIA_HANDLE_KEYWORDS = (
    "news", "sports", "sport", "online", "official", "daily", "tospo", "nikkan", "hochi",
    "sponichi", "sanspo", "fullcount", "baseballking", "oricon", "yahoo", "jiji", "pr",
)
MEDIA_TEXT_MARKERS = (
    "スポーツ報知", "日刊スポーツ", "スポニチ", "サンスポ", "デイリー", "東スポ", "Full-Count",
    "BASEBALL KING", "【速報】", "【巨人】", "記事はこちら", "詳しくはこちら",
)
FAN_OPINION_MARKERS = (
    "と思う", "と思います", "見たい", "気になる", "ほしい", "楽しみ", "不安", "かなり",
    "やっぱり", "正直", "期待", "厳しい", "好き", "ハマる", "かな", "かも",
)
POST_GEN_CLOSE_MARKERS = (
    "気になります",
    "注目です",
    "見たいところです",
    "と思います",
)
POST_GEN_INTRO_ECHO_PREFIXES = (
    "あなたは",
    "読売ジャイアンツ専門ブログ",
)
FAN_COMMENTARY_MARKERS = (
    "なんで", "のか", "べき", "違う", "気がする", "見える", "ほうが", "してほしい",
    "いじらないで", "固定", "序列", "打順", "スタメン", "起用", "若手", "門脇", "浦田",
)
LOW_VALUE_SHARE_MARKERS = (
    "#Yahooニュース", "#SmartNews", "Yahooニュース", "SmartNews", "文春オンライン",
    "日テレNEWS", "日刊スポーツ", "デイリースポーツ", "スポーツ報知", "東スポ",
    "記事はこちら", "詳しくはこちら",
)
SOCIAL_PLAYER_NOTICE_RESCUE_KEYWORDS = (
    "一軍登録",
    "登録抹消",
    "戦力外",
    "復帰",
    "合流",
    "抹消",
    "昇格",
)
SOCIAL_GAME_NOTICE_RESCUE_KEYWORDS = ("復帰", "合流")
SOCIAL_COLUMN_NOTICE_RESCUE_KEYWORDS = (
    "一軍登録",
    "登録抹消",
    "戦力外",
    "抹消",
)
SOCIAL_COLUMN_RESCUE_PATTERNS = (
    (_re.compile(r"初(?:１軍|1軍|一軍)?合流"), "column_escape_draft_join"),
    (_re.compile(r"初(?:１軍|1軍|一軍)"), "column_escape_draft_join"),
    (_re.compile(r"ドラ[1-7１-７](?:位)?"), "column_escape_draft_join"),
)
SOCIAL_VIDEO_SKIP_MARKERS = (
    "【動画】", "動画】", "DAZN BASEBALL", "#だったらDAZN", "月々2,300円",
    "年間プラン・月々払い", "見逃し配信", "ハイライト", "LIVE配信",
)
VIDEO_PROMO_TITLE_MARKERS = ("【動画】", "動画】")
VIDEO_PROMO_SUMMARY_MARKERS = (
    "DAZNベースボールのXから",
    "DAZN BASEBALL",
    "#だったらDAZN",
    "月々2,300円",
    "年間プラン・月々払い",
    "見逃し配信",
)
QUOTE_SKIP_MARKERS = ("DAZN", "BASEBALL", "月々", "年間プラン", "パック")
RULE_BASED_SUBTYPE_TEMPLATE_VERSION = "v0"
_PERMITTED_RULE_BASED_SUBTYPES = frozenset({"lineup", "program", "notice"})
RULE_BASED_PROGRAM_KEYWORDS = (
    "番組",
    "放送",
    "配信",
    "出演",
    "中継",
    "テレビ",
    "ラジオ",
    "特番",
    "インタビュー",
)
RULE_BASED_PROGRAM_CHANNEL_MARKERS = (
    "GIANTS TV",
    "Giants TV",
    "GIANTS_TV",
    "DAZN",
    "Hulu",
    "BS日テレ",
    "日テレジータス",
    "日本テレビ",
    "テレビ",
    "ラジオ",
)
RULE_BASED_SPECULATION_MARKERS = (
    "予想",
    "だろう",
    "期待される",
    "期待したい",
    "かもしれない",
    "ではないか",
    "見込み",
)
RULE_BASED_PROGRAM_PERSON_RE = _re.compile(
    r"([一-龥々ぁ-んァ-ヴー]{2,12}(?:監督|コーチ|投手|捕手|内野手|外野手|選手))"
)
SOCIAL_TEXT_OUTLET_MARKERS = (
    "Sponichi Annex",
    "スポニチ",
    "スポーツ報知",
    "日刊スポーツ",
    "サンスポ",
    "報知新聞社",
    "デイリースポーツ",
    "東スポ",
    "Full-Count",
    "BASEBALL KING",
    "Yahooニュース",
    "SmartNews",
)
SUBJECT_LABEL_STOPWORDS = {
    "Type",
    "Sponichi",
    "Sanspo",
    "Hochi",
    "Daily",
    "SmartNews",
    "Yahoo",
    "News",
    "Giants",
    "班X",
    "巨人班X",
}
SOURCE_BRAND_LABELS = (
    ("スポーツ報知", "報知新聞"),
    ("報知新聞社", "報知新聞"),
    ("日刊スポーツ", "日刊スポーツ"),
    ("スポニチ", "スポニチ"),
    ("Sponichi", "スポニチ"),
    ("サンスポ", "サンスポ"),
    ("Sanspo", "サンスポ"),
    ("デイリースポーツ", "デイリースポーツ"),
    ("東スポ", "東スポ"),
    ("Full-Count", "Full-Count"),
    ("BASEBALL KING", "BASEBALL KING"),
    ("巨人公式", "巨人公式"),
)
AMBIGUOUS_PLAYER_SURNAMES = {
    "田中",
    "佐藤",
    "鈴木",
    "高橋",
    "伊藤",
    "渡辺",
    "中村",
    "小林",
    "加藤",
    "吉田",
    "山田",
    "松本",
    "井上",
}
SUBJECT_CANDIDATE_STOPWORDS = {
    "巨人",
    "ジャイアンツ",
    "出場",
    "出場選手",
    "先発ローテ",
    "ローテ再編",
    "阪神3連戦",
    "シーズンシート",
    "ジャイアンツ球場",
    "東京ドーム",
    "スタメン",
    "オーダー",
    "打順",
    "試合速報",
    "選手情報",
    "首脳陣",
    "補強移籍",
}
SUBJECT_CANDIDATE_SUFFIX_STOPWORDS = (
    "戦",
    "球場",
    "打線",
    "ローテ",
    "起用",
    "登録",
    "抹消",
    "予定",
    "見込み",
)
CATEGORY_REACTION_TERMS = {
    "首脳陣": ("スタメン", "打順", "オーダー", "起用", "序列", "固定", "レギュラー", "若手"),
    "試合速報": ("スタメン", "継投", "采配", "流れ", "代打", "守備", "打順", "勝ちパターン"),
    "選手情報": ("フォーム", "助言", "修正", "昇格", "復帰", "二軍", "2軍", "調整"),
    "補強・移籍": ("補強", "獲得", "トレード", "FA", "支配下", "枠", "外国人"),
}
SUBJECT_ONLY_FAN_REACTION_QUERY_BLOCK_CATEGORIES = {"選手情報", "首脳陣", "補強・移籍"}
ALWAYS_PRECISE_FAN_REACTION_CATEGORIES = {"首脳陣", "補強・移籍"}
DEFAULT_EXCLUDED_REACTION_HANDLES = {"yoshilover6760"}
TRUSTED_SOCIAL_SOURCE_NAMES = {
    "巨人公式X",
    "読売ジャイアンツX",
    "スポーツ報知巨人班X",
    "日刊スポーツX",
    "スポニチ野球記者X",
    "サンスポ巨人X",
    "スポーツ報知X",
    "報知野球X",
    "NPB公式X",
}
GIANTS_EXCLUSIVE_SOCIAL_SOURCE_NAMES = {
    "巨人公式X",
    "読売ジャイアンツX",
    "スポーツ報知巨人班X",
    "サンスポ巨人X",
}
TRUSTED_SOCIAL_SOURCE_HANDLES = {
    "yoshilover6760",
    "tokyogiants",
    "yomiuri_giants",
    "yomiurigiants",
    "hochi_giants",
    "sanspo_giants",
    "sportshochi",
    "hochi_baseball",
    "sponichiyakyu",
    "nikkansports",
    "npb",
    "npb_official",
}
GIANTS_EXCLUSIVE_SOCIAL_HANDLES = {
    "tokyogiants",
    "yomiuri_giants",
    "yomiurigiants",
    "hochi_giants",
    "sanspo_giants",
}
GIANTS_ROSTER_EXTRA_ALIASES = {
    "オコエ瑠偉": ("オコエ瑠偉", "オコエ"),
    "岡本和真": ("岡本和真",),
    "山﨑伊織": ("山﨑伊織", "山崎伊織"),
    "菅野智之": ("菅野智之", "菅野"),
    "中田翔": ("中田翔",),
    "戸根千明": ("戸根千明", "戸根"),
}
TRUSTED_SOCIAL_REPORTABLE_MARKERS = {
    "試合速報": (
        "先発",
        "予告先発",
        "登録",
        "抹消",
        "昇格",
        "公示",
        "打順",
        "オーダー",
        "スタメン",
        "勝利",
        "白星",
        "敗戦",
        "黒星",
        "同点",
        "逆転",
        "先制",
        "本塁打",
        "決勝打",
        "好投",
        "完封",
        "復帰",
        "合流",
    ),
    "選手情報": (
        "復帰",
        "合流",
        "昇格",
        "抹消",
        "登録",
        "先発",
        "実戦",
        "打撃練習",
        "守備練習",
        "ブルペン",
        "調整",
        "コメント",
    ),
    "首脳陣": (
        "監督",
        "コーチ",
        "起用",
        "打順",
        "スタメン",
        "オーダー",
        "競争",
        "コメント",
    ),
    "ドラフト・育成": (
        "二軍",
        "２軍",
        "2軍",
        "ファーム",
        "育成",
        "支配下",
        "昇格",
        "先発",
        "好投",
        "本塁打",
        "マルチ",
        "適時打",
    ),
    "補強・移籍": ("獲得", "移籍", "トレード", "加入", "退団", "調査"),
    "コラム": ("一軍登録", "登録抹消", "戦力外", "合流", "昇格", "初１軍", "初1軍", "初一軍"),
    "球団情報": ("発表", "公示", "開催", "中止", "チケット", "グッズ", "イベント"),
}


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in TRUE_VALUES


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def low_cost_mode_enabled() -> bool:
    return _env_flag("LOW_COST_MODE", False)


def strict_fact_mode_enabled() -> bool:
    return _env_flag("STRICT_FACT_MODE", low_cost_mode_enabled())


def article_parts_renderer_postgame_enabled() -> bool:
    return _env_flag("ENABLE_ARTICLE_PARTS_RENDERER_POSTGAME", False)


def _rule_based_subtype_allowlist() -> frozenset[str]:
    raw = os.environ.get("RULE_BASED_SUBTYPES", "").strip()
    if not raw:
        return frozenset()
    parsed = {part.strip().lower() for part in raw.split(",") if part.strip()}
    return frozenset(part for part in parsed if part in _PERMITTED_RULE_BASED_SUBTYPES)


def _should_use_rule_based(subtype: str | None) -> bool:
    if not subtype:
        return False
    resolved = str(subtype).strip().lower()
    if resolved not in _PERMITTED_RULE_BASED_SUBTYPES:
        return False
    return resolved in _rule_based_subtype_allowlist()


def _env_csv_set(name: str, default: set[str]) -> set[str]:
    value = os.environ.get(name, "")
    if not value.strip():
        return set(default)
    return {item.strip() for item in value.split(",") if item.strip()}


def ai_enabled_categories() -> set[str]:
    default = DEFAULT_LOW_COST_AI_CATEGORIES if low_cost_mode_enabled() else set()
    return _env_csv_set("AI_ENABLED_CATEGORIES", default)


def should_use_ai_for_category(category: str) -> bool:
    enabled = ai_enabled_categories()
    if not enabled:
        return not low_cost_mode_enabled()
    return category in enabled


def _is_notice_like_status_story(title: str, summary: str) -> bool:
    source_text = _strip_html(f"{title} {summary}")
    return any(marker in source_text for marker in PLAYER_NOTICE_ROUTE_MARKERS)


def _is_giants_player_dismissal_story(text: str) -> bool:
    source_text = _strip_html(text)
    if not any(team in source_text for team in ("巨人", "ジャイアンツ")):
        return False
    if any(marker in source_text for marker in PLAYER_DISMISSAL_EXCLUDE_MARKERS):
        return False
    if any(marker in source_text for marker in PLAYER_DISMISSAL_CATEGORY_MARKERS):
        return True
    if "構想外" in source_text and not any(role in source_text for role in ("監督", "コーチ")):
        return True
    if "引退" in source_text and not any(role in source_text for role in ("監督", "コーチ")):
        return True
    return False


def _extract_player_subject_context_windows(title: str, summary: str, subject: str, radius: int = 56) -> list[str]:
    source_text = _strip_html(f"{title} {summary}")
    if not subject or subject in {"巨人", "選手", "出場選手"}:
        return [source_text]
    aliases = [subject]
    family_name = _player_family_name_alias(title, summary, "選手情報")
    if family_name and family_name not in aliases and family_name not in {"巨人", "選手"}:
        aliases.append(family_name)
    windows = []
    for alias in aliases:
        for match in _re.finditer(_re.escape(alias), source_text):
            start = max(0, match.start() - radius)
            end = min(len(source_text), match.end() + radius)
            windows.append(source_text[start:end])
    return windows or [source_text]


def _extract_recovery_subject(title: str, summary: str) -> str:
    notice_subject, _notice_type = _extract_notice_subject_and_type(title, summary)
    if notice_subject and notice_subject not in {"巨人", "選手", "出場選手"}:
        return notice_subject
    return _short_subject_name(title, summary, "選手情報")


def _extract_recovery_injury_part(title: str, summary: str, subject: str = "") -> str:
    source_text = _strip_html(f"{title} {summary}")
    recovery_subject = subject or _extract_recovery_subject(title, summary)
    windows = _extract_player_subject_context_windows(title, summary, recovery_subject)
    for window in windows + [source_text]:
        for pattern in RECOVERY_PART_PATTERNS:
            match = _re.search(pattern, window)
            if match:
                return match.group(0)
    return ""


def _extract_recovery_return_timing(title: str, summary: str, subject: str = "") -> str:
    recovery_subject = subject or _extract_recovery_subject(title, summary)
    family_name = _player_family_name_alias(title, summary, "選手情報")
    sentences = _extract_prompt_fact_sentences(title, summary, max_sentences=6)
    strong_timing_markers = (
        "未定",
        "今月",
        "来月",
        "今季中",
        "数週間",
        "予定",
        "時期",
        "見通し",
        "メド",
        "目安",
        "視野",
        "実戦復帰",
        "戦列復帰",
    )
    timing_marker_sets = (
        strong_timing_markers,
        RECOVERY_RETURN_MARKERS + RECOVERY_PROGRESS_MARKERS,
    )
    for markers in timing_marker_sets:
        for sentence in sentences:
            fact = _ensure_fact_sentence(sentence)
            if not fact or not any(marker in fact for marker in markers):
                continue
            if recovery_subject and recovery_subject not in fact and (not family_name or family_name not in fact):
                # 復帰時期は主語が省略されやすいので、時期表現が強い文は許容する。
                if markers is strong_timing_markers:
                    return fact.rstrip("。")
                if not any(marker in fact for marker in strong_timing_markers):
                    continue
            return fact.rstrip("。")
    return ""


def _is_recovery_like_status_story(title: str, summary: str) -> bool:
    source_text = _strip_html(f"{title} {summary}")
    if not any(marker in source_text for marker in PLAYER_RECOVERY_ROUTE_MARKERS):
        return False
    recovery_subject = _extract_recovery_subject(title, summary)
    windows = _extract_player_subject_context_windows(title, summary, recovery_subject)
    has_strong_signal = any(any(marker in window for marker in RECOVERY_STRONG_MARKERS) for window in windows)
    has_return_signal = any(any(marker in window for marker in RECOVERY_RETURN_MARKERS) for window in windows)
    has_progress_signal = any(any(marker in window for marker in RECOVERY_PROGRESS_MARKERS) for window in windows)
    if has_strong_signal:
        return True
    if has_return_signal and has_progress_signal:
        return True
    if any(marker in source_text for marker in ("実戦復帰", "戦列復帰")):
        return True
    return False


def _detect_player_special_template_kind(title: str, summary: str) -> str:
    if _is_recovery_like_status_story(title, summary):
        return "player_recovery"
    if _is_notice_like_status_story(title, summary):
        return "player_notice"
    return ""


def _is_recovery_template_story(title: str, summary: str, category: str = "選手情報") -> bool:
    if category != "選手情報":
        return False
    return _detect_player_special_template_kind(title, summary) == "player_recovery"


def _resolve_article_generation_category(category: str, title: str, summary: str) -> str:
    if category == "ドラフト・育成" and _is_farm_template_subtype(_detect_article_subtype(title, summary, category, True)):
        return category
    if category in {"コラム", "ドラフト・育成"} and _detect_player_special_template_kind(title, summary):
        return "選手情報"
    return category


def _resolve_article_ai_strategy(
    category: str,
    title: str,
    summary: str,
    has_game: bool,
    article_subtype: str | None = None,
) -> tuple[bool, str, str]:
    effective_category = _resolve_article_generation_category(category, title, summary)
    if effective_category != category and should_use_ai_for_category(effective_category):
        special_kind = _detect_player_special_template_kind(title, summary)
        if special_kind == "player_recovery":
            return True, effective_category, "player_recovery_route"
        return True, effective_category, "player_notice_route"

    if should_use_ai_for_category(category):
        return True, category, "category_enabled"

    subtype = article_subtype or _detect_article_subtype(title, summary, category, has_game)
    if category == "ドラフト・育成" and subtype in {"farm", "farm_lineup"}:
        return True, category, "farm_article_route"

    return False, effective_category, ""


def get_article_ai_mode(has_game: bool, override: str | None = None) -> str:
    env_name = "ARTICLE_AI_MODE" if has_game else "OFFDAY_ARTICLE_AI_MODE"
    default_mode = "gemini" if has_game else "gemini" if low_cost_mode_enabled() else "auto"
    candidate = override if override is not None else os.environ.get(env_name, default_mode)
    mode = candidate.strip().lower()
    if mode in {"auto", "grok", "gemini", "none"}:
        return mode
    return default_mode


def get_fan_reaction_limit() -> int:
    default_limit = 7 if low_cost_mode_enabled() else 15
    return max(0, min(_env_int("FAN_REACTION_LIMIT", default_limit), 15))


def get_gemini_attempt_limit(strict_mode: bool) -> int:
    if strict_mode:
        default_limit = 3
        env_name = "GEMINI_STRICT_MAX_ATTEMPTS"
        upper = 3
    else:
        default_limit = 1 if low_cost_mode_enabled() else 2
        env_name = "GEMINI_GROUNDED_MAX_ATTEMPTS"
        upper = 2
    return max(1, min(_env_int(env_name, default_limit), upper))


def _get_gemini_strict_min_chars(category: str, title: str, summary: str) -> int:
    if category == "首脳陣":
        return 160
    if category == "試合速報" and _is_game_template_subtype(_detect_article_subtype(title, summary, category, True)):
        return 160
    if category == "ドラフト・育成" and _is_farm_template_subtype(_detect_article_subtype(title, summary, category, True)):
        return 160
    if category == "選手情報" and _detect_player_special_template_kind(title, summary):
        return 160
    if category == "選手情報" and _detect_player_article_mode(title, summary, category) == "player_status":
        return 160
    return 220


def get_fan_reaction_max_age_hours() -> int:
    default_hours = 72
    return max(6, _env_int("FAN_REACTION_MAX_AGE_HOURS", default_hours))


def get_fan_reaction_excluded_handles() -> set[str]:
    return {handle.lower().lstrip("@") for handle in _env_csv_set("FAN_REACTION_EXCLUDE_HANDLES", DEFAULT_EXCLUDED_REACTION_HANDLES)}


def enhanced_prompts_enabled() -> bool:
    return os.getenv("ENABLE_ENHANCED_PROMPTS", "0").strip().lower() in TRUE_VALUES


def _enhanced_next_focus_rules(section_name: str = "【次の注目】") -> str:
    if not enhanced_prompts_enabled():
        return ""
    return (
        f"{section_name}では、前の段落や source の言い換えだけで終えず、巨人ファンが次に1つだけ確認したい具体点を必ず書いてください。\n"
        f"{section_name}では、『今後に注目』『期待が高まる』『どうつながるかが注目点』のような抽象語だけで締めないでください。\n"
        f"{section_name}では、見たい場面・数字・起用・登録・打席・登板のどれかを1つに絞ってください。\n"
    )


def _enhanced_player_prompt_rules(player_mode: str) -> str:
    if not enhanced_prompts_enabled():
        return ""
    if player_mode == "player_mechanics":
        return (
            "【ここに注目】では、フォーム修正や助言を一般論に広げず、source に出た動作や言葉をそのまま残してください。\n"
            + _enhanced_next_focus_rules("【次の注目】")
        )
    if player_mode == "player_quote":
        return (
            "【ニュースの整理】では、コメントの内容を精神論に広げず、どの場面に向けた言葉かを先に固定してください。\n"
            + _enhanced_next_focus_rules("【次の注目】")
        )
    return (
        "【ニュースの整理】では、登録・昇格・合流・調整段階のどれなのかを最初に固定し、曖昧な現状整理でぼかさないでください。\n"
        + _enhanced_next_focus_rules("【次の注目】")
    )


def _enhanced_recovery_prompt_rules() -> str:
    if not enhanced_prompts_enabled():
        return ""
    return (
        "【故障の詳細】では、部位が空なら空のまま扱い、元記事にない部位・診断・全治見込みを補わないでください。\n"
        "【リハビリ状況・復帰見通し】では、『順調』『万全』などの断定を避け、source にある段階表現を優先してください。\n"
        + _enhanced_next_focus_rules("【チームへの影響と今後の注目点】")
    )


def _enhanced_notice_prompt_rules() -> str:
    if not enhanced_prompts_enabled():
        return ""
    return (
        "【対象選手の基本情報】では、source に数字がある場合は年齢・成績・試合数のどれかを必ず1つ残してください。\n"
        "【公示の要旨】では、登録・抹消・戦力外・復帰の時点をぼかさず、source にある日付や区分を優先してください。\n"
        + _enhanced_next_focus_rules("【今後の注目点】")
    )


def _enhanced_manager_prompt_rules() -> str:
    if not enhanced_prompts_enabled():
        return ""
    return (
        "【文脈と背景】では、発言だけをなぞらず、巨人のスタメン・序列・継投・競争のどれを動かす話かを先に固定してください。\n"
        + _enhanced_next_focus_rules("【次の注目】")
    )


def _enhanced_game_prompt_rules(article_subtype: str) -> str:
    if not enhanced_prompts_enabled():
        return ""
    base = (
        "source にある選手名・回・スコア・球場・打順・投球回・安打数などの固有情報を、抽象語に言い換えず残してください。\n"
    )
    if article_subtype == "lineup":
        return base + _enhanced_next_focus_rules("【注目ポイント】")
    if article_subtype == "live_anchor":
        return (
            base
            + "【時点】では、何回表/裏終了か、何回何死かなど、節目の時点を1文目で固定してください。\n"
            + "【直近のプレー】では、重要プレーを1〜3点に絞り、未発生事象や予測語を足さないでください。\n"
            + "【ファン視点】は最後の1文だけにしてください。\n"
        )
    if article_subtype == "postgame":
        return (
            base
            + "【ハイライト】と【選手成績】で同じ要約文を繰り返さず、片方は流れ、片方は数字に寄せてください。\n"
            + _enhanced_next_focus_rules("【試合展開】")
        )
    if article_subtype == "live_update":
        return (
            base
            + "【流れが動いた場面】では、イニングの実況を時系列にだらだら並べず、流れが動いた瞬間を1つか2つに絞って書いてください。\n"
            + _enhanced_next_focus_rules("【次にどこを見るか】")
        )
    return (
        base
        + "【具体的な変更内容】では、変更点をそのまま再掲するだけでなく、誰がどう変わったかを1文ずつ分けて整理してください。\n"
        + _enhanced_next_focus_rules("【この変更が意味すること】")
    )


def _enhanced_farm_prompt_rules(article_subtype: str) -> str:
    if not enhanced_prompts_enabled():
        return ""
    if article_subtype == "farm_lineup":
        return (
            "【二軍試合概要】と【二軍スタメン一覧】では、一軍と混同しないよう『二軍』『ファーム』を明記してください。\n"
            + _enhanced_next_focus_rules("【注目選手】")
        )
    return (
        "【二軍個別選手成績】では、source に数字があるなら安打数・打点・投球回・失点のどれかを必ず残してください。\n"
        "【一軍への示唆】では、昇格断定を避けつつ、二軍で何を示したかを1つに絞ってください。\n"
        + _enhanced_next_focus_rules("【一軍への示唆】")
    )


def _enhanced_social_prompt_rules(category: str) -> str:
    if not enhanced_prompts_enabled():
        return ""
    category_hint = {
        "試合速報": "スコア・先発・打順・勝敗など試合の固有情報",
        "選手情報": "選手の状態・昇格・コメント・役割",
        "首脳陣": "監督・コーチ発言がどの起用や采配に結びつくか",
        "ドラフト・育成": "二軍・育成・支配下・ドラフトのどの文脈か",
    }.get(category, "元記事にあるチーム文脈")
    return (
        "ハッシュタグ、URL、媒体名の繰り返し、宣伝文句、SNSの定型句は本文に残さないでください。\n"
        f"【文脈と背景】では、{category_hint} を source にある範囲で具体的に整理してください。\n"
        "【ファンの関心ポイント】では、受け止めが分かれる話題でも、ファンの温度感の言い換えだけで終えず、次に何を見るかを1つだけ書いてください。\n"
    )


def _social_source_prefers_structured_template(category: str, article_subtype: str) -> bool:
    if category == "試合速報" and _is_game_template_subtype(article_subtype):
        return True
    if category == "ドラフト・育成" and _is_farm_template_subtype(article_subtype):
        return True
    return False


def _strip_prompt_role_echo(article_text: str) -> str:
    text = (article_text or "").lstrip()
    if not text:
        return article_text
    if not any(text.startswith(prefix) for prefix in PROMPT_ROLE_ECHO_PREFIXES):
        return article_text
    heading_index = text.find("【")
    if heading_index >= 0:
        return text[heading_index:].lstrip()
    lines = text.splitlines()
    while lines and any(lines[0].strip().startswith(prefix) for prefix in PROMPT_ROLE_ECHO_PREFIXES):
        lines.pop(0)
    return "\n".join(lines).lstrip()


def _enhanced_grounded_rules(category: str, article_subtype: str = "", source_type: str = "news") -> str:
    if not enhanced_prompts_enabled():
        return ""
    common = (
        "・元記事や検索結果の要点を言い換えるだけで段落を埋めない\n"
        "・各見出しで、固有名詞か数字のどちらかを最低1つは残す\n"
    )
    if source_type == "social_news" and not _social_source_prefers_structured_template(category, article_subtype):
        return common + _enhanced_social_prompt_rules(category).replace("【", "・【")
    if category == "首脳陣":
        return common + _enhanced_manager_prompt_rules().replace("【", "・【")
    if category == "選手情報":
        return common + _enhanced_next_focus_rules("【次の注目】").replace("【", "・【")
    if category == "試合速報":
        if article_subtype == "lineup":
            target = "【注目ポイント】"
        elif article_subtype == "live_anchor":
            return common + (
                "・【時点】では、何回表/裏終了時点か、何回何死時点かを最初に固定する\n"
                "・【直近のプレー】では、重要プレーを1〜3点に絞り、未発生事象や予測語を足さない\n"
                "・【ファン視点】は最後の1文だけにする\n"
            )
        elif article_subtype == "postgame":
            target = "【試合展開】"
        elif article_subtype == "live_update":
            target = "【次にどこを見るか】"
        else:
            target = "【この変更が意味すること】"
        return common + _enhanced_next_focus_rules(target).replace("【", "・【")
    if category == "ドラフト・育成":
        target = "【注目選手】" if article_subtype == "farm_lineup" else "【一軍への示唆】"
        return common + _enhanced_next_focus_rules(target).replace("【", "・【")
    return common


def get_x_post_daily_limit() -> int:
    default_limit = 5 if low_cost_mode_enabled() else 20
    return max(0, _env_int("X_POST_DAILY_LIMIT", default_limit))


def get_auto_tweet_categories() -> set[str]:
    return _env_csv_set("AUTO_TWEET_CATEGORIES", DEFAULT_AUTO_TWEET_CATEGORIES)


def auto_tweet_requires_featured_media() -> bool:
    return _env_flag("AUTO_TWEET_REQUIRE_IMAGE", True)


def publish_requires_featured_media() -> bool:
    return _env_flag("PUBLISH_REQUIRE_IMAGE", True)


def auto_tweet_enabled() -> bool:
    return _env_flag("AUTO_TWEET_ENABLED", not low_cost_mode_enabled())


def publish_enabled_for_subtype(article_subtype: str) -> bool:
    if article_subtype == "live_update":
        return False
    env_name = PUBLISH_SUBTYPE_ENV_MAP.get(article_subtype or "", "ENABLE_PUBLISH_FOR_GENERAL")
    return _env_flag(env_name, False)


def x_post_enabled_for_subtype(article_subtype: str) -> bool:
    env_name = X_POST_SUBTYPE_ENV_MAP.get(article_subtype or "", "ENABLE_X_POST_FOR_GENERAL")
    return _env_flag(env_name, False)


def x_post_for_live_update_enabled() -> bool:
    return _env_flag("ENABLE_X_POST_FOR_LIVE_UPDATE", False)


def resolve_publish_gate_subtype(
    title: str,
    summary: str,
    category: str,
    article_subtype: str,
    source_type: str,
) -> str:
    if source_type == "social_news":
        if _social_source_prefers_structured_template(category, article_subtype):
            return "farm" if article_subtype in {"farm", "farm_lineup"} else article_subtype
        return "social"
    if category == "選手情報":
        special_kind = _detect_player_special_template_kind(title, summary)
        if special_kind == "player_notice":
            return "notice"
        if special_kind == "player_recovery":
            return "recovery"
        return "player"
    if article_subtype in {"farm", "farm_lineup"}:
        return "farm"
    if article_subtype in {"game_note", "roster", "", "fallback"}:
        return "general"
    return article_subtype or "general"


def _auto_tweet_source_allowed(source_type: str) -> bool:
    return source_type in {"news", "social_news"}


def get_auto_tweet_skip_reasons(
    *,
    source_type: str,
    category: str,
    article_subtype: str = "",
    draft_only: bool,
    x_post_count: int,
    x_post_daily_limit: int,
    featured_media: int,
    published: bool,
    article_url: str,
) -> list[str]:
    reasons = []
    if not _auto_tweet_source_allowed(source_type):
        reasons.append("source_type_not_supported")
    if category not in get_auto_tweet_categories():
        reasons.append("category_not_allowed")
    if published and article_subtype == "live_update" and not x_post_for_live_update_enabled():
        reasons.append("live_update_x_post_disabled")
    elif (
        published
        and auto_tweet_enabled()
        and article_subtype
        and article_subtype != "live_update"
        and not x_post_enabled_for_subtype(article_subtype)
    ):
        reasons.append("x_post_disabled_for_subtype")
    if draft_only:
        reasons.append("draft_only")
    if not auto_tweet_enabled():
        reasons.append("auto_tweet_disabled")
    if x_post_count >= x_post_daily_limit:
        reasons.append("daily_limit_reached")
    if auto_tweet_requires_featured_media() and not featured_media:
        reasons.append("featured_media_missing")
    if not published:
        reasons.append("not_published")
    if not article_url:
        reasons.append("article_url_missing")
    return reasons


def get_publish_skip_reasons(
    *,
    source_type: str,
    draft_only: bool,
    featured_media: int,
    article_subtype: str = "",
) -> list[str]:
    reasons = []
    if draft_only:
        reasons.append("draft_only")
    else:
        if source_type in {"news", "social_news"} and article_subtype == "live_update":
            reasons.append("live_update_publish_disabled")
        elif source_type in {"news", "social_news"} and article_subtype and not publish_enabled_for_subtype(article_subtype):
            reasons.append("publish_disabled_for_subtype")
        if source_type in {"news", "social_news"} and publish_requires_featured_media() and not featured_media:
            reasons.append("featured_media_missing")
    return reasons


def get_publish_observation_reasons(
    *,
    source_type: str,
    draft_only: bool,
    featured_media: int,
) -> list[str]:
    reasons = []
    if (
        draft_only
        and source_type in {"news", "social_news"}
        and publish_requires_featured_media()
        and not featured_media
    ):
        reasons.append("featured_media_observation_missing")
    return reasons


class _CoreBodyHTMLStripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._parts: list[str] = []
        self._skip_div_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip_div_depth:
            if tag == "div":
                self._skip_div_depth += 1
            return
        attrs_map = {key: value or "" for key, value in attrs}
        classes = set((attrs_map.get("class") or "").split())
        if tag == "div" and "yoshilover-related-posts" in classes:
            self._skip_div_depth = 1
            return
        self._parts.append(self.get_starttag_text())

    def handle_endtag(self, tag: str) -> None:
        if self._skip_div_depth:
            if tag == "div":
                self._skip_div_depth -= 1
            return
        self._parts.append(f"</{tag}>")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip_div_depth:
            return
        self._parts.append(self.get_starttag_text())

    def handle_data(self, data: str) -> None:
        if not self._skip_div_depth:
            self._parts.append(data)

    def handle_entityref(self, name: str) -> None:
        if not self._skip_div_depth:
            self._parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if not self._skip_div_depth:
            self._parts.append(f"&#{name};")

    def get_html(self) -> str:
        return "".join(self._parts)


def _strip_related_posts_section(content_html: str) -> str:
    parser = _CoreBodyHTMLStripper()
    parser.feed(content_html or "")
    parser.close()
    return parser.get_html()


def _strip_html(text: str) -> str:
    return _re.sub(r"<[^>]+>", "", text or "").strip()


def _collapse_ws(text: str) -> str:
    return _re.sub(r"\s+", " ", text or "").strip()


def _core_body_text(content_html: str) -> str:
    return _collapse_ws(_html.unescape(_strip_html(_strip_related_posts_section(content_html or ""))))


def _publish_quality_min_chars(article_subtype: str) -> int:
    subtype = (article_subtype or "").strip().lower()
    if subtype in PUBLISH_QUALITY_MIN_CHARS_BY_SUBTYPE:
        return PUBLISH_QUALITY_MIN_CHARS_BY_SUBTYPE[subtype]
    return PUBLISH_QUALITY_DEFAULT_MIN_CHARS


def _evaluate_publish_quality_guard(*, content_html: str, article_subtype: str) -> dict[str, object]:
    core_text = _core_body_text(content_html)
    min_chars = _publish_quality_min_chars(article_subtype)
    leak_markers = [marker for marker in PUBLISH_QUALITY_LEAK_MARKERS if marker in core_text]
    reasons: list[str] = []
    if len(core_text) < min_chars:
        reasons.append("quality_guard_thin")
    if leak_markers:
        reasons.append("quality_guard_leak")
    return {
        "ok": not reasons,
        "reasons": reasons,
        "core_char_count": len(core_text),
        "min_chars": min_chars,
        "leak_markers": leak_markers,
    }


def _normalize_player_name_key(name: str) -> str:
    clean = _collapse_ws(_html.unescape(_strip_html(name or "")))
    return clean.replace(" ", "").replace("　", "")


def _extract_html_table_rows(html: str) -> list[list[str]]:
    rows = []
    for row_html in _re.findall(r"<tr[^>]*>(.*?)</tr>", html or "", _re.IGNORECASE | _re.DOTALL):
        cells = []
        for cell_html in _re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row_html, _re.IGNORECASE | _re.DOTALL):
            text = _collapse_ws(_html.unescape(_strip_html(cell_html)))
            cells.append(text)
        if cells:
            rows.append(cells)
    return rows


_NUMBER_TRANSLATION_TABLE = str.maketrans({
    "０": "0",
    "１": "1",
    "２": "2",
    "３": "3",
    "４": "4",
    "５": "5",
    "６": "6",
    "７": "7",
    "８": "8",
    "９": "9",
    "．": ".",
    "：": ":",
    "／": "/",
    "−": "-",
    "－": "-",
    "–": "-",
    "—": "-",
    "％": "%",
})


def _normalize_number_token(token: str) -> str:
    return token.translate(_NUMBER_TRANSLATION_TABLE).replace(" ", "").replace("　", "")


def _extract_number_tokens(text: str) -> list[str]:
    clean = _normalize_number_token(_strip_html(text))
    tokens = []
    occupied = [False] * len(clean)

    for pattern in STRUCTURED_NUMBER_TOKEN_RES:
        for match in pattern.finditer(clean):
            start, end = match.span()
            if any(occupied[start:end]):
                continue
            token = clean[start:end]
            tokens.append(token)
            for idx in range(start, end):
                occupied[idx] = True

    for match in NUMERIC_TOKEN_RE.finditer(clean):
        start, end = match.span()
        if any(occupied[start:end]):
            continue
        tokens.append(clean[start:end])

    return tokens


def _expand_number_token_variants(token: str) -> set[str]:
    normalized = _normalize_number_token(token)
    variants = {normalized}

    if match := DATE_SLASH_TOKEN_RE.fullmatch(normalized):
        parts = normalized.split("/")
        if len(parts) == 3:
            year, month, day = parts
            variants.update({
                f"{year}年{int(month)}月{int(day)}日",
                f"{int(month)}月{int(day)}日",
                f"{int(day)}日",
                f"{year}年",
                f"{int(month)}/{int(day)}",
            })
        elif len(parts) == 2:
            month, day = parts
            variants.update({
                f"{int(month)}月{int(day)}日",
                f"{int(day)}日",
            })
        return variants

    if match := DATE_JP_TOKEN_RE.fullmatch(normalized):
        date_match = _re.fullmatch(r"(?:(\d{4})年)?(\d{1,2})月(\d{1,2})日", normalized)
        if date_match:
            year, month, day = date_match.groups()
            variants.update({
                f"{int(month)}/{int(day)}",
                f"{int(day)}日",
            })
            if year:
                variants.add(f"{year}/{int(month)}/{int(day)}")
                variants.add(f"{year}年")
        return variants

    if match := TIME_TOKEN_RE.fullmatch(normalized):
        hour, minute = normalized.split(":")
        variants.add(f"{int(hour)}時{minute}分")
        if minute == "00":
            variants.add(f"{int(hour)}時")
        return variants

    if match := SCORE_TOKEN_RE.fullmatch(normalized):
        left, right = [part.strip() for part in normalized.split("-")]
        variants.add(f"{left}対{right}")
        return variants

    if match := SCORE_VS_TOKEN_RE.fullmatch(normalized):
        left, right = [part.strip() for part in normalized.split("対")]
        variants.add(f"{left}-{right}")
        return variants

    if match := RECORD_TOKEN_RE.fullmatch(normalized):
        record_match = _re.fullmatch(r"(\d+)勝(\d+)敗(?:(\d+)分)?", normalized)
        if record_match:
            wins, losses, draws = record_match.groups()
            variants.update({f"{wins}勝", f"{losses}敗"})
            if draws is not None:
                variants.add(f"{draws}分")
        return variants

    if match := LABELED_DECIMAL_TOKEN_RE.fullmatch(normalized):
        decimal_match = _re.search(r"(\d+\.\d+)$", normalized)
        if decimal_match:
            variants.add(decimal_match.group(1))
        return variants

    return variants


def _collect_allowed_number_tokens(*texts: str) -> set[str]:
    tokens = set()
    for text in texts:
        for token in _extract_number_tokens(text):
            tokens.update(_expand_number_token_variants(token))
    return tokens


def _extract_source_sentences(title: str, summary: str, max_sentences: int = 4) -> list[str]:
    pieces = []
    title_clean = _strip_html(title)
    summary_clean = _strip_html(summary)
    if title_clean:
        pieces.append(title_clean)
    for part in _re.split(r"[。！？\n]+", summary_clean):
        part = part.strip(" ・\t")
        if part:
            pieces.append(part)

    deduped = []
    seen = set()
    for piece in pieces:
        key = piece.replace(" ", "").replace("　", "")
        if key not in seen:
            seen.add(key)
            deduped.append(piece)
        if len(deduped) >= max_sentences:
            break
    return deduped


def _extract_summary_sentences(summary: str, max_sentences: int = 4) -> list[str]:
    return _extract_source_sentences("", summary, max_sentences=max_sentences)


def _strip_title_prefix(title: str) -> str:
    clean = _strip_html(title)
    clean = _re.sub(r"^【[^】]+】", "", clean).strip()
    return clean.strip("。 ")


def _clean_social_entry_text(text: str) -> str:
    clean = _html.unescape(_strip_html(text or ""))
    clean = _re.sub(r'https?://\S+', '', clean)
    clean = _re.sub(r'#[\w一-龯ぁ-ゔァ-ヴー々〆〤]+', '', clean)
    clean = _re.sub(r'(?<!\S)@[\w.\-一-龯ぁ-ゔァ-ヴー々〆〤]+[:：]?', '', clean)
    clean = _re.sub(
        r'\s*[-–—]\s*(スポニチ(?: Sponichi Annex)? 野球|Sponichi Annex 野球|スポーツ報知|報知新聞社|日刊スポーツ|サンスポ.*)$',
        '',
        clean,
        flags=_re.IGNORECASE,
    )
    clean = _re.sub(r'^\s*Type(?=[「『【])', '', clean)
    clean = _re.sub(r"\s+", " ", clean)
    clean = _re.sub(r"\s+([。！？])", r"\1", clean)
    return clean.strip(" ・\t")


def _normalize_social_handle(handle: str) -> str:
    return (handle or "").strip().lower().lstrip("@")


def _normalize_social_source_name(source_name: str) -> str:
    return _collapse_ws(source_name or "")


def _is_trusted_social_source(source_handle: str = "", source_name: str = "") -> bool:
    handle = _normalize_social_handle(source_handle)
    if handle in TRUSTED_SOCIAL_SOURCE_HANDLES:
        return True
    return _normalize_social_source_name(source_name) in TRUSTED_SOCIAL_SOURCE_NAMES


def _is_giants_exclusive_social_source(source_handle: str = "", source_name: str = "") -> bool:
    handle = _normalize_social_handle(source_handle)
    if handle in GIANTS_EXCLUSIVE_SOCIAL_HANDLES:
        return True
    return _normalize_social_source_name(source_name) in GIANTS_EXCLUSIVE_SOCIAL_SOURCE_NAMES


def _is_polluted_social_text(text: str) -> bool:
    clean = _html.unescape(_strip_html(text or "")).strip()
    if not clean:
        return True
    if _re.search(r'https?://\S+', clean):
        return True
    if _re.search(r'#[\w一-龯ぁ-ゔァ-ヴー々〆〤]+', clean):
        return True
    if _re.search(r'(?<!\S)@[\w.\-一-龯ぁ-ゔァ-ヴー々〆〤]+', clean):
        return True
    if _re.search(r'^\s*Type(?=[「『【])', clean):
        return True
    lower_clean = clean.lower()
    return any(marker.lower() in lower_clean for marker in SOCIAL_TEXT_OUTLET_MARKERS)


def _is_polluted_social_entry(
    title: str,
    summary: str,
    *,
    source_name: str = "",
    post_url: str = "",
) -> bool:
    if _is_trusted_social_source(_extract_handle_from_tweet_url(post_url), source_name):
        return False
    return _is_polluted_social_text(title) or _is_polluted_social_text(summary)


def _first_matching_keyword(text: str, keywords: tuple[str, ...]) -> str:
    for keyword in keywords:
        if keyword in text:
            return keyword
    return ""


def _match_social_column_rescue(text: str) -> tuple[str, str]:
    keyword = _first_matching_keyword(text, SOCIAL_COLUMN_NOTICE_RESCUE_KEYWORDS)
    if keyword:
        return "column_escape_notice_keyword", keyword
    for pattern, rescue_reason in SOCIAL_COLUMN_RESCUE_PATTERNS:
        match = pattern.search(text)
        if match:
            return rescue_reason, match.group(0)
    return "", ""


def get_notice_fallback_image_url() -> str:
    return os.environ.get("NOTICE_FALLBACK_IMAGE_URL", DEFAULT_NOTICE_FALLBACK_IMAGE_URL).strip()


def get_story_fallback_image_url(category: str, article_subtype: str) -> str:
    if (category, article_subtype) not in FEATURED_FALLBACK_STORY_TARGETS:
        return ""
    return os.environ.get(
        "FEATURED_IMAGE_FALLBACK_URL",
        DEFAULT_GENERIC_FEATURED_FALLBACK_IMAGE_URL,
    ).strip()


def _extract_notice_type_label(text: str) -> str:
    source_text = _strip_html(text or "")
    checks = (
        ("戦力外通告", "戦力外"),
        ("戦力外", "戦力外"),
        ("自由契約", "自由契約"),
        ("契約解除", "契約解除"),
        ("戦力構想外", "構想外"),
        ("来季構想外", "構想外"),
        ("来年構想外", "構想外"),
        ("構想外", "構想外"),
        ("現役引退", "引退"),
        ("引退会見", "引退"),
        ("引退", "引退"),
        ("再出発", "再出発"),
        ("登録抹消", "登録抹消"),
        ("出場選手登録を抹消", "登録抹消"),
        ("初合流", "初合流"),
        ("初１軍", "初一軍"),
        ("初一軍", "初一軍"),
        ("一軍登録", "一軍登録"),
        ("出場選手登録", "一軍登録"),
        ("再登録", "再登録"),
        ("一軍合流", "一軍合流"),
        ("チーム合流", "一軍合流"),
        ("合流", "一軍合流"),
        ("実戦復帰", "復帰"),
        ("復帰", "復帰"),
        ("昇格", "昇格"),
    )
    for marker, label in checks:
        if marker in source_text:
            return label
    return ""


def _extract_notice_subject_and_type(title: str, summary: str) -> tuple[str, str]:
    source_text = _strip_html(f"{title} {summary}")
    giants_patterns = (
        r"(?:巨人|ジャイアンツ)\s*[・･]\s*([A-Za-zＡ-Ｚａ-ｚ一-龥々ァ-ヴーー\.\-．・]{2,24})(?:投手|捕手|内野手|外野手|選手)",
        r"(?:巨人|ジャイアンツ)(?:】|の|[\s　])([A-Za-zＡ-Ｚａ-ｚ一-龥々ァ-ヴーー\.\-．・]{2,24})(?:投手|捕手|内野手|外野手|選手)",
    )

    for pattern in giants_patterns:
        for match in _re.finditer(pattern, source_text):
            candidate = _re.sub(r"\s+", "", match.group(1)).strip("・･")
            if (
                not candidate
                or candidate in SUBJECT_LABEL_STOPWORDS
                or any(stop in candidate for stop in SUBJECT_CANDIDATE_STOPWORDS)
            ):
                continue
            nearby = source_text[max(0, match.start() - 48): min(len(source_text), match.end() + 32)]
            notice_type = _extract_notice_type_label(nearby) or _extract_notice_type_label(source_text)
            return candidate, notice_type

    fallback_subject = _short_subject_name(title, summary, "選手情報")
    fallback_type = _extract_notice_type_label(source_text)
    return fallback_subject, fallback_type


def _extract_notice_player_position(title: str, summary: str, subject: str = "") -> str:
    source_text = _strip_html(f"{title} {summary}")
    notice_subject = subject or _extract_notice_subject_and_type(title, summary)[0]
    if notice_subject and notice_subject not in {"巨人", "選手", "出場選手"}:
        role_pattern = "|".join(PLAYER_ROLE_SUFFIXES)
        patterns = (
            rf"(?:巨人|ジャイアンツ)\s*[・･]?\s*{_re.escape(notice_subject)}\s*({role_pattern})",
            rf"{_re.escape(notice_subject)}\s*({role_pattern})",
        )
        for pattern in patterns:
            match = _re.search(pattern, source_text)
            if match:
                return match.group(1)
    return _extract_player_position(title, summary)


def _extract_subject_label(title: str, summary: str, category: str) -> str:
    text = f"{_strip_html(title)} {_strip_html(summary)}"
    subject_name_pattern = r"[A-Za-zＡ-Ｚａ-ｚ一-龥々ァ-ヴー・･\.\-．]{2,24}"
    japanese_subject_pattern = r"[一-龥々ァ-ヴー]{2,8}"
    staff_suffix_pattern = r"(?:監督|(?:投手|打撃|守備|総合|ヘッド|チーフ|作戦)?コーチ)"
    player_role_pattern = rf"({subject_name_pattern}\s*(?:投手|捕手|内野手|外野手|選手))"
    staff_role_pattern = rf"({subject_name_pattern}\s*{staff_suffix_pattern})"
    priority_patterns = [
        rf"^({subject_name_pattern})(?:(?:投手|捕手|内野手|外野手|選手)?)(?:が|は|、|「)(?=.{{0,60}}(?:「|$))",
        rf"(?:初先発の|先発の|(?:今日の)?先発は|選んだのは)({subject_name_pattern})(?:(?:投手|捕手|内野手|外野手|選手)?(?:が|は|を|に|で|、|「))?",
        rf"({japanese_subject_pattern}[・･][一-龥々ァ-ヴー]{1,8})(?:が|は|を|に|で|、)",
    ]
    named_subject_patterns = [
        rf"(?:巨人|ジャイアンツ)(?:】|の|・|[\s　])?({subject_name_pattern})(?:(?:投手|捕手|内野手|外野手|選手|{staff_suffix_pattern})?(?:が|は|を|に|で|、|「))",
        rf"^({japanese_subject_pattern})(?:(?:投手|捕手|内野手|外野手|選手)?)(?:が|は|、|「)(?=.{{0,60}}「)",
        rf"(?:初戦は|第[0-9一二三四五六七八九十]+戦は|復帰は|昇格は|登録は|抹消は)({japanese_subject_pattern})(?:(?:投手|捕手|内野手|外野手|選手)?(?:が|は|を|に|で|、|「))?",
        rf"({japanese_subject_pattern})(?:(?:投手|捕手|内野手|外野手|選手)?(?:が|は|を|に|で|、|「))(?:先発|調整|復帰|昇格|登録|抹消|語った|明かした|狙う|務める|濃厚|有力|予定|見込み)",
    ]
    patterns = [r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})"]
    if category == "選手情報":
        patterns = [
            player_role_pattern,
            staff_role_pattern,
        ] + named_subject_patterns + patterns
    elif category == "首脳陣":
        patterns = [
            staff_role_pattern,
            player_role_pattern,
        ] + named_subject_patterns + patterns
    else:
        patterns = [player_role_pattern, staff_role_pattern] + named_subject_patterns + patterns

    def _is_valid_subject_candidate(label: str) -> bool:
        if not label:
            return False
        if label in SUBJECT_LABEL_STOPWORDS:
            return False
        if any(stop in label for stop in SUBJECT_CANDIDATE_STOPWORDS):
            return False
        if label.endswith(SUBJECT_CANDIDATE_SUFFIX_STOPWORDS):
            return False
        if _re.search(r"\d", label):
            return False
        return True

    def _find_subject(source_text: str) -> str:
        for pattern in priority_patterns:
            for match in _re.finditer(pattern, source_text):
                label = _re.sub(r"\s+", "", match.group(1)).strip("・･")
                if label.startswith("巨人") and len(label) > 4:
                    label = label[2:].strip("・･")
                label = _re.sub(r"(投手|捕手|内野手|外野手|選手)$", "", label).strip()
                if _is_valid_subject_candidate(label):
                    return label

        for pattern in patterns:
            matches = list(_re.finditer(pattern, source_text))
            if not matches:
                continue
            iterator = reversed(matches) if pattern in named_subject_patterns else matches
            for match in iterator:
                label = _re.sub(r"\s+", "", match.group(1)).strip("・･")
                if label.startswith("巨人") and len(label) > 4:
                    label = label[2:].strip("・･")
                label = _re.sub(r"(投手|捕手|内野手|外野手|選手)$", "", label).strip()
                if not _is_valid_subject_candidate(label):
                    continue
                return label
        return ""

    label = _find_subject(text)
    if label:
        return label

    summary_text = _strip_html(summary)
    if summary_text:
        summary_label = _find_subject(summary_text)
        if summary_label:
            summary_label = _re.sub(r"(投手|捕手|内野手|外野手|選手)$", "", summary_label).strip()
        if summary_label and summary_label not in {"巨人", "選手", "首脳陣"}:
            return summary_label
        summary_match = _re.search(
            rf"^({japanese_subject_pattern})(?:投手|捕手|内野手|外野手|選手)?(?:が|は|も)",
            summary_text,
        )
        if summary_match:
            summary_label = _re.sub(r"\s+", "", summary_match.group(1)).strip("・･")
            if summary_label.startswith("巨人") and len(summary_label) > 4:
                summary_label = summary_label[2:].strip("・･")
            if _is_valid_subject_candidate(summary_label) and summary_label not in {"巨人", "選手", "首脳陣"}:
                return summary_label
    if category == "首脳陣":
        return "首脳陣"
    if category == "選手情報":
        return "選手"
    return "巨人"


def _compact_subject_label(title: str, summary: str, category: str) -> str:
    subject = _extract_subject_label(title, summary, category)
    subject = _re.sub(r"(投手|捕手|内野手|外野手|監督|コーチ)$", "", subject).strip()
    if subject in {"", "巨人", "選手", "首脳陣"}:
        return ""
    return subject if len(subject) <= 6 else ""


def _player_family_name_alias(title: str, summary: str, category: str) -> str:
    subject = _compact_subject_label(title, summary, category)
    if not subject or not _re.fullmatch(r"[一-龥々ァ-ヴー]{4,8}", subject):
        return ""
    family_name = subject[:2]
    if family_name in AMBIGUOUS_PLAYER_SURNAMES:
        return ""
    return family_name


def _build_safe_summary_snippet(title: str, summary: str) -> str:
    facts = _extract_summary_sentences(summary, max_sentences=2)
    if facts:
        return "。".join(facts).rstrip("。") + "。"
    title_text = _strip_title_prefix(title)
    if title_text:
        return f"{title_text}。"
    return "巨人の最新ニュースを整理します。"


def _extract_post_title_text(post: dict) -> str:
    title_data = (post or {}).get("title") or {}
    if isinstance(title_data, dict):
        return _strip_html(title_data.get("rendered") or title_data.get("raw") or "")
    return _strip_html(str(title_data or ""))


def _extract_post_excerpt_text(post: dict) -> str:
    excerpt_data = (post or {}).get("excerpt") or {}
    if isinstance(excerpt_data, dict):
        return _strip_html(excerpt_data.get("rendered") or excerpt_data.get("raw") or "")
    return _strip_html(str(excerpt_data or ""))


def _parse_wp_post_datetime(post: dict) -> datetime | None:
    for field in ("date_gmt", "date"):
        raw = (post or {}).get(field)
        if not raw:
            continue
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=JST)
        return parsed.astimezone(timezone.utc)
    return None


def _resolve_related_story_subtype(
    title: str,
    summary: str,
    category: str,
    article_subtype: str,
    has_game: bool,
) -> str:
    if category == "選手情報":
        special_story_kind = _detect_player_special_template_kind(title, summary)
        if special_story_kind in {"player_notice", "player_recovery"}:
            return special_story_kind
    return article_subtype or _detect_article_subtype(title, summary, category, has_game)


def _candidate_related_story_subtype(post: dict, category: str, has_game: bool) -> str:
    title = _extract_post_title_text(post)
    summary = _extract_post_excerpt_text(post)
    base_subtype = _detect_article_subtype(title, summary, category, has_game)
    return _resolve_related_story_subtype(title, summary, category, base_subtype, has_game)


def _search_recent_publish_posts(
    wp: WPClient,
    *,
    search: str = "",
    category_id: int = 0,
    per_page: int = 5,
    after_iso: str = "",
) -> list[dict]:
    import requests

    params = {
        "status": "publish",
        "per_page": per_page,
        "orderby": "date",
        "order": "desc",
        "_fields": "id,date,date_gmt,link,title,excerpt,categories",
    }
    if search:
        params["search"] = search
    if category_id:
        params["categories"] = category_id
    if after_iso:
        params["after"] = after_iso

    resp = requests.get(
        f"{wp.api}/posts",
        params=params,
        auth=wp.auth,
        timeout=30,
    )
    wp._raise_for_status(resp, "関連記事検索")
    return resp.json()


def _select_related_posts(
    *,
    player_posts: list[dict],
    subtype_posts: list[dict],
    category_posts: list[dict],
    player_subject: str,
    current_title: str,
    current_url: str,
    category: str,
    article_subtype: str,
    has_game: bool,
    max_items: int = 2,
    now: datetime | None = None,
) -> list[dict]:
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    cutoff = now_utc - timedelta(days=30)
    current_title_norm = WPClient._normalize_title(current_title)
    selected: list[dict] = []
    seen_ids: set[int] = set()
    seen_links: set[str] = set()

    def _maybe_add(post: dict, *, require_player: bool = False, require_subtype: bool = False) -> None:
        if len(selected) >= max_items:
            return
        title_text = _extract_post_title_text(post)
        if not title_text:
            return
        title_norm = WPClient._normalize_title(title_text)
        link = str((post or {}).get("link") or "").strip()
        post_id = int((post or {}).get("id") or 0)
        if current_title_norm and title_norm == current_title_norm:
            return
        if current_url and link and link == current_url:
            return
        if post_id and post_id in seen_ids:
            return
        if link and link in seen_links:
            return

        published_at = _parse_wp_post_datetime(post)
        if published_at and published_at < cutoff:
            return

        if require_player and player_subject and player_subject not in title_text:
            return
        if require_subtype:
            candidate_subtype = _candidate_related_story_subtype(post, category, has_game)
            if candidate_subtype != article_subtype:
                return

        selected.append(
            {
                "id": post_id,
                "title": title_text,
                "link": link,
                "published_at": published_at.isoformat() if published_at else "",
            }
        )
        if post_id:
            seen_ids.add(post_id)
        if link:
            seen_links.add(link)

    for post in player_posts or []:
        _maybe_add(post, require_player=True)
    for post in subtype_posts or []:
        _maybe_add(post, require_subtype=True)
    for post in category_posts or []:
        _maybe_add(post)
    return selected


def _find_related_posts_for_article(
    *,
    title: str,
    summary: str,
    category: str,
    article_subtype: str,
    current_url: str,
    has_game: bool,
    max_items: int = 2,
    wp_factory=WPClient,
    search_posts=None,
    now: datetime | None = None,
) -> list[dict]:
    logger = logging.getLogger("rss_fetcher")
    try:
        wp = wp_factory()
    except Exception as e:
        logger.info("関連記事検索をスキップ: WP 初期化失敗: %s", e)
        return []

    try:
        category_id = wp.resolve_category_id(category)
    except Exception as e:
        logger.info("関連記事検索をスキップ: カテゴリ解決失敗: %s", e)
        category_id = 0

    after_iso = ((now or datetime.now(timezone.utc)).astimezone(timezone.utc) - timedelta(days=30)).isoformat()
    search_callable = search_posts or (
        lambda *, search="", category_id=0, per_page=5, after_iso="": _search_recent_publish_posts(
            wp,
            search=search,
            category_id=category_id,
            per_page=per_page,
            after_iso=after_iso,
        )
    )

    player_subject = _compact_subject_label(title, summary, category)
    player_posts: list[dict] = []
    category_posts: list[dict] = []

    if player_subject:
        try:
            player_posts = search_callable(search=player_subject, category_id=0, per_page=5, after_iso=after_iso) or []
        except Exception as e:
            logger.warning("関連記事検索失敗: player_subject=%s error=%s", player_subject, e)
            player_posts = []

    if category_id:
        try:
            category_posts = search_callable(search="", category_id=category_id, per_page=10, after_iso=after_iso) or []
        except Exception as e:
            logger.warning("関連記事検索失敗: category=%s error=%s", category, e)
            category_posts = []

    return _select_related_posts(
        player_posts=player_posts,
        subtype_posts=category_posts,
        category_posts=category_posts,
        player_subject=player_subject,
        current_title=title,
        current_url=current_url,
        category=category,
        article_subtype=article_subtype,
        has_game=has_game,
        max_items=max_items,
        now=now,
    )


def _build_related_posts_section(related_posts: list[dict]) -> str:
    if not related_posts:
        return ""

    items_html = []
    for post in related_posts[:2]:
        title = (post.get("title") or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        link = (post.get("link") or "").replace("&", "&amp;")
        if not title or not link:
            continue
        items_html.append(
            '<li style="margin:0 0 10px;line-height:1.65;">'
            f'<a href="{link}" style="font-weight:700;text-decoration:none;color:#001e62;" target="_blank" rel="noopener noreferrer">{title}</a>'
            '</li>'
        )
    if not items_html:
        return ""

    return (
        '<!-- wp:html -->\n'
        '<div class="yoshilover-related-posts" style="border:1px solid #e6e6e6;border-radius:12px;padding:16px 18px;margin:12px 0;background:#fff;">'
        '<div style="font-size:1.02em;font-weight:800;color:#111;margin:0 0 10px;">【関連記事】</div>'
        '<ul style="margin:0;padding-left:1.2em;">'
        f'{"".join(items_html)}'
        '</ul>'
        '</div>\n'
        '<!-- /wp:html -->\n\n'
    )


def _player_article_is_mechanics_story(title: str, summary: str) -> bool:
    return _detect_player_article_mode(title, summary, "選手情報") == "player_mechanics"


def _ensure_fact_sentence(text: str, default: str = "") -> str:
    clean = _collapse_ws(_strip_html(text or "")).strip(" ・\t")
    if not clean:
        return default
    return clean if clean.endswith(("。", "！", "？")) else f"{clean}。"


def _extract_player_position(title: str, summary: str) -> str:
    source_text = _strip_html(f"{title} {summary}")
    subject = _extract_subject_label(title, summary, "選手情報")
    for role in PLAYER_ROLE_SUFFIXES:
        if subject.endswith(role):
            return role
    base_name = _compact_subject_label(title, summary, "選手情報")
    if base_name:
        nearby = _re.search(rf"{_re.escape(base_name)}\s*({'|'.join(PLAYER_ROLE_SUFFIXES)})", source_text)
        if nearby:
            return nearby.group(1)
    if any(marker in source_text for marker in PLAYER_CATCHER_HINT_MARKERS):
        return "捕手"
    if any(marker in source_text for marker in PLAYER_PITCHER_HINT_MARKERS):
        return "投手"
    if any(marker in source_text for marker in PLAYER_OUTFIELDER_HINT_MARKERS):
        return "外野手"
    if any(marker in source_text for marker in PLAYER_INFIELDER_HINT_MARKERS):
        return "内野手"
    return "選手"


def _extract_player_role_label(title: str, summary: str) -> str:
    name = _compact_subject_label(title, summary, "選手情報")
    role = _extract_player_position(title, summary)
    if not name:
        return f"この{role}"
    return f"{name}{role}"


def _player_team_query_subject(title: str, summary: str, subject: str) -> str:
    role_label = _extract_player_role_label(title, summary)
    if (
        role_label
        and not role_label.startswith("この")
        and role_label.endswith(("投手", "捕手", "内野手", "外野手"))
    ):
        return role_label
    return subject


def _extract_prompt_fact_sentences(title: str, summary: str, max_sentences: int = 5) -> list[str]:
    pieces = []
    for part in _re.split(r"[。！？\n]+", _strip_html(summary)):
        clean = part.strip(" ・\t")
        if clean:
            pieces.append(clean)
    title_fact = _strip_title_prefix(title)
    if title_fact:
        pieces.append(title_fact)

    deduped = []
    seen = set()
    for piece in pieces:
        key = piece.replace(" ", "").replace("　", "")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(piece)
        if len(deduped) >= max_sentences:
            break
    return deduped


def _find_source_sentence_with_markers(title: str, summary: str, markers: tuple[str, ...], exclude: set[str] | None = None) -> str:
    exclude = exclude or set()
    for sentence in _extract_prompt_fact_sentences(title, summary, max_sentences=5):
        fact = _ensure_fact_sentence(sentence)
        if not fact or fact in exclude:
            continue
        if any(marker in fact for marker in markers):
            return fact
    return ""


def _extract_player_mechanics_topic(title: str, summary: str) -> str:
    source_text = _strip_html(f"{title} {summary}")
    for pattern in PLAYER_MECHANICS_TOPIC_PATTERNS:
        match = _re.search(pattern, source_text)
        if match:
            return match.group(1)
    mechanics_fact = _find_source_sentence_with_markers(
        title,
        summary,
        PLAYER_MECHANICS_SPECIFIC_MARKERS + PLAYER_MECHANICS_CHANGE_MARKERS,
    )
    if mechanics_fact:
        return _strip_title_prefix(mechanics_fact).strip("。 ")
    return "技術面の修正"


def _extract_player_status_topic(title: str, summary: str) -> str:
    source_text = _strip_html(f"{title} {summary}")
    farm_context = any(marker in source_text for marker in ("二軍戦", "２軍戦", "2軍戦", "二軍", "２軍", "2軍", "ファーム", "育成"))
    for pattern, label in PLAYER_STATUS_TOPIC_PATTERNS:
        if label == "一軍昇格" and farm_context:
            continue
        if _re.search(pattern, source_text):
            return label
    if farm_context:
        if any(marker in source_text for marker in ("二軍戦", "２軍戦", "2軍戦")):
            return "二軍戦"
        if any(marker in source_text for marker in ("二軍", "２軍", "2軍", "ファーム", "育成")):
            return "調整"
    for marker in PLAYER_STATUS_MARKERS:
        if marker in {"昇格", "一軍"} and farm_context:
            continue
        if marker in source_text:
            return marker
    return "調整"


def _extract_player_quote_scene(title: str, summary: str) -> str:
    source_text = _strip_html(f"{title} {summary}")
    for pattern in PLAYER_QUOTE_SCENE_PATTERNS:
        match = _re.search(pattern, source_text)
        if match:
            return match.group(1)
    for term in _extract_player_quote_context_terms(title, summary):
        if term.endswith("戦") or "登板" in term or term in {"試合前", "甲子園", "東京ドーム"}:
            return term
    return "試合前"


def _format_source_day_label(source_published_at: datetime | None) -> str:
    if not source_published_at:
        return ""
    local_dt = source_published_at.astimezone()
    return f"{local_dt.month}月{local_dt.day}日"


def _extract_player_status_terms(title: str, summary: str) -> list[str]:
    source_text = _strip_html(f"{title} {summary}")
    return _dedupe_preserve_order([marker for marker in PLAYER_STATUS_MARKERS if marker in source_text])[:4]


def _extract_player_quote_context_terms(title: str, summary: str) -> list[str]:
    source_text = _strip_html(f"{title} {summary}")
    terms = []
    for phrase in _extract_quote_phrases(f"{title}\n{summary}", max_phrases=2):
        terms.append(phrase)
    for marker in PLAYER_QUOTE_CONTEXT_MARKERS:
        if marker in source_text:
            terms.append(marker)
    for team in NPB_TEAM_MARKERS:
        if team in {"巨人", "読売ジャイアンツ"}:
            continue
        if team in source_text:
            terms.append(team)
    return _dedupe_preserve_order([term for term in terms if term and term not in GENERIC_REACTION_TERMS])[:6]


def _detect_player_article_mode(title: str, summary: str, category: str = "選手情報") -> str:
    if category and category != "選手情報":
        return ""
    source_text = _strip_html(f"{title} {summary}")
    has_specific_mechanics = any(marker in source_text for marker in PLAYER_MECHANICS_SPECIFIC_MARKERS)
    has_change_mechanics = any(marker in source_text for marker in PLAYER_MECHANICS_CHANGE_MARKERS)
    if has_specific_mechanics and has_change_mechanics:
        return "player_mechanics"
    if _extract_quote_phrases(f"{title}\n{summary}", max_phrases=1):
        return "player_quote"
    return "player_status"


def _should_skip_stale_player_status_entry(
    category: str,
    title: str,
    summary: str,
    source_published_at: datetime | None,
    max_age_hours: int = 24,
) -> bool:
    if category != "選手情報":
        return False
    if _detect_player_article_mode(title, summary, category) != "player_status":
        return False
    if not source_published_at:
        return False
    threshold = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    return source_published_at < threshold


def _should_skip_stale_postgame_entry(
    category: str,
    title: str,
    summary: str,
    source_published_at: datetime | None,
    max_age_hours: int = 24,
) -> bool:
    if category != "試合速報":
        return False
    if not source_published_at:
        return False
    if _detect_article_subtype(title, summary, category, True) != "postgame":
        return False

    local_published = source_published_at.astimezone(JST)
    local_now = datetime.now(timezone.utc).astimezone(JST)
    if max_age_hours <= 24 and local_published.date() < local_now.date():
        return True

    threshold = datetime.now(timezone.utc) - timedelta(hours=max_age_hours)
    return source_published_at < threshold


def _game_status_indicates_started(game_status: dict | None) -> bool:
    if not game_status:
        return False
    if game_status.get("ended"):
        return True
    state = _collapse_ws(str(game_status.get("state", "")))
    if any(marker in state for marker in ("試合前", "開始前", "中止", "ノーゲーム")):
        return False
    return bool(state)


def _should_skip_started_pregame_entry(
    category: str,
    title: str,
    summary: str,
    has_game: bool,
    game_status: dict | None,
) -> bool:
    if category != "試合速報":
        return False
    if _detect_article_subtype(title, summary, category, has_game) != "pregame":
        return False
    source_text = _strip_html(f"{title} {summary}")
    if any(marker in source_text for marker in ("あす", "明日", "翌日")):
        return False
    return _game_status_indicates_started(game_status)


def _log_pregame_started_skip(
    title: str,
    summary: str,
    post_url: str,
    game_status: dict | None,
    now: datetime | None = None,
):
    reference_now = now or datetime.now(JST)
    source_text = _strip_html(f"{title} {summary}")
    payload = {
        "event": "pregame_started_skip",
        "title": title,
        "post_url": post_url,
        "first_pitch_time": _extract_game_time_token(source_text),
        "now": reference_now.isoformat(),
        "game_state": _collapse_ws(str((game_status or {}).get("state", ""))),
        "game_ended": bool((game_status or {}).get("ended")),
    }
    logging.getLogger("rss_fetcher").info(json.dumps(payload, ensure_ascii=False))


def _display_source_name(name: str) -> str:
    clean = _collapse_ws(name or "スポーツニュース")
    if not clean:
        return "スポーツニュース"

    brand = ""
    for marker, label in SOURCE_BRAND_LABELS:
        if marker in clean:
            brand = label
            break

    if not brand:
        return clean
    if clean == brand or clean.startswith(f"{brand} / ") or clean.startswith(f"{brand}（"):
        return clean
    if clean.endswith("X") or "公式X" in clean or "巨人班X" in clean:
        return f"{brand} / {clean}"
    if "巨人" in clean and brand not in clean:
        return f"{brand} / {clean}"
    return clean


def _infer_social_source_indicator(source_name: str, tweet_url: str = "") -> str:
    clean = _collapse_ws(source_name or "")
    handle = _extract_handle_from_tweet_url(tweet_url).lower().lstrip("@")
    official_markers = (
        "公式",
        "tokyogiants",
        "giants_official",
        "yomiuri",
        "npb",
        "ジャイアンツタウン",
    )
    media_markers = (
        "報知",
        "スポーツ報知",
        "スポニチ",
        "sponichi",
        "日刊スポーツ",
        "nikkansports",
        "サンスポ",
        "sanspo",
        "full-count",
        "baseball king",
    )
    if any(marker.lower() in clean.lower() for marker in official_markers) or any(marker in handle for marker in ("tokyogiants", "npb")):
        return "official"
    if any(marker.lower() in clean.lower() for marker in media_markers) or any(
        marker in handle for marker in ("hochi", "sponichi", "sanspo", "nikkansports", "fullcount", "baseballking")
    ):
        return "media"
    return "player"


def _social_source_intro_label(source_name: str, tweet_url: str = "") -> str:
    display = _display_source_name(source_name or "X")
    indicator = _infer_social_source_indicator(source_name, tweet_url=tweet_url)
    if indicator == "official":
        return f"{display}の投稿"
    if indicator == "media":
        return f"{display}のX投稿"
    return f"{display}本人の投稿"


def _collect_social_source_material(entry: dict | None) -> str:
    if not entry:
        return ""

    fragments: list[str] = []
    for key in ("summary", "description"):
        value = entry.get(key, "")
        if value:
            fragments.append(_clean_social_entry_text(str(value)))

    content_items = entry.get("content") or []
    if isinstance(content_items, list):
        for item in content_items:
            if isinstance(item, dict) and item.get("value"):
                fragments.append(_clean_social_entry_text(str(item.get("value"))))

    deduped: list[str] = []
    seen = set()
    total_chars = 0
    for fragment in fragments:
        clean = _collapse_ws(fragment).strip(" ・\t")
        if not clean:
            continue
        key = clean.replace(" ", "").replace("　", "")
        if key in seen:
            continue
        seen.add(key)
        remaining = 300 - total_chars
        if remaining <= 0:
            break
        if len(clean) > remaining:
            clean = clean[:remaining].rstrip()
        if clean:
            deduped.append(clean)
            total_chars += len(clean)
    return "\n".join(deduped)


def _build_source_fact_block(
    title: str,
    summary: str,
    *,
    source_type: str = "news",
    entry: dict | None = None,
    max_sentences: int = STRICT_PROMPT_MAX_SOURCE_FACTS,
    max_quotes: int = STRICT_PROMPT_MAX_QUOTES,
) -> str:
    extra_material = ""
    if source_type == "social_news":
        extra_material = _collect_social_source_material(entry)
    combined_summary = "\n".join(part for part in [summary, extra_material] if part)

    facts = _extract_source_sentences(title, combined_summary, max_sentences=max_sentences)
    for phrase in _extract_quote_phrases(f"{title}\n{combined_summary}", max_phrases=max_quotes):
        if all(phrase not in fact for fact in facts):
            facts.append(f"元記事中の表現: 「{phrase}」")
    if not facts:
        return "・元記事タイトル以外の追加事実は不明"
    return "\n".join(f"・{fact}" for fact in facts)


def _source_fact_block_metrics(
    title: str,
    summary: str,
    *,
    source_type: str = "news",
    entry: dict | None = None,
) -> tuple[str, int]:
    source_fact_block = _build_source_fact_block(title, summary, source_type=source_type, entry=entry)
    return source_fact_block, len(source_fact_block)


def _thin_source_fact_block_min_chars(source_type: str) -> int:
    if source_type == "social_news":
        return THIN_SOURCE_FACT_BLOCK_MIN_CHARS_SOCIAL_NEWS
    return THIN_SOURCE_FACT_BLOCK_MIN_CHARS_DEFAULT


def _is_thin_source_fact_block(source_type: str, source_fact_block_length: int) -> bool:
    return source_fact_block_length < _thin_source_fact_block_min_chars(source_type)


def _should_skip_thin_source_fact_block(
    *,
    draft_only: bool,
    source_type: str,
    source_fact_block_length: int,
) -> bool:
    return (not draft_only) and _is_thin_source_fact_block(source_type, source_fact_block_length)


def _log_draft_observed_thin_source(
    logger: logging.Logger,
    *,
    title: str,
    post_url: str,
    category: str,
    article_subtype: str,
    source_type: str,
    source_fact_block_length: int,
    min_chars: int,
) -> None:
    logger.info(
        json.dumps(
            {
                "event": "draft_only_thin_source_allowed",
                "title": title,
                "post_url": post_url,
                "category": category,
                "article_subtype": article_subtype,
                "source_type": source_type,
                "source_fact_block_length": source_fact_block_length,
                "min_chars": min_chars,
            },
            ensure_ascii=False,
        )
    )


def _source_mentions_outcome_terms(title: str, summary: str) -> bool:
    source_text = _strip_html(f"{title} {summary}")
    return bool(SCORE_TOKEN_RE.search(source_text) or any(word in source_text for word in NON_GAME_RESULT_WORDS))


def _has_explicit_confirmed_result(text: str) -> bool:
    clean = _strip_html(text or "")
    soft_result_words = ("勝利", "敗戦", "白星", "黒星", "引き分け")
    pregame_cues = ("狙", "目指", "かかる", "予定", "挑む", "挑戦", "あす", "明日", "翌日")
    if any(marker in clean for marker in CONFIRMED_RESULT_MARKERS):
        return True
    if any(word in clean for word in soft_result_words) and not any(cue in clean for cue in pregame_cues):
        return True
    if RESULT_MILESTONE_RE.search(clean) and not any(cue in clean for cue in pregame_cues):
        return True
    return False


def _has_lineup_core(text: str) -> bool:
    clean = _strip_html(text or "")
    if any(keyword in clean for keyword in LINEUP_CORE_KEYWORDS):
        return True
    if "打順" in clean and LINEUP_ORDER_SLOT_RE.search(clean):
        return True
    return len(LINEUP_ORDER_SLOT_RE.findall(clean)) >= 2


def _has_live_update_fragment(text: str) -> bool:
    clean = _strip_html(text or "")
    if any(keyword in clean for keyword in LIVE_UPDATE_FRAGMENT_KEYWORDS):
        return True
    if LIVE_UPDATE_PITCHER_ORDER_RE.search(clean):
        return True
    return bool(LIVE_UPDATE_INNING_RE.search(clean))


def _is_farm_lineup_text(text: str) -> bool:
    clean = _strip_html(text or "")
    return bool(_has_lineup_core(clean) and any(marker in clean for marker in FARM_LINEUP_MARKERS))


def _parse_yahoo_team_batting_stats(html: str) -> dict[str, dict]:
    stats = {}
    for cells in _extract_html_table_rows(html):
        if len(cells) < 20 or cells[0] == "位置" or cells[2] == "選手名":
            continue
        name = cells[2]
        key = _normalize_player_name_key(name)
        if not key:
            continue
        stats[key] = {
            "name": _collapse_ws(name),
            "avg": cells[3],
            "hr": cells[10],
            "rbi": cells[12],
            "sb": cells[19],
        }
    return stats


def _extract_async_starting_section(html: str) -> str:
    start = (html or "").find('<div id="async-starting">')
    if start == -1:
        return ""
    end = (html or "").find('<div id="async-bench">', start)
    if end == -1:
        end = len(html or "")
    return (html or "")[start:end]


def _extract_opponent_name_from_game_html(html: str, team_label: str = "巨人") -> str:
    clean_html = html or ""
    versus_match = _re.search(r'(?:巨人|読売)[^<]{0,40}(?:vs|VS|対)\s*([^<\s]+)', clean_html)
    if versus_match:
        opponent = versus_match.group(1).strip()
        if opponent and opponent not in {team_label, "読売ジャイアンツ"}:
            return opponent

    team_names = [
        _collapse_ws(name)
        for name in _re.findall(r'class="[^"]*bb-gameScoreTable__teamName[^"]*"[^>]*>([^<]+)<', clean_html)
    ]
    for team_name in team_names:
        if team_name and team_name not in {team_label, "読売ジャイアンツ"}:
            return team_name

    for marker in NPB_TEAM_MARKERS:
        if marker in {team_label, "読売ジャイアンツ"}:
            continue
        if marker in clean_html:
            return marker
    return ""


def _parse_yahoo_starting_lineup(html: str, team_label: str = "巨人", opponent_label: str = "") -> list[dict]:
    section = _extract_async_starting_section(html)
    if not section:
        return []

    team_markers = [team_label, "読売ジャイアンツ"]
    start = -1
    for marker in team_markers:
        idx = section.find(marker)
        if idx != -1 and (start == -1 or idx < start):
            start = idx
    if start == -1:
        return []

    end = len(section)
    for marker in [opponent_label, *NPB_TEAM_MARKERS]:
        if not marker or marker == team_label:
            continue
        idx = section.find(marker, start + len(team_label))
        if idx != -1:
            end = min(end, idx)
    team_section = section[start:end]

    rows = []
    for cells in _extract_html_table_rows(team_section):
        if len(cells) < 5:
            continue
        order = cells[0]
        if not _re.fullmatch(r"[1-9]", order):
            continue
        avg = cells[4] if len(cells) >= 6 else cells[-1]
        if not (avg == "-" or _re.fullmatch(r"[\.．]?\d{3}", avg)):
            continue
        rows.append({
            "order": order,
            "position": cells[1],
            "name": _collapse_ws(cells[2]),
            "avg": avg.replace("．", "."),
        })
    return rows


def _merge_lineup_rows_with_stats(lineup_rows: list[dict], team_stats: dict[str, dict]) -> list[dict]:
    merged = []
    for row in lineup_rows:
        key = _normalize_player_name_key(row.get("name", ""))
        stat = team_stats.get(key, {})
        merged.append({
            "order": row.get("order", ""),
            "position": row.get("position", ""),
            "name": row.get("name", ""),
            "avg": stat.get("avg") or row.get("avg", "-"),
            "hr": stat.get("hr", "-"),
            "rbi": stat.get("rbi", "-"),
            "sb": stat.get("sb", "-"),
        })
    return merged


def _extract_yahoo_scoreboard_section(html: str) -> str:
    start = (html or "").find('<table id="ing_brd"')
    if start == -1:
        return ""
    end = (html or "").find("</table>", start)
    if end == -1:
        return ""
    return (html or "")[start:end + len("</table>")]


def _parse_yahoo_game_status(html: str, team_label: str = "巨人") -> dict:
    clean_html = html or ""
    state_match = _re.search(
        r'<p class="bb-gameCard__state">\s*(?:<a [^>]+>|<span>)\s*([^<]+)\s*(?:</a>|</span>)',
        clean_html,
        _re.DOTALL,
    )
    state = _collapse_ws(state_match.group(1)) if state_match else ""
    ended = any(marker in state for marker in ("試合終了", "ゲームセット"))

    team_names = [
        _collapse_ws(name)
        for name in _re.findall(r'<span class="bb-gameTeam__name">([^<]+)</span>', clean_html)
    ]
    home_team = team_names[0] if len(team_names) >= 1 else ""
    away_team = team_names[1] if len(team_names) >= 2 else ""

    top_scores = _re.findall(r'bb-gameTeam__(?:home|away)Score">([^<]+)<', clean_html)
    home_score = _collapse_ws(top_scores[0]) if len(top_scores) >= 1 else ""
    away_score = _collapse_ws(top_scores[1]) if len(top_scores) >= 2 else ""

    totals = {}
    scoreboard = _extract_yahoo_scoreboard_section(clean_html)
    if scoreboard:
        for cells in _extract_html_table_rows(scoreboard):
            if len(cells) < 4:
                continue
            team_name = _collapse_ws(cells[0])
            if not team_name or team_name in {"", "1", "2", "3", "4", "5", "6", "7", "8", "9"}:
                continue
            totals[team_name] = {
                "score": _collapse_ws(cells[-3]) if len(cells) >= 3 else "",
                "hits": _collapse_ws(cells[-2]) if len(cells) >= 2 else "",
                "errors": _collapse_ws(cells[-1]) if len(cells) >= 1 else "",
            }

    opponent = ""
    if home_team == team_label:
        opponent = away_team
    elif away_team == team_label:
        opponent = home_team
    else:
        opponent = _extract_opponent_name_from_game_html(clean_html, team_label=team_label)

    giants_is_home = home_team == team_label
    giants_score = home_score if giants_is_home else away_score
    opponent_score = away_score if giants_is_home else home_score

    giants_totals = totals.get(team_label, {})
    opponent_totals = totals.get(opponent, {}) if opponent else {}
    if giants_totals.get("score"):
        giants_score = giants_totals["score"]
    if opponent_totals.get("score"):
        opponent_score = opponent_totals["score"]

    return {
        "state": state,
        "ended": ended,
        "home_team": home_team,
        "away_team": away_team,
        "opponent": opponent,
        "giants_score": giants_score,
        "opponent_score": opponent_score,
        "giants_hits": giants_totals.get("hits", ""),
        "opponent_hits": opponent_totals.get("hits", ""),
        "giants_errors": giants_totals.get("errors", ""),
        "opponent_errors": opponent_totals.get("errors", ""),
    }


def fetch_giants_batting_stats_from_yahoo() -> dict[str, dict]:
    import urllib.request as _ur

    url = f"https://baseball.yahoo.co.jp/npb/teams/{GIANTS_YAHOO_TEAM_ID}/memberlist?kind=b"
    req = _ur.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with _ur.urlopen(req, timeout=10) as res:
        html = res.read().decode("utf-8", errors="ignore")
    return _parse_yahoo_team_batting_stats(html)


def _format_team_batting_stats_block(team_stats: dict) -> str:
    if not team_stats or not isinstance(team_stats, dict):
        return ""

    def _parse_avg(value) -> float | None:
        text = _collapse_ws(str(value or "")).replace("．", ".")
        if not text or text == "-":
            return None
        if text.startswith("."):
            text = f"0{text}"
        try:
            return float(text)
        except (TypeError, ValueError):
            return None

    def _parse_int(value) -> int | None:
        text = _collapse_ws(str(value or "")).replace(",", "")
        if not text or text == "-":
            return None
        match = _re.search(r"-?\d+", text)
        if not match:
            return None
        try:
            return int(match.group(0))
        except (TypeError, ValueError):
            return None

    try:
        rows = []
        for entry in team_stats.values():
            if not isinstance(entry, dict):
                continue
            name = _collapse_ws(entry.get("name") or "")
            if not name:
                continue
            avg_value = _parse_avg(entry.get("avg"))
            hr_value = _parse_int(entry.get("hr"))
            rbi_value = _parse_int(entry.get("rbi"))
            rows.append(
                {
                    "name": name,
                    "avg_value": avg_value,
                    "avg_display": _collapse_ws(entry.get("avg") or "").replace("．", ".") if avg_value is not None else "-",
                    "hr_display": str(hr_value) if hr_value is not None else "-",
                    "rbi_value": rbi_value,
                    "rbi_display": str(rbi_value) if rbi_value is not None else "-",
                }
            )
        if not rows:
            return ""
        rows.sort(
            key=lambda item: (
                item["avg_value"] is None,
                -(item["avg_value"] if item["avg_value"] is not None else 0.0),
                -(item["rbi_value"] if item["rbi_value"] is not None else -1),
                item["name"],
            )
        )
        return "\n".join(
            f"・{row['name']} {row['avg_display']} / {row['hr_display']}本 / {row['rbi_display']}打点"
            for row in rows[:5]
        )
    except Exception:
        return ""


def _normalize_target_day(target_day: str | None = None) -> str:
    clean = (target_day or "").strip()
    if _re.fullmatch(r"\d{8}", clean):
        return clean
    if _re.fullmatch(r"\d{4}-\d{2}-\d{2}", clean):
        return clean.replace("-", "")
    return datetime.now().strftime("%Y%m%d")


def _extract_giants_game_from_yahoo_team_schedule_html(html: str) -> tuple[str, str, str]:
    marker = "bb-calendarTable__package--today"
    idx = html.find(marker)
    if idx == -1:
        return "", "", ""

    window = html[idx:idx + 2500]
    if any(ng in window for ng in ["中止", "ノーゲーム", "試合はありません"]):
        return "", "", ""

    game_match = _re.search(r"/npb/game/(\d+)/index", window)
    opponent_match = _re.search(r'bb-calendarTable__versusLogo[^>]*>([^<]+)<', window)
    venue_match = _re.search(r'bb-calendarTable__venue">([^<]+)<', window)
    if not game_match:
        return "", "", ""
    opponent = opponent_match.group(1).strip() if opponent_match else ""
    venue = venue_match.group(1).strip() if venue_match else ""
    return game_match.group(1), opponent, venue


def _extract_giants_game_from_yahoo_month_schedule_html(html: str) -> tuple[str, str, str]:
    rows = _re.findall(
        r'(<tr class="bb-scheduleTable__row bb-scheduleTable__row--today">.*?</tr>)',
        html,
        _re.DOTALL,
    )
    for row in rows:
        if any(ng in row for ng in ["中止", "ノーゲーム", "試合はありません"]):
            continue
        if "巨人" not in row and "/npb/teams/1/" not in row:
            continue

        team_names = _re.findall(r'bb-scheduleTable__(?:home|away)Name">\s*<a [^>]+>([^<]+)</a>', row)
        if len(team_names) < 2:
            continue

        home_team, away_team = [name.strip() for name in team_names[:2]]
        if home_team == "巨人":
            opponent = away_team
        elif away_team == "巨人":
            opponent = home_team
        else:
            continue

        game_match = _re.search(r"/npb/game/(\d+)/index", row)
        venue_match = _re.search(r'bb-scheduleTable__data--stadium">\s*([^<]+)\s*<', row)
        if not game_match:
            continue
        venue = venue_match.group(1).strip() if venue_match else ""
        return game_match.group(1), opponent, venue

    return "", "", ""


def _find_giants_game_info_yahoo(target_day: str | None = None) -> tuple[str, str, str]:
    import urllib.request as _ur

    today = _normalize_target_day(target_day)
    logger = logging.getLogger("rss_fetcher")
    urls = [
        f"https://baseball.yahoo.co.jp/npb/teams/{GIANTS_YAHOO_TEAM_ID}/schedule/",
        f"https://baseball.yahoo.co.jp/npb/schedule/?year={today[:4]}&month={today[4:6]}",
    ]

    for url in urls:
        try:
            req = _ur.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with _ur.urlopen(req, timeout=10) as res:
                html = res.read(200000).decode("utf-8", errors="ignore")
        except Exception as e:
            logger.warning(f"Yahoo試合日チェック失敗 {url}: {e}")
            continue

        if f"/npb/teams/{GIANTS_YAHOO_TEAM_ID}/schedule/" in url:
            game_id, opponent, venue = _extract_giants_game_from_yahoo_team_schedule_html(html)
            if game_id:
                return game_id, opponent, venue
        else:
            game_id, opponent, venue = _extract_giants_game_from_yahoo_month_schedule_html(html)
            if game_id:
                return game_id, opponent, venue

    return "", "", ""


def _find_today_giants_game_info_yahoo() -> tuple[str, str, str]:
    return _find_giants_game_info_yahoo()


def fetch_giants_lineup_stats_from_yahoo(target_day: str | None = None, game_id: str = "", opponent: str = "") -> list[dict]:
    import urllib.request as _ur

    resolved_game_id = game_id
    resolved_opponent = opponent
    if not resolved_game_id:
        resolved_game_id, resolved_opponent, _venue = _find_giants_game_info_yahoo(target_day)
    if not resolved_game_id:
        return []

    url = f"https://baseball.yahoo.co.jp/npb/game/{resolved_game_id}/top"
    req = _ur.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with _ur.urlopen(req, timeout=10) as res:
        html = res.read().decode("utf-8", errors="ignore")

    lineup_rows = _parse_yahoo_starting_lineup(html, team_label="巨人", opponent_label=resolved_opponent)
    if not lineup_rows:
        return []

    try:
        team_stats = fetch_giants_batting_stats_from_yahoo()
    except Exception as e:
        logging.getLogger("rss_fetcher").warning("巨人打撃成績の取得失敗: %s", e)
        team_stats = {}
    return _merge_lineup_rows_with_stats(lineup_rows, team_stats)


def fetch_today_giants_lineup_stats_from_yahoo() -> list[dict]:
    return fetch_giants_lineup_stats_from_yahoo()


def fetch_giants_lineup_stats_for_game(game_id: str, opponent: str = "") -> list[dict]:
    return fetch_giants_lineup_stats_from_yahoo(game_id=game_id, opponent=opponent)


def fetch_giants_game_status_from_yahoo(target_day: str | None = None, game_id: str = "", opponent: str = "") -> dict:
    import urllib.request as _ur

    resolved_game_id = game_id
    resolved_opponent = opponent
    if not resolved_game_id:
        resolved_game_id, resolved_opponent, _venue = _find_giants_game_info_yahoo(target_day)
    if not resolved_game_id:
        return {}

    url = f"https://baseball.yahoo.co.jp/npb/game/{resolved_game_id}/top"
    req = _ur.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with _ur.urlopen(req, timeout=10) as res:
        html = res.read().decode("utf-8", errors="ignore")

    status = _parse_yahoo_game_status(html, team_label="巨人")
    status["game_id"] = resolved_game_id
    if not status.get("opponent") and resolved_opponent:
        status["opponent"] = resolved_opponent
    status["post_url"] = url
    return status


def fetch_today_giants_game_status_from_yahoo() -> dict:
    return fetch_giants_game_status_from_yahoo()


def _detect_article_subtype(title: str, summary: str, category: str, has_game: bool) -> str:
    text = _strip_html(f"{title} {summary}")
    if _is_farm_lineup_text(text):
        return "farm_lineup"
    if category == "試合速報":
        if _has_explicit_confirmed_result(text):
            return "postgame"
        if _has_live_update_fragment(text):
            return "live_update"
        if SCORE_TOKEN_RE.search(text):
            return "postgame"
        if _has_lineup_core(text):
            return "lineup"
        if has_game:
            return "pregame"
        subtype = "game_note"
    elif category == "ドラフト・育成":
        subtype = "farm"
    elif category == "首脳陣":
        subtype = "manager"
    elif category == "補強・移籍":
        subtype = "roster"
    elif category == "選手情報":
        subtype = "player"
    else:
        subtype = "general"

    if subtype in {"game_note", "general"}:
        score = _extract_game_score_token(text)
        opponent = _extract_game_opponent_label(text)
        if score and opponent:
            # Keep result-shaped leftovers on the postgame rail instead of a generic default.
            return "postgame"
        if any(marker in text for marker in FACT_NOTICE_PRIMARY_MARKERS):
            # Correction or retraction markers are safer to park in the fact_notice shell.
            return "fact_notice"
    return subtype


def _is_promotional_video_entry(title: str, summary: str) -> bool:
    title_text = _strip_html(title or "")
    summary_text = _strip_html(summary or "")
    if not any(marker in title_text for marker in VIDEO_PROMO_TITLE_MARKERS):
        return False
    promo_text = f"{title_text} {summary_text}"
    return any(marker in promo_text for marker in VIDEO_PROMO_SUMMARY_MARKERS)


def _next_unused_source_fact(title: str, summary: str, used_facts: set[str]) -> str:
    for sentence in _extract_prompt_fact_sentences(title, summary, max_sentences=5):
        fact = _ensure_fact_sentence(sentence)
        if fact and fact not in used_facts:
            return fact
    return ""


def _build_player_quote_strict_prompt(title: str, summary: str) -> str:
    player_role = _extract_player_role_label(title, summary)
    scene = _extract_player_quote_scene(title, summary)
    quote = _extract_quote_phrases(f"{title}\n{summary}", max_phrases=1)
    quote_text = quote[0] if quote else _strip_title_prefix(title)[:24]
    enhanced_rules = _enhanced_player_prompt_rules("player_quote")
    return f"""あなたは読売ジャイアンツ専門ブログの編集者です。
以下の番号付き事実のみ使用可です。それ以外の情報・解釈・感想・一般論を含む文は出力しないでください。
1. {player_role}は読売ジャイアンツ所属である。
2. {player_role}が{scene}に向け「{quote_text}」と話した。{scene}に向けた考え方として出たコメントである。
3. 試合前コメントの記事である。
ですます調、300〜400文字で書いてください。
見出しは【ニュースの整理】と【次の注目】の2つのみです。それ以外の見出しを書いたら出力失敗です。
【ニュースの整理】では、何を言ったかと、どの場面に向けた言葉かだけを書いてください。
【次の注目】では、試合の入り方にこの意識がどう出るかだけを書いてください。
事実にない単語を1つでも足さないでください。事実の言い換えと、次の試合で見るべき点だけで構成してください。
筆者の評価・感想・印象は書かないでください。
【次の注目】内の全ての文で「注目されます」「注目が集まります」「期待されます」は使用禁止です。文末は「〜に注目です」「〜がポイントです」「〜を見たいところです」のどれかで終えてください。
{enhanced_rules}\
本文だけを出力してください。
"""


def _build_player_mechanics_strict_prompt(title: str, summary: str) -> str:
    player_role = _extract_player_role_label(title, summary)
    topic = _extract_player_mechanics_topic(title, summary)
    enhanced_rules = _enhanced_player_prompt_rules("player_mechanics")
    topic_fact = _ensure_fact_sentence(f"{player_role}が{topic}に取り組んでいる。")
    change_fact = _find_source_sentence_with_markers(
        title,
        summary,
        PLAYER_MECHANICS_SPECIFIC_MARKERS + PLAYER_MECHANICS_CHANGE_MARKERS,
        exclude={topic_fact},
    )
    used_facts = {fact for fact in [topic_fact, change_fact] if fact}
    context_fact = _next_unused_source_fact(title, summary, used_facts)
    if not change_fact:
        change_fact = _next_unused_source_fact(title, summary, {topic_fact}) or topic_fact
        used_facts = {fact for fact in [topic_fact, change_fact] if fact}
        context_fact = _next_unused_source_fact(title, summary, used_facts)
    if not context_fact:
        context_fact = change_fact
    return f"""あなたは読売ジャイアンツ専門ブログの編集者です。
以下の番号付き事実のみ使用可です。それ以外の情報・解釈・感想・一般論を含む文は出力しないでください。
1. {player_role}は読売ジャイアンツ所属である。
2. {player_role}が{topic}に取り組んでいる。
3. {change_fact}
4. {context_fact}
ですます調、400〜550文字で書いてください。ただし事実が薄い場合は400文字未満でも構いません。無理に話を広げないでください。
見出しは【ニュースの整理】を必ず使ってください。見出しを3つ使う場合は【ここに注目】【次の注目】の順にしてください。
【ニュースの整理】では、何を変えているかと、どの場面に向けた修正かだけを書いてください。
【ここに注目】では、事実2と事実3に書かれている修正内容を、別の言葉で言い換えずにそのまま整理してください。結果や効果は書かないでください。
【次の注目】では、次の実戦でその修正が続いているかを見る、という点だけを書いてください。
事実にない数字・比較・結果を足さないでください。
事実にない単語を1つでも足さないでください。
同じ事実を繰り返さないでください。一度書いた内容は別の見出しで再度書かないでください。
筆者の評価・感想・印象は書かないでください。
【次の注目】内の全ての文で「注目されます」「注目が集まります」「期待されます」「反映されていくか」「着目していきます」は使用禁止です。文末は「〜に注目です」「〜がポイントです」「〜を見たいところです」のどれかで終えてください。
{enhanced_rules}\
本文だけを出力してください。
"""


def _build_player_status_strict_prompt(title: str, summary: str, source_day_label: str = "") -> str:
    player_role = _extract_player_role_label(title, summary)
    status_topic = _extract_player_status_topic(title, summary)
    enhanced_rules = _enhanced_player_prompt_rules("player_status")
    status_fact = _find_source_sentence_with_markers(title, summary, PLAYER_STATUS_MARKERS)
    used_facts = {fact for fact in [status_fact] if fact}
    context_fact = _next_unused_source_fact(title, summary, used_facts)
    if not status_fact:
        status_fact = _next_unused_source_fact(title, summary, set()) or f"{player_role}が{status_topic}の状態にある。"
        used_facts = {status_fact}
        context_fact = _next_unused_source_fact(title, summary, used_facts)
    if not context_fact:
        context_fact = status_fact
    opening_time_rule = f"本文の最初は必ず「（{source_day_label}時点）」で始めてください。\n" if source_day_label else ""
    return f"""あなたは読売ジャイアンツ専門ブログの編集者です。
以下の番号付き事実のみ使用可です。それ以外の情報・解釈・感想・一般論を含む文は出力しないでください。
1. {player_role}は読売ジャイアンツ所属である。
2. {player_role}が{status_topic}の状態にある。
3. {status_fact}
4. {context_fact}
ですます調、200〜350文字で書いてください。ただし事実が薄い場合は200文字未満でも構いません。無理に話を広げないでください。
{opening_time_rule}見出しは【ニュースの整理】と【次の注目】の2つのみです。それ以外の見出しを書いたら出力失敗です。
【ニュースの整理】では、今どの状態かと、現在の登録・起用状況だけを書いてください。
【次の注目】では、投手は次回登板、野手は次の実戦出場、捕手は次の登録発表のどれか1つだけを書いてください。
事実にない数字・比較・結果を足さないでください。
事実にない単語を1つでも足さないでください。
同じ事実を繰り返さないでください。一度書いた内容は別の見出しで再度書かないでください。
筆者の評価・感想・印象は書かないでください。
【次の注目】内の全ての文で「注目されます」「注目が集まります」「期待されます」「反映されていくか」「着目していきます」は使用禁止です。文末は「〜に注目です」「〜がポイントです」「〜を見たいところです」のどれかで終えてください。
{enhanced_rules}\
本文だけを出力してください。
"""


def _is_notice_template_story(title: str, summary: str, category: str = "選手情報") -> bool:
    if category != "選手情報":
        return False
    return _detect_player_special_template_kind(title, summary) == "player_notice"


def _extract_recovery_detail_fact(title: str, summary: str, exclude: set[str] | None = None) -> str:
    markers = RECOVERY_STRONG_MARKERS + tuple(marker for marker in RECOVERY_RETURN_MARKERS if marker != "復帰")
    fact = _find_source_sentence_with_markers(title, summary, markers, exclude=exclude)
    if fact:
        return fact
    return _next_unused_source_fact(title, summary, exclude or set())


def _extract_recovery_progress_fact(title: str, summary: str, exclude: set[str] | None = None) -> str:
    markers = RECOVERY_RETURN_MARKERS + RECOVERY_PROGRESS_MARKERS
    fact = _find_source_sentence_with_markers(title, summary, markers, exclude=exclude)
    if fact:
        return fact
    return _next_unused_source_fact(title, summary, exclude or set())


def _extract_recovery_impact_fact(title: str, summary: str, exclude: set[str] | None = None) -> str:
    fact = _find_source_sentence_with_markers(title, summary, RECOVERY_IMPACT_MARKERS, exclude=exclude)
    if fact:
        return fact
    return _next_unused_source_fact(title, summary, exclude or set())


def _build_recovery_strict_prompt(title: str, summary: str, source_day_label: str = "") -> str:
    subject = _extract_recovery_subject(title, summary)
    player_position = _extract_notice_player_position(title, summary, subject)
    injury_part = _extract_recovery_injury_part(title, summary, subject)
    enhanced_rules = _enhanced_recovery_prompt_rules()
    return_timing = _extract_recovery_return_timing(title, summary, subject)
    detail_fact = _extract_recovery_detail_fact(title, summary)
    used_facts = {fact for fact in [detail_fact] if fact}
    progress_fact = _extract_recovery_progress_fact(title, summary, exclude=used_facts)
    if progress_fact:
        used_facts.add(progress_fact)
    impact_fact = _extract_recovery_impact_fact(title, summary, exclude=used_facts)
    if not impact_fact:
        impact_fact = progress_fact or detail_fact
    if not detail_fact:
        detail_fact = f"{subject}の故障や離脱の経緯は、元記事にある範囲で整理する。"
    if not progress_fact:
        progress_fact = f"{subject}のリハビリ状況と復帰見通しは、元記事で確認できる範囲に限って整理する。"
    if not impact_fact:
        impact_fact = f"{subject}が抜けた場合の起用や復帰後の役割は、元記事にある材料だけで整理する。"
    injury_label = injury_part or "故障・復帰"
    opening_time_rule = f"本文の最初は必ず「（{source_day_label}時点）」で始めてください。\n" if source_day_label else ""
    return f"""あなたは読売ジャイアンツ専門ブログの編集者です。
以下の番号付き事実のみ使用可です。それ以外の情報・解釈・感想・一般論・医療的な推測を含む文は出力しないでください。
1. {subject}は読売ジャイアンツの{player_position}である。
2. {detail_fact}
3. {progress_fact}
4. {impact_fact}
ですます調、350〜550文字で書いてください。ただし事実が薄い場合は350文字未満でも構いません。無理に話を広げないでください。
{opening_time_rule}見出しは【故障・復帰の要旨】【故障の詳細】【リハビリ状況・復帰見通し】【チームへの影響と今後の注目点】の4つをこの順番で使ってください。
【故障・復帰の要旨】では、{subject}の{injury_label}と現状を最初に整理してください。
【故障の詳細】では、部位、原因、診断名、離脱の経緯のうち source にある事実だけを書いてください。
【リハビリ状況・復帰見通し】では、現在の段階、再開したメニュー、復帰時期や見通しの表現を source のまま残してください。
【チームへの影響と今後の注目点】では、代替選手、起用、ローテ、復帰後の役割のうち source にある材料だけを書いてください。
選手本人や監督・コーチのコメントがあれば1つまで残してください。
部位・期間・診断名など医療関連情報は source にある表現を正確に引用してください。
選手名は見出し以外の本文にも必ず明記してください。
事実にない数字・比較・断定・復帰時期の推測を足さないでください。
同じ事実を繰り返さないでください。
筆者の感想や精神論は書かないでください。
最後は読者視点の締め1〜2文で終え、「みなさんの意見はコメントで教えてください！」を入れてください。
{enhanced_rules}\
本文だけを出力してください。
"""


def _extract_notice_record_fact(title: str, summary: str, exclude: set[str] | None = None) -> str:
    exclude = exclude or set()
    for sentence in _extract_prompt_fact_sentences(title, summary, max_sentences=5):
        fact = _ensure_fact_sentence(sentence)
        if not fact or fact in exclude:
            continue
        if any(marker in fact for marker in NOTICE_RECORD_MARKERS) or _re.search(r"(?:\.\d{3}|\d+)", fact):
            return fact
    return ""


def _extract_notice_background_fact(title: str, summary: str, exclude: set[str] | None = None) -> str:
    fact = _find_source_sentence_with_markers(title, summary, NOTICE_BACKGROUND_MARKERS, exclude=exclude)
    if fact:
        return fact
    return _next_unused_source_fact(title, summary, exclude or set())


def _notice_next_focus_sentence(notice_type: str, player_role: str, subject: str) -> str:
    if notice_type in {"一軍登録", "再登録", "一軍合流", "初合流", "初一軍", "昇格", "復帰"}:
        if player_role == "投手":
            return f"{subject}が次回登板や一軍ベンチ入りのどこで役割を得るかがポイントです。"
        if player_role == "捕手":
            return f"{subject}が次の登録発表やマスク配分でどう扱われるかがポイントです。"
        return f"{subject}が次の一軍出場やスタメン争いでどこに入るかがポイントです。"
    if notice_type == "登録抹消":
        return f"{subject}が次の実戦復帰へ向けてどの段階まで進むかを見たいところです。"
    if notice_type == "戦力外":
        return f"{subject}に関する次の発表や進路の動きがポイントです。"
    if notice_type == "再出発":
        return f"{subject}が次の実戦機会でどんな形を示すかがポイントです。"
    return f"{subject}の次の起用や発表がポイントです。"


def _build_notice_strict_prompt(title: str, summary: str, source_day_label: str = "") -> str:
    subject, notice_type = _extract_notice_subject_and_type(title, summary)
    player_position = _extract_notice_player_position(title, summary, subject)
    enhanced_rules = _enhanced_notice_prompt_rules()
    notice_subject = subject or player_position
    source_text = _strip_html(f"{title} {summary}")
    notice_label = notice_type or _extract_notice_type_label(source_text) or "公示"
    notice_fact = _find_source_sentence_with_markers(
        title,
        summary,
        ("登録", "抹消", "合流", "復帰", "昇格", "戦力外", "再出発"),
    )
    used_facts = {fact for fact in [notice_fact] if fact}
    record_fact = _extract_notice_record_fact(title, summary, exclude=used_facts)
    if record_fact:
        used_facts.add(record_fact)
    background_fact = _extract_notice_background_fact(title, summary, exclude=used_facts)
    if not notice_fact:
        notice_fact = _next_unused_source_fact(title, summary, set()) or f"{notice_subject}が{notice_label}の状態にある。"
        used_facts = {notice_fact}
        if not record_fact:
            record_fact = _extract_notice_record_fact(title, summary, exclude=used_facts)
            if record_fact:
                used_facts.add(record_fact)
        if not background_fact:
            background_fact = _extract_notice_background_fact(title, summary, exclude=used_facts)
    if not record_fact:
        record_fact = f"{notice_subject}の今季成績や現在地は、元記事で確認できる範囲に限って整理する。"
    if not background_fact:
        background_fact = notice_fact
    opening_time_rule = f"本文の最初は必ず「（{source_day_label}時点）」で始めてください。\n" if source_day_label else ""
    return f"""あなたは読売ジャイアンツ専門ブログの編集者です。
以下の番号付き事実のみ使用可です。それ以外の情報・解釈・感想・一般論を含む文は出力しないでください。
1. {notice_subject}は読売ジャイアンツ所属である。
2. {notice_subject}が{notice_label}の状態にある。
3. {notice_fact}
4. {record_fact}
5. {background_fact}
ですます調、350〜550文字で書いてください。ただし事実が薄い場合は350文字未満でも構いません。無理に話を広げないでください。
{opening_time_rule}見出しは【公示の要旨】【対象選手の基本情報】【公示の背景】【今後の注目点】の4つをこの順番で使ってください。
【公示の要旨】では、{notice_subject}に何の公示が出たかを最初に整理してください。
【対象選手の基本情報】では、年齢・ポジション・今季成績など、source にある数字があれば必ず残してください。
【公示の背景】では、故障、調整状況、二軍成績、チーム事情のうち source にある事実だけを書いてください。
【今後の注目点】では、「{_notice_next_focus_sentence(notice_label, player_position, notice_subject)}」という方向だけを書いてください。
選手名は見出し以外の本文にも必ず明記してください。
公示の日付・区分（抹消、昇格、戦力外、復帰など）は source にある表記を残してください。
事実にない数字・比較・推測を足さないでください。
同じ事実を繰り返さないでください。
筆者の感想や精神論は書かないでください。
{NON_LINEUP_STARMEN_PROMPT_GUARD}
最後は読者視点の締め1〜2文で終え、「みなさんの意見はコメントで教えてください！」を入れてください。
{enhanced_rules}\
本文だけを出力してください。
"""


def _build_fact_notice_strict_prompt(
    title: str,
    summary: str,
    source_fact_block: str,
    source_day_label: str = "",
    source_name: str = "",
    tweet_url: str = "",
) -> str:
    source_meta = []
    if source_name:
        source_meta.append(source_name)
    if source_day_label:
        source_meta.append(source_day_label)
    if tweet_url:
        source_meta.append(tweet_url)
    source_reference = " / ".join(source_meta) if source_meta else "source に明示された媒体名・日付・URL などの出典情報"
    return f"""あなたは読売ジャイアンツ専門ブログの編集者です。
以下の『使ってよい事実』に書かれた訂正情報だけを使って、短い訂正記事の本文を書いてください。
source にない訂正理由、経緯、評価、一般論、推測は足さないでください。

【使ってよい事実】
{source_fact_block}

【厳守ルール】
・ですます調
・見出しは【訂正の対象】【訂正内容】【訂正元】【お詫び / ファン視点】の4つをこの順番で使う
{NON_LINEUP_STARMEN_PROMPT_GUARD}
・本文は次の4要素をこの順で満たす: 1. 訂正の対象 2. 訂正内容 3. 訂正元 4. ファン視点1文
・本文は 200〜400 文字に収める(訂正記事は短く)
・【訂正の対象】では、何の記事 / 何の事実に対する訂正かを source にある範囲で短く固定する
・【訂正内容】では、元の誤り → 正しい事実を source に明示された表現だけで整理する。元の誤った内容を詳細に書き直さない
・【訂正元】では、訂正元の媒体名と日付を明示する。URL があれば残す
・【訂正元】では、{source_reference} を優先し、一次情報を核にする。X 単独情報だけで断定しない
・訂正対象以外のトピックに拡張しない。元記事の事実関係の再解説はしない
・推測で補完しない。source にある訂正事実だけを使う
・断定語(『絶対』『必ず』等)は使わない
・ファン視点は最後の1文だけ、中立または短いお詫びに留める。コメント参加を促す定型句は fact_notice では強要しない(訂正記事で議論喚起すると混乱を招く)
・HTMLタグなし、本文だけを出力する
"""


def _social_background_focus_line(category: str) -> str:
    if category == "試合速報":
        return "試合の流れ、スタメン、先発、スコアのうち、source にある試合文脈だけを整理する"
    if category == "選手情報":
        return "選手の調整状況、昇格・復帰、コメントの背景のうち、source にある選手文脈だけを整理する"
    if category == "首脳陣":
        return "監督・コーチの起用意図や指導の文脈を、source にある範囲だけで整理する"
    if category == "ドラフト・育成":
        return "二軍、育成、ドラフト、支配下の文脈を、source にある範囲だけで整理する"
    return "球団やチームの状況のうち、元記事にある背景だけを整理する"


def _build_social_strict_prompt(
    title: str,
    summary: str,
    category: str,
    source_name: str,
    source_fact_block: str,
    source_day_label: str = "",
    tweet_url: str = "",
) -> str:
    source_label = _social_source_intro_label(source_name, tweet_url=tweet_url)
    source_indicator = _infer_social_source_indicator(source_name, tweet_url=tweet_url)
    enhanced_rules = _enhanced_social_prompt_rules(category)
    indicator_line = {
        "official": "発信元が球団公式・公式周辺アカウントなのか、本文冒頭で明確にする",
        "media": "発信元がマスコミ記者・報道アカウントなのか、本文冒頭で明確にする",
        "player": "発信元が選手本人や当事者側の発信なのか、本文冒頭で明確にする",
    }[source_indicator]
    time_rule = f"【話題の要旨】の1文目には「{source_day_label}時点」を自然に入れてください。\n" if source_day_label else ""
    return f"""あなたは読売ジャイアンツ専門ブログの編集者です。
{_strict_material_boundary_intro()}

【使ってよい事実】
{source_fact_block}

【厳守ルール】
・ですます調、380〜680文字
・見出しは「【話題の要旨】」「【発信内容の要約】」「【文脈と背景】」「【ファンの関心ポイント】」の4つをこの順番で使う
・上記の役割説明は本文に書かない。本文は必ず最初の見出し（【...】）から始める
・【話題の要旨】では、{source_label}が何を伝えたのかを2〜3文で整理する
・本文冒頭で発信者名または所属を必ず明記する
・{indicator_line}
・【発信内容の要約】では、Xポストの原文ニュアンスを『』で1〜2か所だけ残しながら整理する。全文転写はしない
・【文脈と背景】では、{_social_background_focus_line(category)}
・【ファンの関心ポイント】では、巨人ファンにとって何が意味を持つかを1〜2文で具体的に書く
{_chain_of_reasoning_prompt_rules("【ファンの関心ポイント】", "この発信が次の起用や話題の広がり")}・【ファンの関心ポイント】の最後の1文より後に説明を足さない
・元記事にない数字、比較、推測、精神論は足さない
・Xポストの転写だけで終わらず、文脈補足を必ず入れる
・source にある固有名詞、選手名、球場名、数字は省略しない
・最後は読者視点の締め1〜2文で終え、「みなさんの意見はコメントで教えてください！」を入れる
・HTMLタグなし、本文だけを出力する
{enhanced_rules}\
{time_rule}"""


def _extract_manager_focus_axis(title: str, summary: str) -> str:
    source_text = _strip_html(f"{title} {summary}")
    if any(keyword in source_text for keyword in ("若手", "競争", "レギュラー", "固定", "序列")):
        return "序列や競争"
    if any(keyword in source_text for keyword in ("スタメン", "打順", "オーダー", "起用")):
        return "スタメンや起用"
    if any(keyword in source_text for keyword in ("継投", "采配", "代打", "守備固め", "ベンチ")):
        return "采配やベンチワーク"
    if any(keyword in source_text for keyword in ("指導", "助言", "熱血指導", "直接指導")):
        return "指導の意図"
    return "次のベンチ判断"


def _manager_context_line(focus_axis: str) -> str:
    if focus_axis == "序列や競争":
        return "この話題は序列や競争をどう動かすか、という文脈で読む必要があります。"
    if focus_axis == "スタメンや起用":
        return "この話題はスタメンや起用をどう動かすか、という文脈で読む必要があります。"
    if focus_axis == "采配やベンチワーク":
        return "この話題は采配やベンチワークをどう動かすか、という文脈で読む必要があります。"
    if focus_axis == "指導の意図":
        return "この話題は、どんな指導を選手に求めているのかという文脈で読む必要があります。"
    return "この話題は、次のベンチ判断をどう変えるかという文脈で読む必要があります。"


def _manager_next_watch_line(focus_axis: str, reaction_line: str = "") -> str:
    if reaction_line:
        return reaction_line
    if focus_axis == "序列や競争":
        return "次に見たいのは、この発言が実際の序列や競争にどう出るかという点です。"
    if focus_axis == "スタメンや起用":
        return "次に見たいのは、この発言が実際のスタメンや起用にどう出るかという点です。"
    if focus_axis == "采配やベンチワーク":
        return "次に見たいのは、この発言が実際の采配やベンチワークにどう出るかという点です。"
    if focus_axis == "指導の意図":
        return "次に見たいのは、この言葉が選手の内容や調整にどう表れるかという点です。"
    return "次に見たいのは、この発言が実際のベンチ判断にどう出るかという点です。"


def _strict_material_boundary_intro() -> str:
    return (
        "以下の『使ってよい事実』に書かれた情報を材料に、巨人ファン向けに本文を書いてください。\n"
        "『使ってよい事実』の範囲にある事実は自由に書いてよいが、そこに無い数字、選手名、比較、結果予想、推測、創作、誇張は書かないでください。\n"
        "source にある事実に基づく解釈と、巨人ファンとしての短い感想は、後述の「事実 → 解釈 → 感想」の流れで必ず書いてください。\n"
        "文章は「事実 → 解釈 → 感想」の順で流し、感想だけを先に書かない。"
    )


def _game_strict_material_boundary_intro() -> str:
    return (
        "以下の『使ってよい事実』に書かれた情報を材料に、巨人ファン向けに本文を書いてください。\n"
        "『使ってよい事実』の範囲にある事実は自由に書いてよいが、そこに無い数字、選手名、比較、結果予想、推測、創作、誇張は書かないでください。\n"
        "source / 材料 にない事実・数字・比較・推測は書かないでください。\n"
        "source にある事実に基づく解釈と、巨人ファンとしての短い感想は、後述の「事実 → 解釈 → 感想」の流れで必ず書いてください。\n"
        "感想は締めの1文だけに限定し、source にある事実に基づく短いファン視点として書いてください。\n"
        "文章は「事実 → 解釈 → 感想」の順で流し、感想だけを先に書かない。"
    )


def _chain_of_reasoning_prompt_rules(section_name: str, interpretation_target: str) -> str:
    return (
        f"・{section_name}は必ず「事実 → 解釈 → 感想」の順で流れを作る\n"
        f"・{section_name}の1文目では、source にある事実を1つだけ短く固定する\n"
        f"・{section_name}の2文目では、その事実が{interpretation_target}にどうつながるかを、source の範囲だけで整理する\n"
        f"・{section_name}の最後の1文では、巨人ファンとして「気になります」「注目です」「見たいところです」「と思います」のどれかを必ず使って締める\n"
        f"・{section_name}で感想だけを先に書かない。新事実、結果予想、過去比較は足さない\n"
    )


def _build_manager_strict_prompt(
    title: str,
    summary: str,
    source_fact_block: str,
    source_day_label: str = "",
    team_stats_block: str = "",
) -> str:
    subject = _extract_subject_label(title, summary, "首脳陣")
    quote_phrases = _extract_quote_phrases(f"{title}\n{summary}", max_phrases=3)
    focus_axis = _extract_manager_focus_axis(title, summary)
    enhanced_rules = _enhanced_manager_prompt_rules()
    next_focus_instruction = {
        "序列や競争": "序列や競争のどこが動くか",
        "スタメンや起用": "スタメンや起用のどこが動くか",
        "采配やベンチワーク": "采配やベンチワークのどこが動くか",
        "指導の意図": "選手の内容や調整のどこに指導意図が出るか",
    }.get(focus_axis, "次のベンチ判断のどこが動くか")
    quote_instruction = (
        "引用が2つ以上ある場合は、【発言内容】で2つまで並べて整理してください。"
        if len(quote_phrases) >= 2
        else "引用は1つだけでも構いません。元記事に引用がなければ発言内容を要約してください。"
    )
    time_rule = ""
    if source_day_label:
        time_rule = f"【発言の要旨】の1文目には「{source_day_label}時点」を自然に入れてください。\n"
    team_stats_reference = ""
    if team_stats_block:
        team_stats_reference = (
            "\n【参考：巨人打者の今季主要指標（下の数字そのものを本文に転記する場合は source facts と矛盾しないことを確認）】\n"
            f"{team_stats_block}\n"
            "・上記は参考値。source facts と食い違う場合は source facts を優先する\n"
            "・個別選手の成績を本文に書くときは .xxx / 本 / 打点 の3点セットで並べる（他指標を勝手に足さない）"
        )
    return f"""あなたは読売ジャイアンツ専門ブログの編集者です。
{_strict_material_boundary_intro()}

【使ってよい事実】
{source_fact_block}{team_stats_reference}

【厳守ルール】
・ですます調、400〜800文字
・発言者は必ず「{subject}」と明記する。「監督」「コーチ」「首脳陣」だけでぼかさない
・見出しはこの4つをこの順番で使う
・【発言の要旨】
・【発言内容】
・【文脈と背景】
・【次の注目】
・【発言の要旨】はH2相当の導入で、タイトルの繰り返しではなく、いつ・どこで・どんな状況での発言かを2〜3文で整理する
{time_rule}・【発言内容】では引用を明示して整理する。{quote_instruction}
・【文脈と背景】では、試合状況・選手状況・チーム状況のうち、元記事にある材料だけを使って背景を整理する
・【次の注目】では、{next_focus_instruction}を1〜2文で具体的に書く
{_chain_of_reasoning_prompt_rules("【次の注目】", next_focus_instruction)}・元記事にない数字、過去比較、一般論、精神論、推測は足さない
・最後は読者視点の締め1〜2文で終え、「みなさんの意見はコメントで教えてください！」を入れる
・HTMLタグなし、本文だけを出力する
{enhanced_rules}\
"""


def _is_game_template_subtype(article_subtype: str) -> bool:
    return article_subtype in GAME_REQUIRED_HEADINGS


def _game_required_headings(article_subtype: str) -> tuple[str, ...]:
    return GAME_REQUIRED_HEADINGS.get(article_subtype, ())


def _is_farm_template_subtype(article_subtype: str) -> bool:
    return article_subtype in FARM_REQUIRED_HEADINGS


def _farm_required_headings(article_subtype: str) -> tuple[str, ...]:
    return FARM_REQUIRED_HEADINGS.get(article_subtype, ())


def _extract_game_score_token(source_text: str) -> str:
    match = _re.search(r"(\d{1,2})[－\-–](\d{1,2})", source_text or "")
    return match.group(0) if match else ""


def _extract_game_time_token(source_text: str) -> str:
    match = _re.search(r"(\d{1,2}:\d{2})", source_text or "")
    return match.group(1) if match else ""


def _extract_game_venue_label(source_text: str) -> str:
    text = source_text or ""
    for marker in TITLE_VENUE_MARKERS:
        if marker and marker in text:
            return marker
    match = _re.search(r"([一-龥ァ-ヴーA-Za-z0-9・]+球場)", text)
    return match.group(1) if match else ""


def _extract_game_opponent_label(source_text: str) -> str:
    text = source_text or ""
    positions = []
    for marker in NPB_TEAM_MARKERS:
        if marker in {"巨人", "読売ジャイアンツ"}:
            continue
        idx = text.find(marker)
        if idx >= 0:
            positions.append((idx, marker))
    if not positions:
        return ""
    positions.sort(key=lambda item: item[0])
    return positions[0][1]


def _extract_game_source_names(title: str, summary: str, lineup_rows: list[dict] | None = None) -> list[str]:
    source_text = f"{title} {summary}"
    names = []
    for match in _re.finditer(r"([一-龥々ァ-ヴー]{1,6}(?:[ 　][一-龥々ァ-ヴー]{1,6})?)(?:投手|捕手|内野手|外野手|選手|監督|コーチ)", source_text):
        candidate = _re.sub(r"\s+", "", match.group(1))
        if candidate and candidate not in names:
            names.append(candidate)
    for match in _re.finditer(r"#([一-龥々ァ-ヴー]{2,8})", source_text):
        candidate = _re.sub(r"\s+", "", match.group(1))
        if candidate and candidate not in names:
            names.append(candidate)
    for row in lineup_rows or []:
        candidate = _re.sub(r"\s+", "", str(row.get("name") or ""))
        if candidate and candidate not in names:
            names.append(candidate)
    return names


def _extract_game_numeric_tokens(title: str, summary: str) -> list[str]:
    source_text = f"{title} {summary}"
    patterns = [
        r"\d{1,2}[－\-–]\d{1,2}",
        r"\d{1,2}:\d{2}",
        r"\d{1,2}回",
        r"\d{1,2}安打",
        r"\d{1,2}打点",
        r"\d{1,2}得点",
        r"\d{1,2}失点",
        r"\d{1,2}奪三振",
        r"\d{1,2}勝\d{1,2}敗",
        r"\d{1,2}勝",
        r"\d{1,2}敗",
        r"防御率\d+\.\d+",
        r"\.\d{3}",
        r"\d番",
        r"\d月\d{1,2}日",
        r"\d{4}年",
        r"\d{1,2}本",
        r"\d{1,2}盗塁",
    ]
    tokens = []
    for pattern in patterns:
        for match in _re.finditer(pattern, source_text):
            token = match.group(0)
            if token not in tokens:
                tokens.append(token)
    return tokens


def _game_numeric_count(title: str, summary: str, article_text: str) -> int:
    body = article_text or ""
    return sum(1 for token in _extract_game_numeric_tokens(title, summary) if token and token in body)


def _game_name_count(title: str, summary: str, article_text: str, lineup_rows: list[dict] | None = None) -> int:
    body_norm = _re.sub(r"\s+", "", article_text or "")
    return sum(1 for token in _extract_game_source_names(title, summary, lineup_rows=lineup_rows) if token and token in body_norm)


def _game_section_count(text: str, article_subtype: str) -> int:
    normalized = _normalize_article_text_structure(text or "", "試合速報", True, article_subtype=article_subtype)
    return sum(1 for heading in _game_required_headings(article_subtype) if heading in normalized)


def _game_body_has_required_structure(text: str, article_subtype: str, has_game: bool) -> bool:
    normalized = _normalize_article_text_structure(text or "", "試合速報", has_game, article_subtype=article_subtype)
    required = _game_required_headings(article_subtype)
    if not required:
        return False
    return all(heading in normalized for heading in required)


def _farm_numeric_count(title: str, summary: str, article_text: str) -> int:
    body = article_text or ""
    return sum(1 for token in _extract_game_numeric_tokens(title, summary) if token and token in body)


def _farm_section_count(text: str, article_subtype: str) -> int:
    normalized = _normalize_article_text_structure(text or "", "ドラフト・育成", True, article_subtype=article_subtype)
    return sum(1 for heading in _farm_required_headings(article_subtype) if heading in normalized)


def _farm_body_has_required_structure(text: str, article_subtype: str) -> bool:
    normalized = _normalize_article_text_structure(text or "", "ドラフト・育成", True, article_subtype=article_subtype)
    required = _farm_required_headings(article_subtype)
    if not required:
        return False
    return all(heading in normalized for heading in required)


def _farm_is_drafted_player_story(title: str, summary: str) -> bool:
    source_text = _strip_html(f"{title} {summary}")
    if any(marker in source_text for marker in FARM_DRAFTED_PLAYER_MARKERS):
        return True
    return bool(_re.search(r"ドラ[1-7１-７](?:位)?", source_text))


def _notice_required_headings() -> tuple[str, ...]:
    return NOTICE_REQUIRED_HEADINGS


def _recovery_required_headings() -> tuple[str, ...]:
    return RECOVERY_REQUIRED_HEADINGS


def _recovery_section_count(text: str) -> int:
    normalized = _normalize_article_text_structure(text or "", "選手情報", False, article_subtype="player_recovery")
    return sum(1 for heading in _recovery_required_headings() if heading in normalized)


def _recovery_body_has_required_structure(text: str) -> bool:
    normalized = _normalize_article_text_structure(text or "", "選手情報", False, article_subtype="player_recovery")
    return all(heading in normalized for heading in _recovery_required_headings())


def _social_required_headings() -> tuple[str, ...]:
    return SOCIAL_REQUIRED_HEADINGS


def _social_section_count(text: str) -> int:
    normalized = _normalize_article_text_structure(text or "", "コラム", False, article_subtype="social_news")
    return sum(1 for heading in _social_required_headings() if heading in normalized)


def _social_body_has_required_structure(text: str) -> bool:
    normalized = _normalize_article_text_structure(text or "", "コラム", False, article_subtype="social_news")
    return all(heading in normalized for heading in _social_required_headings())


def _social_quote_count(title: str, summary: str, article_text: str = "") -> int:
    quote_count = len(_extract_quote_phrases(f"{title}\n{summary}", max_phrases=4))
    body_quote_count = (article_text or "").count("『")
    return max(quote_count, body_quote_count)


def _notice_section_count(text: str) -> int:
    normalized = _normalize_article_text_structure(text or "", "選手情報", False, article_subtype="player_notice")
    return sum(1 for heading in _notice_required_headings() if heading in normalized)


def _notice_body_has_required_structure(text: str) -> bool:
    normalized = _normalize_article_text_structure(text or "", "選手情報", False, article_subtype="player_notice")
    return all(heading in normalized for heading in _notice_required_headings())


def _notice_has_player_name(text: str, title: str, summary: str) -> bool:
    subject, _notice_type = _extract_notice_subject_and_type(title, summary)
    candidate = subject or _short_subject_name(title, summary, "選手情報")
    if not candidate or candidate in {"巨人", "選手", "出場選手"}:
        return False
    return _re.sub(r"\s+", "", candidate) in _re.sub(r"\s+", "", text or "")


def _notice_has_numeric_record(text: str) -> bool:
    body = text or ""
    return any(marker in body for marker in NOTICE_RECORD_MARKERS) or bool(_re.search(r"(?:\.\d{3}|防御率\d+\.\d+|\d+試合|\d+打点|\d+本塁打)", body))


def _starts_with_starmen_prefix(text: str) -> bool:
    clean = _collapse_ws(_strip_html(text or ""))
    return bool(_re.search(rf"^[\s\u3000【\[\(（「『]*{_re.escape(LIVE_UPDATE_LINEUP_TITLE_PREFIX)}", clean))


def _build_game_strict_prompt(
    title: str,
    summary: str,
    article_subtype: str,
    source_fact_block: str,
    source_day_label: str = "",
    team_stats_block: str = "",
) -> str:
    source_text = f"{title} {summary}"
    opponent = _extract_game_opponent_label(source_text)
    venue = _extract_game_venue_label(source_text)
    start_time = _extract_game_time_token(source_text)
    score = _extract_game_score_token(source_text)
    enhanced_rules = _enhanced_game_prompt_rules(article_subtype)
    headings = _game_required_headings(article_subtype)
    opening_time_rule = f"・{source_day_label}時点の情報であることが伝わるように書く\n" if source_day_label else ""
    team_stats_reference = ""
    if team_stats_block:
        team_stats_reference = (
            "\n【参考：巨人打者の今季主要指標（下の数字そのものを本文に転記する場合は source facts と矛盾しないことを確認）】\n"
            f"{team_stats_block}\n"
            "・上記は参考値。source facts と食い違う場合は source facts を優先する\n"
            "・個別選手の成績を本文に書くときは .xxx / 本 / 打点 の3点セットで並べる（他指標を勝手に足さない）"
        )

    if article_subtype == "lineup":
        return f"""あなたは読売ジャイアンツ専門ブログの編集者です。
{_game_strict_material_boundary_intro()}

【使ってよい事実】
{source_fact_block}{team_stats_reference}

【厳守ルール】
・ですます調、400〜800文字
・見出しは「{headings[0]}」「{headings[1]}」「{headings[2]}」「{headings[3]}」の4つをこの順番で使う
・選手名、球場名、開始時刻、打順、成績数字は source にある表記をそのまま残す
・【試合概要】では、{opponent + '戦' if opponent else '対戦カード'}、{venue or '球場'}、{start_time or '開始時刻'}など source にある試合情報を最初に整理する
・【スタメン一覧】では、source にある打順と選手名をそのまま並べる。元記事にない打順や選手は足さない
・【先発投手】では、元記事にある予告先発や先発投手名、成績の数字だけを整理する
・【注目ポイント】では、試合が始まったら最初にどこを見るかを1〜2文で具体的に書く
{_chain_of_reasoning_prompt_rules("【注目ポイント】", "この並びや先発情報が試合の入り方")}・抽象的な期待論や結果予想で膨らませない
・元記事にない数字、選手名、打順、成績、一般論は足さない
・最後は読者視点の締め1〜2文で終え、「みなさんの意見はコメントで教えてください！」を入れる
・HTMLタグなし、本文だけを出力する
{enhanced_rules}\
{opening_time_rule}"""

    if article_subtype == "live_anchor":
        score_rule = f"source にあるスコア {score} を必ず残してください。" if score else "source にあるスコアがあれば必ず残してください。"
        return f"""あなたは読売ジャイアンツ専門ブログの編集者です。
{_game_strict_material_boundary_intro()}

【使ってよい事実】
{source_fact_block}{team_stats_reference}

【厳守ルール】
・ですます調、350〜650文字
・見出しは「{headings[0]}」「{headings[1]}」「{headings[2]}」「{headings[3]}」の4つをこの順番で使う
{NON_LINEUP_STARMEN_PROMPT_GUARD}
・{score_rule}
・本文は次の4要素をこの順で満たす: 1. 節目の時点 2. 現在スコア + 対戦相手 3. その時点までの重要プレー1〜3点 4. ファン視点1文
・時点は『X回表/裏終了時点』『X回Y死時点』等、いつの話か必ず明示する
・【時点】では、節目の時点を最初に短く固定し、進行中の試合であることが伝わるように書く
・【現在スコア】では、現在スコアと対戦相手を source にある表記のまま整理する。現在スコアは source にあるものだけ。未反映の得点を推測しない
・【直近のプレー】では、その時点までの重要プレーを1〜3点に絞って事実だけで整理する。直近プレーは事実のみ。『勝ちそう』『逆転する』等の予測語は使わない
・試合結果の断定、未発生事象の先行記述、終盤の結果予想はしない
・X 単独情報で断定しない。公式 X または NPB ライブに裏付けがある事実のみ記載する
・選手名、回、アウトカウント、スコア、対戦相手の表記は source のまま残す。source にない数字や比較、一般論は足さない
・ファン視点は最後の1文だけにする。【ファン視点】は最後の1文だけにし、「気になります」「注目です」「見たいところです」「と思います」のどれかを使ってから、「みなさんの意見はコメントで教えてください！」を入れる
・HTMLタグなし、本文だけを出力する
{enhanced_rules}\
{opening_time_rule}"""

    if article_subtype == "postgame":
        score_rule = f"source にあるスコア {score} を必ず残してください。" if score else "source にあるスコアがあれば必ず残してください。"
        return f"""あなたは読売ジャイアンツ専門ブログの編集者です。
{_game_strict_material_boundary_intro()}

【使ってよい事実】
{source_fact_block}{team_stats_reference}

【厳守ルール】
・ですます調、400〜800文字
・見出しは「{headings[0]}」「{headings[1]}」「{headings[2]}」「{headings[3]}」の4つをこの順番で使う
{NON_LINEUP_STARMEN_PROMPT_GUARD}
・{score_rule}
・本文は次の6要素をこの順で満たす: 1. 事実核(最終スコア、対戦相手、試合日、勝敗を短く整理) 2. 主要打席(決勝打や大きな打席を事実のみで1〜3点) 3. 継投(先発と主要継投を事実のみで1〜3点) 4. 主要プレー(該当時のみ、守備でのビッグプレー、盗塁、本塁打の文脈を事実のみで整理) 5. 選手コメント欄(optional) 6. ファン視点1文
・【試合結果】では事実核として勝敗、最終スコア、対戦相手、試合日を先に短く整理する
・【ハイライト】では主要打席を先に置き、決勝打や大きな打席を事実のみで1〜3点整理する。該当時のみ主要プレーとして守備でのビッグプレー、盗塁、本塁打の文脈を事実だけで続ける
・【選手成績】では先発と主要継投を先に整理し、source にある投球回、失点、安打数、打点、防御率などの数字をそのまま残す
・source が存在する場合のみ選手コメント欄を付ける。source がなければ欄ごと省略し、推測文を足さない
・【試合展開】では、どこで流れが動いたかを source にある事実だけで整理する
{_chain_of_reasoning_prompt_rules("【試合展開】", "この流れの変化が次戦やチーム状態")}・選手名と数字をぼかさない。source にある固有名詞は省略しない
・元記事にない数字、選手名、比較、一般論は足さない
・ファン視点は最後の1文だけにする。「みなさんの意見はコメントで教えてください！」を入れる
・HTMLタグなし、本文だけを出力する
{enhanced_rules}\
{opening_time_rule}"""

    if article_subtype == "live_update":
        score_rule = f"source にあるスコア {score} を必ず残してください。" if score else "source にあるスコアがあれば必ず残してください。"
        return f"""あなたは読売ジャイアンツ専門ブログの編集者です。
{_game_strict_material_boundary_intro()}

【使ってよい事実】
{source_fact_block}{team_stats_reference}

【厳守ルール】
・ですます調、400〜700文字
・見出しは「{headings[0]}」「{headings[1]}」「{headings[2]}」の3つをこの順番で使う
・{score_rule}
・試合は進行中として書く。勝敗の断定、終盤の結果予想、最終的な講評は書かない
・【いま起きていること】では、現在のイニングとスコアを先に置き、source にある継投・打順・塁状況など「いまの状況」を1〜3文で整理する
・【流れが動いた場面】では、イニングごとの実況を時系列にだらだら並べない。source にある同点・勝ち越し・逆転・継投・満塁・3者凡退など、流れが動いた瞬間を1つか2つに絞って書く
・【次にどこを見るか】では、結果予想ではなく、このあとどの回・どの打順・どの投手継投に注目するかを source にある事実だけで1〜2文で書く
・スタメン発表記事に切り替えない。1番〜9番を並べた一覧、打順表、表組み、箇条書きは禁止
{NON_LINEUP_STARMEN_PROMPT_GUARD}
{_chain_of_reasoning_prompt_rules("【次にどこを見るか】", "いまのスコアと流れから次の見どころ")}・選手名、回、スコア、継投の表記は source のまま残す。source にない数字や選手名、比較、一般論は足さない
・最後は読者視点の締め1〜2文で終え、「みなさんの意見はコメントで教えてください！」を入れる
・HTMLタグなし、本文だけを出力する
{enhanced_rules}\
{opening_time_rule}"""

    return f"""あなたは読売ジャイアンツ専門ブログの編集者です。
{_game_strict_material_boundary_intro()}

【使ってよい事実】
{source_fact_block}{team_stats_reference}

【厳守ルール】
・ですます調、350〜650文字
・見出しは「{headings[0]}」「{headings[1]}」「{headings[2]}」の3つをこの順番で使う
{NON_LINEUP_STARMEN_PROMPT_GUARD}
・本文は次の5要素をこの順で満たす: 1. 先発予告 2. スタメン / 打順ステータス 3. 対戦相手ざっくり 4. 注目点1〜2 5. ファン視点1文
・【変更情報の要旨】では、中止、スライド登板、先発変更などの要点に加え、先発予告とスタメン発表ステータスを最初に整理する
・先発投手名は、source に予告先発や一次情報の明示がある場合のみ書く。source に無い場合は「先発は公式発表待ち」とし、推測で投手名を書かない
・スタメン / 打順は、発表済みか未発表かの status だけを書く。「本日スタメン予定: 未発表 / 発表済み」のような整理にとどめ、打順リストやスタメン本体は pregame 本文に展開しない
・【具体的な変更内容】では、対戦相手名と直近の文脈を事実だけで1〜2文整理し、日付、球場、開始時刻、引用など source にある変更点を順に整理する
・注目点は1〜2点に絞り、source にある事実だけで書く。結果予想や断定はしない
・X 単独の情報で先発やスタメンを断定しない。一次情報または source に明示された内容を核にする
・【この変更が意味すること】では、結果予想はせず、次にどこを見るかだけを1〜2文で書く
{_chain_of_reasoning_prompt_rules("【この変更が意味すること】", "この変更が試合前の見方")}・選手名、日付、球場、開始時刻、引用は source の表記をそのまま残す
・元記事にない数字、選手名、比較、結果予想、一般論は足さない
・ファン視点は最後の1文だけにする。読者視点の締めは最後に1文だけ置き、「みなさんの意見はコメントで教えてください！」を入れる
・HTMLタグなし、本文だけを出力する
{enhanced_rules}\
{opening_time_rule}"""


def _build_farm_strict_prompt(
    title: str,
    summary: str,
    article_subtype: str,
    source_fact_block: str,
    source_day_label: str = "",
) -> str:
    source_text = f"{title} {summary}"
    opponent = _extract_game_opponent_label(source_text)
    venue = _extract_game_venue_label(source_text)
    start_time = _extract_game_time_token(source_text)
    score = _extract_game_score_token(source_text)
    enhanced_rules = _enhanced_farm_prompt_rules(article_subtype)
    headings = _farm_required_headings(article_subtype)
    opening_time_rule = f"・{source_day_label}時点の情報であることが伝わるように書く\n" if source_day_label else ""

    if article_subtype == "farm_lineup":
        return f"""あなたは読売ジャイアンツ専門ブログの編集者です。
{_strict_material_boundary_intro()}

【使ってよい事実】
{source_fact_block}

【厳守ルール】
・ですます調、320〜520文字
・見出しは「{headings[0]}」「{headings[1]}」「{headings[2]}」の3つをこの順番で使う
・【二軍試合概要】では、{opponent + '戦' if opponent else '対戦カード'}、{venue or '球場'}、{start_time or '開始時刻'}など source にある二軍試合情報を最初に整理する
・【二軍スタメン一覧】では、source にある打順、選手名、守備位置だけを並べる。元記事にない打順や選手は足さない
・【注目選手】では、育成選手、支配下候補、ドラフト選手など source にある立場の違いを残しつつ、誰を見たいかを1〜2文で整理する
{_chain_of_reasoning_prompt_rules("【注目選手】", "この並びが二軍の起用意図や若手評価")}・一軍記事のような書き方をしない。二軍戦の並びであることを明確に書く
・数字、打順、選手名、球場名は source にある表記をそのまま残す
・元記事にない数字、選手名、成績、比較、一般論は足さない
・最後は読者視点の締め1〜2文で終え、「みなさんの意見はコメントで教えてください！」を入れる
・HTMLタグなし、本文だけを出力する
{enhanced_rules}\
{opening_time_rule}"""

    score_rule = f"source にあるスコア {score} を必ず残してください。" if score else "source にあるスコアがあれば必ず残してください。"
    return f"""あなたは読売ジャイアンツ専門ブログの編集者です。
{_strict_material_boundary_intro()}

【使ってよい事実】
{source_fact_block}

【厳守ルール】
・ですます調、380〜620文字
・見出しは「{headings[0]}」「{headings[1]}」「{headings[2]}」「{headings[3]}」の4つをこの順番で使う
{NON_LINEUP_STARMEN_PROMPT_GUARD}
・本文は次の4要素をこの順で満たす: 1. 対象選手 / 対象試合 2. 事実核 3. 文脈 4. ファン視点1文
・{score_rule}
・【二軍結果・活躍の要旨】では、対象選手か対象試合のどちらを軸にする記事かを最初に固定し、選手名または試合日+カードを明確にする
・【ファームのハイライト】では、昇格・降格・復帰・試合結果などの事実核を整理し、source に書かれている数字だけを残す
・【二軍個別選手成績】では、怪我明け、調整中、復帰戦など source にある文脈を1〜2文で補う。数字は source にあるものだけ。二軍成績を推測で書かない
・【一軍への示唆】では、一軍昇格の可能性や育成段階を source の範囲だけで整理する。推測で昇格を断定しない。一軍の文脈を勝手に展開しない。一軍情報は source にあり、かつ二軍の出来事と直接関係する時のみ1文以内で触れる
{_chain_of_reasoning_prompt_rules("【一軍への示唆】", "この内容が一軍候補争いや育成段階")}・一軍記事と混同しないよう、「二軍」「ファーム」の文脈を明確にする
・数字、選手名、育成/支配下の区別はぼかさない。source にある固有名詞は省略しない
・元記事にない数字、選手名、比較、一般論は足さない
・ファン視点は最後の1文だけにする。読者視点の締めは最後に1文だけ置き、「みなさんの意見はコメントで教えてください！」を入れる
・HTMLタグなし、本文だけを出力する
{enhanced_rules}\
{opening_time_rule}"""


def _build_game_parts_prompt_postgame(
    title: str,
    summary: str,
    source_fact_block: str,
    score: str,
    win_loss_hint: str,
    team_stats_reference: str,
    source_name: str = "",
    source_url: str = "",
) -> str:
    score_block = f"・score: {score}\n" if score else ""
    win_loss_block = f"・win_loss_hint: {win_loss_hint}\n" if win_loss_hint else ""
    source_attribution_block = ""
    if source_name or source_url:
        source_attribution_block = (
            f"・source_name: {source_name}\n"
            f"・source_url: {source_url}\n"
        )
    team_stats_block = ""
    if team_stats_reference:
        team_stats_block = (
            "\n【参考メモ】\n"
            f"{team_stats_reference}\n"
            "・参考メモを使う場合も、source / 材料 に明示された事実だけを採用する\n"
        )

    return f"""あなたは読売ジャイアンツ専門ブログの編集者です。
以下の source / 材料だけを使って、postgame 記事用の部品 JSON を1つ返してください。
全文の HTML や template 構造は書かないでください。JSON object で返してください。コードフェンスも不要です。

【source / 材料】
・title: {title}
・summary: {summary}
{score_block}{win_loss_block}【source_fact_block】
{source_fact_block}
{source_attribution_block}{team_stats_block}

【返却 JSON schema】
{{
  "title": "str",
  "fact_lead": "str",
  "body_core": ["str"],
  "game_context": "str",
  "fan_view": "str",
  "source_attribution": {{
    "source_name": "str",
    "source_url": "str"
  }}
}}

【field rules】
・title: 記事タイトル。H1 相当の文字列のみ。H タグを含めない
・fact_lead: 事実リード。1〜2文。source / 材料にある事実だけで書く
・body_core: 本文核。2〜5段落。各要素は1段落ぶんの文字列にし、source / 材料にある事実の言い換えだけで構成する
・game_context: 試合文脈。1〜2文。source / 材料にある時系列または前後比較だけを書く
・fan_view: ファン視点。1文のみ。source / 材料にある事実に基づく短い感想だけを書く。close marker の語尾は許可する
・source_attribution: {{"source_name":"str","source_url":"str"}} の dict。source / 材料に明示された値だけを入れ、無い場合は空文字にする

【禁止事項】
・source / 材料 にない事実・数字・比較・推測は禁止
・fan_view 以外で感想は禁止
・H タグ禁止
・全文 HTML 禁止
・template 構造の文章化禁止
・source_attribution 以外の追加 field 禁止
・body_core を1段落だけにしない
・source_attribution を文字列にしない
"""


def _fetch_team_stats_block_for_strict_article(category: str, logger: logging.Logger) -> str:
    team_stats_block = ""
    if os.environ.get("ARTICLE_INJECT_TEAM_STATS", "1") == "1" and category in ("試合速報", "首脳陣"):
        try:
            team_stats = fetch_giants_batting_stats_from_yahoo()
            team_stats_block = _format_team_batting_stats_block(team_stats)
        except Exception as e:
            logger.warning("team batting stats 取得失敗: %s", e)
            team_stats_block = ""
    if team_stats_block:
        logger.info(
            json.dumps(
                {
                    "event": "article_team_stats_injected",
                    "category": category,
                    "line_count": team_stats_block.count("\n") + 1,
                },
                ensure_ascii=False,
            )
        )
    return team_stats_block


def _request_gemini_strict_text(
    *,
    api_key: str,
    prompt: str,
    logger: logging.Logger,
    attempt_limit: int,
    min_chars: int,
    log_label: str = "Gemini strict fact mode",
    source_url: str | None = None,
) -> str:
    import urllib.request
    from src import llm_cost_emitter as _llm_cost

    payload = json.dumps(
        {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": 1536,
                "temperature": 0.35,
                "thinkingConfig": {"thinkingBudget": GEMINI_FLASH_THINKING_BUDGET},
            },
        }
    ).encode("utf-8")
    logger.info("%s で記事生成中（最大%d回試行）...", log_label, attempt_limit)
    for attempt in range(attempt_limit):
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as res:
                data = json.load(res)
            parts = data["candidates"][0]["content"].get("parts", [])
            raw_text = "".join(p.get("text", "") for p in parts if "text" in p).strip()
            raw_text = _strip_prompt_role_echo(raw_text)
            token_in, token_out = _llm_cost.extract_usage_metadata(data)
            _emit_llm_cost_with_observability(
                logger,
                "rss_fetcher._request_gemini_strict_text.success",
                lane="rss_fetcher_strict",
                call_site="rss_fetcher._request_gemini_strict_text",
                post_id=None,
                source_url=source_url,
                content_hash=None,
                model="gemini-2.5-flash",
                input_chars=len(prompt),
                output_chars=len(raw_text),
                token_in=token_in,
                token_out=token_out,
                cache_hit=False,
                skip_reason=None,
                success=True,
                error_class=None,
            )
            if raw_text and len(raw_text) >= min_chars:
                logger.info("%s 生成成功 %d文字", log_label, len(raw_text))
                return raw_text
            logger.warning(
                "%s 応答が短すぎる（%d文字, 必要%d文字）、試行 %d/%d",
                log_label,
                len(raw_text),
                min_chars,
                attempt + 1,
                attempt_limit,
            )
        except Exception as e:
            _emit_llm_cost_with_observability(
                logger,
                "rss_fetcher._request_gemini_strict_text.error",
                lane="rss_fetcher_strict",
                call_site="rss_fetcher._request_gemini_strict_text",
                post_id=None,
                source_url=source_url,
                content_hash=None,
                model="gemini-2.5-flash",
                input_chars=len(prompt),
                output_chars=0,
                token_in=None,
                token_out=None,
                cache_hit=False,
                skip_reason=None,
                success=False,
                error_class=type(e).__name__,
            )
            logger.warning("%s 失敗 試行%d/%d: %s", log_label, attempt + 1, attempt_limit, e)
    logger.error("%s が上限回数に達したため記事生成スキップ", log_label)
    return ""


def _get_gemini_cache_cooldown_hours() -> int:
    raw = str(os.environ.get(GEMINI_CACHE_COOLDOWN_HOURS_ENV, GEMINI_CACHE_COOLDOWN_HOURS_DEFAULT)).strip()
    try:
        parsed = int(raw)
    except ValueError:
        return GEMINI_CACHE_COOLDOWN_HOURS_DEFAULT
    return max(parsed, 0)


def _get_gemini_cache_manager() -> GeminiCacheManager | None:
    if _get_gemini_cache_cooldown_hours() <= 0:
        return None
    return GeminiCacheManager.from_env()


def _gemini_prompt_template_id(category: str, article_subtype: str) -> str:
    safe_category = _re.sub(r"[^a-z0-9一-龯ぁ-んァ-ヴー]+", "_", str(category or "").strip().lower()) or "unknown"
    safe_subtype = _re.sub(r"[^a-z0-9_]+", "_", str(article_subtype or "").strip().lower()) or "general"
    return f"strict_article_{GEMINI_STRICT_PROMPT_TEMPLATE_VERSION}_{safe_category}_{safe_subtype}"


def _build_gemini_cache_content_text(*parts: object) -> str:
    return "\n".join(str(part).strip() for part in parts if str(part or "").strip())


def _build_gemini_cache_key(
    *,
    source_url: str,
    content_text: str,
    prompt_template_id: str,
) -> GeminiCacheKey:
    return GeminiCacheKey(
        source_url_hash=_hash_duplicate_guard_value(source_url),
        content_hash=_compute_gemini_content_hash(content_text),
        prompt_template_id=str(prompt_template_id or "").strip(),
    )


def _gemini_cache_lookup(
    cache_key: GeminiCacheKey,
    *,
    cache_manager: GeminiCacheManager,
    cooldown_hours: int,
    now: datetime | None,
) -> tuple[GeminiCacheValue | None, str, int]:
    return cache_manager.lookup(
        cache_key,
        cooldown_hours=cooldown_hours,
        now=now,
    )


def _gemini_cache_save(
    cache_key: GeminiCacheKey,
    *,
    generated_text: str,
    cache_manager: GeminiCacheManager,
    now: datetime | None,
) -> int:
    return cache_manager.save(
        cache_key,
        generated_text,
        now=now,
        model=GEMINI_CACHE_MODEL_NAME,
    )


def _log_gemini_cache_lookup(
    logger: logging.Logger,
    *,
    source_url: str,
    cache_key: GeminiCacheKey,
    cache_hit: bool,
    cache_hit_reason: str,
    gemini_call_made: bool,
    cache_size_bytes: int,
) -> None:
    payload = {
        "event": "gemini_cache_lookup",
        "post_url": str(source_url or ""),
        "source_url_hash": str(cache_key.source_url_hash or ""),
        "content_hash": str(cache_key.content_hash or ""),
        "prompt_template_id": str(cache_key.prompt_template_id or ""),
        "cache_hit": bool(cache_hit),
        "cache_hit_reason": str(cache_hit_reason or ""),
        "gemini_call_made": bool(gemini_call_made),
        "cache_size_bytes": int(cache_size_bytes or 0),
    }
    logger.info(json.dumps(payload, ensure_ascii=False))


def _log_gemini_cache_backend_error(
    logger: logging.Logger,
    *,
    source_url: str,
    cache_key: GeminiCacheKey,
    stage: str,
    error: Exception,
) -> None:
    payload = {
        "event": "gemini_cache_backend_error",
        "post_url": str(source_url or ""),
        "source_url_hash": str(cache_key.source_url_hash or ""),
        "content_hash": str(cache_key.content_hash or ""),
        "prompt_template_id": str(cache_key.prompt_template_id or ""),
        "stage": str(stage or ""),
        "error_class": type(error).__name__,
        "error": str(error),
    }
    logger.warning(json.dumps(payload, ensure_ascii=False))


def _gemini_text_with_cache(
    *,
    api_key: str,
    prompt: str,
    logger: logging.Logger,
    attempt_limit: int,
    min_chars: int,
    source_url: str,
    content_text: str,
    prompt_template_id: str,
    cache_manager: GeminiCacheManager | None,
    now: datetime | None = None,
    log_label: str = "Gemini strict fact mode",
) -> tuple[str, dict[str, Any]]:
    cache_key = _build_gemini_cache_key(
        source_url=source_url,
        content_text=content_text,
        prompt_template_id=prompt_template_id,
    )
    telemetry: dict[str, Any] = {
        "cache_hit": False,
        "cache_hit_reason": "cache_disabled",
        "source_url_hash": cache_key.source_url_hash,
        "content_hash": cache_key.content_hash,
        "cache_size_bytes": 0,
        "gemini_call_made": True,
    }
    if cache_manager is not None and cache_key.source_url_hash and cache_key.prompt_template_id:
        try:
            cached, hit_reason, cache_size_bytes = _gemini_cache_lookup(
                cache_key,
                cache_manager=cache_manager,
                cooldown_hours=_get_gemini_cache_cooldown_hours(),
                now=now,
            )
        except GeminiCacheBackendError as exc:
            _log_gemini_cache_backend_error(
                logger,
                source_url=source_url,
                cache_key=cache_key,
                stage="lookup",
                error=exc,
            )
            telemetry["cache_hit_reason"] = "cache_backend_error"
        except Exception as exc:
            _log_gemini_cache_backend_error(
                logger,
                source_url=source_url,
                cache_key=cache_key,
                stage="lookup_exception",
                error=exc,
            )
            telemetry["cache_hit_reason"] = "cache_backend_error"
        else:
            telemetry["cache_size_bytes"] = cache_size_bytes
            telemetry["cache_hit_reason"] = hit_reason
            if cached is not None:
                telemetry["cache_hit"] = True
                telemetry["gemini_call_made"] = False
                _log_gemini_cache_lookup(
                    logger,
                    source_url=source_url,
                    cache_key=cache_key,
                    cache_hit=True,
                    cache_hit_reason=hit_reason,
                    gemini_call_made=False,
                    cache_size_bytes=cache_size_bytes,
                )
                return cached.generated_text, telemetry

    text = _request_gemini_strict_text(
        api_key=api_key,
        prompt=prompt,
        logger=logger,
        attempt_limit=attempt_limit,
        min_chars=min_chars,
        log_label=log_label,
        source_url=source_url or None,
    )

    if cache_manager is not None and cache_key.source_url_hash and cache_key.prompt_template_id and text:
        try:
            telemetry["cache_size_bytes"] = _gemini_cache_save(
                cache_key,
                generated_text=text,
                cache_manager=cache_manager,
                now=now,
            )
        except Exception as exc:
            _log_gemini_cache_backend_error(
                logger,
                source_url=source_url,
                cache_key=cache_key,
                stage="save",
                error=exc,
            )

    _log_gemini_cache_lookup(
        logger,
        source_url=source_url,
        cache_key=cache_key,
        cache_hit=False,
        cache_hit_reason=str(telemetry.get("cache_hit_reason") or "miss"),
        gemini_call_made=True,
        cache_size_bytes=int(telemetry.get("cache_size_bytes") or 0),
    )
    if telemetry["cache_hit_reason"] == "cache_disabled":
        telemetry["cache_hit_reason"] = "cache_disabled"
    elif telemetry["cache_hit_reason"] != "cache_backend_error":
        telemetry["cache_hit_reason"] = "miss"
    return text, telemetry


def _emit_llm_cost_with_observability(
    logger: logging.Logger,
    debug_site: str,
    **emit_kwargs,
) -> None:
    lane = str(emit_kwargs.get("lane") or "")
    call_site = str(emit_kwargs.get("call_site") or "")
    logger.debug(
        "llm_cost emit start: debug_site=%s lane=%s call_site=%s",
        debug_site,
        lane,
        call_site,
    )
    try:
        from src import llm_cost_emitter as _llm_cost

        _llm_cost.emit_llm_cost(**emit_kwargs)
    except Exception as e:
        logger.warning("llm_cost emit failed at %s: %s", debug_site, e)
        raise
    logger.debug(
        "llm_cost emit done: debug_site=%s lane=%s call_site=%s",
        debug_site,
        lane,
        call_site,
    )


def _log_article_parts_applied(
    logger: logging.Logger,
    *,
    title: str,
    article_subtype: str,
    body_core_count: int,
) -> None:
    payload = {
        "event": "article_parts_applied",
        "title": title,
        "subtype": article_subtype,
        "body_core_count": body_core_count,
    }
    logger.info(json.dumps(payload, ensure_ascii=False))


def _log_article_parts_fallback(
    logger: logging.Logger,
    *,
    title: str,
    article_subtype: str,
    reason: str,
) -> None:
    payload = {
        "event": "article_parts_fallback",
        "title": title,
        "subtype": article_subtype,
        "reason": reason,
    }
    logger.info(json.dumps(payload, ensure_ascii=False))


def _validate_postgame_article_parts(payload: object) -> ArticleParts:
    if not isinstance(payload, dict):
        raise TypeError("payload_not_object")

    def _require_str(data: dict, key: str, *, allow_empty: bool = False) -> str:
        value = data.get(key)
        if not isinstance(value, str):
            raise TypeError(f"{key}_not_string")
        normalized = value.strip()
        if not normalized and not allow_empty:
            raise ValueError(f"{key}_empty")
        return normalized

    body_core = payload.get("body_core")
    if not isinstance(body_core, list):
        raise TypeError("body_core_not_list")
    normalized_body_core: list[str] = []
    for index, paragraph in enumerate(body_core):
        if not isinstance(paragraph, str):
            raise TypeError(f"body_core_{index}_not_string")
        normalized = paragraph.strip()
        if not normalized:
            raise ValueError(f"body_core_{index}_empty")
        normalized_body_core.append(normalized)
    if not normalized_body_core:
        raise ValueError("body_core_empty")

    source_attribution = payload.get("source_attribution")
    if not isinstance(source_attribution, dict):
        raise TypeError("source_attribution_not_object")

    return {
        "title": _require_str(payload, "title"),
        "fact_lead": _require_str(payload, "fact_lead"),
        "body_core": normalized_body_core,
        "game_context": _require_str(payload, "game_context"),
        "fan_view": _require_str(payload, "fan_view"),
        "source_attribution": {
            "source_name": _require_str(source_attribution, "source_name", allow_empty=True),
            "source_url": _require_str(source_attribution, "source_url", allow_empty=True),
        },
    }


def _build_postgame_ai_body_from_parts(parts: ArticleParts) -> str:
    headings = GAME_REQUIRED_HEADINGS["postgame"]
    body_core = list(parts["body_core"])
    highlight_lines = body_core[:-1] or body_core
    stat_lines = body_core[-1:] if body_core else [parts["game_context"]]
    final_lines = [parts["game_context"]]
    fan_view = (parts.get("fan_view") or "").strip()
    if fan_view:
        final_lines.append(fan_view)
    return "\n".join(
        [
            headings[0],
            parts["fact_lead"],
            headings[1],
            *highlight_lines,
            headings[2],
            *stat_lines,
            headings[3],
            *final_lines,
        ]
    )


def _render_postgame_strict_html(body_text: str) -> str:
    lines = [line.strip() for line in (body_text or "").splitlines() if line.strip()]
    if not lines:
        return ""

    blocks: list[str] = []
    heading_index = 0
    idx = 0
    while idx < len(lines):
        line = lines[idx]
        if line.startswith("【") and "】" in line:
            heading_index += 1
            level = 2 if heading_index == 1 else 3
            safe_heading = _html.escape(line)
            blocks.append(
                f'<!-- wp:heading {{"level":{level}}} -->\n'
                f"<h{level}>{safe_heading}</h{level}>\n"
                f"<!-- /wp:heading -->\n\n"
            )
            idx += 1
            continue
        if line.startswith("・"):
            items: list[str] = []
            while idx < len(lines) and lines[idx].startswith("・"):
                item_text = lines[idx].lstrip("・").strip()
                if item_text:
                    items.append(item_text)
                idx += 1
            if items:
                items_html = "".join(f"<li>{_html.escape(item)}</li>\n" for item in items)
                blocks.append(
                    "<!-- wp:list -->\n"
                    '<ul class="wp-block-list">\n'
                    f"{items_html}"
                    "</ul>\n"
                    "<!-- /wp:list -->\n\n"
                )
            continue
        safe_line = _html.escape(line)
        blocks.append(
            "<!-- wp:paragraph -->\n"
            f"<p>{safe_line}</p>\n"
            "<!-- /wp:paragraph -->\n\n"
        )
        idx += 1
    return "".join(blocks)


class _PostgameStrictReviewFallback:
    """strict ON 時の失敗 sentinel。上位 caller が detect して review 倒し。"""

    __slots__ = ("reason",)

    def __init__(self, reason: str):
        self.reason = str(reason)


class _ManagerQuoteZeroReviewFallback:
    """manager 系 quote_count=0 の review sentinel。上位 caller が detect して review 倒し。"""

    __slots__ = ("reason",)

    def __init__(self, reason: str):
        self.reason = str(reason)


class _WeakTitleReviewFallback:
    """生成 title が weak の場合の review sentinel。上位 caller が detect して review 倒し。"""

    __slots__ = ("reason",)

    def __init__(self, reason: str):
        self.reason = str(reason)


def _maybe_render_postgame_article_parts(
    *,
    title: str,
    summary: str,
    category: str,
    has_game: bool,
    source_name: str,
    source_url: str,
    source_type: str,
    source_entry: dict | None,
    win_loss_hint: str,
    logger: logging.Logger,
) -> tuple[str, str] | _PostgameStrictReviewFallback | None:
    article_subtype = _detect_article_subtype(title, summary, category, has_game)
    strict_mode = strict_fact_mode_enabled()
    if not (category == "試合速報" and article_subtype == "postgame"):
        return None

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return None

    source_fact_block = _build_source_fact_block(
        title,
        summary,
        source_type=source_type,
        entry=source_entry,
    )
    score = _extract_game_score_token(f"{title} {summary}")

    if strict_mode and _postgame_strict_enabled():
        source_block = "\n".join(
            part
            for part in (
                f"title: {title}",
                f"summary: {summary}",
                f"source_name: {source_name}" if source_name else "",
                f"source_url: {source_url}" if source_url else "",
                "[source_fact_block]",
                source_fact_block,
            )
            if part
        )
        prompt = _postgame_strict_prompt.replace("{source_text}", source_block)
        raw_text, _cache_meta = _gemini_text_with_cache(
            api_key=api_key,
            prompt=prompt,
            logger=logger,
            attempt_limit=get_gemini_attempt_limit(strict_mode=True),
            min_chars=1,
            log_label="Gemini postgame strict slot-fill",
            source_url=source_url or "",
            content_text=source_block,
            prompt_template_id=GEMINI_POSTGAME_STRICT_SLOTFILL_TEMPLATE_ID,
            cache_manager=_get_gemini_cache_manager(),
        )
        if not raw_text:
            logger.warning("postgame_strict: empty_response -> review")
            _log_article_parts_fallback(
                logger,
                title=title,
                article_subtype=article_subtype,
                reason="strict_review_fallback:strict_empty_response",
            )
            return _PostgameStrictReviewFallback("strict_empty_response")

        payload, parse_reason = _postgame_strict_parse(raw_text)
        if payload is None:
            logger.warning("postgame_strict: parse_fail reason=%s -> review", parse_reason)
            _log_article_parts_fallback(
                logger,
                title=title,
                article_subtype=article_subtype,
                reason=f"strict_review_fallback:strict_parse_fail:{parse_reason}",
            )
            return _PostgameStrictReviewFallback(f"strict_parse_fail:{parse_reason}")

        is_valid, errors = _postgame_strict_validate(payload, source_block)
        if not is_valid:
            logger.warning("postgame_strict: validation_fail errors=%s -> review", errors)
            _log_article_parts_fallback(
                logger,
                title=title,
                article_subtype=article_subtype,
                reason=f"strict_review_fallback:strict_validation_fail:{','.join(errors)}",
            )
            return _PostgameStrictReviewFallback(f"strict_validation_fail:{','.join(errors)}")

        if not _postgame_strict_has_sufficient_for_render(payload):
            logger.warning("postgame_strict: insufficient_for_render -> review")
            _log_article_parts_fallback(
                logger,
                title=title,
                article_subtype=article_subtype,
                reason="strict_review_fallback:strict_insufficient_for_render",
            )
            return _PostgameStrictReviewFallback("strict_insufficient_for_render")

        try:
            body_text = _postgame_strict_render(payload)
        except Exception as e:
            logger.warning("postgame_strict: render_fail error=%s -> review", type(e).__name__)
            _log_article_parts_fallback(
                logger,
                title=title,
                article_subtype=article_subtype,
                reason=f"strict_review_fallback:strict_render_fail:{type(e).__name__}",
            )
            return _PostgameStrictReviewFallback(f"strict_render_fail:{type(e).__name__}")

        payload_score = ""
        if payload.get("giants_score") is not None and payload.get("opponent_score") is not None:
            payload_score = f"{payload.get('giants_score')}-{payload.get('opponent_score')}"
        strict_source_context = {
            "title": title,
            "source_title": title,
            "source_summary": summary,
            "summary": summary,
            "source_name": source_name,
            "source_url": source_url,
            "scoreline": payload_score or score or "",
            "team_result": win_loss_hint,
            "opponent": str(payload.get("opponent") or _extract_game_opponent_label(f'{title} {summary}') or "").strip(),
        }
        strict_contract_validate = _validate_body_candidate(
            body_text,
            article_subtype,
            source_context=strict_source_context,
        )
        if not strict_contract_validate.get("ok"):
            fail_axes = list(strict_contract_validate.get("fail_axes") or [])
            logger.warning("postgame_strict: contract_fail fail_axes=%s -> review", fail_axes)
            _log_article_parts_fallback(
                logger,
                title=title,
                article_subtype=article_subtype,
                reason=f"strict_review_fallback:strict_contract_fail:{','.join(fail_axes) or 'unknown'}",
            )
            return _PostgameStrictReviewFallback(
                f"strict_contract_fail:{','.join(fail_axes) or 'unknown'}"
            )

        rendered_html = _render_postgame_strict_html(body_text)
        _log_article_parts_applied(
            logger,
            title=title,
            article_subtype=article_subtype,
            body_core_count=len(payload.get("key_events") or []),
        )
        return body_text, rendered_html

    if not (strict_mode and article_parts_renderer_postgame_enabled()):
        return None

    team_stats_block = _fetch_team_stats_block_for_strict_article(category, logger)
    prompt = _build_game_parts_prompt_postgame(
        title=title,
        summary=summary,
        source_fact_block=source_fact_block,
        score=score,
        win_loss_hint=win_loss_hint,
        team_stats_reference=team_stats_block,
        source_name=source_name,
        source_url=source_url,
    )
    raw_text, _cache_meta = _gemini_text_with_cache(
        api_key=api_key,
        prompt=prompt,
        logger=logger,
        attempt_limit=get_gemini_attempt_limit(strict_mode=True),
        min_chars=1,
        log_label="Gemini article parts mode",
        source_url=source_url or "",
        content_text=_build_gemini_cache_content_text(
            title,
            summary,
            source_name,
            source_url,
            source_fact_block,
            score,
            win_loss_hint,
            team_stats_block,
        ),
        prompt_template_id=GEMINI_POSTGAME_PARTS_TEMPLATE_ID,
        cache_manager=_get_gemini_cache_manager(),
    )
    if not raw_text:
        _log_article_parts_fallback(
            logger,
            title=title,
            article_subtype=article_subtype,
            reason="empty_response",
        )
        return None

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as e:
        _log_article_parts_fallback(
            logger,
            title=title,
            article_subtype=article_subtype,
            reason=f"json_parse_error:{e.msg}",
        )
        return None

    try:
        parts = _validate_postgame_article_parts(payload)
    except (TypeError, ValueError) as e:
        _log_article_parts_fallback(
            logger,
            title=title,
            article_subtype=article_subtype,
            reason=f"schema_invalid:{e}",
        )
        return None

    try:
        rendered_html = render_postgame(parts)
    except Exception as e:
        _log_article_parts_fallback(
            logger,
            title=title,
            article_subtype=article_subtype,
            reason=f"render_error:{type(e).__name__}",
        )
        return None

    _log_article_parts_applied(
        logger,
        title=title,
        article_subtype=article_subtype,
        body_core_count=len(parts["body_core"]),
    )
    return _build_postgame_ai_body_from_parts(parts), rendered_html


def _build_gemini_strict_prompt(
    title: str,
    summary: str,
    category: str,
    source_fact_block: str,
    win_loss_hint: str,
    has_game: bool,
    real_reactions: list[str] | None = None,
    source_day_label: str = "",
    source_name: str = "",
    source_type: str = "news",
    tweet_url: str = "",
    team_stats_block: str = "",
) -> str:
    subject = _extract_subject_label(title, "", category)
    first_heading, second_heading, third_heading = _article_section_headings(category, category == "試合速報")
    article_subtype = _detect_article_subtype(title, summary, category, has_game)
    player_mode = _detect_player_article_mode(title, summary, category) if category == "選手情報" else ""
    if article_subtype == "fact_notice":
        return _build_fact_notice_strict_prompt(
            title,
            summary,
            source_fact_block,
            source_day_label=source_day_label,
            source_name=source_name,
            tweet_url=tweet_url,
        )
    if source_type == "social_news" and not _social_source_prefers_structured_template(category, article_subtype):
        return _build_social_strict_prompt(
            title,
            summary,
            category,
            source_name,
            source_fact_block,
            source_day_label=source_day_label,
            tweet_url=tweet_url,
        )
    if category == "選手情報":
        if _is_recovery_template_story(title, summary, category):
            return _build_recovery_strict_prompt(title, summary, source_day_label=source_day_label)
        if _is_notice_template_story(title, summary, category):
            return _build_notice_strict_prompt(title, summary, source_day_label=source_day_label)
        if player_mode == "player_mechanics":
            return _build_player_mechanics_strict_prompt(title, summary)
        if player_mode == "player_quote":
            return _build_player_quote_strict_prompt(title, summary)
        return _build_player_status_strict_prompt(title, summary, source_day_label=source_day_label)
    if category == "首脳陣":
        return _build_manager_strict_prompt(
            title,
            summary,
            source_fact_block,
            source_day_label=source_day_label,
            team_stats_block=team_stats_block,
        )
    if category == "試合速報" and _is_game_template_subtype(article_subtype):
        return _build_game_strict_prompt(
            title,
            summary,
            article_subtype,
            source_fact_block,
            source_day_label=source_day_label,
            team_stats_block=team_stats_block,
        )
    if category == "ドラフト・育成" and _is_farm_template_subtype(article_subtype):
        return _build_farm_strict_prompt(title, summary, article_subtype, source_fact_block, source_day_label=source_day_label)
    opening_focus = "最初の1文でニュースの核心を書く"
    if category == "首脳陣":
        opening_focus = f"最初の1文で{subject}の発言より先に、ベンチが何を動かそうとしているのかを書く"
    elif category == "試合速報":
        if article_subtype == "lineup":
            opening_focus = "最初の1文で今日のスタメンのどこが動いたかを書く"
        elif article_subtype == "live_update":
            opening_focus = "最初の1文で現在のスコアと、どこで流れが動いたかを書く"
        elif article_subtype == "postgame":
            opening_focus = "最初の1文で試合の流れを分けたポイントを書く"
        else:
            opening_focus = "最初の1文で登板や試合前の焦点を書く" if not win_loss_hint else "最初の1文で試合の流れや勝敗のポイントを書く"
    elif category == "ドラフト・育成":
        if article_subtype == "farm_lineup":
            opening_focus = "最初の1文で二軍スタメンのどこに若手や調整組を置いたかを書く"
        else:
            opening_focus = "最初の1文で二軍戦の結果か選手活躍のどちらが軸かを書く"

    fan_block = ""
    if real_reactions:
        reaction_lines = []
        for reaction in real_reactions[:3]:
            clean = _strip_html(_reaction_body_text(reaction)).strip().strip("「」")
            clean = _re.sub(r"\s+", " ", clean)
            if clean:
                reaction_lines.append(f"・{clean}")
        if reaction_lines:
            fan_block = (
                "\n【参考にしてよいファンの反応の温度感】\n"
                + "\n".join(reaction_lines)
                + "\n"
                + "・上の反応は事実として断定せず、期待・不安・注目点などの温度感として1〜2文に要約してよい\n"
                + "・反応本文を長く引用しない\n"
            )
    team_stats_reference = ""
    if team_stats_block:
        team_stats_reference = (
            "\n【参考：巨人打者の今季主要指標（下の数字そのものを本文に転記する場合は source facts と矛盾しないことを確認）】\n"
            f"{team_stats_block}\n"
            "・上記は参考値。source facts と食い違う場合は source facts を優先する\n"
            "・個別選手の成績を本文に書くときは .xxx / 本 / 打点 の3点セットで並べる（他指標を勝手に足さない）"
        )

    category_rules = ""
    if category == "選手情報":
        if player_mode == "player_mechanics":
            category_rules = (
                f"・{second_heading}では、{subject}が何を変えているのか、外から受けた助言や投げ方の変化がどこに出ているのかを先に整理する\n"
                f"・{second_heading}では、結果の羅列よりも、フォーム・投げ方・考え方の変化を1つか2つに絞って掘る\n"
                f"・{third_heading}では、次の実戦でどこを見るかを具体的に書く。『今後に期待』『注目される』のような抽象表現だけで終えない\n"
                "・『可能性があります』『期待が高まります』『注目されます』『重要な意味を持ちます』のような無難語はできるだけ避け、『どこが気になるか』『どこが分かれ目か』で書く\n"
                "・『詳細が分かれば』『データが出れば』『明らかになれば』のように、元記事にない追加材料待ちで文を埋めない\n"
            )
        elif player_mode == "player_quote":
            category_rules = (
                f"・{second_heading}では、{subject}の言葉を言い換えて膨らませず、何を意識したコメントなのかを整理する\n"
                f"・{second_heading}では、フォーム変更・投げ方修正・助言など、元記事にない mechanics の話を足さない\n"
                f"・{third_heading}では、その意識が次の実戦のどこに出るかを書く。相手や球場、立ち上がりなど具体的な観点を置く\n"
                "・薄いコメント記事なので、無理に数字や抽象論で膨らませない\n"
            )
        else:
            category_rules = (
                f"・{second_heading}では、{subject}がいまどの段階にいるのかを整理する。昇格・復帰・二軍戦・登録状況などの現在地を先に置く\n"
                f"・{second_heading}では、精神論や一般論ではなく、今回の動きがチーム内の役割や次の実戦にどうつながるかを書く\n"
                f"・{third_heading}では、次に確認すべきポイントを具体的に書く。『今後に期待』だけで終えない\n"
                "・元記事にない深いフォーム論や長い感想は足さない\n"
            )
    elif category == "首脳陣":
        category_rules = (
            f"・{second_heading}では、発言の言い回しよりも、ベンチがどこを動かそうとしているかを整理する\n"
            f"・{second_heading}では、コメントをそのまま言い換えるだけで終わらせず、起用・采配・役割変更のどこに効く話かを書く\n"
            f"・{third_heading}では、その言葉が次の起用や采配にどうつながるかを1つに絞って書く\n"
        )
    elif category == "試合速報":
        if article_subtype == "lineup":
            category_rules = (
                f"・{second_heading}では、誰が入ったかだけでなく、打順や守備位置のどこが動いたかを整理する\n"
                f"・{third_heading}では、試合が始まったら最初にどこを見たいかを具体的に書く\n"
            )
        elif article_subtype == "live_update":
            category_rules = (
                f"・{second_heading}では、現在のスコアだけでなく、同点・勝ち越し・逆転などどこで流れが変わったかを整理する\n"
                f"・{third_heading}では、次に1点が入りそうなポイントや、ここからどこを見るべきかを具体的に書く\n"
                "・実況の時系列をだらだら並べず、今この時点で押さえるべき3点に絞る\n"
            )
        elif article_subtype == "postgame":
            category_rules = (
                f"・{second_heading}では、勝敗だけでなく、どこで流れが傾いたかを整理する\n"
                f"・{third_heading}では、次戦に残る課題か手応えを1つに絞って書く\n"
            )
        elif not win_loss_hint:
            category_rules = (
                f"・{second_heading}では、試合前の空気や登板の入り方など、結果が出る前でも整理できる論点を掘る\n"
                f"・{third_heading}では、結果予想よりも、最初にどこを見るべきかを具体的に書く\n"
            )
    elif category == "ドラフト・育成" and article_subtype == "farm_lineup":
        category_rules = (
            f"・{second_heading}では、二軍スタメンで誰をどこで試しているか、一軍昇格や守備位置テストにつながる論点を書く\n"
            f"・{third_heading}では、若手や調整組のうち、試合が始まったら最初に誰のどこを見たいかを具体的に書く\n"
        )

    return f"""あなたは読売ジャイアンツ専門ブログの編集者です。
以下の元記事タイトルと要約に含まれる事実だけを使って、読者が最後まで読める日本語の記事本文を書いてください。

【使ってよい事実】
{source_fact_block}{team_stats_reference}
{fan_block}
{win_loss_hint}

【厳守ルール】
・具体的な事実として書いてよいのは上の「使ってよい事実」にある内容だけ
・数字、順位、成績、日付、契約、故障情報、比較、引用は、上にあるものだけ使う
・検索して新事実を足さない。推測しない。架空の出典を書かない
・試合がない記事ではスコア・勝敗・試合結果を書かない
・元記事に試合結果が出ていない場合は、「勝利しました」「敗れました」など結果が確定した書き方をしない
・見出しは最大3つまで。本文は550〜750文字程度。ですます調
・{opening_focus}
・材料が少ない場合でも、上の事実を2文に分けて丁寧に言い換えて厚みを出してよい。ただし事実は増やさない
・新聞要約のように1文へ情報を詰め込みすぎない。1段落1論点で書く
・一番上の見出しは必ず「{first_heading}」にする
・2つ目の見出しは基本として「{second_heading}」を使い、この話題の焦点を整理する
・3つ目を使う場合は「{third_heading}」とし、新事実を足さずに次にどこを見るべきかを1〜2段落で書く
{category_rules}・抽象語だけで1文を終わらせない。読者が「どこを見る記事なのか」が分かる書き方にする
・同じ言い回しを繰り返さない。「今回の話題は」だけで始めない
・最後は「みなさんの意見はコメントで教えてください！」で締める
・HTMLタグなし、記事本文のみ出力
"""


def _extract_quote_phrases(text: str, max_phrases: int = 2) -> list[str]:
    phrases = []
    for phrase in _re.findall(r"[「『]([^」』]{4,30})[」』]", _strip_html(text)):
        clean = phrase.strip()
        if any(marker in clean for marker in QUOTE_SKIP_MARKERS):
            continue
        if clean and clean not in phrases:
            phrases.append(clean)
        if len(phrases) >= max_phrases:
            break
    return phrases


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    deduped = []
    seen = set()
    for item in items:
        key = item.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(key)
    return deduped


def _article_section_headings(category: str, has_game: bool = True) -> tuple[str, str, str]:
    first = "【ニュースの整理】"
    if category == "試合速報":
        second = "【試合のポイント】"
    elif category == "首脳陣":
        second = "【コメントのポイント】"
    elif category == "補強・移籍":
        second = "【補強のポイント】"
    elif category == "球団情報":
        second = "【球団トピック】"
    else:
        second = "【ここに注目】"
    third = "【次の注目】"
    return first, second, third


def _summary_kicker(category: str) -> str:
    mapping = {
        "試合速報": "GIANTS GAME NOTE",
        "選手情報": "GIANTS PLAYER WATCH",
        "首脳陣": "GIANTS MANAGER NOTE",
        "補強・移籍": "GIANTS ROSTER WATCH",
        "球団情報": "GIANTS FRONT NOTE",
        "ドラフト・育成": "GIANTS FARM WATCH",
        "OB・解説者": "GIANTS VOICE CHECK",
    }
    return mapping.get(category, "GIANTS NEWS DIGEST")


def _voice_intro(category: str, subject: str) -> str:
    if category == "試合速報":
        return "先に、巨人ファンが試合前から気にしていた論点を整理します。"
    if category == "選手情報":
        return f"{subject}の現状を整理します。"
    if category == "首脳陣":
        return "まずは言葉の強さより、ベンチがどこを動かそうとしているのかを整理します。"
    if category == "補強・移籍":
        return "補強の話は名前より先に、チームのどこを埋める話なのかを整理します。"
    return "先に、この話題で押さえるべき論点を整理します。"


def _apply_editor_voice(text: str, category: str, subject: str) -> str:
    lines = []
    common_replacements = [
        ("多くのファンが注目を集めていました", "G党の視線が集まっていました"),
        ("多くのファンが注目を集めました", "G党の視線が集まりました"),
        ("注目を集めました", "G党の視線が集まりました"),
        ("注目を集めていました", "G党の視線が集まっていました"),
        ("重要な一戦", "流れを左右しそうな一戦"),
        ("多くのファンが", "G党が"),
        ("多くのファンから", "G党から"),
        ("多くの関心を集めるポイント", "G党が気にしていたポイント"),
        ("多くの関心を集めていました", "G党の視線が集まっていました"),
        ("様々な要素が絡み合っていました", "見どころがいくつも重なっていました"),
        ("特別な意味を持つ", "見え方が少し変わる"),
        ("強い決意を示しており", "腹をくくっていることをにじませており"),
        ("強い決意を示した", "腹をくくっていることをにじませた"),
        ("試合に臨みました", "マウンドに入ろうとしていました"),
        ("試合に臨む", "マウンドに入る"),
        ("重要な転換点となる可能性があります", "見え方の変わり目になりそうです"),
        ("並々ならぬ覚悟の表れと言えるでしょう", "本人がかなり腹をくくっているのが伝わります"),
        ("示唆しています", "感じさせます"),
        ("良い方向に向かっていることを示唆しています", "手応えが出始めているように見えます"),
        ("注目されます", "目が向きます"),
        ("ファンの間で大きな注目を集めています", "G党の視線がかなり集まっています"),
        ("大胆なメスを入れる決断", "フォームに手を入れる決断"),
        ("成長への強い意欲がうかがえます", "まだ伸びるために自分を崩しにいっているのが見えます"),
        ("着実に実を結びつつあることを感じさせます", "少なくとも手応えゼロではないことを感じさせます"),
        ("今後の投球内容への期待感を高めるものです", "次の登板を見たくさせる材料になっています"),
        ("ことは間違いありません", "ことは伝わってきます"),
        ("今後への期待が高まります", "次を見たくなります"),
        ("今後の活躍への期待が高まります", "次の実戦を見たくなります"),
        ("今後の動向に注目です", "次にどう出るかを見たいところです"),
        ("大きな意味を持ちます", "見え方を左右しそうです"),
        ("重要な意味を持ちます", "見え方を左右しそうです"),
        ("が注目されています", "に目が向きます"),
        ("が注目されます", "に目が向きます"),
        ("注目を集めています", "G党の視線が集まっています"),
        ("注目を集めている", "G党の視線が集まっている"),
        ("注目されるのは、", "見たいのは、"),
        ("姿勢が伺えます", "姿勢が見えてきます"),
        ("姿勢がうかがえます", "姿勢が見えてきます"),
        ("重要なポイントとなります", "見どころです"),
        ("重要なポイントです", "見どころです"),
        ("重要な焦点となるでしょう", "そこが分かれ目になりそうです"),
        ("重要な焦点です", "そこが焦点です"),
        ("注目点です", "見たいポイントです"),
        ("と見て良いでしょう", "と見てよさそうです"),
        ("ファンの間でも大きな期待が寄せられています", "G党の期待もかなり出ています"),
        ("ファンの間では", "G党の間では"),
        ("可能性を感じさせます", "少し上向いているように見えます"),
        ("示唆していると言えるでしょう", "ことが伝わってきます"),
        ("考え方やアプローチにも変化をもたらしていることが", "投げ方だけでなく向き合い方まで変わり始めていることが"),
        ("詳細な情報が明らかになることで、フォーム改造の真価が見えてくるでしょう。", "次の実戦で同じ形が出るかを見れば、フォーム改造の手応えはもっと見えてきます。"),
    ]
    category_replacements = {
        "試合速報": [
            ("この試合で何が焦点だったのか、元記事の事実に沿って整理します。", _voice_intro(category, subject)),
            ("まずは今日のスタメンの並びを整理します。", "まずは今日のスタメンでどこが動いたかを整理します。"),
            ("ここで見ておきたいのは、単なる事実確認だけでなく、この動きが次の試合や起用にどうつながるかという点です。", "巨人ファンが見たいのは、目先の結果よりこの流れが次戦にどうつながるかという点です。"),
        ],
        "選手情報": [
            (f"{subject}に関する最新情報を、元記事の事実ベースで整理します。", _voice_intro(category, subject)),
            (f"{subject}の現状を整理します。", _voice_intro(category, subject)),
        ],
        "首脳陣": [
            (f"{subject}の発言や判断材料を、元記事に沿って整理します。", _voice_intro(category, subject)),
            (f"{subject}のコメントのポイントを整理します。", _voice_intro(category, subject)),
        ],
        "補強・移籍": [
            ("補強の話は名前より先に、チームのどこを埋める話なのかを整理します。", _voice_intro(category, subject)),
        ],
    }
    replacements = common_replacements + category_replacements.get(category, [])

    for raw_line in (text or "").split("\n"):
        line = raw_line
        if line.startswith("【") or line.startswith("■") or not line.strip():
            lines.append(line)
            continue
        for old, new in replacements:
            line = line.replace(old, new)
        lines.append(line)
    return "\n".join(lines)


def _normalize_article_heading(heading: str, category: str, has_game: bool, article_subtype: str = "") -> str:
    clean = (heading or "").strip()
    if not clean:
        return clean

    if category == "首脳陣":
        manager_heading_aliases = {
            "【発言の要旨】": "【発言の要旨】",
            "【発言内容】": "【発言内容】",
            "【発言内容の整理】": "【発言内容】",
            "【引用の整理】": "【発言内容】",
            "【文脈と背景】": "【文脈と背景】",
            "【背景と文脈】": "【文脈と背景】",
            "【文脈】": "【文脈と背景】",
            "【次の注目】": "【次の注目】",
            "【今後の注目】": "【次の注目】",
        }
        if clean in manager_heading_aliases:
            return manager_heading_aliases[clean]

    if category == "試合速報" and _is_game_template_subtype(article_subtype):
        game_heading_aliases = {}
        if article_subtype == "lineup":
            game_heading_aliases = {
                "【試合概要】": "【試合概要】",
                "【試合前情報】": "【試合概要】",
                "【スタメン一覧】": "【スタメン一覧】",
                "【スタメン】": "【スタメン一覧】",
                "【打順】": "【スタメン一覧】",
                "【先発投手】": "【先発投手】",
                "【予告先発】": "【先発投手】",
                "【注目ポイント】": "【注目ポイント】",
                "【見どころ】": "【注目ポイント】",
            }
        elif article_subtype == "postgame":
            game_heading_aliases = {
                "【試合結果】": "【試合結果】",
                "【ハイライト】": "【ハイライト】",
                "【選手成績】": "【選手成績】",
                "【個人成績】": "【選手成績】",
                "【試合展開】": "【試合展開】",
                "【勝負の分岐点】": "【試合展開】",
            }
        elif article_subtype == "pregame":
            game_heading_aliases = {
                "【変更情報の要旨】": "【変更情報の要旨】",
                "【具体的な変更内容】": "【具体的な変更内容】",
                "【この変更が意味すること】": "【この変更が意味すること】",
                "【見どころ】": "【この変更が意味すること】",
            }
        elif article_subtype == "live_update":
            game_heading_aliases = {
                "【いま起きていること】": "【いま起きていること】",
                "【現状】": "【いま起きていること】",
                "【現在のスコア】": "【いま起きていること】",
                "【試合経過】": "【流れが動いた場面】",
                "【流れが動いた場面】": "【流れが動いた場面】",
                "【ハイライト】": "【流れが動いた場面】",
                "【次にどこを見るか】": "【次にどこを見るか】",
                "【今後の注目】": "【次にどこを見るか】",
                "【見どころ】": "【次にどこを見るか】",
            }
        if clean in game_heading_aliases:
            return game_heading_aliases[clean]

    if category == "ドラフト・育成" and _is_farm_template_subtype(article_subtype):
        farm_heading_aliases = {}
        if article_subtype == "farm":
            farm_heading_aliases = {
                "【二軍結果・活躍の要旨】": "【二軍結果・活躍の要旨】",
                "【ニュースの整理】": "【二軍結果・活躍の要旨】",
                "【試合結果】": "【二軍結果・活躍の要旨】",
                "【活躍の要旨】": "【二軍結果・活躍の要旨】",
                "【ファームのハイライト】": "【ファームのハイライト】",
                "【ハイライト】": "【ファームのハイライト】",
                "【二軍個別選手成績】": "【二軍個別選手成績】",
                "【選手成績】": "【二軍個別選手成績】",
                "【個別成績】": "【二軍個別選手成績】",
                "【一軍への示唆】": "【一軍への示唆】",
                "【次の注目】": "【一軍への示唆】",
            }
        elif article_subtype == "farm_lineup":
            farm_heading_aliases = {
                "【二軍試合概要】": "【二軍試合概要】",
                "【ニュースの整理】": "【二軍試合概要】",
                "【試合概要】": "【二軍試合概要】",
                "【二軍スタメン一覧】": "【二軍スタメン一覧】",
                "【スタメン一覧】": "【二軍スタメン一覧】",
                "【スタメン】": "【二軍スタメン一覧】",
                "【打順】": "【二軍スタメン一覧】",
                "【注目選手】": "【注目選手】",
                "【ここに注目】": "【注目選手】",
                "【次の注目】": "【注目選手】",
            }
        if clean in farm_heading_aliases:
            return farm_heading_aliases[clean]

    if category == "選手情報" and article_subtype == "player_notice":
        notice_heading_aliases = {
            "【公示の要旨】": "【公示の要旨】",
            "【ニュースの整理】": "【公示の要旨】",
            "【対象選手の基本情報】": "【対象選手の基本情報】",
            "【基本情報】": "【対象選手の基本情報】",
            "【公示の背景】": "【公示の背景】",
            "【背景】": "【公示の背景】",
            "【今後の注目点】": "【今後の注目点】",
            "【次の注目】": "【今後の注目点】",
        }
        if clean in notice_heading_aliases:
            return notice_heading_aliases[clean]

    if category == "選手情報" and article_subtype == "player_recovery":
        recovery_heading_aliases = {
            "【故障・復帰の要旨】": "【故障・復帰の要旨】",
            "【ニュースの整理】": "【故障・復帰の要旨】",
            "【故障の詳細】": "【故障の詳細】",
            "【詳細】": "【故障の詳細】",
            "【背景】": "【故障の詳細】",
            "【リハビリ状況・復帰見通し】": "【リハビリ状況・復帰見通し】",
            "【復帰見通し】": "【リハビリ状況・復帰見通し】",
            "【リハビリ状況】": "【リハビリ状況・復帰見通し】",
            "【チームへの影響と今後の注目点】": "【チームへの影響と今後の注目点】",
            "【今後の注目点】": "【チームへの影響と今後の注目点】",
            "【次の注目】": "【チームへの影響と今後の注目点】",
        }
        if clean in recovery_heading_aliases:
            return recovery_heading_aliases[clean]

    if article_subtype == "social_news":
        social_heading_aliases = {
            "【話題の要旨】": "【話題の要旨】",
            "【ニュースの整理】": "【話題の要旨】",
            "【発信内容の要約】": "【発信内容の要約】",
            "【発信内容】": "【発信内容の要約】",
            "【引用の整理】": "【発信内容の要約】",
            "【文脈と背景】": "【文脈と背景】",
            "【背景】": "【文脈と背景】",
            "【ファンの関心ポイント】": "【ファンの関心ポイント】",
            "【次の注目】": "【ファンの関心ポイント】",
        }
        if clean in social_heading_aliases:
            return social_heading_aliases[clean]

    first, second, third = _article_section_headings(category, has_game)
    first_aliases = {
        "■今日のジャイアンツ",
        "■今日のポイント",
        "■選手情報の整理",
        "■首脳陣コメントの整理",
        "■補強・移籍の整理",
        "【ニュースの整理】",
    }
    second_aliases = {
        "【試合のポイント】",
        "【コメントのポイント】",
        "【補強のポイント】",
        "【球団トピック】",
        "【ここに注目】",
        "【ポイント整理】",
    }
    third_aliases = {
        "【ヨシラバー視点】",
        "【ファン目線の注目点】",
        "【ここからの注目】",
        "【次の注目】",
    }

    if clean in first_aliases:
        return first
    if clean in second_aliases:
        return second
    if clean in third_aliases:
        return third
    return clean


def _normalize_article_text_structure(text: str, category: str, has_game: bool, article_subtype: str = "") -> str:
    normalized_lines = []
    seen_headings = set()
    for raw_line in (text or "").split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("【") or line.startswith("■") or line.startswith("▶"):
            normalized = _normalize_article_heading(line, category, has_game, article_subtype=article_subtype)
            if normalized in seen_headings:
                continue
            seen_headings.add(normalized)
            normalized_lines.append(normalized)
            continue
        normalized_lines.append(line)
    return "\n".join(normalized_lines)


def _extract_handle_from_tweet_url(tweet_url: str) -> str:
    match = _re.search(r"https?://(?:x|twitter)\.com/([^/]+)/status/", tweet_url or "", _re.IGNORECASE)
    if not match:
        return ""
    handle = match.group(1).strip()
    if not handle or handle in {"i", "home", "search", "explore"}:
        return ""
    return "@" + handle


def _reaction_text(reaction) -> str:
    if isinstance(reaction, dict):
        return (reaction.get("text") or reaction.get("summary") or "").strip()
    return (reaction or "").strip()


def _reaction_url(reaction) -> str:
    if isinstance(reaction, dict):
        return (reaction.get("url") or reaction.get("link") or "").strip()
    return ""


def _reaction_handle(reaction: object, fallback_index: int = 0) -> str:
    if isinstance(reaction, dict):
        handle = (reaction.get("handle") or "").strip()
        if handle:
            return handle
        handle = _extract_handle_from_tweet_url(_reaction_url(reaction))
        if handle:
            return handle
    elif isinstance(reaction, str):
        match = _re.match(r"^(@\S+)[:：]\s*(.+)$", reaction.strip())
        if match:
            return match.group(1)
    suffix = f"{fallback_index:02d}" if fallback_index else "00"
    return f"@x_user_{suffix}"


def _reaction_body_text(reaction) -> str:
    if isinstance(reaction, dict):
        return _reaction_text(reaction)
    match = _re.match(r"^@\S+[:：]\s*(.+)$", (reaction or "").strip())
    if match:
        return match.group(1).strip()
    return (reaction or "").strip()


def _clean_reaction_snippet(text: str, max_chars: int = 46) -> str:
    clean = _strip_html(text or "")
    clean = _re.sub(r"https?://\S+|pic\.twitter\.com/\S+", "", clean)
    clean = _re.sub(r"\s+", " ", clean).strip(" 。")
    return clean[:max_chars].rstrip("。 ")


def _reaction_is_media_like(handle: str, text: str) -> bool:
    handle_lower = (handle or "").lower().lstrip("@")
    text_clean = _strip_html(text or "")
    if any(keyword in handle_lower for keyword in MEDIA_HANDLE_KEYWORDS):
        return True
    if any(marker in text_clean for marker in MEDIA_TEXT_MARKERS):
        return True
    return False


def _reaction_handle_is_media_like(handle: str) -> bool:
    handle_lower = (handle or "").lower().lstrip("@")
    return any(keyword in handle_lower for keyword in MEDIA_HANDLE_KEYWORDS)


def _reaction_opinion_score(text: str) -> int:
    clean = _strip_html(text or "")
    score = 0
    for marker in FAN_OPINION_MARKERS:
        if marker in clean:
            score += 1
    if any(symbol in clean for symbol in ("！", "?", "？", "w", "笑", "泣", "🙏", "🔥", "✨")):
        score += 1
    return score


def _reaction_commentary_score(text: str) -> int:
    clean = _strip_html(text or "")
    score = 0
    for marker in FAN_COMMENTARY_MARKERS:
        if marker in clean:
            score += 1
    if clean.count("。") >= 1 or clean.count("、") >= 2:
        score += 1
    return score


def _reaction_is_reply_like(text: str) -> bool:
    clean = _strip_html(text or "").strip()
    return clean.startswith("@")


def _reaction_similarity_tokens(text: str) -> set[str]:
    clean = _strip_html(text or "")
    clean = _re.sub(r"https?://\S+|pic\.twitter\.com/\S+", "", clean)
    tokens = {
        token for token in _re.findall(r"[一-龥ァ-ヴーA-Za-z0-9]{2,12}", clean)
        if token not in GENERIC_REACTION_TERMS
    }
    return tokens


def _reactions_are_too_similar(text_a: str, text_b: str) -> bool:
    if not text_a or not text_b:
        return False
    tokens_a = _reaction_similarity_tokens(text_a)
    tokens_b = _reaction_similarity_tokens(text_b)
    if not tokens_a or not tokens_b:
        return False
    overlap = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    if union == 0:
        return False
    return (overlap / union) >= 0.6


def _reaction_focus_score(text: str, title: str, summary: str, category: str, focus_terms: list[str]) -> int:
    clean = _strip_html(text or "")
    score = 0
    subject = _extract_subject_label(title, summary, category)
    if subject and subject in clean:
        score += 1

    for term in focus_terms:
        if term in GENERIC_REACTION_TERMS or term == subject:
            continue
        if term and term in clean:
            score += 2

    for phrase in _extract_quote_phrases(f"{title}\n{summary}", max_phrases=2):
        if phrase and phrase in clean:
            score += 2

    for term in CATEGORY_REACTION_TERMS.get(category, ()):
        if term in clean:
            score += 1

    return score


def _reaction_has_subject_context(text: str, title: str, summary: str, category: str) -> bool:
    clean = _strip_html(text or "")
    subject = _extract_subject_label(title, summary, category)
    compact_subject = _compact_subject_label(title, summary, category)
    family_name_alias = _player_family_name_alias(title, summary, category)
    generic_subjects = {"巨人", "選手", "首脳陣"}
    if subject and subject not in generic_subjects and subject in clean:
        return True
    if compact_subject and compact_subject not in generic_subjects and compact_subject in clean:
        return True
    if family_name_alias and family_name_alias in clean:
        return True
    return False


def _reaction_context_hit_flags(
    text: str,
    title: str,
    summary: str,
    category: str,
    focus_terms: list[str] | None = None,
) -> dict[str, bool]:
    clean = _strip_html(text or "")
    subject = _extract_subject_label(title, summary, category)
    compact_subject = _compact_subject_label(title, summary, category)
    family_name_alias = _player_family_name_alias(title, summary, category)
    ignored_terms = {term for term in (subject, compact_subject, family_name_alias) if term}
    topical_terms = focus_terms if focus_terms is not None else _build_fan_reaction_focus_terms(title, summary, category)
    topical_hit = any(
        term in clean
        for term in topical_terms
        if term and term not in GENERIC_REACTION_TERMS and term not in ignored_terms
    )
    quote_hit = any(phrase in clean for phrase in _extract_quote_phrases(f"{title}\n{summary}", max_phrases=2))
    status_terms = _extract_player_status_terms(title, summary) if category == "選手情報" else []
    status_hit = any(term in clean for term in status_terms if term and term not in GENERIC_REACTION_TERMS)
    category_hit = any(
        term in clean
        for term in CATEGORY_REACTION_TERMS.get(category, ())
        if term and term not in GENERIC_REACTION_TERMS
    )
    return {
        "topical_hit": topical_hit,
        "quote_hit": quote_hit,
        "status_hit": status_hit,
        "category_hit": category_hit,
    }


def _reaction_can_fill_shortage(
    text: str,
    title: str,
    summary: str,
    category: str,
    opinion_score: int,
    commentary_score: int,
    focus_score: int,
    focus_terms: list[str] | None = None,
) -> bool:
    clean = _strip_html(text or "")
    subject = _extract_subject_label(title, summary, category)
    compact_subject = _compact_subject_label(title, summary, category)
    family_name_alias = _player_family_name_alias(title, summary, category)
    player_mode = _detect_player_article_mode(title, summary, category) if category == "選手情報" else ""
    context_flags = _reaction_context_hit_flags(clean, title, summary, category, focus_terms=focus_terms)
    if focus_score >= 2:
        return False
    if not any(context_flags.values()):
        return False
    if category == "選手情報" and player_mode == "player_quote":
        quote_hit = context_flags["quote_hit"]
        context_term_hits = sum(1 for term in _extract_player_quote_context_terms(title, summary) if term in clean)
        return (
            _reaction_has_subject_context(clean, title, summary, category)
            and (quote_hit or context_term_hits >= 1)
            and (opinion_score >= 1 or commentary_score >= 1)
        )
    if category == "選手情報" and player_mode == "player_status":
        status_hits = sum(1 for term in _extract_player_status_terms(title, summary) if term in clean)
        return (
            _reaction_has_subject_context(clean, title, summary, category)
            and status_hits >= 1
            and (opinion_score >= 1 or commentary_score >= 1)
        )
    if focus_score >= 1 and (opinion_score >= 1 or commentary_score >= 1):
        return True
    if subject and subject not in {"巨人", "選手", "首脳陣"} and subject in clean and commentary_score >= 1:
        return True
    if compact_subject and compact_subject in clean and (opinion_score >= 1 or commentary_score >= 1):
        return True
    if category == "選手情報" and family_name_alias and family_name_alias in clean and commentary_score >= 1:
        return True
    if category != "選手情報" and family_name_alias and family_name_alias in clean and (opinion_score >= 1 or commentary_score >= 1):
        return True
    if any(term in clean for term in CATEGORY_REACTION_TERMS.get(category, ())) and (opinion_score >= 1 or commentary_score >= 1):
        return True
    return False


def _source_requires_precise_fan_reactions(source_name: str, category: str) -> bool:
    clean = source_name or ""
    if category in ALWAYS_PRECISE_FAN_REACTION_CATEGORIES:
        return True
    return category == "選手情報" and ("X" in clean or "公式" in clean)


def _reaction_matches_precise_source_context(
    text: str,
    title: str,
    summary: str,
    category: str,
    focus_terms: list[str],
) -> bool:
    clean = _strip_html(text or "")
    player_mode = _detect_player_article_mode(title, summary, category) if category == "選手情報" else ""
    context_flags = _reaction_context_hit_flags(clean, title, summary, category, focus_terms=focus_terms)
    if category == "選手情報" and player_mode == "player_quote":
        context_term_hits = sum(1 for term in _extract_player_quote_context_terms(title, summary) if term in clean)
        return context_flags["quote_hit"] or (
            _reaction_has_subject_context(clean, title, summary, category) and context_term_hits >= 1
        )
    if category == "選手情報" and player_mode == "player_status":
        status_hits = sum(1 for term in _extract_player_status_terms(title, summary) if term in clean)
        return _reaction_has_subject_context(clean, title, summary, category) and status_hits >= 1
    if context_flags["quote_hit"]:
        return True
    if category in ALWAYS_PRECISE_FAN_REACTION_CATEGORIES:
        return any(context_flags.values())
    return _reaction_has_subject_context(clean, title, summary, category) and (
        context_flags["topical_hit"] or context_flags["category_hit"] or context_flags["status_hit"]
    )


def _reaction_is_low_value_share(
    text: str,
    title: str,
    summary: str,
    opinion_score: int,
    commentary_score: int,
) -> bool:
    clean = _strip_html(text or "").strip()
    if "http" not in clean:
        return False
    if clean.startswith("【"):
        return True
    share_marker = clean.startswith("【") or any(marker in clean for marker in LOW_VALUE_SHARE_MARKERS)
    source_like = _reactions_are_too_similar(clean, f"{_strip_title_prefix(title)} {_strip_html(summary)}")
    if not share_marker and not source_like:
        return False
    return opinion_score <= 1 and commentary_score == 0


def _build_fan_reaction_focus_terms(title: str, summary: str, category: str) -> list[str]:
    subject = _compact_subject_label(title, summary, category)
    text = f"{_strip_title_prefix(title)} {_strip_html(summary)}"
    candidates = []
    player_mode = _detect_player_article_mode(title, summary, category) if category == "選手情報" else ""
    if category == "選手情報" and player_mode == "player_quote":
        candidates.extend(_extract_player_quote_context_terms(title, summary))
        return _dedupe_preserve_order(candidates)[:8]
    if category == "選手情報" and player_mode == "player_status":
        candidates.extend(_extract_player_status_terms(title, summary))
        return _dedupe_preserve_order([term for term in candidates if term not in GENERIC_REACTION_TERMS])[:8]
    for keyword in TOPICAL_REACTION_KEYWORDS:
        if keyword in text and keyword not in GENERIC_REACTION_TERMS:
            candidates.append(keyword)
    for token in _re.findall(r"[一-龥ァ-ヴーA-Za-z0-9]{2,10}", text):
        token = token.strip()
        if not token or token == subject or token in GENERIC_REACTION_TERMS:
            continue
        if token.isdigit():
            continue
        candidates.append(token)
    return _dedupe_preserve_order(candidates)[:8]


def _build_fan_reaction_queries(title: str, summary: str, category: str) -> list[str]:
    subject = _extract_subject_label(title, summary, category)
    compact_subject = _compact_subject_label(title, summary, category)
    team_query_subject = _player_team_query_subject(title, summary, subject) if category == "選手情報" else subject
    focus_terms = _build_fan_reaction_focus_terms(title, summary, category)
    player_mode = _detect_player_article_mode(title, summary, category) if category == "選手情報" else ""
    topic = _strip_title_prefix(title)
    topic = _re.sub(r"[「」『』【】\[\]]", "", topic)
    topic = topic[:24].strip("。 ")
    generic_subjects = {"選手", "首脳陣", "巨人"}
    allow_subject_only_queries = category not in SUBJECT_ONLY_FAN_REACTION_QUERY_BLOCK_CATEGORIES
    queries = []

    if category == "選手情報" and player_mode == "player_quote":
        quote_terms = _extract_quote_phrases(f"{title}\n{summary}", max_phrases=2)
        context_terms = [term for term in _extract_player_quote_context_terms(title, summary) if term not in quote_terms]
        if subject and subject not in generic_subjects:
            for phrase in quote_terms[:2]:
                queries.append(f"{subject} {phrase}")
            for term in context_terms[:2]:
                queries.append(f"{subject} {term}")
            queries.append(f"{team_query_subject} 巨人")
        if compact_subject and compact_subject not in generic_subjects and compact_subject != subject:
            for phrase in quote_terms[:1]:
                queries.append(f"{compact_subject} {phrase}")
            for term in context_terms[:1]:
                queries.append(f"{compact_subject} {term}")
        if quote_terms:
            queries.append(f"巨人 {quote_terms[0]}")
        return _dedupe_preserve_order(queries)[:6]

    if category == "選手情報" and player_mode == "player_status":
        status_terms = _extract_player_status_terms(title, summary)
        if subject and subject not in generic_subjects:
            for term in status_terms[:3]:
                queries.append(f"{subject} {term}")
            queries.append(f"{team_query_subject} 巨人")
        if compact_subject and compact_subject not in generic_subjects and compact_subject != subject:
            for term in status_terms[:2]:
                queries.append(f"{compact_subject} {term}")
            queries.append(f"{compact_subject} 巨人")
        if subject:
            queries.append(f"ジャイアンツ {subject}")
        return _dedupe_preserve_order(queries)[:6]

    if subject and subject not in generic_subjects:
        for term in focus_terms[:2]:
            queries.append(f"{subject} {term}")
        queries.append(f"{team_query_subject} 巨人")
        if allow_subject_only_queries:
            queries.append(subject)

    if compact_subject and compact_subject not in generic_subjects and compact_subject != subject:
        for term in focus_terms[:2]:
            queries.append(f"{compact_subject} {term}")
        queries.append(f"{compact_subject} 巨人")
        if allow_subject_only_queries:
            queries.append(compact_subject)

    for phrase in _extract_quote_phrases(title) + _extract_quote_phrases(summary):
        if subject and subject not in generic_subjects:
            queries.append(f"{subject} {phrase}")
        if compact_subject and compact_subject not in generic_subjects and compact_subject != subject:
            queries.append(f"{compact_subject} {phrase}")
        queries.append(f"巨人 {phrase}")

    if topic:
        queries.append(f"巨人 {topic}")

    if subject and category == "選手情報":
        queries.append(f"ジャイアンツ {team_query_subject}")

    return _dedupe_preserve_order(queries)[:6]


def _extract_article_heading_lines(text: str) -> list[str]:
    return [
        line.strip()
        for line in (text or "").split("\n")
        if line.strip().startswith("【") or line.strip().startswith("■") or line.strip().startswith("▶")
    ]


def _manager_section_count(text: str) -> int:
    normalized = _normalize_article_text_structure(text or "", "首脳陣", False, article_subtype="manager")
    headings = _extract_article_heading_lines(normalized)
    return len(_dedupe_preserve_order(headings))


def _manager_quote_count(title: str, summary: str) -> int:
    return len(_extract_quote_phrases(f"{title}\n{summary}", max_phrases=4))


MANAGER_QUOTE_REVIEW_SUBTYPES = frozenset(
    {
        "manager",
        "coach",
        "player_comment",
        "player_quote",
        "manager_quote",
        "coach_quote",
    }
)


def _should_review_zero_quote_manager(article_subtype, quote_count) -> bool:
    """quote_count=0 で manager / coach / player_comment 系なら review 倒し対象。"""
    normalized = str(article_subtype or "").strip().lower()
    if normalized not in MANAGER_QUOTE_REVIEW_SUBTYPES:
        return False
    try:
        return int(quote_count) == 0
    except (ValueError, TypeError):
        return False


def _maybe_route_zero_quote_manager_review(
    *,
    article_subtype: str,
    quote_count: int,
    title: str,
    source_name: str,
    logger: logging.Logger,
) -> _ManagerQuoteZeroReviewFallback | None:
    if not _should_review_zero_quote_manager(article_subtype, quote_count):
        return None
    logger.warning(
        json.dumps(
            {
                "event": "manager_quote_zero_review",
                "subtype": article_subtype,
                "title": title,
                "source_name": source_name,
                "reason": "quote_count_zero",
            },
            ensure_ascii=False,
        )
    )
    return _ManagerQuoteZeroReviewFallback("quote_count_zero")


def _maybe_route_weak_generated_title_review(
    *,
    article_subtype: str,
    rewritten_title: str,
    original_title: str,
    source_name: str,
    logger: logging.Logger,
) -> _WeakTitleReviewFallback | None:
    """LLM rewritten_title が weak かつ source title と異なる場合、review sentinel を返す。"""
    rewritten = str(rewritten_title or "").strip()
    original = str(original_title or "").strip()
    if not rewritten or rewritten == original:
        return None
    is_weak, weak_reason = is_weak_generated_title(rewritten)
    if not is_weak:
        return None
    logger.warning(
        json.dumps(
            {
                "event": "weak_generated_title_review",
                "subtype": article_subtype,
                "title": rewritten,
                "source_name": source_name,
                "reason": weak_reason,
            },
            ensure_ascii=False,
        )
    )
    return _WeakTitleReviewFallback(weak_reason)


def _maybe_route_weak_subject_title_review(
    *,
    article_subtype: str,
    rewritten_title: str,
    original_title: str,
    source_name: str,
    logger: logging.Logger,
    speaker_name: str = "",
) -> _WeakTitleReviewFallback | None:
    """生成 title が主語弱化 pattern の場合、review sentinel を返す。"""
    rewritten = str(rewritten_title or "").strip()
    original = str(original_title or "").strip()
    speaker = str(speaker_name or "").strip()
    if not rewritten or rewritten == original:
        return None
    is_weak, weak_reason = is_weak_subject_title(rewritten)
    speaker_is_non_name = bool(speaker) and is_non_name_speaker_label(speaker)
    if not is_weak and speaker_is_non_name and not title_has_person_name_candidate(rewritten):
        is_weak = True
        weak_reason = "generic_noun_only_no_person_name"
    if not is_weak:
        return None
    payload = {
        "event": "weak_subject_title_review",
        "subtype": article_subtype,
        "title": rewritten,
        "source_name": source_name,
        "reason": weak_reason,
    }
    if speaker_is_non_name:
        payload["speaker_name"] = speaker
    logger.warning(json.dumps(payload, ensure_ascii=False))
    return _WeakTitleReviewFallback(weak_reason)


def _manager_body_has_required_structure(text: str, has_game: bool) -> bool:
    normalized = _normalize_article_text_structure(text or "", "首脳陣", has_game, article_subtype="manager")
    headings = set(_extract_article_heading_lines(normalized))
    return all(heading in headings for heading in MANAGER_REQUIRED_HEADINGS)


def _build_manager_safe_fallback(title: str, summary: str, real_reactions: list[str] | None = None) -> str:
    def _clean_manager_fact(sentence: str) -> str:
        clean = _collapse_ws((sentence or "").replace("\n", " ").strip())
        clean = _re.sub(r"^【[^】]+】", "", clean).strip()
        return clean.rstrip("。")

    facts = [_clean_manager_fact(sentence) for sentence in _extract_summary_sentences(summary, max_sentences=4)]
    facts = [fact for fact in facts if fact]
    if not facts:
        title_text = _strip_title_prefix(title)
        facts = [_clean_manager_fact(title_text) or "元記事の内容を確認中です"]

    lead = facts[0]
    detail = facts[1] if len(facts) > 1 else ""
    extra = facts[2] if len(facts) > 2 else ""
    subject = _extract_subject_label(title, summary, "首脳陣")
    quote_phrases = _extract_quote_phrases(f"{title}\n{summary}", max_phrases=2)
    focus_axis = _extract_manager_focus_axis(title, summary)
    if quote_phrases and subject not in {"", "首脳陣"} and ("「" in lead or "『" in lead) and "」" not in lead and detail:
        lead = f"{subject}が「{quote_phrases[0]}」と話した"
        detail = ""

    intro_lines = [MANAGER_REQUIRED_HEADINGS[0]]
    intro_lines.append(f"{lead}。")
    if detail:
        intro_lines.append(f"{detail}。")
    else:
        intro_lines.append(f"この発言は、{subject}が{focus_axis}をどう動かそうとしているのかを見る材料です。")

    quote_lines = [MANAGER_REQUIRED_HEADINGS[1]]
    if quote_phrases:
        quote_lines.append(f"今回の発言の軸は「{quote_phrases[0]}」という言葉です。")
        if len(quote_phrases) >= 2:
            quote_lines.append(f"あわせて「{quote_phrases[1]}」という表現も出ており、判断の置きどころがより見えやすくなっています。")
        else:
            quote_lines.append(f"{subject}の言葉をそのまま追うことで、どこを重く見ているのかが読み取りやすくなります。")
    else:
        quote_lines.append(f"今回の記事では、{subject}が{focus_axis}について考えを示したことが発言の芯です。")
        quote_lines.append("言い回しの強さよりも、ベンチが何を動かそうとしているかに注目したいコメントです。")

    background_lines = [MANAGER_REQUIRED_HEADINGS[2]]
    if extra:
        background_lines.append(f"{extra}。")
    elif detail:
        background_lines.append(f"{detail}。")
    background_lines.append(_manager_context_line(focus_axis))

    reaction_line = ""
    if real_reactions:
        snippets = []
        for reaction in real_reactions[:2]:
            clean = _clean_reaction_snippet(_reaction_body_text(reaction))
            if clean:
                snippets.append(clean)
        if snippets:
            reaction_line = f"反応を見ると、この発言の強さよりも、{focus_axis}が実際にどう動くかを見たい空気が強いです。"

    next_lines = [MANAGER_REQUIRED_HEADINGS[3]]
    next_lines.append(_manager_next_watch_line(focus_axis, reaction_line=reaction_line))
    next_lines.append("みなさんの意見はコメントで教えてください！")

    return "\n".join(intro_lines + quote_lines + background_lines + next_lines)


def _extract_game_pitcher_lines(title: str, summary: str) -> list[str]:
    source_text = f"{title} {summary}"
    lines = []
    source_names = _extract_game_source_names(title, summary)
    pitcher_names = [name for name in source_names if f"{name}投手" in source_text]
    if "予告先発" in source_text and pitcher_names:
        if len(pitcher_names) >= 2:
            lines.append(f"予告先発は{pitcher_names[0]}と{pitcher_names[1]}です。")
        else:
            lines.append(f"予告先発は{pitcher_names[0]}です。")
    elif pitcher_names:
        lines.append(f"先発投手として見たいのは{pitcher_names[0]}です。")

    for fact in _extract_summary_sentences(summary, max_sentences=4):
        clean = fact.strip().rstrip("。")
        if any(token in clean for token in ("防御率", "勝", "敗", "WHIP", "奪三振", "先発")):
            lines.append(f"{clean}。")
    return _dedupe_preserve_order(lines)[:3]


def _build_lineup_safe_fallback(
    title: str,
    summary: str,
    lineup_rows: list[dict] | None = None,
    real_reactions: list[str] | None = None,
) -> str:
    facts = [fact.rstrip("。") for fact in _extract_summary_sentences(summary, max_sentences=5)]
    if not facts:
        facts = [_strip_title_prefix(title) or "元記事の内容を確認中です"]
    source_text = f"{title} {summary}"
    opponent = _extract_game_opponent_label(source_text)
    venue = _extract_game_venue_label(source_text)
    start_time = _extract_game_time_token(source_text)
    headings = _game_required_headings("lineup")

    intro_lines = [headings[0]]
    if opponent:
        overview_line = f"巨人は{opponent}戦に臨みます"
    else:
        overview_line = "巨人の試合前情報です"
    if venue:
        overview_line += f"。球場は{venue}です"
    if start_time:
        overview_line += f"。開始は{start_time}です"
    intro_lines.append(overview_line if overview_line.endswith("。") else f"{overview_line}。")
    intro_lines.append(f"{facts[0]}。")
    if len(facts) > 1:
        intro_lines.append(f"{facts[1]}。")
    else:
        intro_lines.append("スタメン発表の時点で、打順や守備位置のどこが動いたかが最初の論点です。")

    lineup_lines = [headings[1]]
    if lineup_rows:
        for row in lineup_rows[:9]:
            order = str(row.get("order") or "").strip()
            name = str(row.get("name") or "").strip()
            position = str(row.get("position") or "").strip()
            if order and name:
                lineup_lines.append(f"{order}番 {name} {position}".strip())
    else:
        listed = False
        for fact in facts[1:]:
            if any(marker in fact for marker in ("1番", "2番", "3番", "4番", "5番", "6番", "7番", "8番", "9番")):
                lineup_lines.append(f"{fact}。")
                listed = True
        if not listed:
            lineup_lines.append("元記事で確認できた打順と選手名を、そのまま追っておきたい並びです。")

    starter_lines = [headings[2]]
    starter_lines.extend(_extract_game_pitcher_lines(title, summary))
    if len(starter_lines) == 1:
        starter_lines.append("先発投手の情報は、元記事で確認できる範囲をそのまま押さえておきたいです。")

    watch_lines = [headings[3]]
    if real_reactions:
        watch_lines.append("反応を見ると、初回の入り方と上位打線の流れを早めに見たい空気が強いです。")
    else:
        watch_lines.append("まず見たいのは、この並びが初回の攻め方にどう出るかという点です。")
    watch_lines.append("スタメンの意味は試合が始まってからはっきりします。みなさんの意見はコメントで教えてください！")
    return "\n".join(intro_lines + lineup_lines + starter_lines + watch_lines)


def _build_postgame_safe_fallback(title: str, summary: str, real_reactions: list[str] | None = None) -> str:
    facts = [fact.rstrip("。") for fact in _extract_summary_sentences(summary, max_sentences=5)]
    if not facts:
        facts = [_strip_title_prefix(title) or "元記事の内容を確認中です"]
    source_text = f"{title} {summary}"
    score = _extract_game_score_token(source_text)
    opponent = _extract_game_opponent_label(source_text) or "相手"
    headings = _game_required_headings("postgame")

    result_lines = [headings[0]]
    result_sentence = facts[0]
    if score and score not in result_sentence:
        result_sentence = f"{result_sentence}。スコアは{score}でした"
    result_lines.append(f"{result_sentence}。")
    result_lines.append(f"{opponent}戦の勝敗とスコアを最初に押さえると、試合全体の見え方が揃います。")

    highlight_lines = [headings[1]]
    highlight_source = facts[1] if len(facts) > 1 else _strip_title_prefix(title)
    highlight_lines.append(f"{highlight_source.rstrip('。')}。")
    highlight_lines.append("決勝打や好投など、勝敗を動かした場面を先に追うと試合の芯が見えやすくなります。")

    stat_lines = [headings[2]]
    stat_facts = []
    for fact in facts[1:]:
        if any(token in fact for token in _extract_game_source_names(title, summary)) or _re.search(r"\d", fact):
            stat_facts.append(f"{fact.rstrip('。')}。")
    stat_lines.extend(_dedupe_preserve_order(stat_facts)[:2])
    if len(stat_lines) == 1:
        stat_lines.append("元記事にある数字と選手名を、そのまま並べて押さえておきたい試合です。")

    flow_lines = [headings[3]]
    if len(facts) > 2:
        flow_lines.append(f"{facts[2]}。")
    elif len(facts) > 1:
        flow_lines.append(f"{facts[1]}。")
    elif score:
        flow_lines.append(f"{score}で決まるまで、どこで流れが動いたかを見ておきたい試合でした。")
    else:
        flow_lines.append("どこで流れが傾いたかを追うと、この試合の見え方が整理しやすくなります。")
    if real_reactions:
        flow_lines.append("反応を見ると、勝敗だけでなく次戦へどの流れを持ち込めるかを見たい空気があります。")
    flow_lines.append("次戦にどの流れを持ち込めるかまで見ていきたいです。みなさんの意見はコメントで教えてください！")
    return "\n".join(result_lines + highlight_lines + stat_lines + flow_lines)


def _build_pregame_safe_fallback(title: str, summary: str, real_reactions: list[str] | None = None) -> str:
    facts = [fact.rstrip("。") for fact in _extract_summary_sentences(summary, max_sentences=5)]
    if not facts:
        facts = [_strip_title_prefix(title) or "元記事の内容を確認中です"]
    source_text = f"{title} {summary}"
    headings = _game_required_headings("pregame")
    opponent = _extract_game_opponent_label(source_text)
    venue = _extract_game_venue_label(source_text)
    start_time = _extract_game_time_token(source_text)

    lead_lines = [headings[0]]
    lead_lines.append(f"{facts[0]}。")
    if opponent or venue or start_time:
        details = []
        if opponent:
            details.append(f"{opponent}戦")
        if venue:
            details.append(venue)
        if start_time:
            details.append(start_time)
        lead_lines.append(" / ".join(details) + "の試合前情報として整理します。")

    detail_lines = [headings[1]]
    for fact in facts[1:3]:
        detail_lines.append(f"{fact}。")
    if len(detail_lines) == 1:
        detail_lines.append("元記事にある日程や先発情報を、そのまま押さえておきたい変更です。")

    impact_lines = [headings[2]]
    if real_reactions:
        impact_lines.append("反応を見ると、変更そのものよりも次の試合前の入り方をどう整えるかに視線が向いています。")
    else:
        impact_lines.append("結果予想より先に、この変更で次の試合前をどう迎えるかがポイントです。")
    impact_lines.append("変更の意味は実際の入り方にどう出るかで見えてきます。みなさんの意見はコメントで教えてください！")
    return "\n".join(lead_lines + detail_lines + impact_lines)


def _build_notice_safe_fallback(
    title: str,
    summary: str,
    real_reactions: list[str] | None = None,
    source_day_label: str = "",
) -> str:
    facts = [fact.rstrip("。") for fact in _extract_summary_sentences(summary, max_sentences=5)]
    if not facts:
        facts = [_strip_title_prefix(title) or "元記事の内容を確認中です"]
    subject, notice_type = _extract_notice_subject_and_type(title, summary)
    player_position = _extract_notice_player_position(title, summary, subject)
    notice_subject = subject or player_position
    notice_label = notice_type or _extract_notice_type_label(f"{title} {summary}") or "公示"
    record_fact = _extract_notice_record_fact(title, summary)
    background_fact = _extract_notice_background_fact(title, summary, exclude={record_fact} if record_fact else set())
    opening = f"（{source_day_label}時点）" if source_day_label else ""

    lead_lines = [NOTICE_REQUIRED_HEADINGS[0]]
    lead_lines.append(f"{opening}{notice_subject}に{notice_label}の動きが出ました。".strip())
    lead_lines.append(f"{facts[0]}。")
    if len(facts) > 1:
        lead_lines.append(f"{facts[1]}。")

    basic_lines = [NOTICE_REQUIRED_HEADINGS[1]]
    basic_lines.append(f"{notice_subject}は読売ジャイアンツの{player_position}です。")
    if record_fact:
        basic_lines.append(record_fact)
    else:
        basic_lines.append(f"{notice_subject}の今季成績や現在の立ち位置は、元記事で確認できる範囲を押さえておきたいところです。")

    background_lines = [NOTICE_REQUIRED_HEADINGS[2]]
    if background_fact:
        background_lines.append(background_fact)
    elif len(facts) > 2:
        background_lines.append(f"{facts[2]}。")
    else:
        background_lines.append(f"{notice_subject}に今回の公示が出た背景は、元記事の事実を順に追うと見えやすくなります。")
    if len(facts) > 3 and facts[3] not in background_lines:
        background_lines.append(f"{facts[3]}。")

    next_lines = [NOTICE_REQUIRED_HEADINGS[3]]
    if real_reactions:
        next_lines.append(f"反応を見ると、{notice_subject}が次にどんな役割を得るかを見たい空気があります。")
    next_lines.append(_notice_next_focus_sentence(notice_label, player_position, notice_subject))
    next_lines.append("みなさんの意見はコメントで教えてください！")
    return "\n".join(lead_lines + basic_lines + background_lines + next_lines)


def _build_recovery_safe_fallback(
    title: str,
    summary: str,
    real_reactions: list[str] | None = None,
    source_day_label: str = "",
) -> str:
    facts = [fact.rstrip("。") for fact in _extract_summary_sentences(summary, max_sentences=6)]
    if not facts:
        facts = [_strip_title_prefix(title) or "元記事の内容を確認中です"]
    subject = _extract_recovery_subject(title, summary)
    player_position = _extract_notice_player_position(title, summary, subject)
    injury_part = _extract_recovery_injury_part(title, summary, subject)
    return_timing = _extract_recovery_return_timing(title, summary, subject)
    detail_fact = _extract_recovery_detail_fact(title, summary)
    progress_fact = _extract_recovery_progress_fact(title, summary, exclude={detail_fact} if detail_fact else set())
    impact_fact = _extract_recovery_impact_fact(
        title,
        summary,
        exclude={fact for fact in [detail_fact, progress_fact] if fact},
    )
    opening = f"（{source_day_label}時点）" if source_day_label else ""

    lead_lines = [RECOVERY_REQUIRED_HEADINGS[0]]
    lead_lines.append(f"{opening}{subject}の故障・復帰状況を整理します。".strip())
    lead_lines.append(f"{facts[0]}。")
    if len(facts) > 1:
        lead_lines.append(f"{facts[1]}。")

    detail_lines = [RECOVERY_REQUIRED_HEADINGS[1]]
    if injury_part:
        detail_lines.append(f"{subject}は{player_position}で、現在確認できる部位は{injury_part}です。")
    else:
        detail_lines.append(f"{subject}は読売ジャイアンツの{player_position}です。")
    if detail_fact:
        detail_lines.append(detail_fact)

    progress_lines = [RECOVERY_REQUIRED_HEADINGS[2]]
    if progress_fact:
        progress_lines.append(progress_fact)
    elif return_timing:
        progress_lines.append(f"{subject}の復帰見通しは「{return_timing}」と整理できます。")
    else:
        progress_lines.append(f"{subject}のリハビリ状況や復帰の段階は、元記事の事実をそのまま追いたいところです。")

    impact_lines = [RECOVERY_REQUIRED_HEADINGS[3]]
    if impact_fact:
        impact_lines.append(impact_fact)
    elif len(facts) > 2:
        impact_lines.append(f"{facts[2]}。")
    else:
        impact_lines.append(f"{subject}が戻るまでの代役や復帰後の起用がどう動くかを見たいところです。")
    if real_reactions:
        impact_lines.append(f"反応を見ると、{subject}の復帰時期と起用のされ方を見たい声があります。")
    impact_lines.append("みなさんの意見はコメントで教えてください！")
    return "\n".join(lead_lines + detail_lines + progress_lines + impact_lines)


def _build_game_safe_fallback(
    title: str,
    summary: str,
    article_subtype: str,
    lineup_rows: list[dict] | None = None,
    real_reactions: list[str] | None = None,
) -> str:
    if article_subtype == "live_anchor":
        facts = [fact.rstrip("。") for fact in _extract_summary_sentences(summary, max_sentences=5)]
        if not facts:
            facts = [_strip_title_prefix(title) or "元記事の内容を確認中です"]
        source_text = f"{title} {summary}"
        headings = _game_required_headings("live_anchor")
        state_match = _re.search(r"(\d+回(?:表|裏)(?:終了)?時点|\d+回\d死時点)", source_text)
        state_label = state_match.group(1) if state_match else ""
        score = _extract_game_score_token(source_text)
        opponent = _extract_game_opponent_label(source_text) or "相手"

        time_lines = [headings[0]]
        if state_label:
            time_lines.append(f"{state_label}という節目で、試合の流れを整理します。")
        else:
            time_lines.append("節目の時点は元記事で確認できる範囲を整理します。")

        score_lines = [headings[1]]
        if score:
            score_lines.append(f"現在スコアは{opponent}戦で{score}です。")
        else:
            score_lines.append(f"現在スコアは{opponent}戦の途中経過として確認中です。")

        play_lines = [headings[2]]
        play_facts = []
        for fact in facts:
            clean = fact.rstrip("。")
            if not clean:
                continue
            if state_label and state_label in clean and len(facts) > 1:
                continue
            if score and score in clean and len(facts) > 1:
                continue
            play_facts.append(f"{clean}。")
        play_lines.extend(_dedupe_preserve_order(play_facts)[:2])
        if len(play_lines) == 1:
            play_lines.append("その時点までの主なプレーは、元記事で確認できる範囲を押さえておきたいです。")

        fan_lines = [headings[3]]
        if real_reactions:
            fan_lines.append("反応を見ると、この節目のあとにどこで流れが動くかを見たい空気があります。")
        fan_lines.append("この節目のあとに次の1点や継投がどう動くかは気になります。みなさんの意見はコメントで教えてください！")
        return "\n".join(time_lines + score_lines + play_lines + fan_lines)
    if article_subtype == "lineup":
        return _build_lineup_safe_fallback(title, summary, lineup_rows=lineup_rows, real_reactions=real_reactions)
    if article_subtype == "postgame":
        return _build_postgame_safe_fallback(title, summary, real_reactions=real_reactions)
    return _build_pregame_safe_fallback(title, summary, real_reactions=real_reactions)


def _build_farm_safe_fallback(title: str, summary: str, real_reactions: list[str] | None = None) -> str:
    facts = [fact.rstrip("。") for fact in _extract_summary_sentences(summary, max_sentences=6)]
    if not facts:
        facts = [_strip_title_prefix(title) or "元記事の内容を確認中です"]
    source_text = f"{title} {summary}"
    score = _extract_game_score_token(source_text)
    drafted_story = _farm_is_drafted_player_story(title, summary)

    lead_lines = [FARM_REQUIRED_HEADINGS["farm"][0]]
    if score:
        lead_lines.append(f"巨人二軍の試合は{score}という結果でした。")
    lead_lines.append(f"{facts[0]}。")
    if len(facts) > 1:
        lead_lines.append(f"{facts[1]}。")

    highlight_lines = [FARM_REQUIRED_HEADINGS["farm"][1]]
    if len(facts) > 2:
        highlight_lines.append(f"{facts[2]}。")
    elif len(facts) > 1:
        highlight_lines.append(f"{facts[1]}。")
    else:
        highlight_lines.append("二軍戦では得点の動きと投手の内容を先に押さえると全体像が見えやすくなります。")
    highlight_lines.append("ファームの結果は、一軍へ上げたい選手がどこで数字を残したかを見る材料になります。")

    stat_lines = [FARM_REQUIRED_HEADINGS["farm"][2]]
    stat_facts = []
    for fact in facts:
        if _re.search(r"\d", fact):
            stat_facts.append(f"{fact}。")
    stat_lines.extend(_dedupe_preserve_order(stat_facts)[:2])
    if len(stat_lines) == 1:
        stat_lines.append("元記事にある打率、本塁打、打点、投球回などの数字をそのまま追っておきたい内容です。")

    watch_lines = [FARM_REQUIRED_HEADINGS["farm"][3]]
    if drafted_story:
        watch_lines.append("ドラフトや育成の立場にある選手は、二軍の数字がそのまま一軍昇格の材料になります。")
    else:
        watch_lines.append("二軍での内容が次の一軍候補争いにどうつながるかを見たいところです。")
    if real_reactions:
        watch_lines.append("反応を見ると、結果だけでなく一軍に近づく打席内容や投球内容を見たい空気があります。")
    watch_lines.append("次にどんな数字を積み上げるかまで追っていきたいです。みなさんの意見はコメントで教えてください！")
    return "\n".join(lead_lines + highlight_lines + stat_lines + watch_lines)


def _build_farm_lineup_safe_fallback(title: str, summary: str, real_reactions: list[str] | None = None) -> str:
    facts = [fact.rstrip("。") for fact in _extract_summary_sentences(summary, max_sentences=5)]
    if not facts:
        facts = [_strip_title_prefix(title) or "元記事の内容を確認中です"]
    source_text = f"{title} {summary}"
    opponent = _extract_game_opponent_label(source_text)
    venue = _extract_game_venue_label(source_text)
    start_time = _extract_game_time_token(source_text)
    drafted_story = _farm_is_drafted_player_story(title, summary)

    lead_lines = [FARM_REQUIRED_HEADINGS["farm_lineup"][0]]
    overview = "巨人二軍の試合前情報です"
    if opponent:
        overview = f"巨人二軍は{opponent}戦に臨みます"
    if venue:
        overview += f"。球場は{venue}です"
    if start_time:
        overview += f"。開始は{start_time}です"
    lead_lines.append(overview if overview.endswith("。") else f"{overview}。")
    lead_lines.append(f"{facts[0]}。")
    if len(facts) > 1:
        lead_lines.append(f"{facts[1]}。")

    lineup_lines = [FARM_REQUIRED_HEADINGS["farm_lineup"][1]]
    lineup_facts = []
    for fact in facts:
        if any(marker in fact for marker in ("1番", "2番", "3番", "4番", "5番", "6番", "7番", "8番", "9番", "スタメン", "先発")):
            lineup_facts.append(f"{fact}。")
    lineup_lines.extend(_dedupe_preserve_order(lineup_facts)[:3])
    if len(lineup_lines) == 1:
        lineup_lines.append("元記事で確認できる打順と選手名を、そのまま追っておきたい二軍スタメンです。")

    watch_lines = [FARM_REQUIRED_HEADINGS["farm_lineup"][2]]
    if drafted_story:
        watch_lines.append("ドラフトや育成の選手がどの打順と守備位置で起用されているかが最初の見どころです。")
    else:
        watch_lines.append("若手や調整組をどこに置いたかが、この二軍スタメンの見どころです。")
    if real_reactions:
        watch_lines.append("反応を見ると、二軍でも一軍昇格につながる並びかどうかを見たい空気があります。")
    watch_lines.append("試合が始まったら、並びの意図がどこに出るかを見たいところです。みなさんの意見はコメントで教えてください！")
    return "\n".join(lead_lines + lineup_lines + watch_lines)


def _build_social_safe_fallback(
    title: str,
    summary: str,
    category: str,
    source_name: str = "",
    tweet_url: str = "",
    source_day_label: str = "",
    real_reactions: list[str] | None = None,
) -> str:
    facts = _extract_summary_sentences(summary, max_sentences=4)
    if not facts:
        title_text = _strip_title_prefix(title)
        facts = [title_text or "X投稿で伝えられた内容を確認中です"]

    source_label = _social_source_intro_label(source_name, tweet_url=tweet_url)
    display_source = _display_source_name(source_name or "X")
    quote_phrases = _extract_quote_phrases(f"{title}\n{summary}", max_phrases=2)
    intro_prefix = f"（{source_day_label}時点）" if source_day_label else ""
    lead_lines = [SOCIAL_REQUIRED_HEADINGS[0]]
    lead_lines.append(f"{intro_prefix}{source_label}として、{facts[0]}。".strip())
    if len(facts) > 1:
        lead_lines.append(f"{facts[1]}。")
    else:
        lead_lines.append(f"{display_source}が伝えた要点を、最初に整理したい話題です。")

    summary_lines = [SOCIAL_REQUIRED_HEADINGS[1]]
    if quote_phrases:
        summary_lines.append(f"{display_source}の投稿では『{quote_phrases[0]}』という言い回しが目を引きます。")
    summary_lines.append(f"{facts[0]}。")
    if len(facts) > 2:
        summary_lines.append(f"{facts[2]}。")

    background_lines = [SOCIAL_REQUIRED_HEADINGS[2]]
    if len(facts) > 3:
        background_lines.append(f"{facts[3]}。")
    else:
        background_lines.append(_social_background_focus_line(category) + "。")

    reaction_line = ""
    if real_reactions:
        snippets = []
        for reaction in real_reactions[:2]:
            clean = _clean_reaction_snippet(_reaction_body_text(reaction))
            if clean:
                snippets.append(clean)
        if snippets:
            reaction_line = f"反応を見ると「{' / '.join(snippets)}」という温度感があり、この話題の受け止め方が分かれています。"

    watch_lines = [SOCIAL_REQUIRED_HEADINGS[3]]
    watch_lines.append(reaction_line or "巨人ファンにとっては、この発信が次の試合や起用、話題の広がりにどう動くかを見ておきたいところです。")
    watch_lines.append("発信内容そのものだけでなく、ここからどんな動きにつながるかを見たいところです。みなさんの意見はコメントで教えてください！")
    return "\n".join(lead_lines + summary_lines + background_lines + watch_lines)


def _build_safe_article_fallback(
    title: str,
    summary: str,
    category: str,
    has_game: bool,
    source_name: str = "",
    source_type: str = "news",
    tweet_url: str = "",
    source_day_label: str = "",
    real_reactions: list[str] | None = None,
) -> str:
    article_subtype = _detect_article_subtype(title, summary, category, has_game)
    if source_type == "social_news" and not _social_source_prefers_structured_template(category, article_subtype):
        return _build_social_safe_fallback(
            title,
            summary,
            category,
            source_name=source_name,
            tweet_url=tweet_url,
            source_day_label=source_day_label,
            real_reactions=real_reactions,
        )
    if category == "首脳陣":
        return _build_manager_safe_fallback(title, summary, real_reactions=real_reactions)
    if category == "ドラフト・育成" and article_subtype == "farm":
        return _build_farm_safe_fallback(title, summary, real_reactions=real_reactions)
    if category == "ドラフト・育成" and article_subtype == "farm_lineup":
        return _build_farm_lineup_safe_fallback(title, summary, real_reactions=real_reactions)

    facts = _extract_summary_sentences(summary, max_sentences=4)
    if not facts:
        title_text = _strip_title_prefix(title)
        facts = [title_text or "元記事の内容を確認中です"]

    if article_subtype == "fact_notice":
        correction_headings = ("【訂正の対象】", "【訂正内容】", "【訂正元】", "【お詫び / ファン視点】")
        title_target = _strip_title_prefix(title)
        title_target = _re.sub(r"^(?:訂正|誤報|取り下げ)\s*", "", title_target).strip("　 。")
        target_line = title_target or facts[0].rstrip("。")
        correction_lines = []
        for fact in facts:
            clean = fact.rstrip("。")
            if any(marker in clean for marker in FACT_NOTICE_PRIMARY_MARKERS) or any(
                marker in clean for marker in ("正しくは", "誤って", "修正", "訂正内容")
            ):
                correction_lines.append(f"{clean}。")
        source_meta = [item for item in (source_name, source_day_label, tweet_url) if item]

        paragraphs = [
            correction_headings[0],
            f"訂正の対象は{target_line or '元記事で確認中の内容'}です。",
        ]
        if facts and target_line and target_line not in facts[0]:
            paragraphs.append(f"{facts[0].rstrip('。')}。")
        paragraphs.append(correction_headings[1])
        if correction_lines:
            paragraphs.extend(_dedupe_preserve_order(correction_lines)[:2])
        else:
            paragraphs.append("訂正内容は確認中です。")
        paragraphs.append(correction_headings[2])
        if source_meta:
            paragraphs.append(f"訂正元は{' / '.join(source_meta)}です。")
        else:
            paragraphs.append("訂正元は元記事で確認中です。")
        paragraphs.append(correction_headings[3])
        if correction_lines:
            paragraphs.append("現時点で確認できた範囲だけを整理しました。追加の訂正があれば追記します。")
        else:
            paragraphs.append("訂正内容は確認中です。確認できた事実だけを短く整理します。")
        return "\n".join(paragraphs)

    lead = facts[0].rstrip("。")
    detail = facts[1].rstrip("。") if len(facts) > 1 else ""
    extra = facts[2].rstrip("。") if len(facts) > 2 else ""
    extra2 = facts[3].rstrip("。") if len(facts) > 3 else ""
    subject = _extract_subject_label(title, summary, category)
    topic = _strip_title_prefix(title)
    pregame_article = _is_pregame_article(title, summary, category, has_game)
    quote_phrases = _extract_quote_phrases(f"{title}\n{summary}", max_phrases=2)
    player_mode = _detect_player_article_mode(title, summary, category) if category == "選手情報" else ""
    player_mechanics_story = player_mode == "player_mechanics"
    player_quote_story = player_mode == "player_quote"
    player_status_story = player_mode == "player_status"
    player_status_terms = _extract_player_status_terms(title, summary) if category == "選手情報" else []
    subject_display = _extract_player_role_label(title, summary) if category == "選手情報" and player_mechanics_story else subject
    intro = "まずは今回のニュースで押さえておきたいポイントから整理します。"
    if category == "選手情報":
        if player_mechanics_story:
            intro = f"{subject_display}が何を変えているのか整理します。"
        elif player_quote_story:
            intro = f"{subject}のコメントと試合前の論点を整理します。"
        else:
            intro = f"{subject}の現状を整理します。"
    elif category == "首脳陣":
        intro = "整理すると、今回のニュースは3点です。"
    elif category == "補強・移籍":
        intro = "補強の話は名前より先に、チームのどこを埋める話なのかを整理します。"
    elif category == "ドラフト・育成" and article_subtype == "farm_lineup":
        intro = "まずは二軍スタメンの並びを整理します。"
    elif category == "試合速報":
        if article_subtype == "lineup":
            intro = "まずは今日のスタメンの並びを整理します。"
        elif article_subtype == "live_update":
            intro = "まずは今のスコアと流れが動いた場面を整理します。"
        else:
            intro = "この試合で何が焦点だったのか、元記事の事実に沿って整理します。"
        if pregame_article and article_subtype != "lineup":
            intro = "先に、巨人ファンが試合前から気にしていた論点を整理します。"

    reaction_line = ""
    if real_reactions:
        snippets = []
        for reaction in real_reactions[:2]:
            clean = _clean_reaction_snippet(_reaction_body_text(reaction))
            if clean:
                snippets.append(clean)
        if snippets and category == "選手情報" and player_mechanics_story:
            reaction_line = f"反応を見ると、{subject}の今回の好投そのものより、いまのフォーム変更が次の実戦でも続くかを見たい空気が強いです。"
        elif snippets and category == "選手情報" and player_quote_story and quote_phrases:
            reaction_line = f"反応を見ると、{subject}が口にした「{quote_phrases[0]}」という意識が次の実戦でどう出るかを見たい空気が強いです。"
        elif snippets and category == "選手情報" and player_status_story:
            if any(term in player_status_terms for term in ("昇格", "一軍", "登録", "復帰", "合流")):
                reaction_line = f"反応を見ると、{subject}の今回の動きが一軍での立ち位置にどうつながるかを見たい空気が強いです。"
            else:
                reaction_line = f"反応を見ると、{subject}の今回の動きが次の登板や実戦内容にどうつながるかを見たい空気が強いです。"
        elif snippets and category == "選手情報":
            reaction_line = f"反応を見ると、{subject}の今回のコメントや準備が次の実戦でどう表れるかを見たい空気が強いです。"
        elif snippets and category == "首脳陣":
            reaction_line = "反応を見ると、このコメントの強さそのものより、次のスタメンや起用がどう動くかを見たい空気が強いです。"
        elif snippets:
            joined = " / ".join(snippets)
            reaction_line = f"反応を見ると「{joined}」という温度感があり、次の動きへの期待と不安が同時に出ている話題です。"

    if category == "選手情報" and player_mechanics_story:
        closing = f"{subject}は次の実戦で、今回いじっている部分をそのまま出せるかが一番の見どころです。結果より先に、球の見え方がどう変わるかを追っていきたいです。今回の記事は、その入口としてかなり分かりやすい材料になっています。みなさんの意見はコメントで教えてください！"
    elif category == "選手情報" and player_quote_story and quote_phrases:
        closing = f"{subject}は次の実戦で、今回口にした「{quote_phrases[0]}」という意識をどこまで内容に落とし込めるかが見どころです。言葉だけで終わるのか、阪神戦の入り方や配球にまで出るのかを追っていきたいです。みなさんの意見はコメントで教えてください！"
    elif category == "選手情報" and player_status_story:
        if any(term in player_status_terms for term in ("昇格", "一軍", "登録", "復帰", "合流")):
            closing = f"{subject}は次に、一軍でどこまで役割をもらえるかが見どころです。名前が戻るだけで終わるのか、実際の起用や序列にまで踏み込むのかを追っていきたいです。みなさんの意見はコメントで教えてください！"
        else:
            closing = f"{subject}は次の実戦で、今回の動きがどこまで内容に出るかが見どころです。二軍戦や調整登板の先で、一軍につながる材料をどこまで見せられるかを追っていきたいです。みなさんの意見はコメントで教えてください！"
    elif category == "選手情報":
        closing = f"{subject}は次の実戦で、今回のコメントや準備がどこまで内容に出るかが見どころです。結果だけでなく、入り方や組み立ての変化まで追っていきたいです。みなさんの意見はコメントで教えてください！"
    elif category == "首脳陣":
        closing = "このコメントが次のスタメンや継投、ベンチの空気にどう出るかまで見ていきたいです。誰を残し、誰を動かすのかまで見えてくると、この発言の重さも変わってきます。みなさんの意見はコメントで教えてください！"
    elif category == "試合速報":
        if article_subtype == "lineup":
            closing = "スタメン発表の時点では、並びの意味をどう読むかが一番のポイントです。試合が始まって最初にどこを見るかまで、コメントで教えてください！"
        elif article_subtype == "live_update":
            closing = "途中経過の記事で大事なのは、スコアそのものより流れがどこで変わったかです。ここから次にどこを見るか、コメントで教えてください！"
        elif _source_has_confirmed_result(title, summary):
            closing = "試合内容の手応えと課題が次戦の流れにどうつながるか、ここからの修正点も含めて見ていきたいです。みなさんの意見はコメントで教えてください！"
        else:
            closing = "この登板や試合前の空気が実際の結果にどうつながるか、次の動きまで追っていきたいです。みなさんの意見はコメントで教えてください！"
    elif category == "補強・移籍":
        closing = "補強や移籍の話は、実際に動いた後の競争と編成の変化まで見て初めて評価できます。みなさんの意見はコメントで教えてください！"
    elif category == "ドラフト・育成" and article_subtype == "farm_lineup":
        closing = "二軍スタメンは結果より先に、誰をどこで試しているかを見る記事です。一軍につながりそうな並びや守備位置まで、コメントで教えてください！"
    else:
        closing = "ここでは元記事の事実を土台に論点を整理しました。続報が出れば見え方も変わるので、みなさんの意見はコメントで教えてください！"

    headings = list(_article_section_headings(category, has_game))

    if article_subtype == "farm_lineup":
        farm_focus = extra2 or "二軍スタメンで見たいのは、若手や調整組をどこに置いたかです。"
        farm_context = ""
        if detail:
            farm_context = f"{detail}。この配置が、いま何を試しているかを読む入口になります。"
        elif extra:
            farm_context = f"{extra}。この並びが一軍昇格や守備位置テストのヒントになります。"
        elif topic and topic not in lead:
            farm_context = f"{topic}というテーマが、今回の二軍スタメンを読む入口です。"

        paragraphs = [
            headings[0],
            intro,
            f"{lead}。",
        ]
        if detail:
            paragraphs.append(f"{detail}。")
        paragraphs.extend([
            headings[1],
            farm_focus if farm_focus.endswith("。") else f"{farm_focus}。",
        ])
        if extra:
            paragraphs.append(f"{extra}。")
        if farm_context:
            paragraphs.append(farm_context if farm_context.endswith("。") else f"{farm_context}。")
        paragraphs.extend([
            headings[2],
            reaction_line if reaction_line else "まず見たいのは、この並びが一軍昇格の候補や守備位置テストにどうつながるかという点です。",
            closing,
        ])
    elif article_subtype == "lineup":
        lineup_focus = extra2 or "今日のスタメン記事で大事なのは、誰が入ったかだけでなく、打順や守備位置のどこが動いたかです。"
        lineup_context = ""
        if detail:
            lineup_context = f"{detail}。この1行が、ベンチの狙いを読む入口になります。"
        elif extra:
            lineup_context = f"{extra}。この動きが今日の攻め方を考える材料になります。"
        elif topic and topic not in lead:
            lineup_context = f"{topic}というテーマが、今日のスタメンを読む入口です。"

        paragraphs = [
            headings[0],
            intro,
            f"{lead}。",
        ]
        if detail:
            paragraphs.append(f"{detail}。")
        paragraphs.extend([
            headings[1],
            lineup_focus if lineup_focus.endswith("。") else f"{lineup_focus}。",
        ])
        if extra:
            paragraphs.append(f"{extra}。")
        if lineup_context:
            paragraphs.append(lineup_context if lineup_context.endswith("。") else f"{lineup_context}。")
        paragraphs.extend([
            headings[2],
            reaction_line if reaction_line else "試合前にまず見たいのは、この並びが初回からどう機能するか、そしてベンチがどこを勝負どころに置いているかです。",
            closing,
        ])
    elif article_subtype == "live_update":
        live_focus = extra2 or "途中経過では、いまのスコアより先に流れがどこで動いたかを見るのが大事です。"
        live_context = ""
        if detail:
            live_context = f"{detail}。この場面が、いまの試合の空気を左右しています。"
        elif extra:
            live_context = f"{extra}。ここまでの流れを読む材料になります。"
        elif topic and topic not in lead:
            live_context = f"{topic}というテーマが、いまの途中経過を読む入口です。"

        paragraphs = [
            headings[0],
            intro,
            f"{lead}。",
        ]
        if detail:
            paragraphs.append(f"{detail}。")
        paragraphs.extend([
            headings[1],
            live_focus if live_focus.endswith("。") else f"{live_focus}。",
        ])
        if extra:
            paragraphs.append(f"{extra}。")
        if live_context:
            paragraphs.append(live_context if live_context.endswith("。") else f"{live_context}。")
        paragraphs.extend([
            headings[2],
            reaction_line if reaction_line else "ここから同点・勝ち越し・継投のどこが次に動くかが見どころです。",
            closing,
        ])
    elif pregame_article:
        quote_line = ""
        if quote_phrases:
            quote_line = f"今回の話題で目を引くのは「{quote_phrases[0]}」という言葉です。試合前の記事だからこそ、この一言に試合への入り方や集中の置きどころが表れています。"
        pregame_focus = extra2 or "結果が出る前の記事だからこそ、入っていき方や空気への向き合い方が大きな論点になります。"
        context_line = ""
        if extra:
            context_line = f"{extra}。この背景があるからこそ、球場の空気にどう入るかへ視線が集まります。"
        elif extra2:
            context_line = f"{extra2}。この仕切り直し感も、試合前の記事に独特の熱を残しています。"
        if not context_line and topic and topic not in lead:
            context_line = f"{topic}というテーマそのものが、この試合前の記事を厚くしているポイントです。"

        paragraphs = [
            headings[0],
            intro,
            f"{lead}。",
            "試合結果がまだ出ていない段階でも、この記事には登板前ならではの緊張感が残っています。",
        ]
        if detail:
            paragraphs.append(f"{detail}。")
        paragraphs.extend([
            headings[1],
            f"{pregame_focus}。" if pregame_focus and not pregame_focus.endswith("。") else pregame_focus,
        ])
        if quote_line:
            paragraphs.append(quote_line)
        if context_line:
            paragraphs.append(f"{context_line}。" if context_line and not context_line.endswith("。") else context_line)
        paragraphs.extend([
            headings[2],
            reaction_line if reaction_line else "結果が出る前の記事だからこそ、巨人ファンが見たいのは目先の勝敗予想よりも、この空気が実際の登板内容にどうつながるかという点です。",
            closing,
        ])
    else:
        focus_line = ""
        watch_line = reaction_line if reaction_line else "ここで見ておきたいのは、単なる事実確認だけでなく、この動きが次の試合や起用にどうつながるかという点です。"
        news_lines = []
        if category == "選手情報":
            if player_mechanics_story and quote_phrases:
                focus_line = f"今回の言葉で目を引くのは「{quote_phrases[0]}」という部分です。フォームそのものより、外からの助言を受け入れて投げ方を組み替えているところに今の本気度が出ています。数字だけを追う記事ではなく、何を崩してでも前へ進もうとしているのかが見える話です。完成形を守る段階ではなく、自分を崩してでも戻しにいっているところが今回の芯です。"
            elif player_quote_story and quote_phrases:
                focus_line = f"今回のニュースで目を引くのは「{quote_phrases[0]}」という言葉です。コメントの強さだけでなく、{subject}が相手打線へどう入ろうとしているのか、その考え方が短い一言の中に出ています。試合前の記事として読むと、調子の良し悪しより先に、何を意識してマウンドに上がるのかが見えてくる材料です。"
                watch_line = reaction_line if reaction_line else f"次に見たいのは、{subject}が口にした「{quote_phrases[0]}」という意識が実戦の内容にどうつながるかという点です。立ち上がりや配球の組み立てにその考えが出るなら、今回のコメントの重さも見えてきます。"
            elif player_status_story:
                if any(term in player_status_terms for term in ("昇格", "一軍", "登録", "復帰", "合流")):
                    focus_line = f"今回のニュースで大事なのは、{subject}がいま一軍の戦力表のどこに戻ってくるのかという点です。名前が載ったこと自体より、どの役割で呼ばれるのか、既存の序列をどう動かすのかまで見て読む記事です。復帰や昇格はゴールではなく、ここからどこまで食い込めるかが本当の焦点になります。"
                    watch_line = reaction_line if reaction_line else f"次に見たいのは、{subject}が今回の動きの先でどんな役割をもらうかという点です。ベンチ入りだけで終わるのか、スタメンや勝ちパターンまで踏み込むのかを見ていきたいです。"
                else:
                    focus_line = f"今回のニュースで大事なのは、{subject}がいまどの段階にいるのかという点です。二軍戦や調整登板の見出しだけで終わらず、一軍へ上がる前のどこを確認している段階なのかを整理して読むべき記事です。状態そのものより、チームが何をチェックしているのかまで見えると意味が変わってきます。"
                    watch_line = reaction_line if reaction_line else f"次に見たいのは、{subject}の今回の動きが次の登板や一軍合流にどうつながるかという点です。数字だけでなく、起用のされ方まで追っていきたいです。"
            else:
                focus_line = f"数字以上に気になるのは、{subject}が今回どんな入り方や準備を意識しているのかという点です。単に状態を追う記事ではなく、次の実戦で何を見ればいいかのヒントが入っているタイプの話です。短いコメントでも、相手や場面に対する考え方が見えると読み味はかなり変わってきます。"
                watch_line = reaction_line if reaction_line else f"次に見たいのは、{subject}の今回のコメントや準備が次の実戦でもそのまま出るかという点です。立ち上がりや攻め方に変化が見えれば、今回の記事の意味もはっきりしてきます。"
            if player_mechanics_story:
                watch_line = reaction_line if reaction_line else f"次に見たいのは、{subject}の今回の調整が次の実戦でもそのまま出るかという点です。球筋や制球の見え方が変わるなら、今回の取り組みが本物かどうかも見えてきます。"
        elif category == "試合速報":
            focus_line = "結果だけを並べるより、どこで流れが動いたかを見ておきたい試合です。得点の前後で何が起きたのかまで追うと、見え方が変わってきます。"
            watch_line = reaction_line if reaction_line else "次に見たいのは、この試合で出た手応えや課題が次戦にも続くのかという点です。"
        elif category == "首脳陣":
            if quote_phrases:
                if "若手" in f"{title}{summary}" or "競争" in f"{title}{summary}":
                    news_lines.append(f"まず、{subject}が「{quote_phrases[0]}」と話し、若手も含めて結果重視で競争を促す考えを出したことです。")
                else:
                    news_lines.append(f"まず、{subject}が「{quote_phrases[0]}」と話し、結果次第で起用を見直す姿勢を出したことです。")
            elif lead:
                news_lines.append(f"まず、{lead}。")
            if quote_phrases:
                news_lines.append(f"次に「{quote_phrases[0]}」という言葉が出たことで、起用を固定しない姿勢がはっきりしました。")
            if "若手" in f"{title}{summary}" or "競争" in f"{title}{summary}":
                news_lines.append("そして、若手起用とセットで序列を動かす前提まで見えてきたのが今回の整理ポイントです。")
            else:
                news_lines.append("そして、結果次第で序列や役割を動かす前提が見えてきたのが今回の整理ポイントです。")
            if quote_phrases:
                focus_line = f"今回の一言で目を引くのは「{quote_phrases[0]}」です。優しい言い方に見えて、実際にはレギュラー固定でいかないという意思表示にも見えます。若手起用の話と合わせて読むと、ベンチは名前より結果で並びを動かす前提に見えてきます。裏を返せば、既存の序列も安泰ではないという空気が出ています。ここを曖昧にせず出したのが、今回のコメントのいちばん大きいところです。"
            else:
                focus_line = "今回の話題で大事なのは、言葉の強さそのものより、ベンチがどこを動かそうとしているかです。コメントをなぞるだけでなく、起用や采配のどこに効く話なのかを見たい記事です。"
            watch_line = reaction_line if reaction_line else "次に見たいのは、この発言が実際のスタメンやベンチワークにどう出るかという点です。"
        elif category == "補強・移籍":
            focus_line = "補強の話は名前のインパクトだけでは足りません。どこの穴を埋める話なのか、既存戦力とどうかみ合うかまで見ておきたいです。"
            watch_line = reaction_line if reaction_line else "次に見たいのは、この動きで一軍の競争や編成全体がどう変わるかという点です。"

        if category == "選手情報":
            paragraphs = [
                headings[0],
                intro,
                f"{lead}。",
            ]
            if detail:
                paragraphs.append(f"{detail}。")
            if extra:
                paragraphs.append(f"{extra}。")
            paragraphs.append(headings[1])
            if focus_line:
                paragraphs.append(focus_line)
            if extra2:
                paragraphs.append(f"{extra2}。")
            paragraphs.extend([
                headings[2],
                watch_line,
                closing,
            ])
        else:
            paragraphs = [
                headings[0],
                intro,
            ]
            if news_lines:
                paragraphs.extend(news_lines)
            else:
                paragraphs.append(f"{lead}。")
            paragraphs.extend([
                headings[1],
            ])
            if category == "首脳陣":
                if extra:
                    paragraphs.append(f"{extra}。")
                elif detail and "」" not in detail and len(detail) >= 18:
                    paragraphs.append(f"{detail}。")
                if extra2 and "」" not in extra2:
                    paragraphs.append(f"{extra2}。")
            else:
                if detail:
                    paragraphs.append(f"{detail}。")
                if extra:
                    paragraphs.append(f"{extra}。")
                if extra2:
                    paragraphs.append(f"{extra2}。")
            if not (category == "首脳陣") and topic and topic not in lead and category not in {"補強・移籍"}:
                paragraphs.append(f"{topic}というテーマが、今回の注目点です。")
            if focus_line:
                paragraphs.append(focus_line)
            paragraphs.extend([
                headings[2],
                watch_line,
                closing,
            ])
    return "\n".join(paragraphs)


def _rule_based_source_day_is_current(source_day_label: str) -> bool:
    label = (source_day_label or "").strip()
    if not label:
        return True
    match = _re.search(r"(\d{1,2})月(\d{1,2})日", label)
    if not match:
        return True
    now = datetime.now(JST)
    return int(match.group(1)) == now.month and int(match.group(2)) == now.day


def _clip_rule_based_fact(text: str, limit: int = 200) -> str:
    clean = _collapse_ws(_strip_html(text or "")).strip()
    if not clean:
        return ""
    if len(clean) <= limit:
        return clean
    return clean[:limit].rstrip(" 、。") + "…"


def _rule_based_fact_ok(text: str) -> bool:
    clean = _collapse_ws(_strip_html(text or "")).strip()
    if not clean:
        return False
    return not any(marker in clean for marker in RULE_BASED_SPECULATION_MARKERS)


def _rule_based_fact_lines(title: str, summary: str, max_sentences: int = 5, limit: int = 120) -> list[str]:
    lines = []
    for sentence in _extract_source_sentences(title, summary, max_sentences=max_sentences):
        clipped = _clip_rule_based_fact(sentence, limit=limit)
        if clipped and _rule_based_fact_ok(clipped):
            lines.append(clipped.rstrip("。"))
    return _dedupe_preserve_order(lines)


def _extract_rule_based_date_label(text: str, fallback: str = "") -> str:
    if fallback:
        return fallback
    for regex in (DATE_JP_TOKEN_RE, DATE_SLASH_TOKEN_RE):
        match = regex.search(text or "")
        if match:
            return match.group(0)
    return ""


def _extract_rule_based_program_channel(text: str) -> str:
    for marker in RULE_BASED_PROGRAM_CHANNEL_MARKERS:
        if marker in text:
            return marker
    return ""


def _extract_rule_based_program_name(title: str, summary: str, channel: str = "") -> str:
    quoted = _extract_quote_phrases(f"{title}\n{summary}", max_phrases=1)
    if quoted:
        return f"{channel}「{quoted[0]}」" if channel else quoted[0]
    clean_title = _clip_rule_based_fact(_strip_title_prefix(title), limit=80)
    clean_title = _re.sub(r"[（(]?(?:\d{1,2}月\d{1,2}日|\d{1,2}/\d{1,2}).*$", "", clean_title).strip("　 -")
    return clean_title


def _extract_rule_based_program_schedule_label(text: str) -> str:
    date_label = _extract_rule_based_date_label(text)
    time_match = TIME_TOKEN_RE.search(text or "")
    if date_label and time_match:
        return f"{date_label} {time_match.group(0)}"
    if date_label:
        return date_label
    if time_match and any(keyword in text for keyword in RULE_BASED_PROGRAM_KEYWORDS):
        return time_match.group(0)
    return ""


def _extract_rule_based_program_hosts(title: str, summary: str) -> list[str]:
    text = _strip_html(f"{title} {summary}")
    hosts = [match.group(1) for match in RULE_BASED_PROGRAM_PERSON_RE.finditer(text)]
    return _dedupe_preserve_order([host.strip() for host in hosts if host.strip()])[:5]


def _looks_like_rule_based_program_story(title: str, summary: str) -> bool:
    text = _strip_html(f"{title} {summary}")
    text_lower = text.lower()
    if _is_promotional_video_entry(title, summary):
        return True
    return (
        any(keyword in text for keyword in RULE_BASED_PROGRAM_KEYWORDS)
        or any(keyword in text_lower for keyword in ("program", "broadcast", "tv", "hulu", "dazn"))
    )


def _resolve_rule_based_target_subtype(
    *,
    title: str,
    summary: str,
    generation_category: str,
    article_subtype: str,
    special_story_kind: str = "",
    source_type: str = "news",
) -> str:
    resolved_subtype = str(article_subtype or "").strip().lower()
    if resolved_subtype == "lineup":
        return "lineup"
    if special_story_kind == "player_notice" and generation_category == "選手情報":
        return "notice"
    if source_type != "social_news" and _looks_like_rule_based_program_story(title, summary):
        return "program"
    return ""


def _render_lineup_rule_based(
    *,
    title: str,
    summary: str,
    source_url: str,
    source_day_label: str = "",
    lineup_rows: list[dict] | None = None,
) -> str | None:
    if source_day_label and not _rule_based_source_day_is_current(source_day_label):
        return None

    source_text = _strip_html(f"{title} {summary}")
    headings = _game_required_headings("lineup")
    game_date = _extract_rule_based_date_label(source_text, fallback=source_day_label)
    opponent = _extract_game_opponent_label(source_text)
    stadium = _extract_game_venue_label(source_text)
    start_time = _extract_game_time_token(source_text)
    starter_lines = [line.rstrip("。") for line in _extract_game_pitcher_lines(title, summary) if _rule_based_fact_ok(line)]
    overview_facts = _rule_based_fact_lines(title, summary, max_sentences=3, limit=100)

    lineup_table: list[str] = []
    focus_lines: list[str] = []
    for row in lineup_rows or []:
        order = str(row.get("order") or "").strip()
        name = str(row.get("name") or "").strip()
        position = str(row.get("position") or "").strip()
        if not order or not name:
            continue
        line = f"{order}番 {name}"
        if position:
            line += f" {position}"
        lineup_table.append(line.strip())
        if order in {"1", "4", "9"}:
            focus_lines.append(line.strip())

    if not lineup_table:
        for fact in overview_facts:
            if LINEUP_ORDER_SLOT_RE.search(fact):
                lineup_table.append(fact)

    if not lineup_table and not starter_lines:
        return None

    overview_lines = [headings[0]]
    details = [item for item in (game_date, f"{opponent}戦" if opponent else "", stadium, f"{start_time}開始" if start_time else "") if item]
    if details:
        overview_lines.append(" / ".join(details))
    overview_lines.extend(f"{fact}。" for fact in overview_facts[:2] if not LINEUP_ORDER_SLOT_RE.search(fact))
    if len(overview_lines) == 1:
        overview_lines.append("巨人の試合前情報です。")

    lineup_section = [headings[1]]
    lineup_section.extend(lineup_table[:9])

    starter_section = [headings[2]]
    starter_section.extend(f"{line}。" for line in starter_lines[:3])
    if len(starter_section) == 1:
        starter_section.append("先発投手の確定情報は元記事で確認できる範囲に限ります。")

    focus_section = [headings[3]]
    for line in _dedupe_preserve_order(focus_lines)[:3]:
        focus_section.append(f"{line}。")
    if not any(line != headings[3] for line in focus_section):
        for fact in overview_facts:
            if fact not in lineup_table:
                focus_section.append(f"{fact}。")
            if len(focus_section) >= 3:
                break
    if source_url:
        focus_section.append(f"出典: {source_url}")
    return "\n".join(overview_lines + lineup_section + starter_section + focus_section)


def _render_program_rule_based(
    *,
    title: str,
    summary: str,
    source_url: str,
) -> str | None:
    source_text = _strip_html(f"{title} {summary}")
    channel = _extract_rule_based_program_channel(source_text)
    schedule_label = _extract_rule_based_program_schedule_label(source_text)
    program_name = _extract_rule_based_program_name(title, summary, channel=channel)
    hosts = _extract_rule_based_program_hosts(title, summary)
    highlights = [
        fact for fact in _rule_based_fact_lines(title, summary, max_sentences=5, limit=120)
        if fact != program_name and fact != schedule_label
    ]
    if not program_name or not schedule_label:
        return None
    if not (channel or hosts or highlights):
        return None

    sections = ["【番組概要】"]
    sections.append(f"番組名は{program_name}です。")
    if channel:
        sections.append(f"媒体は{channel}です。")
    sections.append("【放送・配信日時】")
    sections.append(f"放送・配信日時は{schedule_label}です。")
    if channel:
        sections.append(f"配信先は{channel}です。")
    sections.append("【出演・見どころ】")
    if hosts:
        sections.append("出演者: " + " / ".join(hosts[:5]))
    for fact in highlights[:3]:
        sections.append(f"{fact}。")
    sections.append("【視聴メモ】")
    if source_url:
        sections.append(f"出典: {source_url}")
    return "\n".join(sections)


def _render_notice_rule_based(
    *,
    title: str,
    summary: str,
    source_url: str,
    source_name: str = "",
    source_day_label: str = "",
) -> str | None:
    source_text = _strip_html(f"{title} {summary}")
    notice_subject, notice_type = _extract_notice_subject_and_type(title, summary)
    player_position = _extract_notice_player_position(title, summary, notice_subject) or "選手"
    notice_date = _extract_rule_based_date_label(source_text, fallback=source_day_label)
    notice_fact = _find_source_sentence_with_markers(
        title,
        summary,
        ("登録", "抹消", "合流", "復帰", "昇格", "戦力外", "再出発"),
    )
    notice_fact = _clip_rule_based_fact(notice_fact, limit=200)
    if not _rule_based_fact_ok(notice_fact):
        notice_fact = ""
    record_fact = _clip_rule_based_fact(_extract_notice_record_fact(title, summary), limit=120)
    if not _rule_based_fact_ok(record_fact):
        record_fact = ""
    background_fact = _clip_rule_based_fact(
        _extract_notice_background_fact(title, summary, exclude={notice_fact} if notice_fact else set()),
        limit=160,
    )
    if not _rule_based_fact_ok(background_fact) or background_fact == notice_fact:
        background_fact = ""

    if not notice_type or not notice_date:
        return None
    if not notice_subject:
        notice_subject = "対象選手"
    if not notice_fact:
        return None

    source_label = _display_source_name(source_name) if source_name else ""
    sections = [NOTICE_REQUIRED_HEADINGS[0]]
    opening = f"（{source_day_label}時点）" if source_day_label else ""
    sections.append(f"{opening}{notice_subject}が{notice_type}となりました。".strip())
    sections.append(f"公示日は{notice_date}です。")
    sections.append(f"{notice_fact}。")
    if source_label:
        sections.append(f"報道 source は{source_label}です。")

    sections.append(NOTICE_REQUIRED_HEADINGS[1])
    sections.append(f"{notice_subject}は読売ジャイアンツの{player_position}です。")
    if record_fact:
        sections.append(f"{record_fact}。")

    sections.append(NOTICE_REQUIRED_HEADINGS[2])
    sections.append(f"{background_fact or notice_fact}。")

    sections.append(NOTICE_REQUIRED_HEADINGS[3])
    sections.append(_notice_next_focus_sentence(notice_type, player_position, notice_subject))
    if source_url:
        sections.append(f"出典: {source_url}")
    return "\n".join(sections)


def _build_rule_based_subtype_body(
    *,
    title: str,
    summary: str,
    generation_category: str,
    article_subtype: str,
    special_story_kind: str = "",
    source_url: str = "",
    source_name: str = "",
    source_day_label: str = "",
    source_type: str = "news",
    lineup_rows: list[dict] | None = None,
) -> tuple[str, str] | None:
    target_subtype = _resolve_rule_based_target_subtype(
        title=title,
        summary=summary,
        generation_category=generation_category,
        article_subtype=article_subtype,
        special_story_kind=special_story_kind,
        source_type=source_type,
    )
    if not _should_use_rule_based(target_subtype):
        return None

    body = None
    if target_subtype == "lineup":
        body = _render_lineup_rule_based(
            title=title,
            summary=summary,
            source_url=source_url,
            source_day_label=source_day_label,
            lineup_rows=lineup_rows,
        )
    elif target_subtype == "program":
        body = _render_program_rule_based(
            title=title,
            summary=summary,
            source_url=source_url,
        )
    elif target_subtype == "notice":
        body = _render_notice_rule_based(
            title=title,
            summary=summary,
            source_url=source_url,
            source_name=source_name,
            source_day_label=source_day_label,
        )
    if not body:
        return None
    return target_subtype, body


def _log_rule_based_subtype_skip_gemini(
    logger: logging.Logger,
    *,
    subtype: str,
    source_url: str,
    input_chars: int,
    output_chars: int,
    saved_gemini_calls: int = 3,
    template_version: str = RULE_BASED_SUBTYPE_TEMPLATE_VERSION,
) -> None:
    payload = {
        "event": "rule_based_subtype_skip_gemini",
        "subtype": str(subtype or "").strip().lower(),
        "source_url_hash": _hash_duplicate_guard_value(source_url),
        "input_chars": int(input_chars or 0),
        "output_chars": int(output_chars or 0),
        "saved_gemini_calls": int(saved_gemini_calls or 0),
        "rule_based_template_version": template_version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    logger.info(json.dumps(payload, ensure_ascii=False))


def _article_reads_too_generic(text: str, category: str) -> bool:
    if category != "選手情報":
        return False
    clean = _strip_html(text or "")
    hit_count = sum(1 for marker in GENERIC_PLAYER_ARTICLE_MARKERS if marker in clean)
    return hit_count >= 1


def infer_article_has_game(title: str, summary: str, category: str, daily_has_game: bool) -> bool:
    text = f"{_strip_html(title)} {_strip_html(summary)}"
    if category == "試合速報":
        return True
    if SCORE_TOKEN_RE.search(text):
        return True
    if any(keyword in text for keyword in GAME_ARTICLE_KEYWORDS):
        return True
    return daily_has_game and any(marker in text for marker in ("vs", "VS", "対"))


def _find_unverified_number_tokens(text: str, allowed_tokens: set[str]) -> list[str]:
    found = []
    for token in _extract_number_tokens(text):
        normalized = _normalize_number_token(token)
        token_variants = _expand_number_token_variants(normalized)
        if token_variants.isdisjoint(allowed_tokens):
            found.append(normalized)

    deduped = []
    seen = set()
    for token in found:
        if token not in seen:
            seen.add(token)
            deduped.append(token)
    return deduped


def _text_has_fake_citation(text: str) -> bool:
    return any(marker in text for marker in FAKE_CITATION_MARKERS)


def _source_has_confirmed_result(title: str, summary: str) -> bool:
    source_text = _strip_html(f"{title} {summary}")
    if _has_explicit_confirmed_result(source_text):
        return True
    return bool(SCORE_TOKEN_RE.search(source_text))


def _is_pregame_article(title: str, summary: str, category: str, has_game: bool) -> bool:
    return bool(category == "試合速報" and has_game and not _source_has_confirmed_result(title, summary))


def _text_guardrail_flags(title: str, summary: str, text: str, has_game: bool) -> dict:
    allowed_tokens = _collect_allowed_number_tokens(title, summary)
    clean_text = text.strip()
    source_has_result = _source_has_confirmed_result(title, summary)
    source_mentions_outcome = _source_mentions_outcome_terms(title, summary)
    return {
        "unverified_numbers": _find_unverified_number_tokens(clean_text, allowed_tokens),
        "bad_score": bool(
            (not has_game)
            and (not source_mentions_outcome)
            and (SCORE_TOKEN_RE.search(clean_text) or any(word in clean_text for word in NON_GAME_RESULT_WORDS))
        ),
        "fake_citation": bool(_text_has_fake_citation(clean_text)),
        "fabricated_result": bool((not source_has_result) and any(marker in clean_text for marker in DEFINITE_RESULT_MARKERS)),
    }


def _text_is_safe(title: str, summary: str, text: str, has_game: bool) -> bool:
    flags = _text_guardrail_flags(title, summary, text, has_game)
    return not (flags["unverified_numbers"] or flags["bad_score"] or flags["fake_citation"] or flags["fabricated_result"])


def _apply_article_guardrails(title: str, summary: str, category: str, article_text: str, has_game: bool, logger: logging.Logger) -> str:
    if not article_text:
        return ""

    clean_text = article_text.strip()
    flags = _text_guardrail_flags(title, summary, clean_text, has_game)

    if flags["unverified_numbers"] or flags["bad_score"] or flags["fake_citation"] or flags["fabricated_result"]:
        logger.warning(
            "記事ガードレール発動: %s",
            {
                "category": category,
                "unverified_numbers": flags["unverified_numbers"][:8],
                "bad_score": flags["bad_score"],
                "fake_citation": flags["fake_citation"],
                "fabricated_result": flags["fabricated_result"],
            },
        )
        return _build_safe_article_fallback(title, summary, category, has_game)
    return clean_text


def _split_text_sections(text: str) -> list[tuple[str, str]]:
    clean_lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not clean_lines:
        return []

    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_lines: list[str] = []
    for line in clean_lines:
        if line.startswith("【") and "】" in line:
            if current_heading or current_lines:
                sections.append((current_heading, "\n".join(current_lines).strip()))
            current_heading = line
            current_lines = []
            continue
        current_lines.append(line)
    if current_heading or current_lines:
        sections.append((current_heading, "\n".join(current_lines).strip()))
    return sections


def _evaluate_post_gen_validate(
    text: str,
    article_subtype: str = "",
    title: str = "",
    source_refs: dict[str, object] | None = None,
) -> dict[str, object]:
    raw_text = text or ""
    clean_text = _collapse_ws(_strip_html(raw_text))
    title_text = _collapse_ws(_strip_html(title or ""))
    fail_axes: list[str] = []
    source_refs = source_refs or {}

    def _append_fail_axis(axis: str) -> None:
        if axis not in fail_axes:
            fail_axes.append(axis)

    if any(clean_text.startswith(prefix) for prefix in POST_GEN_INTRO_ECHO_PREFIXES):
        _append_fail_axis("intro_echo")

    sections = _split_text_sections(text)
    final_section_text = sections[-1][1] if sections else clean_text
    if article_subtype != "lineup" and not any(marker in final_section_text for marker in POST_GEN_CLOSE_MARKERS):
        _append_fail_axis("close_marker")

    normalized_headings: list[str] = []
    if article_subtype in NON_LINEUP_STARMEN_GUARD_SUBTYPES or article_subtype == "live_update":
        heading_candidates = [heading for heading, _body in sections if heading]
        heading_candidates.extend(
            match
            for match in _re.findall(r"<h[23][^>]*>(.*?)</h[23]>", raw_text, flags=_re.IGNORECASE | _re.DOTALL)
            if match
        )
        normalized_headings = [
            _collapse_ws(_strip_html(heading)).strip("【】")
            for heading in heading_candidates
            if heading and _collapse_ws(_strip_html(heading))
        ]

    if article_subtype in NON_LINEUP_STARMEN_GUARD_SUBTYPES:
        if _starts_with_starmen_prefix(title_text):
            _append_fail_axis("starmen_title_prefix")
        if any(_starts_with_starmen_prefix(heading) for heading in normalized_headings):
            _append_fail_axis("starmen_heading_prefix")

    if article_subtype == "live_update":
        if any(any(keyword in heading for keyword in LIVE_UPDATE_LINEUP_HEADING_KEYWORDS) for heading in normalized_headings):
            _append_fail_axis("live_update_lineup_heading")
        batting_order_markers = {match.group(0) for match in _re.finditer(r"[1-9１-９]番", clean_text)}
        has_lineup_table = "<table" in raw_text.lower() and any(keyword in clean_text for keyword in LIVE_UPDATE_LINEUP_HEADING_KEYWORDS)
        if has_lineup_table or len(batting_order_markers) >= 4:
            _append_fail_axis("live_update_lineup_structure")

    if article_subtype == "lineup":
        lineup_tokens: list[str] = []
        for key in ("opponent", "scoreline"):
            value = _collapse_ws(_strip_html(str(source_refs.get(key) or "")))
            if value:
                lineup_tokens.append(value)

        source_title_text = _collapse_ws(_strip_html(str(source_refs.get("source_title") or "")))
        source_summary_text = _collapse_ws(_strip_html(str(source_refs.get("source_summary") or source_refs.get("summary") or "")))
        context_text = "\n".join(part for part in (title_text, source_title_text, source_summary_text) if part)
        score_match = _re.search(r"\d{1,2}\s*[－\-–]\s*\d{1,2}", context_text)
        if score_match:
            lineup_tokens.append(score_match.group(0))
        opponent_match = _re.search(r"(阪神|中日|ヤクルト|広島|DeNA|ＤｅＮＡ|横浜|日本ハム|ソフトバンク|楽天|ロッテ|西武|オリックス)", context_text)
        if opponent_match:
            lineup_tokens.append(opponent_match.group(1))

        fact_conflict_payload = {
            "title": title_text,
            "body_text": clean_text,
            "game_id": str(source_refs.get("game_id") or "").strip(),
            "scoreline": str(source_refs.get("scoreline") or "").strip(),
            "team_result": str(source_refs.get("team_result") or "").strip(),
            "opponent": str(source_refs.get("opponent") or "").strip(),
            "required_tokens": tuple(dict.fromkeys(token for token in lineup_tokens if token)),
        }
        if _detect_no_game_but_result(fact_conflict_payload, source_refs):
            _append_fail_axis("NO_GAME_BUT_RESULT")
        if _detect_game_result_conflict(fact_conflict_payload, source_refs):
            _append_fail_axis("GAME_RESULT_CONFLICT")
        if _detect_title_body_entity_mismatch(title_text, fact_conflict_payload):
            _append_fail_axis("TITLE_BODY_ENTITY_MISMATCH")

    stop_reason = ""
    if any(axis.startswith("starmen_") for axis in fail_axes):
        stop_reason = "starmen_prefix_guard"
    elif any(axis.startswith("live_update_") for axis in fail_axes):
        stop_reason = "live_update_lineup_guard"
    elif fail_axes:
        stop_reason = fail_axes[0]

    return {
        "ok": not fail_axes,
        "fail_axes": fail_axes,
        "final_section_heading": sections[-1][0] if sections else "",
        "final_section_text": final_section_text,
        "stop_reason": stop_reason,
    }


def _log_article_skipped_post_gen_validate(
    logger: logging.Logger,
    *,
    title: str,
    post_url: str,
    category: str,
    article_subtype: str,
    fail_axes: list[str],
    stop_reason: str = "",
):
    payload = {
        "event": "article_skipped_post_gen_validate",
        "post_id": None,
        "title": title,
        "post_url": post_url,
        "category": category,
        "article_subtype": article_subtype,
        "fail_axis": fail_axes,
    }
    if stop_reason:
        payload["stop_reason"] = stop_reason
    logger.info(json.dumps(payload, ensure_ascii=False))


def _find_first_timeline_owner(obj):
    if isinstance(obj, dict):
        timeline = obj.get("timeline")
        if isinstance(timeline, dict) and isinstance(timeline.get("entry"), list):
            return obj
        for value in obj.values():
            found = _find_first_timeline_owner(value)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find_first_timeline_owner(value)
            if found is not None:
                return found
    return None


def _find_first_best_tweet(obj):
    if isinstance(obj, dict):
        best_tweet = obj.get("bestTweet")
        if isinstance(best_tweet, dict):
            return best_tweet
        for value in obj.values():
            found = _find_first_best_tweet(value)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for value in obj:
            found = _find_first_best_tweet(value)
            if found is not None:
                return found
    return None


def _extract_yahoo_realtime_payload(html: str, logger: logging.Logger, context: str) -> tuple[list, dict]:
    json_match = _re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, _re.DOTALL)
    if not json_match:
        logger.warning("Yahoo realtime parse failed (%s): __NEXT_DATA__ not found", context)
        return [], {}

    try:
        data = json.loads(json_match.group(1))
    except json.JSONDecodeError as e:
        logger.warning("Yahoo realtime parse failed (%s): invalid JSON: %s", context, e)
        return [], {}

    try:
        page_data = data["props"]["pageProps"]["pageData"]
    except (KeyError, TypeError):
        page_data = _find_first_timeline_owner(data)
        if page_data is None:
            logger.warning("Yahoo realtime parse failed (%s): timeline entry path not found", context)
            return [], {}

    timeline = page_data.get("timeline", {}) if isinstance(page_data, dict) else {}
    entries = timeline.get("entry") if isinstance(timeline, dict) else None
    if not isinstance(entries, list):
        fallback_owner = _find_first_timeline_owner(page_data)
        if fallback_owner is not None:
            entries = fallback_owner.get("timeline", {}).get("entry")
    if not isinstance(entries, list):
        logger.warning("Yahoo realtime parse failed (%s): timeline.entry missing", context)
        return [], {}

    best_tweet = page_data.get("bestTweet") if isinstance(page_data, dict) else None
    if not isinstance(best_tweet, dict):
        best_tweet = _find_first_best_tweet(page_data) or _find_first_best_tweet(data) or {}
    return entries, best_tweet


# ──────────────────────────────────────────────────────────
# Yahoo リアルタイム検索からXポスト取得
# ──────────────────────────────────────────────────────────
def fetch_yahoo_realtime_entries(keyword: str) -> list:
    """Yahoo リアルタイム検索から巨人関連の人気Xポストを取得。feedparser互換の形式で返す。"""
    import urllib.request, urllib.parse
    logger = logging.getLogger("rss_fetcher")
    try:
        q = urllib.parse.quote(keyword)
        url = f"https://search.yahoo.co.jp/realtime/search?p={q}&ei=UTF-8"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode("utf-8", errors="ignore")
        entries_raw, best_tweet = _extract_yahoo_realtime_payload(html, logger, f"keyword={keyword}")
        if not entries_raw and not best_tweet:
            return []
        # bestTweet（Yahoo選定の最バズ投稿）を先頭に追加
        bt_text = best_tweet.get("displayText", "")
        bt_text = _re.sub(r'\s*(START|END)\s*', ' ', bt_text).strip()
        if bt_text and len(bt_text) > 15 and best_tweet.get("url"):
            entries_raw = [{"displayText": bt_text, "url": best_tweet["url"],
                            "rt": best_tweet.get("rt", 999), "like": best_tweet.get("like", 999),
                            "createdAt": best_tweet.get("createdAt")} ] + list(entries_raw)
        # 新しさ優先＋人気補正でソート
        scored = []
        for e in entries_raw:
            text = e.get("displayText", "") or e.get("text", "")
            text = _re.sub(r'\s*(START|END)\s*', ' ', text).strip()
            tweet_url = e.get("url", "")
            rt = e.get("rtCount", e.get("rt", 0)) or 0
            like = e.get("likesCount", e.get("like", 0)) or 0
            created_at = e.get("createdAt")
            if not text or len(text) < 15 or not tweet_url:
                continue
            scored.append(((created_at or 0), rt * 3 + like, {
                "title": text[:80],
                "summary": text,
                "link": tweet_url,
                "rt": rt,
                "like": like,
                "created_at": created_at,
                "published_parsed": None,
            }))
        # スコア上位10件のみ返す
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return [entry for _, _, entry in scored[:10]]
    except Exception as e:
        logger.warning("Yahoo realtime entries fetch failed (keyword=%s): %s", keyword, e)
        return []


# ──────────────────────────────────────────────────────────
# OG画像取得
# ──────────────────────────────────────────────────────────
def fetch_og_image(url: str) -> str:
    """記事URLからOGP画像URLを取得。取得できなければ空文字を返す。"""
    imgs = fetch_article_images(url, max_images=1)
    return imgs[0] if imgs else ""


def _fetch_url_html(url: str, max_bytes: int = 200000, timeout: int = 12) -> str:
    import urllib.request

    req = urllib.request.Request(url, headers={"User-Agent": HTTP_USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as res:
            return res.read(max_bytes).decode("utf-8", errors="ignore")
    except Exception:
        try:
            result = subprocess.run(
                ["curl", "-fsSL", "-A", HTTP_USER_AGENT, url],
                capture_output=True,
                check=True,
                timeout=timeout + 3,
            )
            return result.stdout[:max_bytes].decode("utf-8", errors="ignore")
        except Exception:
            return ""


def _get_image_candidate_exclusion_reason(image_url: str) -> str:
    low = _html.unescape((image_url or "").strip()).lower()
    if _re.search(r"\babs(?:-\d+)?\.twimg\.com/emoji/", low):
        return "emoji_svg_url"
    return ""


def _filter_image_candidates(
    image_urls: list[str],
    source_url: str = "",
    logger: logging.Logger | None = None,
) -> list[str]:
    filtered = []
    seen = set()
    logger = logger or logging.getLogger("rss_fetcher")
    normalized_source_url = _html.unescape((source_url or "").strip())

    for image_url in image_urls or []:
        normalized_url = _html.unescape((image_url or "").strip())
        if not normalized_url or normalized_url in seen:
            continue
        reason = _get_image_candidate_exclusion_reason(normalized_url)
        if reason:
            payload = {
                "event": "image_candidate_excluded",
                "reason": reason,
                "excluded_url": normalized_url,
                "source_url": normalized_source_url,
            }
            logger.info(json.dumps(payload, ensure_ascii=False))
            continue
        seen.add(normalized_url)
        filtered.append(normalized_url)
    return filtered


def _ensure_notice_featured_images(
    image_urls: list[str],
    title: str,
    summary: str,
    category: str,
) -> list[str]:
    if image_urls:
        return image_urls
    if not _is_notice_template_story(title, summary, category):
        return image_urls
    fallback_url = get_notice_fallback_image_url()
    return [fallback_url] if fallback_url else image_urls


def _upload_featured_media_with_fallback(
    wp: WPClient,
    image_urls: list[str],
    post_url: str,
    logger: logging.Logger | None = None,
) -> int:
    logger = logger or logging.getLogger("rss_fetcher")
    candidates = [_html.unescape((url or "").strip()) for url in (image_urls or []) if (url or "").strip()]
    if not candidates:
        return 0

    primary_url = candidates[0]
    for candidate_url in candidates:
        featured_media = wp.upload_image_from_url(candidate_url, source_url=post_url)
        if featured_media:
            if candidate_url != primary_url:
                logger.info(
                    json.dumps(
                        {
                            "event": "featured_media_fallback_used",
                            "post_url": post_url,
                            "primary_url": primary_url,
                            "fallback_url": candidate_url,
                        },
                        ensure_ascii=False,
                    )
                )
            return featured_media
    return 0


def _refetch_article_images_if_empty(
    image_urls: list[str],
    page_url: str,
    logger: logging.Logger | None = None,
    max_images: int = 3,
) -> list[str]:
    if image_urls or not page_url:
        return image_urls
    logger = logger or logging.getLogger("rss_fetcher")
    retry_images = _filter_image_candidates(
        fetch_article_images(page_url, max_images=max_images),
        page_url,
        logger,
    )
    if retry_images:
        logger.info(
            json.dumps(
                {
                    "event": "article_image_refetched",
                    "source_url": page_url,
                    "image_count": len(retry_images),
                    "first_image_url": retry_images[0],
                },
                ensure_ascii=False,
            )
        )
    return retry_images or image_urls


def _ensure_story_featured_images(
    image_urls: list[str],
    title: str,
    summary: str,
    category: str,
    article_subtype: str,
    source_url: str = "",
    logger: logging.Logger | None = None,
) -> list[str]:
    if image_urls:
        return image_urls
    logger = logger or logging.getLogger("rss_fetcher")
    fallback_url = ""
    fallback_type = ""
    if _is_notice_template_story(title, summary, category):
        fallback_url = get_notice_fallback_image_url()
        fallback_type = "notice"
    else:
        fallback_url = get_story_fallback_image_url(category, article_subtype)
        if fallback_url:
            fallback_type = f"{category}:{article_subtype}"
    if not fallback_url:
        return image_urls
    logger.info(
        json.dumps(
            {
                "event": "featured_image_fallback_applied",
                "source_url": source_url,
                "category": category,
                "article_subtype": article_subtype,
                "fallback_type": fallback_type,
                "fallback_url": fallback_url,
            },
            ensure_ascii=False,
        )
    )
    return [fallback_url]


def fetch_article_images(url: str, max_images: int = 3) -> list:
    """記事ページから写真URLを最大 max_images 枚スクレイピングして返す。
    og:image を先頭に、本文中の <img> から大きそうなものを追加する。"""
    try:
        import urllib.parse
        html = _fetch_url_html(url, max_bytes=200000, timeout=12)
        if not html:
            return []

        seen = set()
        images = []

        def _add(img_url: str):
            if not img_url or img_url in seen:
                return
            # 絶対URLに変換
            if img_url.startswith("//"):
                img_url = "https:" + img_url
            elif img_url.startswith("/"):
                parsed = urllib.parse.urlparse(url)
                img_url = f"{parsed.scheme}://{parsed.netloc}{img_url}"
            elif not img_url.startswith("http"):
                return
            # アイコン・バナー・広告っぽいものを除外
            low = img_url.lower()
            if any(ng in low for ng in ["logo", "icon", "banner", "ad", "button",
                                         "sprite", "blank", "noimage", "no_image",
                                         "spacer", "pixel", "tracking", "1x1"]):
                return
            # 小さい画像を除外（URLにサイズ情報がある場合）
            size_m = _re.search(r'[_\-x](\d+)[_\-x](\d+)', low)
            if size_m:
                w, h = int(size_m.group(1)), int(size_m.group(2))
                if w < 300 or h < 150:
                    return
            seen.add(img_url)
            images.append(img_url)

        # 1. og:image（最優先）
        for pat in [
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        ]:
            m = _re.search(pat, html)
            if m:
                _add(m.group(1))
                break

        # 2. 本文エリアの <img> タグ（article / main / section 内を優先）
        # 記事本文っぽいブロックを切り出す
        article_html = html
        for area_pat in [
            r'<article[^>]*>(.*?)</article>',
            r'<div[^>]+class=["\'][^"\']*(?:article|content|body|main)[^"\']*["\'][^>]*>(.*?)</div>',
        ]:
            am = _re.search(area_pat, html, _re.DOTALL | _re.IGNORECASE)
            if am:
                article_html = am.group(1)
                break

        for img_m in _re.finditer(
            r'<img[^>]+(?:src|data-src|data-lazy-src)=["\']([^"\']+)["\']',
            article_html, _re.IGNORECASE
        ):
            _add(img_m.group(1))
            if len(images) >= max_images:
                break

        # 3. 本文外でも足りなければ全体から補完
        if len(images) < max_images:
            for img_m in _re.finditer(
                r'<img[^>]+src=["\']([^"\']+\.(?:jpg|jpeg|png|webp))["\']',
                html, _re.IGNORECASE
            ):
                _add(img_m.group(1))
                if len(images) >= max_images:
                    break

        return images[:max_images]
    except Exception:
        return []


def _extract_entry_image_urls(entry: dict, page_url: str = "", max_images: int = 3) -> list[str]:
    import urllib.parse as _urlparse

    title_text = entry.get("title", "") or ""
    fragment = entry.get("summary", "") or entry.get("description", "")
    if not fragment:
        content_list = entry.get("content") or []
        if content_list and isinstance(content_list, list):
            fragment = content_list[0].get("value", "")
    if not fragment and not title_text:
        return []

    seen = set()
    images = []

    def _add(img_url: str):
        if not img_url or img_url in seen:
            return
        if img_url.startswith("//"):
            img_url = "https:" + img_url
        elif img_url.startswith("/") and page_url:
            parsed = _urlparse.urlparse(page_url)
            img_url = f"{parsed.scheme}://{parsed.netloc}{img_url}"
        elif not img_url.startswith("http"):
            return
        low = img_url.lower()
        if any(ng in low for ng in ["logo", "icon", "banner", "ad", "button", "sprite", "blank", "spacer", "pixel"]):
            return
        seen.add(img_url)
        images.append(img_url)

    for img_m in _re.finditer(
        r'<img[^>]+(?:src|data-src|data-lazy-src)=["\']([^"\']+)["\']',
        fragment,
        _re.IGNORECASE,
    ):
        _add(img_m.group(1))
        if len(images) >= max_images:
            break

    linked_text = _html.unescape(_strip_html(f"{title_text} {fragment}"))
    linked_urls = []
    for url_m in _re.finditer(r'https?://[^\s<>"\')]+', linked_text):
        candidate_url = url_m.group(0).rstrip(".,)")
        parsed = _urlparse.urlparse(candidate_url)
        host = parsed.netloc.lower()
        if not host or host.endswith(("x.com", "twitter.com", "t.co")):
            continue
        if candidate_url in linked_urls:
            continue
        linked_urls.append(candidate_url)

    for candidate_url in linked_urls[:3]:
        for img_url in fetch_article_images(candidate_url, max_images=1):
            _add(img_url)
            if len(images) >= max_images:
                return images[:max_images]
    return images[:max_images]


# ──────────────────────────────────────────────────────────
# Yahoo リアルタイム検索でファン反応を取得（記事に組み込む用）
# ──────────────────────────────────────────────────────────
def fetch_fan_reactions_from_yahoo(
    title: str,
    summary: str = "",
    category: str = "",
    source_name: str = "",
) -> list:
    """記事タイトルからキーワードを抽出し、Yahoo リアルタイム検索でファン投稿を取得。"""
    logger = logging.getLogger("rss_fetcher")
    queries = _build_fan_reaction_queries(title, summary, category)
    if not queries:
        return []

    fan_reaction_limit = get_fan_reaction_limit()
    focus_terms = _build_fan_reaction_focus_terms(title, summary, category)
    excluded_handles = get_fan_reaction_excluded_handles()
    max_age_hours = get_fan_reaction_max_age_hours()
    strict_source_match = _source_requires_precise_fan_reactions(source_name, category)
    now_ts = int(datetime.now(timezone.utc).timestamp())
    primary_candidates = []
    reserve_candidates = []
    seen = set()
    for keyword in queries:
        try:
            entries = fetch_yahoo_realtime_entries(keyword)
        except Exception as e:
            logger.warning("Yahoo fan reactions fetch failed (keyword=%s): %s", keyword, e)
            continue

        for idx, e in enumerate(entries[:20], start=1):
            text = e.get("summary", "") or e.get("displayText", "") or e.get("text", "")
            text = _re.sub(r'\s*(START|END)\s*', ' ', text).strip()
            created_at = e.get("created_at")
            if created_at and (now_ts - int(created_at)) > max_age_hours * 3600:
                continue
            if len(text) < 20 or len(text) > 180:
                continue
            if text.count("http") > 1:
                continue
            if any(ng in text for ng in ["フォロー", "RT", "プレゼント", "キャンペーン", "告知"]):
                continue
            if _reaction_is_reply_like(text):
                continue
            handle = _extract_handle_from_tweet_url(e.get("link", "")) or f"@x_user_{idx:02d}"
            if handle.lower().lstrip("@") in excluded_handles:
                continue
            if _reaction_handle_is_media_like(handle):
                continue
            opinion_score = _reaction_opinion_score(text)
            commentary_score = _reaction_commentary_score(text)
            focus_score = _reaction_focus_score(text, title, summary, category, focus_terms)
            if _reaction_is_low_value_share(text, title, summary, opinion_score, commentary_score):
                continue
            if strict_source_match and not _reaction_matches_precise_source_context(
                text,
                title,
                summary,
                category,
                focus_terms,
            ):
                continue
            reaction = {
                "handle": handle,
                "text": text,
                "url": e.get("link", ""),
                "created_at": created_at,
            }
            dedupe_key = (reaction["handle"] + reaction["text"]).replace(" ", "").replace("　", "")
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            reaction["media_like"] = _reaction_is_media_like(reaction["handle"], reaction["text"])
            reaction["opinion_score"] = opinion_score
            reaction["commentary_score"] = commentary_score
            reaction["focus_score"] = focus_score
            if focus_score >= 2:
                primary_candidates.append(reaction)
            elif _reaction_can_fill_shortage(
                text,
                title,
                summary,
                category,
                opinion_score,
                commentary_score,
                focus_score,
                focus_terms=focus_terms,
            ):
                reserve_candidates.append(reaction)

    for candidates in (primary_candidates, reserve_candidates):
        candidates.sort(
            key=lambda r: (
                0 if r["media_like"] else 1,
                r["focus_score"],
                r["commentary_score"],
                r["opinion_score"],
                int(r["created_at"] or 0),
            ),
            reverse=True,
        )

    reactions = []
    for reaction in primary_candidates + reserve_candidates:
        if any(_reactions_are_too_similar(reaction["text"], selected["text"]) for selected in reactions):
            continue
        reactions.append({
            "handle": reaction["handle"],
            "text": reaction["text"],
            "url": reaction["url"],
            "created_at": reaction["created_at"],
        })
        if len(reactions) >= fan_reaction_limit:
            break

    if reactions:
        logger.info(
            "Yahoo fan reactions fetched: %d件 (strict=%d reserve=%d)",
            len(reactions),
            len(primary_candidates),
            len(reserve_candidates),
        )
    else:
        logger.info("Yahoo fan reactions unavailable: queries=%s", queries)
    return reactions


# ──────────────────────────────────────────────────────────
# GrokでリアルなXファン反応を取得
# ──────────────────────────────────────────────────────────
def _parse_responses_api_text(data: dict) -> str:
    """Responses API（/v1/responses）のレスポンスからテキストを抽出。
    ツール使用時は output に custom_tool_call が混在するため type==message を探す。"""
    for item in data.get("output", []):
        if item.get("type") == "message":
            for content in item.get("content", []):
                if isinstance(content, dict) and content.get("type") == "output_text":
                    return content.get("text", "").strip()
    return ""


def fetch_fan_reactions_with_grok(title: str) -> list:
    """Grok Responses APIでXの巨人ファン反応を最大10件取得。失敗時は空リストを返す。"""
    import urllib.request, urllib.error
    api_key = os.environ.get("GROK_API_KEY", "")
    if not api_key:
        return []

    # 検索クエリ用にタイトルを短縮
    import re
    query = re.sub(r'【.*?】', '', title).strip()[:30]

    from datetime import datetime, timedelta
    today_dt  = datetime.now()
    from_date = today_dt.strftime("%Y-%m-%d")
    to_date   = today_dt.strftime("%Y-%m-%d")

    payload = json.dumps({
        "model": "grok-4-1-fast-non-reasoning",
        "max_turns": 1,
        "max_output_tokens": 500,
        "input": [
            {
                "role": "user",
                "content": (
                    f"「{query}」に関して、Xに投稿された巨人ファンの本音コメントを10件探してください。\n"
                    "各コメントを以下の形式で返してください（説明不要）：\n"
                    "@アカウント名: コメント内容\n"
                    "@アカウント名: コメント内容\n"
                    "喜び・悔しさ・驚き・批判など感情が多様になるよう選んでください。実際の投稿を優先してください。"
                )
            }
        ],
        "tools": [{"type": "x_search", "from_date": from_date, "to_date": to_date}]
    }).encode("utf-8")

    try:
        req = urllib.request.Request(
            "https://api.x.ai/v1/responses",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }
        )
        with urllib.request.urlopen(req, timeout=30) as res:
            data = json.load(res)
        text = _parse_responses_api_text(data)
        if not text:
            return []
        import re as _re2
        def _clean(s: str) -> str:
            # [[数字]](URL) 形式の引用リンクを除去
            return _re2.sub(r'\[\[\d+\]\]\([^)]+\)', '', s).strip()

        # 「・」で始まる行を優先、なければ非空行を抽出
        # @handle: text 形式を優先パース
        import re as _re3
        handle_lines = [_clean(line.strip()) for line in text.split("\n")
                        if _re3.match(r'^@\S+[:：]', line.strip())]
        if handle_lines:
            return [l for l in handle_lines if l][:10]
        bullet_lines = [_clean(line.lstrip("・").strip()) for line in text.split("\n") if line.strip().startswith("・")]
        if bullet_lines:
            return [l for l in bullet_lines if l][:10]
        # フォールバック: 20文字以上の行をファン反応として取得
        plain_lines = [_clean(line.strip()) for line in text.split("\n") if len(line.strip()) > 20]
        return [l for l in plain_lines if l][:10]
    except Exception as e:
        return []


# ──────────────────────────────────────────────────────────
# ハルシネーションチェック（生成後の数値をWeb検索で事実確認）
# ──────────────────────────────────────────────────────────
def _fact_check_article(title: str, article_text: str, api_key: str) -> str:
    """生成記事の統計数値をGemini 2.0 Flash + Google Searchで事実確認・修正する。"""
    import re
    import shutil
    from datetime import date
    from src import llm_cost_emitter as _llm_cost
    logger = logging.getLogger("rss_fetcher")

    # 数値が含まれるか確認（打率・防御率・本塁打・勝率など）
    has_stats = bool(re.search(r'(?:\.\d{2,3}|[0-9]+本|[0-9]+勝|[0-9]+敗|[0-9]+打点|防御率|打率|出塁率|OPS|WAR|wRC)', article_text))
    if not has_stats:
        logger.info("ハルシネーションチェック: 数値なし → スキップ")
        return article_text

    if not shutil.which("gemini"):
        logger.info("ハルシネーションチェック: Gemini CLI なし → スキップ")
        return article_text

    today_str = date.today().strftime("%Y年%m月%d日")
    check_prompt = f"""以下の野球記事（読売ジャイアンツ関連）をWeb検索で最新データと照合し、数字を正確にして充実させてください。

タイトル: {title}

記事本文:
{article_text}

【照合・修正ルール（厳守）】
1. npb.jp・baseball.yahoo.co.jp・1point02.jpをWeb検索して{today_str}現在のデータを取得する
2. 記事内の数字をWeb検索結果と照合し、間違いは正しい数字に修正する
3. 「〜とみられる」「〜程度」の箇所は、Web検索で確認できれば正確な数字に置き換え「（npb.jp）」等の出典を付ける
4. 数字が少ない箇所は、Web検索で見つけたデータを追加し出典を付けて充実させる
5. 岡本和真は2025年オフにMLB移籍済み → 2026年巨人の成績には絶対に登場させない
6. 完全に事実と異なる文章は削除または修正する
7. 修正後の記事本文のみ出力（説明コメント不要）
8. 元の文体・見出し構成は保持する
9. HTMLタグなし・本文のみ出力"""

    try:
        logger.info("ハルシネーションチェック開始（Gemini 2.0 Flash + Google Search）...")
        import urllib.request as _ureq
        payload = json.dumps({
            "contents": [{"parts": [{"text": check_prompt}]}],
            "tools": [{"google_search": {}}],
            "generationConfig": {"maxOutputTokens": 2048, "temperature": 0.1}
        }).encode("utf-8")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        req = _ureq.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with _ureq.urlopen(req, timeout=30) as res:
            data = json.load(res)
        checked = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        token_in, token_out = _llm_cost.extract_usage_metadata(data)
        _emit_llm_cost_with_observability(
            logger,
            "rss_fetcher._fact_check_article.success",
            lane="rss_fetcher_fact_check",
            call_site="rss_fetcher._fact_check_article",
            post_id=None,
            source_url=None,
            content_hash=None,
            model="gemini-2.0-flash",
            input_chars=len(check_prompt),
            output_chars=len(checked),
            token_in=token_in,
            token_out=token_out,
            cache_hit=False,
            skip_reason=None,
            success=True,
            error_class=None,
        )
        if checked and len(checked) > 100:
            logger.info(f"ハルシネーションチェック完了（{len(article_text)}→{len(checked)}文字）")
            article_text = checked
        else:
            logger.warning("チェック結果が短すぎる → 元の記事を維持")
    except Exception as e:
        _emit_llm_cost_with_observability(
            logger,
            "rss_fetcher._fact_check_article.error",
            lane="rss_fetcher_fact_check",
            call_site="rss_fetcher._fact_check_article",
            post_id=None,
            source_url=None,
            content_hash=None,
            model="gemini-2.0-flash",
            input_chars=len(check_prompt),
            output_chars=0,
            token_in=None,
            token_out=None,
            cache_hit=False,
            skip_reason=None,
            success=False,
            error_class=type(e).__name__,
        )
        logger.warning(f"ハルシネーションチェック失敗 → 元の記事を維持: {e}")

    return article_text


# ──────────────────────────────────────────────────────────
# Geminiでニュース解説記事を生成
# ──────────────────────────────────────────────────────────
def generate_article_with_gemini(
    title: str,
    summary: str,
    category: str,
    real_reactions: list = None,
    has_game: bool = True,
    source_name: str = "",
    source_day_label: str = "",
    source_type: str = "news",
    tweet_url: str = "",
    source_entry: dict | None = None,
) -> str:
    """Geminiで巨人ファン向け解説記事を生成。失敗時は空文字を返す。"""
    import urllib.request, urllib.error
    from dotenv import load_dotenv
    from src import llm_cost_emitter as _llm_cost
    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        return ""

    import re
    from datetime import date
    today_str = date.today().strftime("%Y年%m月%d日")
    summary_plain = re.sub(r"<[^>]+>", "", summary).strip()
    strict_mode = strict_fact_mode_enabled()
    summary_max_chars = STRICT_PROMPT_SUMMARY_MAX_CHARS if strict_mode else DEFAULT_PROMPT_SUMMARY_MAX_CHARS
    summary_clean = summary_plain[:summary_max_chars]

    # ファン反応（呼び出し元から渡された場合はそれを使う、なければ取得）
    if real_reactions is None:
        real_reactions = fetch_fan_reactions_from_yahoo(title, summary, category, source_name=source_name)
    if real_reactions:
        fan_voices = "\n".join(f"「{_reaction_body_text(r)}」" for r in real_reactions[:3])
        fan_section = f"※以下は実際のXユーザーの声（記事には含めなくてよい、雰囲気の参考のみ）\n{fan_voices}"
    else:
        fan_section = ""
    source_fact_block = _build_source_fact_block(
        title,
        summary_clean,
        source_type=source_type,
        entry=source_entry,
    )
    source_url_for_cost = tweet_url or ""
    if not source_url_for_cost and isinstance(source_entry, dict):
        source_url_for_cost = str(source_entry.get("url") or source_entry.get("link") or "")
    source_url_for_cost = source_url_for_cost or None

    data_sources = f"""【STEP1: まず以下のサイトをWeb検索して{today_str}現在の最新データを取得せよ】
① npb.jp → 今季個人成績・チーム成績・順位表（最優先）
② baseball.yahoo.co.jp/npb → スポーツナビ選手成績（必ずスポナビの数字を使う）
③ 1point02.jp → セイバーメトリクス（wRC+・WAR・FIP等）
④ baseballking.jp / full-count.jp → 最新ニュース・コメント
⑤ nikkansports.com / hochi.news → 試合速報・選手コメント
【STEP2: 取得したデータをもとに記事を書く（順位・成績は上記Web検索結果の最新値を使う）】"""

    # タイトル・要約から勝敗を判定してプロンプトに明示
    import re as _re2
    score_match = _re2.search(r'(\d{1,2})[－\-–](\d{1,2})', title + " " + summary_clean)
    win_loss_hint = ""
    if score_match:
        g_score = int(score_match.group(1))
        o_score = int(score_match.group(2))
        if "巨人" in (title + summary_clean)[:20]:
            if g_score > o_score:
                win_loss_hint = f"※この試合は巨人が{g_score}-{o_score}で【勝利】した試合です。"
            elif g_score < o_score:
                win_loss_hint = f"※この試合は巨人が{g_score}-{o_score}で【敗戦】した試合です。負け試合として正直に書くこと。"
            else:
                win_loss_hint = f"※この試合は{g_score}-{o_score}の【引き分け】です。"
    elif any(w in (title + summary_clean) for w in ["勝利", "白星", "連勝", "サヨナラ勝"]):
        win_loss_hint = "※この試合は巨人が【勝利】した試合です。"
    elif any(w in (title + summary_clean) for w in ["敗れ", "敗戦", "連敗", "黒星", "完封負"]):
        win_loss_hint = "※この試合は巨人が【敗戦】した試合です。負け試合として正直に書くこと。前向きに美化しない。"

    article_subtype = _detect_article_subtype(title, summary_clean, category, has_game)
    enhanced_grounded_rules = _enhanced_grounded_rules(category, article_subtype=article_subtype, source_type=source_type)
    logger = logging.getLogger("rss_fetcher")

    if strict_mode:
        attempt_limit = get_gemini_attempt_limit(strict_mode=True)
        min_chars = _get_gemini_strict_min_chars(category, title, summary_clean)
        team_stats_block = _fetch_team_stats_block_for_strict_article(category, logger)
        prompt = _build_gemini_strict_prompt(
            title,
            summary_clean,
            category,
            source_fact_block,
            win_loss_hint,
            has_game,
            real_reactions=real_reactions,
            source_day_label=source_day_label,
            source_name=source_name,
            source_type=source_type,
            tweet_url=tweet_url,
            team_stats_block=team_stats_block,
        )
        cached_text, _cache_meta = _gemini_text_with_cache(
            api_key=api_key,
            prompt=prompt,
            logger=logger,
            attempt_limit=attempt_limit,
            min_chars=min_chars,
            log_label="Gemini strict fact mode",
            source_url=source_url_for_cost or "",
            content_text=_build_gemini_cache_content_text(
                title,
                summary_clean,
                category,
                source_name,
                source_day_label,
                source_type,
                tweet_url,
                source_url_for_cost or "",
                win_loss_hint,
                source_fact_block,
                team_stats_block,
                " ".join(_reaction_body_text(reaction) for reaction in real_reactions[:3]),
            ),
            prompt_template_id=_gemini_prompt_template_id(category, article_subtype),
            cache_manager=_get_gemini_cache_manager(),
        )
        return cached_text

    game_category_prompt = ""
    if category == "試合速報" and _is_game_template_subtype(article_subtype):
        headings = _game_required_headings(article_subtype)
        if article_subtype == "lineup":
            game_category_prompt = f"""あなたは読売ジャイアンツ専門ブログの編集者です。
今日は{today_str}です。まずWeb検索で必要な事実を確認してから、試合前のスタメン記事を日本語で書いてください。

{data_sources}

タイトル: {title}
ニュース要約: {summary_clean}

{fan_section}

【構成】
・見出しは「{headings[0]}」「{headings[1]}」「{headings[2]}」「{headings[3]}」の4つをこの順番で使う
・本文は400〜800文字
・対戦カード、球場、開始時刻、打順、先発投手、成績数字は source か Web検索で確認できた表記をそのまま残す
・【スタメン一覧】では打順と選手名を具体的に整理する
・【先発投手】では両軍の予告先発と、確認できた成績数字だけを残す
・【注目ポイント】では試合が始まったら最初にどこを見るかを書く
・抽象的な期待論や結果予想で膨らませない
{enhanced_grounded_rules}\
・最後は「みなさんの意見はコメントで！」で締める
・HTMLタグなし・本文のみ出力"""
        elif article_subtype == "postgame":
            game_category_prompt = f"""あなたは読売ジャイアンツ専門ブログの編集者です。
今日は{today_str}です。まずWeb検索で必要な事実を確認してから、試合後の記事を日本語で書いてください。

{win_loss_hint}
{data_sources}

タイトル: {title}
ニュース要約: {summary_clean}

{fan_section}

【構成】
・見出しは「{headings[0]}」「{headings[1]}」「{headings[2]}」「{headings[3]}」の4つをこの順番で使う
・本文は400〜800文字
・スコア、勝敗、選手名、安打数、打点、投球回、防御率などの数字は必ず残す
・【ハイライト】では決勝打、好投、守備など source にある決め手を整理する
・【選手成績】では数字つきの個人成績を具体的に整理する
・【試合展開】ではどこで流れが動いたかを source にある事実だけで書く
・抽象的な総論で埋めず、数字と固有名詞を残す
{enhanced_grounded_rules}\
・最後は「みなさんの意見はコメントで！」で締める
・HTMLタグなし・本文のみ出力"""
        elif article_subtype == "live_anchor":
            game_category_prompt = f"""あなたは読売ジャイアンツ専門ブログの編集者です。
今日は{today_str}です。まずWeb検索で必要な事実を確認してから、試合途中の節目を整理する記事を日本語で書いてください。

{data_sources}

タイトル: {title}
ニュース要約: {summary_clean}

{fan_section}

【構成】
・見出しは「{headings[0]}」「{headings[1]}」「{headings[2]}」「{headings[3]}」の4つをこの順番で使う
・本文は350〜650文字
・節目の時点、現在スコア、対戦相手、重要プレー1〜3点を source にある表記のまま残す
・【時点】では、何回表/裏終了時点か、何回何死時点かを必ず明示する
・【現在スコア】では source にあるスコアだけを使い、未反映の得点を推測しない
・【直近のプレー】では、重要プレーを1〜3点に絞り、予測語や未発生事象を足さない
・X単独で断定せず、公式XまたはNPBライブで裏付けられる事実だけを書く
・【ファン視点】は最後の1文だけにする
・見出しで「{LIVE_UPDATE_LINEUP_TITLE_PREFIX}」を使わない。「打順」「スタメン」「先発メンバー」を section heading にしない
{enhanced_grounded_rules}\
・最後は「みなさんの意見はコメントで！」で締める
・HTMLタグなし・本文のみ出力"""
        elif article_subtype == "live_update":
            game_category_prompt = f"""あなたは読売ジャイアンツ専門ブログの編集者です。
今日は{today_str}です。まずWeb検索で必要な事実を確認してから、試合途中経過の記事を日本語で書いてください。

{data_sources}

タイトル: {title}
ニュース要約: {summary_clean}

{fan_section}

【構成】
・見出しは「{headings[0]}」「{headings[1]}」「{headings[2]}」の3つをこの順番で使う
・本文は400〜700文字
・現在のイニング、スコア、継投、打席、塁状況など source にある途中経過だけを残す
・試合は進行中として書き、勝敗の断定、最終講評、結果予想は書かない
・【流れが動いた場面】では実況を全イニング分並べず、同点・勝ち越し・逆転・継投など流れが動いた瞬間だけを絞って整理する
・【次にどこを見るか】では、このあとどの回・どの打順・どの投手継投に注目するかを source にある事実だけで書く
・スタメン発表記事に切り替えない。1番〜9番を並べた一覧、打順表、表組み、箇条書きは禁止
・見出しで「{LIVE_UPDATE_LINEUP_TITLE_PREFIX}」を使わない。「打順」「スタメン」「先発メンバー」を section heading にしない
・抽象的な期待論や一般論で膨らませない
{enhanced_grounded_rules}\
・最後は「みなさんの意見はコメントで！」で締める
・HTMLタグなし・本文のみ出力"""
        else:
            game_category_prompt = f"""あなたは読売ジャイアンツ専門ブログの編集者です。
今日は{today_str}です。まずWeb検索で必要な事実を確認してから、試合前の変更情報記事を日本語で書いてください。

{data_sources}

タイトル: {title}
ニュース要約: {summary_clean}

{fan_section}

【構成】
・見出しは「{headings[0]}」「{headings[1]}」「{headings[2]}」の3つをこの順番で使う
・本文は350〜650文字
・中止、スライド登板、先発変更、球場、開始時刻、日付、選手名は必ず残す
・【具体的な変更内容】では新日程、新先発、引用など source にある事実を順に整理する
・【この変更が意味すること】では結果予想はせず、次にどこを見るかだけを書く
・抽象的な期待論や一般論で膨らませない
{enhanced_grounded_rules}\
・最後は「みなさんの意見はコメントで！」で締める
・HTMLタグなし・本文のみ出力"""

    player_recovery_prompt = ""
    if category == "選手情報" and _is_recovery_template_story(title, summary_clean, category):
        recovery_subject = _extract_recovery_subject(title, summary_clean)
        injury_part = _extract_recovery_injury_part(title, summary_clean, recovery_subject)
        return_timing = _extract_recovery_return_timing(title, summary_clean, recovery_subject)
        player_recovery_prompt = f"""あなたは読売ジャイアンツ専門ブログの編集者です。
今日は{today_str}です。まずWeb検索で必要な事実を確認してから、故障・復帰関連の記事を日本語で書いてください。

{data_sources}

タイトル: {title}
ニュース要約: {summary_clean}

{fan_section}

【構成】
・見出しは「【故障・復帰の要旨】」「【故障の詳細】」「【リハビリ状況・復帰見通し】」「【チームへの影響と今後の注目点】」の4つをこの順番で使う
・本文は350〜650文字
・選手名はタイトルと本文の両方に必ず明記する
・部位、診断名、期間、復帰時期は source にある表現を正確に残す
・{injury_part or '故障部位'}や{return_timing or '復帰見通し'}の表現は source にない形へ言い換えない
・【故障の詳細】では原因、診断、離脱の経緯を source にある範囲だけで整理する
・【リハビリ状況・復帰見通し】では現在の段階、再開したメニュー、復帰時期の見通しを整理する
・【チームへの影響と今後の注目点】では代替選手、起用、ローテへの影響を source にある材料だけで書く
・選手本人や監督・コーチのコメントがあれば1つまで残す
・推測、断定、精神論、医療判断の補完は書かない
{enhanced_grounded_rules}\
・最後は「みなさんの意見はコメントで！」で締める
・HTMLタグなし・本文のみ出力"""

    player_notice_prompt = ""
    if category == "選手情報" and _is_notice_template_story(title, summary_clean, category):
        notice_subject, notice_type = _extract_notice_subject_and_type(title, summary_clean)
        notice_label = notice_type or _extract_notice_type_label(f"{title} {summary_clean}") or "公示"
        player_notice_prompt = f"""あなたは読売ジャイアンツ専門ブログの編集者です。
今日は{today_str}です。まずWeb検索で必要な事実を確認してから、公示・登録関連の記事を日本語で書いてください。

{data_sources}

タイトル: {title}
ニュース要約: {summary_clean}

{fan_section}

【構成】
・見出しは「【公示の要旨】」「【対象選手の基本情報】」「【公示の背景】」「【今後の注目点】」の4つをこの順番で使う
・本文は350〜650文字
・選手名はタイトルと本文の両方に必ず明記する
・{notice_label}の区分、日付、登録・抹消・合流などの表記は source にある形を残す
・数字があれば、打率、防御率、試合数、本塁打、打点など今季の具体数字を必ず残す
・【対象選手の基本情報】では{notice_subject or '対象選手'}のポジションや現在地を整理する
・【公示の背景】では故障、調整状況、二軍成績、チーム事情のうち source にある材料だけを書く
・【今後の注目点】では次の登録、出場、復帰時期のどこを見るかだけを書く
・推測、精神論、一般論で膨らませない
{enhanced_grounded_rules}\
・最後は「みなさんの意見はコメントで！」で締める
・HTMLタグなし・本文のみ出力"""

    # カテゴリ別プロンプト
    category_prompts = {
        "試合速報": game_category_prompt or f"""あなたは読売ジャイアンツの現実的なファンブロガー兼データアナリストです。
今日は{today_str}です。まずWeb検索でデータを調べてから、データ豊富な試合分析記事を日本語で書いてください。

{win_loss_hint}
【重要】勝ち試合は喜びを、負け試合は課題・問題点を正直に書く。結果に反した美化・提灯記事は厳禁。

{data_sources}

タイトル: {title}
ニュース要約: {summary_clean}

【記事に必ず入れる数字（Web検索で取得）】
・今試合のスコア・投球回・奪三振・失点
・先発投手の今季防御率・WHIP・通算成績
・打者のヒット数・打率・得点圏打率
・今季チーム順位・勝敗・得失点差
・セ・リーグ他球団との比較データ1つ以上

{fan_section}

【構成】
・見出し3〜4個（【】か■で始める）
・各セクション1〜2段落
・500〜600文字
・Web検索で確認できた数字は積極的に使い、末尾に「（npb.jp）」「（スポーツナビ）」「（1point02.jp）」など出典を括弧書きで付ける
・確認できなかった数字は「〜とみられる」「〜程度」と明示（出典なし）
{enhanced_grounded_rules}\
・最後は「みなさんの意見はコメントで！」で締める
・HTMLタグなし・本文のみ出力""",

        "選手情報": player_recovery_prompt or player_notice_prompt or f"""あなたは読売ジャイアンツの熱狂的なファンブロガー兼データアナリストです。
今日は{today_str}です。まずWeb検索でデータを調べてから、データ豊富な選手分析コラムを日本語で書いてください。

{data_sources}

タイトル: {title}
ニュース要約: {summary_clean}

【記事に必ず入れる数字（Web検索で取得）】
・対象選手の今季打率・出塁率・長打率・OPS（または防御率・WHIP・K/9）
・昨季との比較（数値の変化を具体的に）
・チーム内ランキングでの位置（「チーム〇位」等）
・セイバーメトリクス指標1つ以上（wRC+・WAR・FIPなど）
・同ポジション他球団選手との比較1名以上

{fan_section}

【構成】
・見出し4〜5個（【】か■で始める）
・各セクション1〜2段落
・500〜600文字
・Web検索で確認できた数字は積極的に使い、末尾に「（npb.jp）」「（スポーツナビ）」「（1point02.jp）」など出典を括弧書きで付ける
・確認できなかった数字は「〜とみられる」「〜程度」と明示（出典なし）
{enhanced_grounded_rules}\
・最後は「みなさんの意見はコメントで！」で締める
・HTMLタグなし・本文のみ出力""",

        "補強・移籍": f"""あなたは読売ジャイアンツの熱狂的なファンブロガー兼データアナリストです。
今日は{today_str}です。まずWeb検索でデータを調べてから、データ豊富な補強分析記事を日本語で書いてください。

{data_sources}

タイトル: {title}
ニュース要約: {summary_clean}

【記事に必ず入れる数字（Web検索で取得）】
・補強選手の直近2〜3年の成績（打率・本塁打・OPS等）
・チームの現状弱点データ（この補強が必要な理由）
・補強前後の想定スタメン・戦力比較
・過去の類似補強選手との成績比較
・チーム順位・得点力・防御力の現状数値

{fan_section}

【構成】
・見出し4〜5個（【】か■で始める）
・各セクション1〜2段落
・500〜600文字
・Web検索で確認できた数字は積極的に使い、末尾に「（npb.jp）」「（スポーツナビ）」「（1point02.jp）」など出典を括弧書きで付ける
・確認できなかった数字は「〜とみられる」「〜程度」と明示（出典なし）
{enhanced_grounded_rules}\
・最後は「みなさんの意見はコメントで！」で締める
・HTMLタグなし・本文のみ出力""",

        "首脳陣": f"""あなたは読売ジャイアンツ専門ブログの編集者です。
今日は{today_str}です。まずWeb検索で必要な事実を確認してから、監督・コーチの発言を軸にした記事を日本語で書いてください。

{data_sources}

タイトル: {title}
ニュース要約: {summary_clean}

{fan_section}

【構成】
・見出しは「【発言の要旨】」「【発言内容】」「【文脈と背景】」「【次の注目】」の4つをこの順番で使う
・本文は400〜800文字
・発言者を必ず明記する
・引用が2つ以上ある場合は【発言内容】で並べて整理する
・【文脈と背景】では試合状況、選手状況、チーム状況のどれかを必ず整理する
・【次の注目】では次の起用、采配、役割変化のどこを見るかを具体的に書く
・元記事にない数字、比較、一般論、精神論は足さない
{enhanced_grounded_rules}\
・最後は「みなさんの意見はコメントで！」で締める
・HTMLタグなし・本文のみ出力""",
    }

    prompt = category_prompts.get(category, f"""あなたは読売ジャイアンツの熱狂的なファンブロガー兼データアナリストです。
今日は{today_str}です。まずWeb検索でデータを調べてから、データ豊富な分析記事を日本語で書いてください。

{data_sources}

タイトル: {title}
カテゴリ: {category}
ニュース要約: {summary_clean}

【記事に必ず入れる数字（Web検索で取得）】
・関連選手の今季成績（打率・本塁打・OPS or 防御率・WHIP等）
・昨季との比較データ
・チーム順位・勝敗・得失点差
・セ・リーグ他球団との比較1つ以上

{fan_section}

【構成】
・見出し3〜4個（【】か■で始める）
・各セクション1〜2段落
・500〜600文字
・Web検索で確認できた数字は積極的に使い、末尾に「（npb.jp）」「（スポーツナビ）」「（1point02.jp）」など出典を括弧書きで付ける
・確認できなかった数字は「〜とみられる」「〜程度」と明示（出典なし）
{enhanced_grounded_rules}\
・最後は「みなさんの意見はコメントで！」で締める
・HTMLタグなし・本文のみ出力""")

    logger = logging.getLogger("rss_fetcher")

    # Gemini 2.0 Flash + Google Search グラウンディング（Web検索付きAPI・CLIより高速）
    payload_grounded = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "tools": [{"google_search": {}}],
        "generationConfig": {
            "maxOutputTokens": 2048,
            "temperature": 0.7,
            "thinkingConfig": {"thinkingBudget": GEMINI_FLASH_THINKING_BUDGET},
        }
    }).encode("utf-8")

    attempt_limit = get_gemini_attempt_limit(strict_mode=False)
    logger.info("Gemini 2.5 Flash + Google Search 検索付きで記事生成中（最大%d回試行）...", attempt_limit)
    for attempt in range(attempt_limit):
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
            req = urllib.request.Request(url, data=payload_grounded, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=90) as res:
                data = json.load(res)
            # Google Searchツール使用時はpartsが複数になることがある。テキストのみ結合
            parts = data["candidates"][0]["content"].get("parts", [])
            raw_text = "".join(p.get("text", "") for p in parts if "text" in p).strip()
            raw_text = _strip_prompt_role_echo(raw_text)
            token_in, token_out = _llm_cost.extract_usage_metadata(data)
            _emit_llm_cost_with_observability(
                logger,
                "rss_fetcher.generate_article_with_gemini.success",
                lane="rss_fetcher_grounded",
                call_site="rss_fetcher.generate_article_with_gemini",
                post_id=None,
                source_url=source_url_for_cost,
                content_hash=None,
                model="gemini-2.5-flash",
                input_chars=len(prompt),
                output_chars=len(raw_text),
                token_in=token_in,
                token_out=token_out,
                cache_hit=False,
                skip_reason=None,
                success=True,
                error_class=None,
            )
            if raw_text and len(raw_text) > 150:
                logger.info(f"Gemini 2.5 Flash（Google検索付き）生成成功 {len(raw_text)}文字")
                return raw_text
            logger.warning("Gemini応答が短すぎる（%d文字）、試行 %d/%d", len(raw_text), attempt + 1, attempt_limit)
        except Exception as e:
            _emit_llm_cost_with_observability(
                logger,
                "rss_fetcher.generate_article_with_gemini.error",
                lane="rss_fetcher_grounded",
                call_site="rss_fetcher.generate_article_with_gemini",
                post_id=None,
                source_url=source_url_for_cost,
                content_hash=None,
                model="gemini-2.5-flash",
                input_chars=len(prompt),
                output_chars=0,
                token_in=None,
                token_out=None,
                cache_hit=False,
                skip_reason=None,
                success=False,
                error_class=type(e).__name__,
            )
            logger.warning(f"Gemini 2.5 Flash失敗 試行{attempt+1}/{attempt_limit}: {e}")

    logger.error("Gemini 2.5 Flash（Google検索付き）が上限回数に達したため記事生成スキップ")
    return ""


# ──────────────────────────────────────────────────────────
# Grokで記事生成（Web検索＋X検索を1回で完結）
# ──────────────────────────────────────────────────────────
def generate_article_with_grok(title: str, summary: str, category: str, win_loss_hint: str = "") -> tuple:
    """Grok 4-1-fast で記事生成 + Xファンの声取得を同時に行う。
    Returns: (article_text, fan_reactions_list)"""
    import urllib.request, urllib.error
    from dotenv import load_dotenv
    from datetime import date
    import re
    load_dotenv(ROOT / ".env")
    api_key = os.environ.get("GROK_API_KEY", "")
    logger = logging.getLogger("rss_fetcher")
    if not api_key:
        return "", []

    today_str = date.today().strftime("%Y年%m月%d日")
    fan_reaction_limit = get_fan_reaction_limit()
    strict_mode = strict_fact_mode_enabled()
    summary_plain = re.sub(r"<[^>]+>", "", summary).strip()
    summary_max_chars = STRICT_PROMPT_SUMMARY_MAX_CHARS if strict_mode else DEFAULT_PROMPT_SUMMARY_MAX_CHARS
    summary_clean = summary_plain[:summary_max_chars]
    source_fact_block = _build_source_fact_block(title, summary_clean)

    query_short = re.sub(r'【.*?】', '', title).strip()[:20]

    if strict_mode:
        prompt = f"""読売ジャイアンツのファンブログ記事を書いてください。今日は{today_str}です。

【使ってよい事実】
{source_fact_block}

{win_loss_hint}

X検索で「{query_short} 巨人」のファンの声を{fan_reaction_limit}件探してください。

【絶対ルール】
・---ARTICLE---、---SUMMARY---、---STATS--- に書ける事実は「使ってよい事実」に含まれる内容だけ
・新しい数字、順位、成績、日付、契約、故障、比較、引用、出典を足さない
・試合がない記事ではスコア・勝敗・試合結果を書かない
・ファンの声は ---FANS--- のみに書く。---ARTICLE--- には混ぜない
・本文はですます調。見出しは3つまで。誇張しすぎない
・---STATS--- は「使ってよい事実」にある数字だけ箇条書きにする。なければ空欄でよい
・---IMPRESSION--- も新しい事実を書かず、感想だけを書く

---SUMMARY---
（元記事の事実だけで2〜3文）
---ARTICLE---
（元記事の事実だけで350〜500文字。説明不要）
---FANS---
（X検索で見つけた実際のコメント。形式：@アカウント名: コメント内容。1行1件。{fan_reaction_limit}件）
---STATS---
（使ってよい事実の数字のみ。形式：・項目: 値）
---IMPRESSION---
（感想のみ。最後は「コメント欄で教えてください！」）"""
    elif win_loss_hint:
        # 試合記事プロンプト
        prompt = f"""読売ジャイアンツの熱狂的ファンブログ記事を書いてください。今日は{today_str}。

{win_loss_hint}タイトル: {title}
要約: {summary_clean}

X検索で「{query_short} 巨人」のファンの声を{fan_reaction_limit}件探してください。

【絶対ルール】
・文体は「ですます調」（〜です、〜ます）で統一する
・---SUMMARY---は3〜4文のオリジナル要約。試合の核心・選手名・監督コメントを盛り込み読者が続きを読みたくなる文章にする
・---ARTICLE---の最初の見出しは必ず「【ニュースの整理】」にする
・その下に続く見出しは「【試合のポイント】」「【次の注目】」など、論点が伝わる短い見出しにする
・最初の段落はファン目線で興奮気味に描写。「画面の前で思わずガッツポーズしました！」など共感フレーズを1つ入れる
・本文は500〜700文字。各段落は3文以内でテンポよく
・成績数字は上記「タイトル」「要約」に明記されているもののみ使用。書かれていない数字は書かない・推測・架空禁止
・負け試合は正直に課題を書く。前向きに美化しない
・岡本和真は2025年オフMLB移籍済み → 2026年巨人成績に登場させない
・---STATS---はタイトル・要約に含まれる情報のみ箇条書き。書かれていない項目は省略する（空欄可）
・---IMPRESSION---は300文字のブロガー感想（ですます調・最後は「コメント欄で教えてください！」）
・「ファンの声」「Xより」などの見出しは---ARTICLE---内に書かない（---FANS---に書く）

---SUMMARY---
（2〜3文の要約）
---ARTICLE---
（上記ルール厳守で記事本文のみ。説明不要）
---FANS---
（X検索で見つけた実際のコメント。形式：@アカウント名: コメント内容。1行1件。{fan_reaction_limit}件。喜び・悔しさ・驚き・批判など感情を多様に選ぶ）
---STATS---
（タイトル・要約に書かれた情報のみ。形式：・項目: 値。書かれていない数字は書かない）
---IMPRESSION---
（300文字の感想。ですます調）"""
    else:
        # 選手ニュース・コラム記事プロンプト（試合なし）
        prompt = f"""読売ジャイアンツ応援ブログの記事を書いてください。今日は{today_str}。

タイトル: {title}
要約: {summary_clean}

X検索で「{query_short} 巨人」に関するファンの声を{fan_reaction_limit}件探してください。

【絶対ルール】
・文体は「ですます調」（〜です、〜ます）で統一する
・これは試合記事ではない。スコア・勝敗・試合結果は絶対に書かない・推測もしない
・---SUMMARY---はこのニュースの要点を3〜4文で。選手名・コメント・背景を盛り込む
・---ARTICLE---の最初の見出しは必ず「【ニュースの整理】」にする
・その下の見出しは「【ここに注目】」「【次の注目】」など、論点が伝わる短い見出しにする
・本文は500〜700文字。各段落は3文以内でテンポよく
・数字は上記「タイトル」「要約」に明記されているもののみ使用。書かれていない数字は書かない・推測・架空禁止
・岡本和真は2025年オフMLB移籍済み → 2026年巨人成績に登場させない
・---STATS---はタイトル・要約に含まれる情報のみ。書かれていない数字は省略（空欄可）。試合スコア・勝敗は書かない
・---IMPRESSION---は300文字のブロガー感想（ですます調・最後は「コメント欄で教えてください！」）
・「ファンの声」「Xより」などの見出しは---ARTICLE---内に書かない（---FANS---に書く）

---SUMMARY---
（3〜4文の要約）
---ARTICLE---
（上記ルール厳守で記事本文のみ。説明不要）
---FANS---
（X検索で見つけた実際のコメント。形式：@アカウント名: コメント内容。1行1件。{fan_reaction_limit}件）
---STATS---
（タイトル・要約に書かれた情報のみ。形式：・項目: 値。書かれていない数字は書かない）
---IMPRESSION---
（300文字の感想。ですます調）"""

    # X検索の日付範囲（当日のみ。当日0件なら前日も含む）
    today = datetime.now()
    from_date = today.strftime("%Y-%m-%d")   # 今日
    to_date   = today.strftime("%Y-%m-%d")

    base_payload = {
        "input": [{"role": "user", "content": prompt}],
        "max_turns": 1,
        "max_output_tokens": 800,
        "tools": [
            {
                "type": "x_search",
                "from_date": from_date,
                "to_date": to_date
            }
        ]
    }

    models_to_try = ["grok-4-1-fast-non-reasoning"]
    logger.info("Grok Responses API (Web+X検索) で記事生成中...")
    for model_name in models_to_try:
        payload_obj = dict(base_payload)
        payload_obj["model"] = model_name
        payload_current = json.dumps(payload_obj).encode("utf-8")
        for attempt in range(2):
            try:
                req = urllib.request.Request(
                    "https://api.x.ai/v1/responses",
                    data=payload_current,
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
                )
                with urllib.request.urlopen(req, timeout=90) as res:
                    data = json.load(res)
                # ツール呼び出し回数ログ（コスト確認用）
                tool_usage = data.get("usage", {}).get("server_side_tool_usage", {})
                if tool_usage:
                    logger.info(f"[Grok tool usage] {tool_usage}")
                # 出力切れ監視（max_output_tokens に達した場合は incomplete_details に理由が入る）
                incomplete = data.get("incomplete_details")
                if incomplete:
                    logger.warning(f"[Grok incomplete] {incomplete} → max_output_tokens を 1800 に上げることを検討")
                text = _parse_responses_api_text(data)

                # セクション分割: SUMMARY / ARTICLE / FANS / STATS / IMPRESSION
                def _extract(t, marker):
                    """---MARKER--- の次から次のセパレータまでを抽出"""
                    import re as _r
                    m = _r.search(rf'---{marker}---\s*(.*?)(?=---[A-Z]+---|$)', t, _r.DOTALL)
                    return m.group(1).strip() if m else ""

                summary_text  = _extract(text, "SUMMARY")
                article_text  = _extract(text, "ARTICLE")
                fans_raw      = _extract(text, "FANS")
                stats_text    = _extract(text, "STATS")
                impression    = _extract(text, "IMPRESSION")

                # ARTICLE が取れなければ全体を記事として扱う
                if not article_text:
                    article_text = text

                import re as _r2
                fan_reactions = [l.strip() for l in fans_raw.split("\n")
                                 if l.strip() and len(l.strip()) > 10][:15]

                if article_text and len(article_text) > 150:
                    logger.info(f"Grok ({model_name}) 生成成功 記事{len(article_text)}文字 ファン声{len(fan_reactions)}件")
                    return article_text, fan_reactions, summary_text, stats_text, impression
                logger.warning(f"Grok ({model_name}) 応答が短すぎる（{len(article_text)}文字）、リトライ {attempt+1}/2")
            except Exception as e:
                logger.warning(f"Grok ({model_name}) 失敗 試行{attempt+1}/2: {e}")

    logger.error("Grok全モデル失敗 → Geminiにフォールバック")
    return "", [], "", "", ""


# ──────────────────────────────────────────────────────────
# ニュース記事ブロックHTML生成
# ──────────────────────────────────────────────────────────
def build_news_block(title: str, summary: str, url: str, source_name: str, category: str = "コラム", og_image_url: str = "", media_id: int = 0, extra_images: list = None, has_game: bool = True, article_ai_mode_override: str | None = None, source_links: list[dict] | None = None, source_day_label: str = "", source_type: str = "news", media_quotes: list[dict] | None = None, source_entry: dict | None = None, duplicate_guard_context: dict | None = None) -> tuple[str, str]:
    import re
    summary_clean = re.sub(r"<[^>]+>", "", summary).strip()
    article_subtype = _detect_article_subtype(title, summary_clean, category, has_game)
    use_ai_for_article, generation_category, ai_route_reason = _resolve_article_ai_strategy(
        category,
        title,
        summary_clean,
        has_game,
        article_subtype=article_subtype,
    )
    social_story = source_type == "social_news" and not _social_source_prefers_structured_template(generation_category, article_subtype)
    special_story_kind = _detect_player_special_template_kind(title, summary_clean) if generation_category == "選手情報" and not social_story else ""
    recovery_story = special_story_kind == "player_recovery"
    notice_story = special_story_kind == "player_notice"
    body_category = generation_category if special_story_kind else category
    body_subtype = "social_news" if social_story else "player_recovery" if recovery_story else "player_notice" if notice_story else article_subtype
    effective_generation_category = category if social_story else generation_category
    article_ai_mode = get_article_ai_mode(has_game, article_ai_mode_override) if use_ai_for_article else "none"
    fan_reaction_limit = get_fan_reaction_limit()
    logger = logging.getLogger("rss_fetcher")
    rendered_ai_body_html = ""
    postgame_strict_review_reason = ""
    manager_quote_zero_review_reason = ""
    rule_based_generated = False
    if ai_route_reason and ai_route_reason != "category_enabled":
        logger.info(
            json.dumps(
                {
                    "event": "article_ai_route_override",
                    "source_url": url,
                    "original_category": category,
                    "generation_category": generation_category,
                    "article_subtype": article_subtype,
                    "reason": ai_route_reason,
                    "title": title,
                },
                ensure_ascii=False,
            )
        )
    lineup_stat_rows = []
    if category == "試合速報" and article_subtype == "lineup":
        try:
            lineup_stat_rows = fetch_today_giants_lineup_stats_from_yahoo()
        except Exception as e:
            logging.getLogger("rss_fetcher").warning("スタメン成績の取得失敗: %s", e)
            lineup_stat_rows = []
    lineup_stats_rendered = False

    # 試合がない日は勝敗ヒントを生成しない（架空スコア捏造防止）
    win_loss_hint = ""
    if has_game:
        import re as _re2
        score_match = _re2.search(r'(\d{1,2})[－\-–](\d{1,2})', title + " " + summary_clean)
        if score_match:
            g, o = int(score_match.group(1)), int(score_match.group(2))
            if "巨人" in (title + summary_clean)[:20]:
                if g > o:   win_loss_hint = f"※この試合は巨人が{g}-{o}で【勝利】した試合です。"
                elif g < o: win_loss_hint = f"※この試合は巨人が{g}-{o}で【敗戦】した試合です。負け試合として正直に書くこと。前向きに美化しない。"
        elif any(w in (title + summary_clean) for w in ["勝利", "白星", "連勝", "サヨナラ勝"]):
            win_loss_hint = "※この試合は巨人が【勝利】した試合です。"
        elif any(w in (title + summary_clean) for w in ["敗れ", "敗戦", "連敗", "黒星", "完封負"]):
            win_loss_hint = "※この試合は巨人が【敗戦】した試合です。負け試合として正直に書くこと。前向きに美化しない。"

    def _generate_gemini_body() -> tuple[str, str]:
        nonlocal postgame_strict_review_reason, manager_quote_zero_review_reason, rule_based_generated
        parts_rendered = _maybe_render_postgame_article_parts(
            title=title,
            summary=summary_clean,
            category=effective_generation_category,
            has_game=has_game,
            source_name=source_name,
            source_url=url,
            source_type=source_type,
            source_entry=source_entry,
            win_loss_hint=win_loss_hint,
            logger=logger,
        )
        if isinstance(parts_rendered, _PostgameStrictReviewFallback):
            postgame_strict_review_reason = parts_rendered.reason
            logger.warning("postgame_strict: route_to_review reason=%s", parts_rendered.reason)
            if isinstance(duplicate_guard_context, dict):
                duplicate_guard_context["postgame_strict_review_reason"] = parts_rendered.reason
            return "", ""
        if parts_rendered is not None:
            return parts_rendered
        duplicate_context = duplicate_guard_context or _build_duplicate_news_context(
            source_url=url,
            title=title,
            summary=summary_clean,
            category=effective_generation_category,
            source_type=source_type,
            has_game=has_game,
            source_entry=source_entry,
            source_name=source_name,
        )
        if _evaluate_pre_gemini_duplicate_guard(logger, duplicate_context) == "skip":
            if isinstance(duplicate_guard_context, dict):
                duplicate_guard_context.update(duplicate_context)
            return "", ""
        if isinstance(duplicate_guard_context, dict):
            duplicate_guard_context.update(duplicate_context)
            if str(duplicate_guard_context.get("guard_outcome") or "") != "review":
                manager_review = _maybe_route_zero_quote_manager_review(
                    article_subtype=article_subtype,
                    quote_count=_manager_quote_count(title, summary_clean),
                    title=title,
                    source_name=source_name,
                    logger=logger,
                )
                if isinstance(manager_review, _ManagerQuoteZeroReviewFallback):
                    manager_quote_zero_review_reason = manager_review.reason
                    logger.warning("manager_quote_zero_review: route_to_review reason=%s", manager_review.reason)
                    duplicate_guard_context["manager_quote_zero_review_reason"] = manager_review.reason
                    return "", ""
        rule_based_body = _build_rule_based_subtype_body(
            title=title,
            summary=summary_clean,
            generation_category=effective_generation_category,
            article_subtype=article_subtype,
            special_story_kind=special_story_kind,
            source_url=url,
            source_name=source_name,
            source_day_label=source_day_label,
            source_type=source_type,
            lineup_rows=lineup_stat_rows if article_subtype == "lineup" else None,
        )
        if rule_based_body is not None:
            rule_based_generated = True
            resolved_subtype, body_text = rule_based_body
            _log_rule_based_subtype_skip_gemini(
                logger,
                subtype=resolved_subtype,
                source_url=url,
                input_chars=len(summary_clean or ""),
                output_chars=len(body_text),
            )
            return body_text, ""
        return (
            generate_article_with_gemini(
                title,
                summary_clean,
                effective_generation_category,
                real_reactions=real_reactions_yahoo,
                has_game=has_game,
                source_name=source_name,
                source_day_label=source_day_label,
                source_type=source_type,
                tweet_url=url,
                source_entry=source_entry,
            ),
            "",
        )

    if article_ai_mode == "none":
        real_reactions_yahoo = fetch_fan_reactions_from_yahoo(title, summary_clean, effective_generation_category, source_name=source_name)
        ai_body = ""
        real_reactions = real_reactions_yahoo
        summary_block = ""
        stats_block = ""
        impression_block = ""
    elif article_ai_mode == "gemini":
        real_reactions_yahoo = fetch_fan_reactions_from_yahoo(title, summary_clean, effective_generation_category, source_name=source_name)
        ai_body, rendered_ai_body_html = _generate_gemini_body()
        real_reactions = real_reactions_yahoo
        summary_block = ""
        stats_block = ""
        impression_block = ""
    elif article_ai_mode == "grok":
        ai_body, real_reactions, summary_block, stats_block, impression_block = generate_article_with_grok(title, summary_clean, effective_generation_category, win_loss_hint)
        if not ai_body:
            real_reactions_yahoo = fetch_fan_reactions_from_yahoo(title, summary_clean, effective_generation_category, source_name=source_name)
            ai_body, rendered_ai_body_html = _generate_gemini_body()
            real_reactions = real_reactions_yahoo
            summary_block = ""
            stats_block = ""
            impression_block = ""
    else:
        # 試合あり → Grok（X検索でファンの声取得）、試合なし → Gemini直行（コスト削減）
        if has_game:
            ai_body, real_reactions, summary_block, stats_block, impression_block = generate_article_with_grok(title, summary_clean, effective_generation_category, win_loss_hint)
            if not ai_body:
                real_reactions_yahoo = fetch_fan_reactions_from_yahoo(title, summary_clean, effective_generation_category, source_name=source_name)
                ai_body, rendered_ai_body_html = _generate_gemini_body()
                real_reactions = real_reactions_yahoo
                summary_block = ""
                stats_block = ""
                impression_block = ""
        else:
            real_reactions_yahoo = fetch_fan_reactions_from_yahoo(title, summary_clean, effective_generation_category, source_name=source_name)
            ai_body, rendered_ai_body_html = _generate_gemini_body()
            real_reactions = real_reactions_yahoo
            summary_block = ""
            stats_block = ""
            impression_block = ""

    if duplicate_guard_context and duplicate_guard_context.get("guard_outcome") == "skip":
        return "", ""

    if postgame_strict_review_reason:
        return "", ""

    if manager_quote_zero_review_reason:
        return "", ""

    if not rendered_ai_body_html:
        ai_body = _apply_article_guardrails(title, summary_clean, effective_generation_category, ai_body, has_game, logger)
        if not ai_body:
            logger.warning("記事本文が空のため、安全フォールバック本文を使用")
            ai_body = _build_safe_article_fallback(
                title,
                summary_clean,
                effective_generation_category,
                has_game,
                source_name=source_name,
                source_type=source_type,
                tweet_url=url,
                source_day_label=source_day_label,
                real_reactions=real_reactions,
            )
        subject = _extract_subject_label(title, summary_clean, effective_generation_category)

        def _apply_body_contract_reroll(normalized_body: str, fallback_body: str) -> str:
            if not _body_validator_supports_subtype(article_subtype):
                return normalized_body
            validation = _validate_body_candidate(normalized_body, article_subtype)
            if validation["ok"] or validation["action"] != "reroll":
                return normalized_body
            _log_body_validator_reroll(
                logger,
                source_url=url,
                category=category,
                article_subtype=article_subtype,
                fail_axes=list(validation["fail_axes"]),
                expected_first_block=str(validation.get("expected_first_block") or ""),
                actual_first_block=str(validation.get("actual_first_block") or ""),
                missing_required_blocks=list(validation.get("missing_required_blocks") or []),
                actual_block_order=list(validation.get("actual_block_order") or []),
            )
            rerolled_body = _apply_editor_voice(fallback_body, effective_generation_category, subject)
            return _normalize_article_text_structure(rerolled_body, body_category, has_game, article_subtype=body_subtype)

        if not rule_based_generated:
            ai_body = _apply_editor_voice(ai_body, effective_generation_category, subject)
        if not rule_based_generated and _article_reads_too_generic(ai_body, effective_generation_category):
            logger.info("記事本文が汎用表現に寄りすぎたため、安全版へ差し替え")
            ai_body = _apply_editor_voice(
                _build_safe_article_fallback(
                    title,
                    summary_clean,
                    effective_generation_category,
                    has_game,
                    source_name=source_name,
                    source_type=source_type,
                    tweet_url=url,
                    source_day_label=source_day_label,
                    real_reactions=real_reactions,
                ),
                effective_generation_category,
                subject,
            )
        if social_story:
            normalized_social_body = _normalize_article_text_structure(ai_body, body_category, has_game, article_subtype="social_news")
            if _social_body_has_required_structure(normalized_social_body):
                ai_body = normalized_social_body
            else:
                ai_body = _apply_editor_voice(
                    _build_social_safe_fallback(
                        title,
                        summary_clean,
                        effective_generation_category,
                        source_name=source_name,
                        tweet_url=url,
                        source_day_label=source_day_label,
                        real_reactions=real_reactions,
                    ),
                    effective_generation_category,
                    subject,
                )
        elif generation_category == "首脳陣" and article_subtype == "manager":
            normalized_manager_body = _normalize_article_text_structure(ai_body, generation_category, has_game, article_subtype=article_subtype)
            if _manager_body_has_required_structure(normalized_manager_body, has_game):
                ai_body = normalized_manager_body
            else:
                ai_body = _apply_editor_voice(
                    _build_manager_safe_fallback(title, summary_clean, real_reactions=real_reactions),
                    generation_category,
                    subject,
                )
        elif generation_category == "試合速報" and _is_game_template_subtype(article_subtype):
            normalized_game_body = _normalize_article_text_structure(ai_body, generation_category, has_game, article_subtype=article_subtype)
            game_fallback = _build_game_safe_fallback(
                title,
                summary_clean,
                article_subtype,
                lineup_rows=lineup_stat_rows if article_subtype == "lineup" else None,
                real_reactions=real_reactions,
            )
            if _game_body_has_required_structure(normalized_game_body, article_subtype, has_game):
                ai_body = _apply_body_contract_reroll(normalized_game_body, game_fallback)
            else:
                ai_body = _apply_editor_voice(game_fallback, generation_category, subject)
        elif generation_category == "ドラフト・育成" and _is_farm_template_subtype(article_subtype):
            normalized_farm_body = _normalize_article_text_structure(ai_body, generation_category, has_game, article_subtype=article_subtype)
            farm_fallback = (
                _build_farm_lineup_safe_fallback(title, summary_clean, real_reactions=real_reactions)
                if article_subtype == "farm_lineup"
                else _build_farm_safe_fallback(title, summary_clean, real_reactions=real_reactions)
            )
            if _farm_body_has_required_structure(normalized_farm_body, article_subtype):
                ai_body = _apply_body_contract_reroll(normalized_farm_body, farm_fallback)
            else:
                ai_body = _apply_editor_voice(farm_fallback, generation_category, subject)
        elif article_subtype == "fact_notice":
            normalized_fact_notice_body = _normalize_article_text_structure(ai_body, body_category, has_game, article_subtype=article_subtype)
            ai_body = _apply_body_contract_reroll(
                normalized_fact_notice_body,
                _build_safe_article_fallback(
                    title,
                    summary_clean,
                    effective_generation_category,
                    has_game,
                    source_name=source_name,
                    source_type=source_type,
                    tweet_url=url,
                    source_day_label=source_day_label,
                    real_reactions=real_reactions,
                ),
            )
        elif recovery_story:
            normalized_recovery_body = _normalize_article_text_structure(ai_body, generation_category, False, article_subtype="player_recovery")
            if _recovery_body_has_required_structure(normalized_recovery_body):
                ai_body = normalized_recovery_body
            else:
                ai_body = _apply_editor_voice(
                    _build_recovery_safe_fallback(
                        title,
                        summary_clean,
                        real_reactions=real_reactions,
                        source_day_label=source_day_label,
                    ),
                    generation_category,
                    subject,
                )
        elif notice_story:
            normalized_notice_body = _normalize_article_text_structure(ai_body, generation_category, False, article_subtype="player_notice")
            if _notice_body_has_required_structure(normalized_notice_body) and _notice_has_player_name(normalized_notice_body, title, summary_clean):
                ai_body = normalized_notice_body
            else:
                ai_body = _apply_editor_voice(
                    _build_notice_safe_fallback(
                        title,
                        summary_clean,
                        real_reactions=real_reactions,
                        source_day_label=source_day_label,
                    ),
                    generation_category,
                    subject,
                )
    if summary_block and not _text_is_safe(title, summary_clean, summary_block, has_game):
        logger.warning("SUMMARYブロックを破棄: 事実制約に違反")
        summary_block = ""
    if stats_block and not _text_is_safe(title, summary_clean, stats_block, has_game):
        logger.warning("STATSブロックを破棄: 事実制約に違反")
        stats_block = ""
    if impression_block and not _text_is_safe(title, summary_clean, impression_block, has_game):
        logger.warning("IMPRESSIONブロックを破棄: 事実制約に違反")
        impression_block = ""

    import re as _re3

    def _manager_cta_labels() -> dict[str, str]:
        source_text = f"{title} {summary_clean}"
        if any(keyword in source_text for keyword in ("競争", "レギュラー", "固定", "序列", "若手")):
            return {
                "news": "この競争、どう見る？",
                "next": "次の序列どうなる？",
                "fans": "率直にどう思う？",
            }
        if any(keyword in source_text for keyword in ("スタメン", "打順", "オーダー", "起用")):
            return {
                "news": "この起用、どう見る？",
                "next": "次のスタメンどうする？",
                "fans": "率直にどう思う？",
            }
        if any(keyword in source_text for keyword in ("継投", "采配", "ベンチ", "勝負手", "代打", "守備固め")):
            return {
                "news": "この采配、どう見る？",
                "next": "次はどう動く？",
                "fans": "率直にどう思う？",
            }
        return {
            "news": "この発言、どう見る？",
            "next": "次はどう動く？",
            "fans": "率直にどう思う？",
        }

    cta_enabled = article_subtype != "fact_notice"  # 訂正記事で議論喚起を避けるため。

    def _comment_button(slot: str = "fans") -> str:
        labels = {
            "news": "このニュース、どう見る？",
            "next": "先に予想を書く？",
            "fans": "みんなの本音は？",
        }
        if category == "試合速報" and article_subtype == "postgame":
            labels = {
                "news": "この試合、どう見る？",
                "next": "勝負の分岐点は？",
                "fans": "今日のMVPは？",
            }
        elif category == "首脳陣":
            labels = _manager_cta_labels()
        elif recovery_story:
            labels = {
                "news": "この復帰状況どう見る？",
                "next": "復帰時期どうなる？",
                "fans": "率直にどう思う？",
            }
        elif notice_story:
            labels = {
                "news": "この公示、どう見る？",
                "next": "次の起用どうなる？",
                "fans": "率直にどう思う？",
            }
        label = labels.get(slot, labels["fans"])
        if slot in {"news", "next"}:
            return (
                f'<!-- wp:buttons {{"layout":{{"type":"flex","justifyContent":"center"}}}} -->\n'
                f'<div class="wp-block-buttons" style="margin:12px 0 14px;">\n'
                f'<!-- wp:button {{"className":"is-style-outline"}} -->\n'
                f'<div class="wp-block-button is-style-outline"><a class="wp-block-button__link wp-element-button" href="#respond" style="font-size:0.96em;padding:12px 18px;line-height:1.35;font-weight:700;color:#F5811F;border-color:#F5811F;border-width:2px;border-style:solid;border-radius:999px;">💬 {label}</a></div>\n'
                f'<!-- /wp:button -->\n'
                f'</div>\n'
                f'<!-- /wp:buttons -->\n\n'
            )
        return (
            f'<!-- wp:buttons {{"layout":{{"type":"flex","justifyContent":"center"}}}} -->\n'
            f'<div class="wp-block-buttons" style="margin:16px 0 4px;">\n'
            f'<!-- wp:button -->\n'
            f'<div class="wp-block-button"><a class="wp-block-button__link wp-element-button" href="#respond" style="background-color:#F5811F;color:#fff;font-size:1.06em;padding:15px 26px;line-height:1.35;font-weight:700;border-radius:999px;">💬 {label}</a></div>\n'
            f'<!-- /wp:button -->\n'
            f'</div>\n'
            f'<!-- /wp:buttons -->\n\n'
        )

    def _x_card(reaction: str) -> str:
        """@handle: text 形式をXカード風HTML blockに変換。"""
        handle = _reaction_handle(reaction)
        text = _reaction_body_text(reaction)
        initials = handle[1:3].upper() if len(handle) > 1 else "X"
        safe_text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        safe_handle = handle.replace("&", "&amp;")
        display_name = handle.lstrip("@")
        if display_name.startswith("x_user_"):
            suffix = display_name.split("_")[-1]
            display_name = f"Xユーザー{suffix}"
        elif display_name == "x_user":
            display_name = "Xユーザー"
        colors = ["#e8272a", "#001e62", "#c9a227", "#e8272a", "#001e62"]
        color = colors[hash(handle) % len(colors)]
        return (
            f'<!-- wp:html -->\n'
            f'<div style="border:1px solid #cfd9de;border-radius:12px;padding:16px;margin:8px 0;background:#fff;">'
            f'<div style="display:flex;align-items:center;margin-bottom:10px;">'
            f'<div style="width:40px;height:40px;border-radius:50%;background:{color};color:#fff;display:flex;align-items:center;justify-content:center;font-weight:bold;font-size:0.9em;margin-right:10px;flex-shrink:0;">{initials}</div>'
            f'<div style="flex:1;min-width:0;">'
            f'<div style="font-weight:bold;font-size:0.9em;">{display_name}</div>'
            f'<div style="color:#536471;font-size:0.8em;">{safe_handle}</div>'
            f'</div>'
            f'<div style="color:#000;font-weight:900;font-size:1.1em;">𝕏</div>'
            f'</div>'
            f'<p style="margin:0;font-size:0.92em;line-height:1.7;">{safe_text}</p>'
            f'</div>\n'
            f'<!-- /wp:html -->\n\n'
        )

    def _sep():
        return (
            f'<!-- wp:separator -->\n'
            f'<hr class="wp-block-separator has-alpha-channel-opacity"/>\n'
            f'<!-- /wp:separator -->\n\n'
        )

    def _para(text: str) -> str:
        safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return (
            f'<!-- wp:paragraph -->\n<p>{safe}</p>\n<!-- /wp:paragraph -->\n\n'
            f'<!-- wp:spacer {{"height":"8px"}} -->\n'
            f'<div style="height:8px" aria-hidden="true" class="wp-block-spacer"></div>\n'
            f'<!-- /wp:spacer -->\n\n'
        )

    def _lineup_stats_block(rows: list[dict]) -> str:
        if not rows:
            return ""
        header = (
            '<!-- wp:heading {"level":3} -->\n'
            '<h3>📊 今日のスタメンデータ</h3>\n'
            '<!-- /wp:heading -->\n\n'
        )
        note = (
            '<!-- wp:paragraph -->\n'
            '<p style="font-size:0.82em;color:#666;">※スポーツナビ掲載の今季成績（打率 / 本塁打 / 打点 / 盗塁）</p>\n'
            '<!-- /wp:paragraph -->\n\n'
        )
        table_rows = [
            "<tr><th>打順</th><th>位置</th><th>選手名</th><th>打率</th><th>本塁打</th><th>打点</th><th>盗塁</th></tr>"
        ]
        for row in rows:
            order = str(row.get("order", "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            position = str(row.get("position", "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            name = str(row.get("name", "")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            avg = str(row.get("avg", "-")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            hr = str(row.get("hr", "-")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            rbi = str(row.get("rbi", "-")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            sb = str(row.get("sb", "-")).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            table_rows.append(
                "<tr>"
                f"<td>{order}</td>"
                f"<td>{position}</td>"
                f"<td>{name}</td>"
                f"<td>{avg}</td>"
                f"<td>{hr}</td>"
                f"<td>{rbi}</td>"
                f"<td>{sb}</td>"
                "</tr>"
            )
        table_html = (
            '<!-- wp:html -->\n'
            '<div class="yoshilover-lineup-stats" style="overflow-x:auto;margin:0 0 12px;">'
            '<table style="width:100%;border-collapse:collapse;font-size:0.92em;">'
            f"{''.join(table_rows)}"
            "</table>"
            "</div>\n"
            '<!-- /wp:html -->\n\n'
        )
        return header + note + table_html

    def _lineup_watch_block(rows: list[dict]) -> str:
        if not rows:
            return ""

        def _row_by_order(order: str) -> dict:
            for row in rows:
                if str(row.get("order", "")) == order:
                    return row
            return {}

        leadoff = _row_by_order("1")
        second = _row_by_order("2")
        cleanup = _row_by_order("4")
        catcher = next((row for row in rows if row.get("position") == "捕"), {})
        ninth = _row_by_order("9")

        points = []
        if leadoff and cleanup:
            points.append(
                f"{leadoff['order']}番{leadoff['name']}から{cleanup['order']}番{cleanup['name']}までの流れ。"
            )
        elif leadoff:
            points.append(f"{leadoff['order']}番{leadoff['name']}がどう出塁するか。")
        else:
            points.append("上位打線が序盤にどう形を作るか。")

        if second and cleanup:
            points.append(
                f"{second['order']}番{second['name']}がつなぎ、{cleanup['order']}番{cleanup['name']}で返せるか。"
            )
        elif cleanup:
            points.append(f"{cleanup['order']}番{cleanup['name']}がどこで走者を返せるか。")
        else:
            points.append("中軸で長打と打点が出るか。")

        if catcher:
            points.append(f"捕手{catcher['name']}を含めた下位打線の入り。")
        elif ninth:
            points.append(f"{ninth['order']}番{ninth['name']}から上位へ戻せるか。")
        else:
            points.append("下位打線から上位へどう戻すか。")

        return (
            '<!-- wp:heading {"level":3} -->\n'
            '<h3>👀 スタメンの見どころ</h3>\n'
            '<!-- /wp:heading -->\n\n'
            + '<!-- wp:list -->\n'
            + '<ul class="wp-block-list">\n'
            + "".join(f"<li>{point}</li>\n" for point in points[:3])
            + '</ul>\n'
            + '<!-- /wp:list -->\n\n'
        )

    def _postgame_score_token() -> str:
        score_match = _re3.search(r'(\d{1,2})[－\-–](\d{1,2})', f"{title} {summary_clean}")
        if not score_match:
            return ""
        return f"{score_match.group(1)}-{score_match.group(2)}"

    def _livegame_state_label() -> str:
        state_match = _re3.search(r'(\d+回[表裏]?)', f"{title} {summary_clean}")
        return state_match.group(1) if state_match else "途中経過"

    def _livegame_result_label() -> str:
        source_text = f"{title} {summary_clean}"
        if "逆転" in source_text:
            return "逆転"
        if "勝ち越し" in source_text:
            return "勝ち越し"
        if "同点" in source_text:
            return "同点"
        return "途中経過"

    def _postgame_result_label() -> str:
        source_text = f"{title} {summary_clean}"
        if "引き分け" in source_text:
            return "引き分け"
        if any(marker in source_text for marker in ("勝利", "白星", "サヨナラ勝", "連勝", "完封勝")):
            return "巨人勝利"
        if any(marker in source_text for marker in ("敗れ", "敗戦", "黒星", "連敗", "完封負")):
            return "巨人敗戦"
        return "結果確認中"

    def _postgame_opponent_label() -> str:
        source_text = f"{title} {summary_clean}"
        for marker in NPB_TEAM_MARKERS:
            if marker in {"巨人", "読売ジャイアンツ"}:
                continue
            if marker in source_text:
                return marker
        return "相手"

    def _postgame_key_play() -> str:
        facts = _extract_summary_sentences(summary_clean, max_sentences=4)
        for fact in facts[1:]:
            clean = fact.strip().rstrip("。")
            if clean:
                return clean[:36]
        stripped_title = _strip_title_prefix(title)
        stripped_title = _re3.sub(r'^【巨人】', '', stripped_title).strip()
        stripped_title = _re3.sub(r'^\S+に\d{1,2}[－\-–]\d{1,2}で(?:勝利|敗れ)[　 ]*', '', stripped_title).strip("　 。")
        return (stripped_title or "流れを分けたポイント").strip()[:36]

    def _postgame_result_block() -> str:
        score = _postgame_score_token()
        if not score and article_subtype != "postgame":
            return ""

        result = _postgame_result_label()
        opponent = _postgame_opponent_label()
        key_play = _postgame_key_play()
        items = [
            ("結果", result),
            ("スコア", score or "-"),
            ("相手", opponent),
            ("決め手", key_play),
        ]
        rows_html = "".join(
            '<div style="display:grid;grid-template-columns:80px 1fr;gap:10px;padding:10px 0;border-bottom:1px solid #e6e6e6;">'
            f'<div style="font-size:0.84em;color:#666;font-weight:700;">{label}</div>'
            f'<div style="font-size:0.95em;color:#111;font-weight:700;line-height:1.5;">{value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")}</div>'
            '</div>'
            for label, value in items
        )
        return (
            '<!-- wp:heading {"level":3} -->\n'
            '<h3>📊 今日の試合結果</h3>\n'
            '<!-- /wp:heading -->\n\n'
            '<!-- wp:html -->\n'
            '<div class="yoshilover-postgame-summary" style="border:1px solid #e6e6e6;border-radius:12px;padding:12px 16px;margin:0 0 12px;background:#fff;">'
            f'{rows_html}'
            '</div>\n'
            '<!-- /wp:html -->\n\n'
        )

    def _postgame_watch_block() -> str:
        facts = _extract_summary_sentences(summary_clean, max_sentences=4)
        points = []
        score = _postgame_score_token()
        result = _postgame_result_label()

        for fact in facts[1:]:
            clean = fact.strip().rstrip("。")
            if clean:
                points.append(f"{clean}。")

        if score and result == "巨人勝利":
            points.append(f"{score}をどう勝ち切ったか。")
        elif score and result == "巨人敗戦":
            points.append(f"{score}で落とした終盤の流れ。")
        elif score and result == "引き分け":
            points.append(f"{score}で並走した終盤の流れ。")

        points.append("得点の前後でベンチがどう動いたか。")
        points.append("この内容が次戦にも続くか。")

        deduped = []
        for point in points:
            normalized = point.strip()
            if not normalized or normalized in deduped:
                continue
            deduped.append(normalized)

        return (
            '<!-- wp:heading {"level":3} -->\n'
            '<h3>👀 勝負の分岐点</h3>\n'
            '<!-- /wp:heading -->\n\n'
            + '<!-- wp:list -->\n'
            + '<ul class="wp-block-list">\n'
            + "".join(f"<li>{point.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')}</li>\n" for point in deduped[:3])
            + '</ul>\n'
            + '<!-- /wp:list -->\n\n'
        )

    def _livegame_result_block() -> str:
        score = _postgame_score_token()
        if not score and article_subtype != "live_update":
            return ""

        items = [
            ("現在", _livegame_state_label()),
            ("スコア", score or "-"),
            ("流れ", _livegame_result_label()),
            ("相手", _postgame_opponent_label()),
        ]
        rows_html = "".join(
            '<div style="display:grid;grid-template-columns:80px 1fr;gap:10px;padding:10px 0;border-bottom:1px solid #e6e6e6;">'
            f'<div style="font-size:0.84em;color:#666;font-weight:700;">{label}</div>'
            f'<div style="font-size:0.95em;color:#111;font-weight:700;line-height:1.5;">{value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")}</div>'
            '</div>'
            for label, value in items
        )
        return (
            '<!-- wp:heading {"level":3} -->\n'
            '<h3>📊 現在の試合状況</h3>\n'
            '<!-- /wp:heading -->\n\n'
            '<!-- wp:html -->\n'
            '<div class="yoshilover-livegame-summary" style="border:1px solid #e6e6e6;border-radius:12px;padding:12px 16px;margin:0 0 12px;background:#fff;">'
            f'{rows_html}'
            '</div>\n'
            '<!-- /wp:html -->\n\n'
        )

    def _livegame_watch_block() -> str:
        points = []
        state = _livegame_state_label()
        flow = _livegame_result_label()
        score = _postgame_score_token()
        facts = _extract_summary_sentences(summary_clean, max_sentences=4)

        if state:
            points.append(f"{state}の時点で、いまの流れをどう見るか。")
        if flow == "逆転":
            points.append("逆転の前後で何が変わったか。")
        elif flow == "勝ち越し":
            points.append("勝ち越し点のあと、ベンチがどう守り切るか。")
        elif flow == "同点":
            points.append("同点に追いついた後の次の1点。")
        if score:
            points.append(f"{score}のまま終盤へ入るのか、それとも次に動くのか。")
        for fact in facts[1:]:
            clean = fact.strip().rstrip("。")
            if clean:
                points.append(f"{clean}。")
        points.append("ここから継投や代打をどう切るか。")

        deduped = []
        for point in points:
            normalized = point.strip()
            if not normalized or normalized in deduped:
                continue
            deduped.append(normalized)

        return (
            '<!-- wp:heading {"level":3} -->\n'
            '<h3>👀 ここまでの見どころ</h3>\n'
            '<!-- /wp:heading -->\n\n'
            + '<!-- wp:list -->\n'
            + '<ul class="wp-block-list">\n'
            + "".join(f"<li>{point.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')}</li>\n" for point in deduped[:3])
            + '</ul>\n'
            + '<!-- /wp:list -->\n\n'
        )

    blocks = ""

    # ──────────────────────────────────────────────────────────
    # ① 記事の要約（タイトル付き）
    # ──────────────────────────────────────────────────────────
    summary_text_to_show = summary_block if summary_block else _build_safe_summary_snippet(title, summary_clean)
    safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    display_source_links = [
        {
            **item,
            "name": _display_source_name(item.get("name") or "スポーツニュース"),
        }
        for item in (source_links or [{"name": source_name or "スポーツニュース", "url": url}])
    ]
    source_badge = " / ".join(
        (item.get("name") or "スポーツニュース").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        for item in display_source_links[:3]
    )
    safe_source = source_badge if source_badge else "スポーツニュース"
    summary_kicker = _summary_kicker(category)
    blocks += (
        f'<!-- wp:html -->\n'
        f'<div style="background:linear-gradient(135deg,#001e62 0%,#e8272a 100%);border-radius:10px;padding:18px 20px;margin:0 0 4px 0;">'
          f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
            f'<span style="background:rgba(255,255,255,0.2);color:#fff;font-size:0.78em;font-weight:800;padding:4px 10px;border-radius:20px;letter-spacing:0.05em;">📰 {safe_source}</span>'
            f'<span style="color:rgba(255,255,255,0.82);font-size:0.72em;font-weight:700;letter-spacing:0.08em;">⚾ {summary_kicker}</span>'
          f'</div>'
          f'<div style="color:#fff;font-size:1.1em;font-weight:900;line-height:1.4;">{safe_title}</div>'
        f'</div>\n'
        f'<!-- /wp:html -->\n\n'
    )
    blocks += _para(summary_text_to_show) + _sep()

    if media_quotes:
        media_section_label = (media_quotes[0].get("section_label") or "📌 関連ポスト").strip()
        blocks += (
            '<!-- wp:heading {"level":3} -->\n'
            f'<h3>{media_section_label}</h3>\n'
            '<!-- /wp:heading -->\n\n'
        )
        widget_script_included = False
        display_media_quotes = media_quotes[:2]
        for index, media_quote in enumerate(display_media_quotes, start=1):
            media_url = (media_quote.get("url") or "").strip()
            if not media_url:
                continue
            if len(display_media_quotes) > 1:
                source_label = (
                    (media_quote.get("source_name") or "").strip()
                    or (media_quote.get("quote_account") or "").strip()
                    or (media_quote.get("handle") or "").strip()
                )
                if source_label:
                    safe_source_label = source_label.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                    blocks += (
                        '<!-- wp:html -->\n'
                        f'<div class="yoshilover-media-quote-source" style="font-size:0.78em;color:#666;font-weight:700;margin:0 0 8px;">{index}. {safe_source_label}</div>\n'
                        '<!-- /wp:html -->\n\n'
                    )
            blocks += build_oembed_block(
                media_url,
                compact=False,
                include_script=not widget_script_included,
            ) + "\n\n"
            widget_script_included = True
        blocks += _sep()

    # ──────────────────────────────────────────────────────────
    # ② 記事本文（ニュースの整理を最上段にする）
    # ──────────────────────────────────────────────────────────
    if rendered_ai_body_html:
        blocks += rendered_ai_body_html
        if cta_enabled:
            blocks += _comment_button("news")
            blocks += _comment_button("next")
    elif ai_body:
        ai_body = _re3.sub(r'\[\[\d+\]\]\([^)]+\)', '', ai_body)
        ai_body = _re3.sub(r'（\d+文字）', '', ai_body)
        first_line = ai_body.strip().split('\n')[0].strip()
        first_line_is_structured_heading = False
        if body_category == "首脳陣" and article_subtype == "manager":
            first_line_is_structured_heading = first_line in MANAGER_REQUIRED_HEADINGS
        elif body_category == "試合速報" and _is_game_template_subtype(article_subtype):
            first_line_is_structured_heading = first_line in _game_required_headings(article_subtype)
        elif body_category == "ドラフト・育成" and _is_farm_template_subtype(article_subtype):
            first_line_is_structured_heading = first_line in _farm_required_headings(article_subtype)
        elif notice_story:
            first_line_is_structured_heading = first_line in NOTICE_REQUIRED_HEADINGS
        elif recovery_story:
            first_line_is_structured_heading = first_line in RECOVERY_REQUIRED_HEADINGS
        elif body_subtype == "social_news":
            first_line_is_structured_heading = first_line in SOCIAL_REQUIRED_HEADINGS
        first_line_looks_like_heading = first_line.startswith("【") or first_line.startswith("■") or first_line.startswith("▶")
        clean_title = _re3.sub(r'[【】\s]', '', title)
        clean_first = _re3.sub(r'[【】\s]', '', first_line)
        if not first_line_is_structured_heading and clean_title and clean_first and (clean_title in clean_first or clean_first in clean_title):
            ai_body = '\n'.join(ai_body.strip().split('\n')[1:]).strip()
        ai_body = _re3.sub(r'.*ファンの声.*\n?', '', ai_body)
        ai_body = _re3.sub(r'.*Xより.*\n?', '', ai_body)
        ai_body = _normalize_article_text_structure(ai_body, body_category, has_game, article_subtype=body_subtype)
        render_lines = [p.strip() for p in ai_body.split("\n") if p.strip()]

        def _normalize_rendered_opening(value: str) -> str:
            normalized = _strip_html(value or "")
            normalized = _re3.sub(r"[【】「」『』（）()\s]", "", normalized)
            return normalized.strip("。・")

        summary_signature = _normalize_rendered_opening(summary_text_to_show)
        if summary_signature and (first_line_is_structured_heading or first_line_looks_like_heading):
            deduped_render_lines = []
            section_index = 0
            for line in render_lines:
                if line.startswith("【") or line.startswith("■") or line.startswith("▶"):
                    section_index += 1
                    deduped_render_lines.append(line)
                    continue
                if section_index >= 1 and _normalize_rendered_opening(line) == summary_signature:
                    continue
                deduped_render_lines.append(line)
            render_lines = deduped_render_lines

        para_count = 0
        seen_headings = set()
        current_heading = ""
        current_paragraphs = []
        rendered_cta_slots = set()

        def _render_paragraph_with_media(text: str) -> str:
            nonlocal para_count
            rendered = _para(text)
            para_count += 1
            return rendered

        def _flush_section() -> None:
            nonlocal blocks, current_heading, current_paragraphs, lineup_stats_rendered
            if not current_heading and not current_paragraphs:
                return
            if current_heading:
                heading_level = 3
                if body_category == "首脳陣" and article_subtype == "manager" and current_heading == "【発言の要旨】":
                    heading_level = 2
                if body_category == "試合速報" and _is_game_template_subtype(article_subtype) and current_heading == _game_required_headings(article_subtype)[0]:
                    heading_level = 2
                if body_category == "ドラフト・育成" and _is_farm_template_subtype(article_subtype) and current_heading == _farm_required_headings(article_subtype)[0]:
                    heading_level = 2
                if notice_story and current_heading == NOTICE_REQUIRED_HEADINGS[0]:
                    heading_level = 2
                if recovery_story and current_heading == RECOVERY_REQUIRED_HEADINGS[0]:
                    heading_level = 2
                if body_subtype == "social_news" and current_heading == SOCIAL_REQUIRED_HEADINGS[0]:
                    heading_level = 2
                blocks += (
                    f'<!-- wp:heading {{"level":{heading_level}}} -->\n'
                    f'<h{heading_level}>{current_heading}</h{heading_level}>\n'
                    f'<!-- /wp:heading -->\n\n'
                )
            for paragraph in current_paragraphs:
                blocks += _render_paragraph_with_media(paragraph)
            if (
                current_heading == ("【試合概要】" if article_subtype == "lineup" else "【ニュースの整理】")
                and body_category == "試合速報"
                and article_subtype == "lineup"
                and lineup_stat_rows
                and not lineup_stats_rendered
            ):
                blocks += _lineup_stats_block(lineup_stat_rows)
                blocks += _lineup_watch_block(lineup_stat_rows)
                lineup_stats_rendered = True
            if (
                current_heading == "【ニュースの整理】"
                and body_category == "試合速報"
                and article_subtype == "live_update"
            ):
                blocks += _livegame_result_block()
                blocks += _livegame_watch_block()
            if (
                current_heading == "【試合結果】"
                and body_category == "試合速報"
                and article_subtype == "postgame"
            ):
                blocks += _postgame_result_block()
                blocks += _postgame_watch_block()
            game_slot_map = {}
            if article_subtype == "lineup":
                game_slot_map = {"【試合概要】": "news", "【注目ポイント】": "next"}
            elif article_subtype == "live_anchor":
                game_slot_map = {"【時点】": "news", "【ファン視点】": "next"}
            elif article_subtype == "postgame":
                game_slot_map = {"【試合結果】": "news", "【試合展開】": "next"}
            elif article_subtype == "pregame":
                game_slot_map = {"【変更情報の要旨】": "news", "【この変更が意味すること】": "next"}
            farm_slot_map = {}
            if article_subtype == "farm":
                farm_slot_map = {"【二軍結果・活躍の要旨】": "news", "【一軍への示唆】": "next"}
            elif article_subtype == "farm_lineup":
                farm_slot_map = {"【二軍試合概要】": "news", "【注目選手】": "next"}
            social_slot_map = {}
            if body_subtype == "social_news":
                social_slot_map = {"【話題の要旨】": "news", "【ファンの関心ポイント】": "next"}
            section_slot = {
                "【ニュースの整理】": "news",
                "【次の注目】": "next",
                "【故障・復帰の要旨】": "news",
                "【チームへの影響と今後の注目点】": "next",
                "【公示の要旨】": "news",
                "【今後の注目点】": "next",
                **game_slot_map,
                **farm_slot_map,
                **social_slot_map,
            }.get(current_heading)
            if cta_enabled and section_slot:
                blocks += _comment_button(section_slot)
                rendered_cta_slots.add(section_slot)
            current_paragraphs = []

        for p in render_lines:
            if p.startswith("【") or p.startswith("■") or p.startswith("▶"):
                heading_text = _normalize_article_heading(p, body_category, has_game, article_subtype=body_subtype)
                if heading_text in seen_headings:
                    continue
                _flush_section()
                seen_headings.add(heading_text)
                current_heading = heading_text
            elif "コメント" in p and ("意見" in p or "教えてください" in p):
                continue
            else:
                current_paragraphs.append(p)

        _flush_section()
        if cta_enabled and "news" not in rendered_cta_slots:
            blocks += _comment_button("news")
        if cta_enabled and "next" not in rendered_cta_slots:
            blocks += _comment_button("next")
    related_posts = _find_related_posts_for_article(
        title=title,
        summary=summary_clean,
        category=category,
        article_subtype=body_subtype,
        current_url=url,
        has_game=has_game,
    )
    related_posts_section = _build_related_posts_section(related_posts)

    followup_section_rendered = False

    # ──────────────────────────────────────────────────────────
    # ③ 今日の記録（本文の後）
    # ──────────────────────────────────────────────────────────
    if stats_block:
        blocks += _sep()
        blocks += (
            f'<!-- wp:heading {{"level":3}} -->\n'
            f'<h3>📊 今日の記録</h3>\n'
            f'<!-- /wp:heading -->\n\n'
        )
        stat_items = [l.lstrip("・").strip() for l in stats_block.split("\n") if l.strip() and len(l.strip()) > 3]
        if stat_items:
            li_html = "\n".join(f"<li>{s.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;')}</li>" for s in stat_items)
            blocks += f'<!-- wp:list -->\n<ul class="wp-block-list">\n{li_html}\n</ul>\n<!-- /wp:list -->\n\n'
        blocks += _sep()
        followup_section_rendered = True

    if lineup_stat_rows and not lineup_stats_rendered:
        if not followup_section_rendered:
            blocks += _sep()
        blocks += _lineup_stats_block(lineup_stat_rows)
        blocks += _lineup_watch_block(lineup_stat_rows)
        followup_section_rendered = True

    # ──────────────────────────────────────────────────────────
    # ④ ファンの声（Xカード 最大fan_reaction_limit件）
    # ──────────────────────────────────────────────────────────
    if real_reactions:
        if not followup_section_rendered:
            blocks += _sep()
        blocks += (
            f'<!-- wp:heading {{"level":3}} -->\n'
            f'<h3>💬 ファンの声（Xより）</h3>\n'
            f'<!-- /wp:heading -->\n\n'
        )
        widget_script_included = False
        for reaction in real_reactions[:fan_reaction_limit]:
            reaction_url = _reaction_url(reaction)
            if reaction_url:
                blocks += build_oembed_block(
                    reaction_url,
                    compact=True,
                    include_script=not widget_script_included,
                ) + "\n\n"
                widget_script_included = True
            else:
                blocks += _x_card(reaction)
        followup_section_rendered = True

    # ──────────────────────────────────────────────────────────
    # ⑤ 感想（約300文字）
    # ──────────────────────────────────────────────────────────
    if impression_block:
        if not followup_section_rendered:
            blocks += _sep()
        blocks += (
            f'<!-- wp:heading {{"level":3}} -->\n'
            f'<h3>⚾ 今日の感想</h3>\n'
            f'<!-- /wp:heading -->\n\n'
            + _para(impression_block)
        )
        followup_section_rendered = True

    if related_posts_section:
        if not followup_section_rendered:
            blocks += _sep()
        blocks += related_posts_section
        followup_section_rendered = True

    if not followup_section_rendered:
        blocks += _sep()
    if cta_enabled:
        blocks += _comment_button("fans")

    # ⑥ 出典
    blocks += _sep()
    source_link_html = " / ".join(
        f'<a href="{(item.get("url") or url).replace("&", "&amp;")}" target="_blank" rel="noopener noreferrer">{(item.get("name") or "スポーツニュース").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")}</a>'
        for item in display_source_links
    )
    blocks += (
        f'<!-- wp:paragraph -->\n'
        f'<p style="font-size:0.8em;color:#999;">'
        f'📰 参照元: {source_link_html}'
        f'</p>\n'
        f'<!-- /wp:paragraph -->'
    )
    return blocks, ai_body

# ──────────────────────────────────────────────────────────
# 設定
# ──────────────────────────────────────────────────────────
RSS_SOURCES_FILE  = ROOT / "config" / "rss_sources.json"
KEYWORDS_FILE     = ROOT / "config" / "keywords.json"
GIANTS_ROSTER_FILE = ROOT / "config" / "giants_roster.json"
HISTORY_FILE      = ROOT / "data"   / "rss_history.json"
GCS_BUCKET        = os.environ.get("GCS_BUCKET", "")
GCS_HISTORY_KEY   = "rss_history.json"
LOG_FILE          = ROOT / "logs"   / "rss_fetcher.log"

GIANTS_KEYWORDS = [
    "巨人",
    "ジャイアンツ",
    "読売ジャイアンツ",
    "東京ドーム",
    "Giants",
    "GIANTS",
    "TokyoGiants",
    "Tokyo Giants",
    "yomiurigiants",
    "YOMIURIGIANTS",
    "#yomiurigiants",
    "#YOMIURIGIANTS",
    "#GIANTS",
    "#巨人ファン",
]
GIANTS_TRANSFER_CONTEXT_MARKERS = (
    "FA",
    "トレード",
    "移籍",
    "獲得",
    "補強",
    "退団",
    "入団",
    "加入",
    "自由契約",
    "人的補償",
    "戦力外",
)
NON_GIANTS_TEAM_MARKERS = tuple(marker for marker in NPB_TEAM_MARKERS if marker != "巨人")

# ──────────────────────────────────────────────────────────
# ロガー設定
# ──────────────────────────────────────────────────────────
def setup_logger():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("rss_fetcher")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = logging.FileHandler(LOG_FILE, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger

# ──────────────────────────────────────────────────────────
# 履歴管理（GCS対応：Cloud Runでも永続化）
# ──────────────────────────────────────────────────────────
def _gcs_client():
    try:
        from google.cloud import storage
        return storage.Client()
    except Exception:
        return None


def _load_gcs_history_with_generation():
    client = _gcs_client()
    if not client:
        return None, None

    bucket = client.bucket(GCS_BUCKET)
    blob = bucket.blob(GCS_HISTORY_KEY)
    if not blob.exists():
        return {}, 0

    blob.reload()
    generation = int(blob.generation or 0)
    data = blob.download_as_text(encoding="utf-8")
    return json.loads(data), generation

def load_history() -> dict:
    if GCS_BUCKET:
        try:
            history, _generation = _load_gcs_history_with_generation()
            if history is not None:
                return history
        except Exception as e:
            logging.getLogger("rss_fetcher").warning(f"GCS load失敗、ローカルにフォールバック: {e}")
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def persist_history(history: dict):
    data = json.dumps(history, ensure_ascii=False, indent=2)
    if GCS_BUCKET:
        try:
            from google.api_core.exceptions import PreconditionFailed

            for _ in range(4):
                remote_history, generation = _load_gcs_history_with_generation()
                if remote_history is None:
                    break

                merged_history = dict(remote_history)
                merged_history.update(history)
                payload = json.dumps(merged_history, ensure_ascii=False, indent=2)

                client = _gcs_client()
                if not client:
                    break
                bucket = client.bucket(GCS_BUCKET)
                blob = bucket.blob(GCS_HISTORY_KEY)
                precondition = generation if generation else 0
                try:
                    blob.upload_from_string(
                        payload,
                        content_type="application/json",
                        if_generation_match=precondition,
                    )
                    history.clear()
                    history.update(merged_history)
                    return
                except PreconditionFailed:
                    logging.getLogger("rss_fetcher").warning("GCS history 競合検知: 再試行します")
                    continue
        except Exception as e:
            logging.getLogger("rss_fetcher").warning(f"GCS save失敗、ローカルにフォールバック: {e}")
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        f.write(data)


def save_history(url: str, history: dict, title_norm: str = ""):
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    history[url] = now_str
    if title_norm and len(title_norm) > 5:
        history[f"title_norm:{title_norm[:60]}"] = now_str
    persist_history(history)


def finalize_post_publication(
    wp: WPClient,
    post_id: int,
    post_url: str,
    history: dict,
    entry_title_norm: str,
    logger: logging.Logger,
    draft_only: bool = False,
) -> bool:
    if draft_only:
        logger.info(f"  [下書き止め] post_id={post_id}")
        return False

    wp.update_post_status(post_id, "publish")
    save_history(post_url, history, entry_title_norm)
    return True


def save_history_batch(urls: list[str], history: dict, title_norms: list[str] | None = None):
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    for url in _dedupe_preserve_order([u for u in urls if u]):
        history[url] = now_str
    for title_norm in _dedupe_preserve_order(title_norms or []):
        if title_norm and len(title_norm) > 5:
            history[f"title_norm:{title_norm[:60]}"] = now_str
    persist_history(history)


def _normalize_history_title(title: str) -> str:
    import re as _re3

    return _re3.sub(r"[\s　【】「」『』〔〕（）()・\-_]", "", (title or "")).lower()


def _normalize_title_for_dedupe(title: str) -> str:
    import re as _re3
    import unicodedata

    if not title:
        return ""
    normalized = unicodedata.normalize("NFKC", str(title).strip())
    normalized = _re3.sub(r"[\s　,.、。!?！？「」『』【】<>＜＞・…\"'“”‘’]+", " ", normalized)
    return normalized.strip().lower()


def _normalize_duplicate_subject(subject: str) -> str:
    normalized = _normalize_title_for_dedupe(subject)
    return normalized.replace(" ", "")


def _normalize_duplicate_canonical_url(url: str | None) -> str:
    from urllib.parse import urlparse, urlunparse

    raw = _html.unescape(str(url or "")).strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
    except Exception:
        return raw.lower()
    if not parsed.scheme or not parsed.netloc:
        return raw.lower()
    cleaned = parsed._replace(
        scheme=parsed.scheme.lower(),
        netloc=parsed.netloc.lower(),
        fragment="",
    )
    return urlunparse(cleaned)


def _extract_source_family(source_url: str) -> str:
    from urllib.parse import urlparse

    raw = _html.unescape(str(source_url or "")).strip()
    if not raw:
        return "unknown"
    family = _source_trust_classify_url_family(raw)
    if family and family != "unknown":
        return str(family)
    try:
        host = urlparse(raw).netloc.lower()
    except Exception:
        return "unknown"
    return host or "unknown"


def _duplicate_source_family_priority(family: str) -> int:
    normalized = str(family or "").strip()
    explicit = {
        "giants_official": 0,
        "npb_official": 0,
        "yomiuri_online": 1,
        "hochi": 2,
        "nikkansports": 2,
        "sponichi": 2,
        "sanspo": 2,
        "daily": 2,
        "yahoo_news_aggregator": 3,
    }
    if normalized in explicit:
        return explicit[normalized]
    trust_level = _source_trust_get_family_trust_level(normalized)
    if trust_level == "high":
        return 0
    if trust_level == "mid-high":
        return 1
    if trust_level == "mid":
        return 2
    return 4


def _is_first_tier_duplicate_family(family: str) -> bool:
    normalized = str(family or "").strip()
    if not normalized or normalized == "yahoo_news_aggregator":
        return False
    return _duplicate_source_family_priority(normalized) <= 2


def _hash_duplicate_guard_value(value: str | None) -> str:
    import hashlib

    raw = str(value or "").strip()
    if not raw:
        return ""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _extract_duplicate_game_id(source_url: str, explicit_game_id: str = "") -> str:
    explicit = str(explicit_game_id or "").strip()
    if explicit:
        return explicit
    match = _re.search(r"/game/([0-9]{8,})/", str(source_url or ""))
    if match:
        return match.group(1)
    return ""


def _extract_entry_canonical_url(entry: dict | None) -> str:
    if not isinstance(entry, dict):
        return ""
    for key in ("canonical_url", "canonical", "resolved_url", "original_url", "feedburner_origlink"):
        value = _normalize_duplicate_canonical_url(entry.get(key))
        if value:
            return value
    for link in entry.get("links") or []:
        if not isinstance(link, dict):
            continue
        rel = str(link.get("rel") or "").strip().lower()
        href = _normalize_duplicate_canonical_url(link.get("href") or link.get("url"))
        if rel == "canonical" and href:
            return href
    return ""


def _extract_duplicate_player(title: str, summary: str, category: str) -> str:
    if category == "選手情報":
        return _normalize_duplicate_subject(
            _compact_subject_label(title, summary, category) or _extract_subject_label(title, summary, category)
        )
    if category == "首脳陣":
        manager_subject = _extract_subject_label(title, summary, category)
        manager_subject = _re.sub(r"(監督|コーチ)$", "", manager_subject).strip()
        return _normalize_duplicate_subject(manager_subject)
    return ""


def _duplicate_key_basis(
    *,
    canonical_url: str,
    game_id: str,
    player: str,
    subtype: str,
) -> str:
    if canonical_url:
        return "canonical"
    if game_id and subtype:
        return "game_subtype"
    if player and subtype:
        return "player_subtype_title"
    return "title_family"


def compute_duplicate_key(
    *,
    source_url: str | None,
    canonical_url: str | None,
    title: str,
    source_family: str | None = None,
    game_id: str | None = None,
    player: str | None = None,
    subtype: str | None = None,
    topic_key: str | None = None,
) -> str:
    import hashlib

    title_norm = _normalize_title_for_dedupe(title or "")
    canonical_value = _normalize_duplicate_canonical_url(canonical_url)
    resolved_subtype = str(subtype or "").strip().lower()
    resolved_player = _normalize_duplicate_subject(player or "")
    resolved_game_id = str(game_id or "").strip().lower()
    resolved_topic_key = _normalize_duplicate_subject(topic_key or "")
    if canonical_value:
        return hashlib.sha256(f"canonical:{canonical_value}".encode("utf-8")).hexdigest()[:16]
    if resolved_game_id and resolved_subtype:
        base = f"game:{resolved_game_id}:subtype:{resolved_subtype}"
    elif resolved_player and resolved_subtype:
        base = f"player:{resolved_player}:subtype:{resolved_subtype}:title:{title_norm[:80]}"
    else:
        family = str(source_family or _extract_source_family(source_url or "")).strip().lower() or "unknown"
        base = f"title:{title_norm[:120]}:family:{family}"
    parts = [base]
    if resolved_topic_key:
        parts.append(f"topic:{resolved_topic_key}")
    if resolved_subtype:
        parts.append(f"sub:{resolved_subtype}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _compute_duplicate_group_signature(
    *,
    canonical_url: str,
    title: str,
    game_id: str = "",
    player: str = "",
    subtype: str = "",
    topic_key: str = "",
) -> str:
    title_norm = _normalize_title_for_dedupe(title or "")
    if canonical_url:
        return f"canonical:{canonical_url}"
    if game_id and subtype:
        return f"game:{game_id}:{subtype}"
    if player and subtype:
        return f"player:{player}:{subtype}:{title_norm[:80]}"
    if topic_key:
        return f"topic:{topic_key}:{subtype or 'none'}"
    if title_norm:
        return f"title:{title_norm[:120]}"
    return ""


def _duplicate_guard_enabled_for_subtype(article_subtype: str) -> bool:
    return str(article_subtype or "").strip().lower() != "lineup"


def _parse_duplicate_ledger_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _duplicate_candidate_time_sort_value(value: object) -> float:
    if isinstance(value, datetime):
        target = value
    else:
        parsed = _parse_duplicate_ledger_datetime(value)
        if parsed is None:
            return float("inf")
        target = parsed
    if target.tzinfo is None:
        target = target.replace(tzinfo=timezone.utc)
    return target.astimezone(timezone.utc).timestamp()


def _duplicate_hours_gap(existing: object, current: object) -> float | None:
    existing_dt = _parse_duplicate_ledger_datetime(existing)
    current_dt = _parse_duplicate_ledger_datetime(current)
    if existing_dt is None or current_dt is None:
        return None
    return abs((current_dt - existing_dt).total_seconds()) / 3600.0


def _duplicate_candidate_priority_sort_key(candidate: dict) -> tuple[object, ...]:
    return (
        int(candidate.get("source_family_priority", 4) or 4),
        0 if candidate.get("canonical_url") else 1,
        -int(candidate.get("body_length", 0) or 0),
        _duplicate_candidate_time_sort_value(candidate.get("published_at")),
        int(candidate.get("source_rank", 0) or 0),
        int(candidate.get("entry_index", 0) or 0),
    )


def _duplicate_candidate_record_comparison_key(payload: dict) -> tuple[object, ...]:
    return (
        int(payload.get("source_family_priority", 4) or 4),
        0 if payload.get("canonical_url") or payload.get("canonical_present") else 1,
        -int(payload.get("body_length", 0) or 0),
        _duplicate_candidate_time_sort_value(payload.get("published_at")),
    )


def _duplicate_record_priority_sort_key(record: dict) -> tuple[object, ...]:
    return (
        int(record.get("source_family_priority", 4) or 4),
        0 if record.get("canonical_present") else 1,
        -int(record.get("body_length", 0) or 0),
        _duplicate_candidate_time_sort_value(record.get("published_at")),
        0 if record.get("primary") else 1,
        _duplicate_candidate_time_sort_value(record.get("timestamp")),
    )


def _duplicate_guard_cooldown_hours() -> int:
    raw = os.getenv("RSS_DUPLICATE_COOLDOWN_HOURS", str(RSS_DUPLICATE_COOLDOWN_HOURS_DEFAULT)).strip()
    try:
        return max(int(raw), 0)
    except ValueError:
        return RSS_DUPLICATE_COOLDOWN_HOURS_DEFAULT


class _DuplicateNewsLedger:
    _shared_instance: "_DuplicateNewsLedger | None" = None

    def __init__(
        self,
        ledger_path: str | Path | None = None,
        cooldown_hours: int | None = None,
        *,
        now: datetime | None = None,
    ):
        self.ledger_path = Path(ledger_path) if ledger_path is not None else ROOT / "logs" / "rss_fetcher_duplicate_ledger.jsonl"
        self.cooldown_hours = _duplicate_guard_cooldown_hours() if cooldown_hours is None else max(int(cooldown_hours), 0)
        self._memory_by_key: dict[str, dict] = {}
        self._memory_by_group: dict[str, dict] = {}
        self._load_recent(now=now)

    @classmethod
    def shared(cls) -> "_DuplicateNewsLedger":
        if cls._shared_instance is None:
            cls._shared_instance = cls()
        return cls._shared_instance

    @classmethod
    def reset_shared(cls) -> None:
        cls._shared_instance = None

    def _threshold(self, now: datetime | None = None) -> datetime:
        reference_now = now or datetime.now(timezone.utc)
        if reference_now.tzinfo is None:
            reference_now = reference_now.replace(tzinfo=timezone.utc)
        return reference_now.astimezone(timezone.utc) - timedelta(hours=self.cooldown_hours)

    def _load_recent(self, *, now: datetime | None = None) -> None:
        if not self.ledger_path.exists():
            return
        threshold = self._threshold(now=now)
        try:
            with self.ledger_path.open("r", encoding="utf-8") as handle:
                for raw_line in handle:
                    line = raw_line.strip()
                    if not line:
                        continue
                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if not isinstance(payload, dict):
                        continue
                    timestamp = _parse_duplicate_ledger_datetime(payload.get("timestamp"))
                    if timestamp is None or timestamp < threshold:
                        continue
                    self._remember(payload)
        except OSError:
            return

    def _remember(self, payload: dict) -> None:
        duplicate_key = str(payload.get("duplicate_key") or "").strip()
        group_signature = str(payload.get("group_signature") or "").strip()
        if duplicate_key:
            current = self._memory_by_key.get(duplicate_key)
            if current is None or _duplicate_record_priority_sort_key(payload) < _duplicate_record_priority_sort_key(current):
                self._memory_by_key[duplicate_key] = dict(payload)
        if group_signature:
            current_group = self._memory_by_group.get(group_signature)
            if current_group is None or _duplicate_record_priority_sort_key(payload) < _duplicate_record_priority_sort_key(current_group):
                self._memory_by_group[group_signature] = dict(payload)

    def find_recent(self, duplicate_key: str, group_signature: str = "") -> dict | None:
        if duplicate_key:
            hit = self._memory_by_key.get(duplicate_key)
            if hit is not None:
                return dict(hit)
        if group_signature:
            hit = self._memory_by_group.get(group_signature)
            if hit is not None:
                return dict(hit)
        return None

    def record(
        self,
        *,
        duplicate_key: str,
        group_signature: str,
        source_url_hash: str,
        source_family: str,
        source_family_priority: int,
        title_norm: str,
        subtype: str,
        post_id: int | str | None,
        primary: bool,
        canonical_present: bool,
        body_length: int,
        published_at: str = "",
        player: str = "",
        game_id: str = "",
        topic_key: str = "",
        match_basis: str = "",
        now: datetime | None = None,
    ) -> dict:
        reference_now = now or datetime.now(timezone.utc)
        if reference_now.tzinfo is None:
            reference_now = reference_now.replace(tzinfo=timezone.utc)
        payload = {
            "timestamp": reference_now.astimezone(JST).isoformat(),
            "duplicate_key": str(duplicate_key or ""),
            "group_signature": str(group_signature or ""),
            "source_url_hash": str(source_url_hash or ""),
            "source_family": str(source_family or "unknown"),
            "source_family_priority": int(source_family_priority or 0),
            "title_norm": str(title_norm or "")[:80],
            "subtype": str(subtype or ""),
            "post_id": int(post_id) if isinstance(post_id, int) or str(post_id or "").isdigit() else None,
            "primary": bool(primary),
            "canonical_present": bool(canonical_present),
            "body_length": int(body_length or 0),
            "published_at": str(published_at or ""),
            "player": str(player or ""),
            "game_id": str(game_id or ""),
            "topic_key": str(topic_key or ""),
            "match_basis": str(match_basis or ""),
        }
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with self.ledger_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, default=str))
            handle.write("\n")
        self._remember(payload)
        return payload


def _emit_duplicate_news_structured(
    logger: logging.Logger,
    *,
    event: str,
    duplicate_key: str,
    title_norm: str,
    subtype: str,
    source_family: str,
    skipped_source_url_hash: str = "",
    candidate_source_url_hash: str = "",
    primary_source_url_hash: str = "",
    existing_source_url_hash: str = "",
    primary_post_id: int | None = None,
    ambiguity_reason: str = "",
) -> None:
    payload = {
        "event": event,
        "duplicate_key": str(duplicate_key or ""),
        "title_norm": str(title_norm or "")[:80],
        "subtype": str(subtype or ""),
        "source_family": str(source_family or "unknown"),
        "timestamp": datetime.now(JST).isoformat(),
    }
    if skipped_source_url_hash:
        payload["skipped_source_url_hash"] = skipped_source_url_hash
    if candidate_source_url_hash:
        payload["candidate_source_url_hash"] = candidate_source_url_hash
    if primary_source_url_hash:
        payload["primary_source_url_hash"] = primary_source_url_hash
    if existing_source_url_hash:
        payload["existing_source_url_hash"] = existing_source_url_hash
    if primary_post_id is not None:
        payload["primary_post_id"] = primary_post_id
    if ambiguity_reason:
        payload["ambiguity_reason"] = ambiguity_reason
    logger.info(json.dumps(payload, ensure_ascii=False))


def _is_duplicate_review_ambiguous(existing: dict, current: dict) -> tuple[bool, str]:
    current_player = str(current.get("player") or "")
    existing_player = str(existing.get("player") or "")
    current_subtype = str(current.get("subtype") or "")
    existing_subtype = str(existing.get("subtype") or "")
    if (
        current_player
        and current_player == existing_player
        and current_subtype
        and current_subtype == existing_subtype
        and not str(current.get("game_id") or "")
        and not str(existing.get("game_id") or "")
    ):
        gap_hours = _duplicate_hours_gap(existing.get("published_at"), current.get("published_at"))
        if gap_hours is not None and gap_hours > _duplicate_guard_cooldown_hours():
            return True, "player_subtype_match_time_gap"
    current_title_norm = str(current.get("title_norm") or "")
    existing_title_norm = str(existing.get("title_norm") or "")
    current_family = str(current.get("source_family") or "")
    existing_family = str(existing.get("source_family") or "")
    if (
        current_title_norm
        and current_title_norm == existing_title_norm
        and current_family
        and existing_family
        and current_family != existing_family
        and _is_first_tier_duplicate_family(current_family)
        and _is_first_tier_duplicate_family(existing_family)
    ):
        return True, "title_match_different_family"
    return False, ""


def _build_duplicate_news_context(
    *,
    source_url: str,
    title: str,
    summary: str,
    category: str,
    source_type: str,
    has_game: bool,
    source_entry: dict | None = None,
    game_id: str = "",
    source_name: str = "",
    published_at: datetime | None = None,
    source_rank: int = 0,
    entry_index: int = 0,
) -> dict | None:
    if source_type not in {"news", "social_news"}:
        return None
    article_subtype = _detect_article_subtype(title, summary, category, has_game)
    if not _duplicate_guard_enabled_for_subtype(article_subtype):
        return None
    canonical_url = _extract_entry_canonical_url(source_entry)
    source_family = _extract_source_family(source_url)
    player = _extract_duplicate_player(title, summary, category)
    resolved_game_id = _extract_duplicate_game_id(source_url, explicit_game_id=game_id)
    topic_key = ""
    duplicate_key = compute_duplicate_key(
        source_url=source_url,
        canonical_url=canonical_url,
        title=title,
        source_family=source_family,
        game_id=resolved_game_id,
        player=player,
        subtype=article_subtype,
        topic_key=topic_key,
    )
    group_signature = _compute_duplicate_group_signature(
        canonical_url=canonical_url,
        title=title,
        game_id=resolved_game_id,
        player=player,
        subtype=article_subtype,
        topic_key=topic_key,
    )
    if not duplicate_key or not group_signature:
        return None
    return {
        "duplicate_key": duplicate_key,
        "group_signature": group_signature,
        "match_basis": _duplicate_key_basis(
            canonical_url=canonical_url,
            game_id=resolved_game_id,
            player=player,
            subtype=article_subtype,
        ),
        "source_url_hash": _hash_duplicate_guard_value(source_url),
        "source_family": source_family,
        "source_family_priority": _duplicate_source_family_priority(source_family),
        "canonical_url": canonical_url,
        "title_norm": _normalize_title_for_dedupe(title),
        "subtype": article_subtype,
        "player": player,
        "game_id": resolved_game_id,
        "topic_key": topic_key,
        "published_at": published_at.isoformat() if isinstance(published_at, datetime) else "",
        "body_length": len(_strip_html(f"{title} {summary}")),
        "source_name": source_name,
        "source_type": source_type,
        "source_rank": int(source_rank or 0),
        "entry_index": int(entry_index or 0),
        "guard_outcome": "allow",
    }


def _build_duplicate_news_context_from_prepared_entry(item: dict) -> dict | None:
    return _build_duplicate_news_context(
        source_url=str(item.get("post_url") or ""),
        title=str(item.get("raw_title") or item.get("title") or ""),
        summary=str(item.get("summary") or ""),
        category=str(item.get("category") or ""),
        source_type=str(item.get("source_type") or ""),
        has_game=bool(item.get("entry_has_game", True)),
        source_entry=item.get("entry"),
        game_id=str(item.get("game_id") or ""),
        source_name=str(item.get("source_name") or ""),
        published_at=item.get("published_at"),
        source_rank=int(item.get("source_rank", 0) or 0),
        entry_index=int(item.get("entry_index", 0) or 0),
    )


def _annotate_duplicate_guard_contexts(candidates: list[dict]) -> list[dict]:
    annotated: list[dict] = []
    groups: dict[str, list[dict]] = {}

    for item in candidates:
        context = _build_duplicate_news_context_from_prepared_entry(item)
        if context is None:
            annotated.append(item)
            continue
        cloned = dict(item)
        cloned["duplicate_guard_context"] = context
        annotated.append(cloned)
        groups.setdefault(context["group_signature"], []).append(context)

    for contexts in groups.values():
        primary = min(contexts, key=_duplicate_candidate_priority_sort_key)
        for context in contexts:
            context["same_run_group_size"] = len(contexts)
            context["same_run_primary"] = context is primary
            context["same_run_primary_source_url_hash"] = primary.get("source_url_hash", "")
            context["same_run_primary_post_id"] = primary.get("post_id")
            if context is primary:
                continue
            ambiguous, reason = _is_duplicate_review_ambiguous(primary, context)
            context["same_run_ambiguous"] = ambiguous
            context["same_run_ambiguity_reason"] = reason
    return annotated


def _evaluate_pre_gemini_duplicate_guard(
    logger: logging.Logger,
    duplicate_guard_context: dict | None,
) -> str:
    if not isinstance(duplicate_guard_context, dict) or not duplicate_guard_context.get("duplicate_key"):
        return "allow"

    duplicate_guard_context["guard_outcome"] = "allow"

    if (
        int(duplicate_guard_context.get("same_run_group_size", 1) or 1) > 1
        and not bool(duplicate_guard_context.get("same_run_primary", True))
    ):
        if duplicate_guard_context.get("same_run_ambiguous"):
            _emit_duplicate_news_structured(
                logger,
                event="candidate_duplicate_review",
                duplicate_key=str(duplicate_guard_context.get("duplicate_key") or ""),
                candidate_source_url_hash=str(duplicate_guard_context.get("source_url_hash") or ""),
                existing_source_url_hash=str(duplicate_guard_context.get("same_run_primary_source_url_hash") or ""),
                primary_post_id=duplicate_guard_context.get("same_run_primary_post_id"),
                title_norm=str(duplicate_guard_context.get("title_norm") or ""),
                subtype=str(duplicate_guard_context.get("subtype") or ""),
                source_family=str(duplicate_guard_context.get("source_family") or ""),
                ambiguity_reason=str(duplicate_guard_context.get("same_run_ambiguity_reason") or ""),
            )
            duplicate_guard_context["guard_outcome"] = "review"
            return "review"
        _emit_duplicate_news_structured(
            logger,
            event="duplicate_news_pre_gemini_skip",
            duplicate_key=str(duplicate_guard_context.get("duplicate_key") or ""),
            skipped_source_url_hash=str(duplicate_guard_context.get("source_url_hash") or ""),
            primary_source_url_hash=str(duplicate_guard_context.get("same_run_primary_source_url_hash") or ""),
            primary_post_id=duplicate_guard_context.get("same_run_primary_post_id"),
            title_norm=str(duplicate_guard_context.get("title_norm") or ""),
            subtype=str(duplicate_guard_context.get("subtype") or ""),
            source_family=str(duplicate_guard_context.get("source_family") or ""),
        )
        duplicate_guard_context["guard_outcome"] = "skip"
        return "skip"

    ledger = _DuplicateNewsLedger.shared()
    recent = ledger.find_recent(
        str(duplicate_guard_context.get("duplicate_key") or ""),
        str(duplicate_guard_context.get("group_signature") or ""),
    )
    if recent is None:
        return "allow"

    if _duplicate_candidate_record_comparison_key(duplicate_guard_context) < _duplicate_candidate_record_comparison_key(recent):
        return "allow"

    ambiguous, reason = _is_duplicate_review_ambiguous(recent, duplicate_guard_context)
    if ambiguous:
        _emit_duplicate_news_structured(
            logger,
            event="candidate_duplicate_review",
            duplicate_key=str(duplicate_guard_context.get("duplicate_key") or ""),
            candidate_source_url_hash=str(duplicate_guard_context.get("source_url_hash") or ""),
            existing_source_url_hash=str(recent.get("source_url_hash") or ""),
            primary_post_id=recent.get("post_id"),
            title_norm=str(duplicate_guard_context.get("title_norm") or ""),
            subtype=str(duplicate_guard_context.get("subtype") or ""),
            source_family=str(duplicate_guard_context.get("source_family") or ""),
            ambiguity_reason=reason,
        )
        duplicate_guard_context["guard_outcome"] = "review"
        return "review"

    _emit_duplicate_news_structured(
        logger,
        event="duplicate_news_pre_gemini_skip",
        duplicate_key=str(duplicate_guard_context.get("duplicate_key") or ""),
        skipped_source_url_hash=str(duplicate_guard_context.get("source_url_hash") or ""),
        primary_source_url_hash=str(recent.get("source_url_hash") or ""),
        primary_post_id=recent.get("post_id"),
        title_norm=str(duplicate_guard_context.get("title_norm") or ""),
        subtype=str(duplicate_guard_context.get("subtype") or ""),
        source_family=str(duplicate_guard_context.get("source_family") or ""),
    )
    duplicate_guard_context["guard_outcome"] = "skip"
    return "skip"


def _record_duplicate_guard_success(duplicate_guard_context: dict | None, post_id: int | None) -> None:
    if not isinstance(duplicate_guard_context, dict):
        return
    if duplicate_guard_context.get("guard_outcome") == "skip":
        return
    duplicate_key = str(duplicate_guard_context.get("duplicate_key") or "").strip()
    group_signature = str(duplicate_guard_context.get("group_signature") or "").strip()
    if not duplicate_key or not group_signature:
        return
    _DuplicateNewsLedger.shared().record(
        duplicate_key=duplicate_key,
        group_signature=group_signature,
        source_url_hash=str(duplicate_guard_context.get("source_url_hash") or ""),
        source_family=str(duplicate_guard_context.get("source_family") or "unknown"),
        source_family_priority=int(duplicate_guard_context.get("source_family_priority", 4) or 4),
        title_norm=str(duplicate_guard_context.get("title_norm") or ""),
        subtype=str(duplicate_guard_context.get("subtype") or ""),
        post_id=post_id,
        primary=bool(duplicate_guard_context.get("same_run_primary", True)),
        canonical_present=bool(duplicate_guard_context.get("canonical_url")),
        body_length=int(duplicate_guard_context.get("body_length", 0) or 0),
        published_at=str(duplicate_guard_context.get("published_at") or ""),
        player=str(duplicate_guard_context.get("player") or ""),
        game_id=str(duplicate_guard_context.get("game_id") or ""),
        topic_key=str(duplicate_guard_context.get("topic_key") or ""),
        match_basis=str(duplicate_guard_context.get("match_basis") or ""),
    )


def _is_history_duplicate(post_url: str, entry_title_norm: str, history: dict) -> bool:
    if post_url and post_url in history:
        return True
    if entry_title_norm and len(entry_title_norm) > 5:
        title_key = f"title_norm:{entry_title_norm[:60]}"
        if title_key in history:
            return True
    return False


def _get_title_collision_meta(history: dict, rewritten_title_norm: str, source_url: str) -> dict | None:
    if not rewritten_title_norm or len(rewritten_title_norm) <= 5:
        return None
    meta = history.get(f"rewritten_title_norm:{rewritten_title_norm[:60]}")
    if not isinstance(meta, dict):
        return None
    existing_post_url = meta.get("post_url", "")
    if not existing_post_url or existing_post_url == source_url:
        return None
    return meta


def _log_title_collision_if_needed(
    logger: logging.Logger,
    history: dict,
    source_url: str,
    rewritten_title: str,
) -> str:
    rewritten_title_norm = _normalize_history_title(rewritten_title)
    collision_meta = _get_title_collision_meta(history, rewritten_title_norm, source_url)
    if collision_meta:
        payload = {
            "event": "title_collision_detected",
            "source_url": source_url,
            "rewritten_title": rewritten_title,
            "title_norm": rewritten_title_norm[:60],
            "existing_post_url": collision_meta.get("post_url", ""),
            "existing_title": collision_meta.get("original_title", ""),
        }
        logger.warning(json.dumps(payload, ensure_ascii=False))
    return rewritten_title_norm


def _create_draft_with_same_fire_guard(
    wp: WPClient,
    logger: logging.Logger,
    same_fire_source_urls: set[str],
    same_fire_title_sources: dict[str, set[str]],
    draft_title: str,
    content: str,
    categories: list,
    source_url: str,
    featured_media: int | None = None,
) -> int:
    normalized_source_url = _html.unescape((source_url or "").strip())
    rewritten_title_norm = _normalize_history_title(draft_title)
    if normalized_source_url:
        same_fire_source_urls.add(normalized_source_url)
        if rewritten_title_norm and len(rewritten_title_norm) > 5:
            seen_sources = same_fire_title_sources.setdefault(rewritten_title_norm, set())
            if seen_sources and normalized_source_url not in seen_sources:
                logger.info(
                    "same_fire_distinct_source_detected source_url=%s rewritten_title=%s",
                    normalized_source_url,
                    draft_title,
                )
            seen_sources.add(normalized_source_url)
    return wp.create_post(
        draft_title,
        content,
        categories=categories,
        status="draft",
        featured_media=featured_media or None,
        source_url=normalized_source_url or None,
        allow_title_only_reuse=False,
    )


def _resolve_effective_featured_media(
    wp: WPClient,
    post_id: int,
    featured_media: int,
    logger: logging.Logger | None = None,
) -> int:
    if featured_media:
        return featured_media
    logger = logger or logging.getLogger("rss_fetcher")
    try:
        post = wp.get_post(post_id)
    except Exception as exc:
        logger.info(
            json.dumps(
                {
                    "event": "featured_media_lookup_failed",
                    "post_id": post_id,
                    "error": str(exc),
                },
                ensure_ascii=False,
            )
        )
        return 0
    existing_featured_media = int(post.get("featured_media") or 0)
    if existing_featured_media:
        logger.info(
            json.dumps(
                {
                    "event": "featured_media_reused_from_existing_post",
                    "post_id": post_id,
                    "featured_media": existing_featured_media,
                },
                ensure_ascii=False,
            )
        )
    return existing_featured_media


def persist_processed_entry_history(
    history: dict,
    history_urls: list[str],
    history_title_norms: list[str] | None = None,
    rewritten_title: str = "",
    original_title: str = "",
    published: bool = False,
    publish_skip_reasons: list[str] | None = None,
) -> bool:
    reasons = set(publish_skip_reasons or [])
    if not published and "draft_only" not in reasons:
        return False
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    for url in _dedupe_preserve_order([u for u in history_urls if u]):
        history[url] = now_str
    for title_norm in _dedupe_preserve_order(history_title_norms or []):
        if title_norm and len(title_norm) > 5:
            history[f"title_norm:{title_norm[:60]}"] = now_str
    rewritten_title_norm = _normalize_history_title(rewritten_title)
    if rewritten_title_norm and len(rewritten_title_norm) > 5:
        history[f"rewritten_title_norm:{rewritten_title_norm[:60]}"] = {
            "post_url": next((u for u in history_urls if u), ""),
            "original_title": original_title,
            "rewritten_title": rewritten_title,
            "saved_at": now_str,
        }
    persist_history(history)
    return True


def _entry_day_key(entry: dict) -> str:
    published_at = _entry_published_datetime(entry)
    if not published_at:
        return ""
    try:
        return published_at.astimezone().strftime("%Y-%m-%d")
    except Exception:
        return ""


def _entry_published_datetime(entry: dict) -> datetime | None:
    pub = entry.get("published_parsed") or entry.get("updated_parsed")
    if not pub:
        return None
    try:
        return datetime(*pub[:6], tzinfo=timezone.utc)
    except Exception:
        return None


def _merge_source_summary(candidates: list[dict], max_sentences: int = 6) -> str:
    pieces = []
    for candidate in candidates:
        pieces.extend(_extract_source_sentences(candidate.get("title", ""), candidate.get("summary", ""), max_sentences=3))

    deduped = []
    seen = set()
    for piece in pieces:
        key = piece.replace(" ", "").replace("　", "")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(piece)
        if len(deduped) >= max_sentences:
            break

    if not deduped:
        return ""
    return "。".join(deduped).rstrip("。") + "。"


def _aggregate_lineup_candidates(candidates: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, str], list[dict]] = {}
    passthrough: list[dict] = []

    for candidate in candidates:
        subtype = _detect_article_subtype(candidate.get("title", ""), candidate.get("summary", ""), candidate.get("category", ""), candidate.get("entry_has_game", True))
        if not (
            candidate.get("source_type") == "news"
            and candidate.get("category") == "試合速報"
            and subtype == "lineup"
        ):
            passthrough.append(candidate)
            continue
        key = (candidate.get("published_day") or "", "lineup")
        grouped.setdefault(key, []).append(candidate)

    aggregated: list[dict] = list(passthrough)
    for _, group in grouped.items():
        ordered_group = sorted(group, key=lambda item: (item.get("source_rank", 0), item.get("entry_index", 0)))
        if len(ordered_group) <= 1:
            aggregated.extend(ordered_group)
            continue

        selected = ordered_group[:3]
        primary = max(
            selected,
            key=lambda item: (
                len(_strip_html(item.get("title", ""))),
                len(_strip_html(item.get("summary", ""))),
                -item.get("source_rank", 0),
            ),
        )
        merged = dict(primary)
        merged["entry_index"] = min(item.get("entry_index", 0) for item in ordered_group)
        merged["summary"] = _merge_source_summary(selected) or primary.get("summary", "")
        merged["source_name"] = " / ".join(_dedupe_preserve_order([item.get("source_name", "") for item in selected if item.get("source_name")]))
        merged["source_links"] = [
            {"name": item.get("source_name", "スポーツニュース"), "url": item.get("post_url", "")}
            for item in selected
            if item.get("post_url")
        ]
        merged["history_urls"] = _dedupe_preserve_order(
            [url for item in ordered_group for url in item.get("history_urls", [item.get("post_url", "")]) if url]
        )
        merged["history_title_norms"] = _dedupe_preserve_order(
            [title_norm for item in ordered_group for title_norm in item.get("history_title_norms", [item.get("entry_title_norm", "")]) if title_norm]
        )
        merged["merged_source_count"] = len(selected)
        aggregated.append(merged)

    return sorted(aggregated, key=lambda item: item.get("entry_index", 0))


def _prioritize_prepared_entries_for_creation(candidates: list[dict]) -> list[dict]:
    def _is_priority_candidate(candidate: dict) -> bool:
        subtype = _detect_article_subtype(
            candidate.get("title", ""),
            candidate.get("summary", ""),
            candidate.get("category", ""),
            candidate.get("entry_has_game", True),
        )
        return candidate.get("source_type") in {"news", "social_news"} and subtype in {"lineup", "farm_lineup"}

    return sorted(candidates, key=lambda item: 0 if _is_priority_candidate(item) else 1)


def _has_primary_lineup_candidate(candidates: list[dict]) -> bool:
    for candidate in candidates:
        subtype = _detect_article_subtype(
            candidate.get("title", ""),
            candidate.get("summary", ""),
            candidate.get("category", ""),
            candidate.get("entry_has_game", True),
        )
        if candidate.get("source_type") == "news" and candidate.get("category") == "試合速報" and subtype == "lineup":
            return True
    return False


def _has_primary_postgame_candidate(candidates: list[dict]) -> bool:
    for candidate in candidates:
        subtype = _detect_article_subtype(
            candidate.get("title", ""),
            candidate.get("summary", ""),
            candidate.get("category", ""),
            candidate.get("entry_has_game", True),
        )
        if candidate.get("source_type") == "news" and candidate.get("category") == "試合速報" and subtype == "postgame":
            return True
    return False


def _has_primary_live_candidate(candidates: list[dict]) -> bool:
    for candidate in candidates:
        subtype = _detect_article_subtype(
            candidate.get("title", ""),
            candidate.get("summary", ""),
            candidate.get("category", ""),
            candidate.get("entry_has_game", True),
        )
        if candidate.get("source_type") in {"news", "social_news"} and candidate.get("category") == "試合速報" and subtype == "live_update":
            return True
    return False


def _build_yahoo_lineup_candidate(opponent: str, venue: str, rows: list[dict], entry_index: int) -> dict | None:
    if not rows:
        return None

    top_rows = rows[:4]
    head = "、".join(f"{row.get('order', '')}番{row.get('name', '')}" for row in top_rows if row.get("name"))
    opponent_part = f"{opponent}戦" if opponent else "今日の試合"
    venue_part = f"（{venue}）" if venue else ""
    title = f"【巨人スタメン】{opponent_part}{venue_part} {head}".strip()

    summary_lines = []
    for row in top_rows:
        name = row.get("name", "")
        order = row.get("order", "")
        position = row.get("position", "")
        avg = row.get("avg", "-")
        if name and order:
            summary_lines.append(f"{order}番{position}{name}の打率は{avg}")
    summary = "。".join(summary_lines).rstrip("。") + "。"
    if opponent:
        summary += f" 巨人が{opponent}戦のスタメンを発表した。"
    else:
        summary += " 巨人が今日のスタメンを発表した。"

    game_id, _, _ = _find_today_giants_game_info_yahoo()
    post_url = f"https://baseball.yahoo.co.jp/npb/game/{game_id}/top" if game_id else "https://baseball.yahoo.co.jp/npb/teams/1/"
    title_norm = _re.sub(r"[\s　【】「」『』〔〕（）()・\-_]", "", title).lower()
    today_key = datetime.now().strftime("%Y-%m-%d")
    return {
        "entry_index": entry_index,
        "source_rank": -1,
        "source_name": "Yahoo!プロ野球 スタメン",
        "source_type": "news",
        "entry": {
            "title": title,
            "summary": summary,
            "link": post_url,
            "published_parsed": datetime.now().timetuple(),
        },
        "post_url": post_url,
        "title_text": f"{title} {summary}",
        "category": "試合速報",
        "title": title,
        "summary": summary,
        "entry_title_norm": title_norm,
        "entry_has_game": True,
        "published_day": today_key,
        "history_urls": [f"{post_url}#lineup"],
        "history_title_norms": [title_norm],
        "is_synthetic_lineup": True,
    }


def _build_yahoo_postgame_candidate(opponent: str, venue: str, game_status: dict, entry_index: int) -> dict | None:
    if not game_status or not game_status.get("ended"):
        return None

    opponent_label = game_status.get("opponent") or opponent or "相手"
    giants_score = game_status.get("giants_score", "")
    opponent_score = game_status.get("opponent_score", "")
    if not giants_score or not opponent_score:
        return None

    try:
        g_score = int(giants_score)
        o_score = int(opponent_score)
    except ValueError:
        return None

    if g_score > o_score:
        result_word = "勝利"
        title = f"【巨人試合結果】{opponent_label}に{g_score}-{o_score}で勝利"
        lead = f"巨人が{opponent_label}に{g_score}-{o_score}で勝利した。"
    elif g_score < o_score:
        result_word = "敗戦"
        title = f"【巨人試合結果】{opponent_label}に{g_score}-{o_score}で敗戦"
        lead = f"巨人が{opponent_label}に{g_score}-{o_score}で敗れた。"
    else:
        result_word = "引き分け"
        title = f"【巨人試合結果】{opponent_label}と{g_score}-{o_score}で引き分け"
        lead = f"巨人が{opponent_label}と{g_score}-{o_score}で引き分けた。"

    giants_hits = game_status.get("giants_hits", "")
    opponent_hits = game_status.get("opponent_hits", "")
    giants_errors = game_status.get("giants_errors", "")
    opponent_errors = game_status.get("opponent_errors", "")

    stat_bits = []
    if giants_hits:
        stat_bits.append(f"巨人は{giants_hits}安打")
    if opponent_hits:
        stat_bits.append(f"{opponent_label}は{opponent_hits}安打")
    stat_line = "、".join(stat_bits) + "。" if stat_bits else ""

    error_bits = []
    if giants_errors:
        error_bits.append(f"巨人{giants_errors}失策")
    if opponent_errors:
        error_bits.append(f"{opponent_label}{opponent_errors}失策")
    error_line = "、".join(error_bits) + "。" if error_bits else ""

    venue_line = f"{venue}で試合終了を確認した。" if venue else "Yahoo!プロ野球で試合終了を確認した。"
    summary = " ".join(piece for piece in [lead, stat_line, error_line, venue_line] if piece).strip()

    post_url = game_status.get("post_url") or f"https://baseball.yahoo.co.jp/npb/game/{game_status.get('game_id', '')}/top"
    title_norm = _re.sub(r"[\s　【】「」『』〔〕（）()・\-_]", "", title).lower()
    today_key = datetime.now().strftime("%Y-%m-%d")
    return {
        "entry_index": entry_index,
        "source_rank": -1,
        "source_name": "Yahoo!プロ野球 試合結果",
        "source_type": "news",
        "entry": {
            "title": title,
            "summary": summary,
            "link": post_url,
            "published_parsed": datetime.now().timetuple(),
        },
        "post_url": post_url,
        "title_text": f"{title} {summary}",
        "category": "試合速報",
        "title": title,
        "summary": summary,
        "entry_title_norm": title_norm,
        "entry_has_game": True,
        "published_day": today_key,
        "history_urls": [f"{post_url}#postgame"],
        "history_title_norms": [title_norm],
        "is_synthetic_postgame": True,
        "synthetic_postgame_result": result_word,
    }


def _load_live_game_state(history: dict, game_id: str) -> dict:
    raw = history.get(f"live_state:{game_id}")
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _save_live_game_state(history: dict, game_id: str, game_status: dict):
    try:
        payload = {
            "giants_score": game_status.get("giants_score", ""),
            "opponent_score": game_status.get("opponent_score", ""),
            "state": game_status.get("state", ""),
            "ended": bool(game_status.get("ended")),
        }
        history[f"live_state:{game_id}"] = json.dumps(payload, ensure_ascii=False)
    except Exception:
        pass


def _detect_live_update_reason(game_status: dict, previous_state: dict) -> str:
    if not game_status or game_status.get("ended"):
        return ""
    try:
        g_score = int(game_status.get("giants_score", ""))
        o_score = int(game_status.get("opponent_score", ""))
    except (TypeError, ValueError):
        return ""

    total_runs = g_score + o_score
    if total_runs <= 0:
        return ""

    prev_g = prev_o = None
    try:
        prev_g = int(previous_state.get("giants_score", "")) if previous_state else None
        prev_o = int(previous_state.get("opponent_score", "")) if previous_state else None
    except (TypeError, ValueError):
        prev_g = prev_o = None

    if prev_g is None or prev_o is None:
        return "first_score"
    if g_score == prev_g and o_score == prev_o:
        return ""
    if g_score == o_score and prev_g != prev_o:
        return "tie_game"
    if (g_score > o_score and prev_g <= prev_o) or (g_score < o_score and prev_g >= prev_o):
        return "lead_change"
    if abs((g_score + o_score) - (prev_g + prev_o)) >= 2:
        return "multi_run"
    return ""


def _build_yahoo_live_update_candidate(opponent: str, venue: str, game_status: dict, entry_index: int, reason: str) -> dict | None:
    if not reason or not game_status or game_status.get("ended"):
        return None

    opponent_label = game_status.get("opponent") or opponent or "相手"
    state_label = game_status.get("state") or "途中経過"
    giants_score = game_status.get("giants_score", "")
    opponent_score = game_status.get("opponent_score", "")
    if not giants_score or not opponent_score:
        return None

    score_token = f"{giants_score}-{opponent_score}"
    if reason == "tie_game":
        title = f"【巨人途中経過】{state_label} 巨人{score_token}{opponent_label}と同点"
        lead = f"巨人が{state_label}で{opponent_label}と{score_token}の同点に持ち込んだ。"
    elif reason == "lead_change":
        try:
            g_score = int(giants_score)
            o_score = int(opponent_score)
        except ValueError:
            return None
        if g_score > o_score:
            title = f"【巨人途中経過】{state_label} 巨人{score_token}{opponent_label}に勝ち越し"
            lead = f"巨人が{state_label}で{opponent_label}に{score_token}と勝ち越した。"
        else:
            title = f"【巨人途中経過】{state_label} 巨人{score_token}{opponent_label}に逆転許す"
            lead = f"巨人が{state_label}で{opponent_label}に{score_token}と逆転を許した。"
    elif reason == "multi_run":
        title = f"【巨人途中経過】{state_label} 巨人{score_token}{opponent_label} スコア動く"
        lead = f"巨人戦は{state_label}の時点で{opponent_label}に{score_token}。スコアが大きく動いた。"
    else:
        title = f"【巨人途中経過】{state_label} 巨人{score_token}{opponent_label}"
        lead = f"巨人戦は{state_label}の時点で{opponent_label}に{score_token}。"

    stat_bits = []
    if game_status.get("giants_hits"):
        stat_bits.append(f"巨人は{game_status['giants_hits']}安打")
    if game_status.get("opponent_hits"):
        stat_bits.append(f"{opponent_label}は{game_status['opponent_hits']}安打")
    if game_status.get("giants_errors"):
        stat_bits.append(f"巨人{game_status['giants_errors']}失策")
    if game_status.get("opponent_errors"):
        stat_bits.append(f"{opponent_label}{game_status['opponent_errors']}失策")
    detail = "、".join(stat_bits) + "。" if stat_bits else ""
    venue_line = f"{venue}の途中経過。" if venue else "Yahoo!プロ野球の途中経過。"
    summary = " ".join(piece for piece in [lead, detail, venue_line] if piece).strip()

    post_url = game_status.get("post_url") or f"https://baseball.yahoo.co.jp/npb/game/{game_status.get('game_id', '')}/top"
    title_norm = _re.sub(r"[\s　【】「」『』〔〕（）()・\-_]", "", title).lower()
    today_key = datetime.now().strftime("%Y-%m-%d")
    return {
        "entry_index": entry_index,
        "source_rank": -1,
        "source_name": "Yahoo!プロ野球 途中経過",
        "source_type": "news",
        "entry": {
            "title": title,
            "summary": summary,
            "link": post_url,
            "published_parsed": datetime.now().timetuple(),
        },
        "post_url": post_url,
        "title_text": f"{title} {summary}",
        "category": "試合速報",
        "title": title,
        "summary": summary,
        "entry_title_norm": title_norm,
        "entry_has_game": True,
        "published_day": today_key,
        "history_urls": [f"{post_url}#live-{score_token}"],
        "history_title_norms": [title_norm],
        "is_synthetic_live_update": True,
        "synthetic_live_reason": reason,
    }

# ──────────────────────────────────────────────────────────
# 巨人キーワードフィルタ
# ──────────────────────────────────────────────────────────
def _normalize_roster_signal_text(text: str) -> str:
    clean = _strip_html(text or "")
    clean = _html.unescape(clean)
    return _re.sub(r"[\s　【】「」『』〔〕（）()・･．\.,，/／\-ーｰ:：]", "", clean)


@lru_cache(maxsize=1)
def _load_giants_roster() -> tuple[dict, ...]:
    try:
        with open(GIANTS_ROSTER_FILE, encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return ()
    return tuple(entry for entry in data if isinstance(entry, dict))


@lru_cache(maxsize=1)
def _giants_roster_alias_index() -> tuple[dict, ...]:
    alias_map: dict[str, set[str]] = {}
    for entry in _load_giants_roster():
        name = (entry.get("name") or "").strip()
        if not name:
            continue
        alias_bucket = alias_map.setdefault(name, set())
        aliases = [name] + list(entry.get("aliases") or [])
        for alias in aliases:
            normalized = _normalize_roster_signal_text(alias)
            if len(normalized) < 2:
                continue
            alias_bucket.add(normalized)

    for name, aliases in GIANTS_ROSTER_EXTRA_ALIASES.items():
        alias_bucket = alias_map.setdefault(name, set())
        for alias in aliases:
            normalized = _normalize_roster_signal_text(alias)
            if len(normalized) >= 2:
                alias_bucket.add(normalized)

    index: list[dict] = []
    for name, alias_bucket in alias_map.items():
        normalized_aliases = sorted(alias_bucket, key=len, reverse=True)
        if normalized_aliases:
            index.append(
                {
                    "name": name,
                    "aliases": tuple(sorted(normalized_aliases, key=len, reverse=True)),
                }
            )
    return tuple(index)


def _matching_giants_roster_names(text: str) -> list[str]:
    normalized_text = _normalize_roster_signal_text(text)
    if not normalized_text:
        return []
    hits: list[str] = []
    for entry in _giants_roster_alias_index():
        if any(alias in normalized_text for alias in entry["aliases"]):
            hits.append(entry["name"])
    return hits


def _is_other_team_transfer_story(text: str, roster_hits: list[str]) -> bool:
    if not roster_hits:
        return False
    source_text = text or ""
    if any(marker in source_text for marker in GIANTS_KEYWORDS):
        return False
    if "読売" in source_text:
        return False
    if not any(marker in source_text for marker in NON_GIANTS_TEAM_MARKERS):
        return False
    return any(marker in source_text for marker in GIANTS_TRANSFER_CONTEXT_MARKERS)


def _trusted_social_signal_match(text: str, category: str, article_subtype: str) -> str:
    markers = list(TRUSTED_SOCIAL_REPORTABLE_MARKERS.get(category, ()))
    if article_subtype == "pregame":
        markers.extend(("先発", "予告先発", "スタメン", "打順", "オーダー"))
    for marker in markers:
        if marker in text:
            return marker
    return ""


def is_giants_related(text: str, source_name: str = "", post_url: str = "") -> bool:
    source_text = text or ""
    if any(kw in source_text for kw in GIANTS_KEYWORDS):
        return True
    if _is_giants_exclusive_social_source(_extract_handle_from_tweet_url(post_url), source_name):
        return True
    roster_hits = _matching_giants_roster_names(source_text)
    if not roster_hits:
        return False
    return not _is_other_team_transfer_story(source_text, roster_hits)

# ──────────────────────────────────────────────────────────
# カテゴリ自動分類
# ──────────────────────────────────────────────────────────
def classify_category(text: str, keywords: dict) -> str:
    if _is_giants_player_dismissal_story(text):
        return "選手情報"
    if _is_farm_lineup_text(text):
        return "ドラフト・育成"
    if any(marker in text for marker in ("二軍戦", "２軍戦", "2軍戦", "二軍", "２軍", "2軍", "ファーム", "育成")):
        return "ドラフト・育成"
    for category, kws in keywords.items():
        if any(kw in text for kw in kws):
            return category
    return "コラム"


def _resolve_draft_category_ids(
    wp: WPClient,
    category: str,
    logger: logging.Logger | None = None,
) -> list[int]:
    requested_category = (category or "").strip() or DRAFT_CATEGORY_FALLBACK_NAME
    category_names = [requested_category]
    if requested_category != DRAFT_CATEGORY_FALLBACK_NAME:
        category_names.append(DRAFT_CATEGORY_FALLBACK_NAME)

    for index, category_name in enumerate(category_names):
        category_id = int(wp.resolve_category_id(category_name) or 0)
        if not category_id:
            continue
        if index > 0 and logger is not None:
            logger.warning(
                "draft category fallback applied requested=%s fallback=%s",
                requested_category,
                category_name,
            )
        return [category_id]

    raise ValueError(
        f"draft category resolution failed requested={requested_category} fallback={DRAFT_CATEGORY_FALLBACK_NAME}"
    )


def _evaluate_authoritative_social_entry(
    title: str,
    summary: str,
    category: str,
    article_subtype: str,
    source_name: str = "",
    source_handle: str = "",
) -> tuple[bool, dict | None]:
    text = _strip_html(f"{title} {summary}")
    trusted_source = _is_trusted_social_source(source_handle, source_name)
    if _is_promotional_video_entry(title, summary) or any(marker in text for marker in SOCIAL_VIDEO_SKIP_MARKERS):
        return False, None
    has_quote = "「" in text and "」" in text

    if article_subtype in {"lineup", "farm_lineup", "postgame"}:
        return True, None
    if article_subtype == "live_update":
        return ENABLE_LIVE_UPDATE_ARTICLES, None
    if category in {"首脳陣", "選手情報"} and has_quote:
        return True, None
    if category == "選手情報":
        matched_keyword = _first_matching_keyword(text, SOCIAL_PLAYER_NOTICE_RESCUE_KEYWORDS)
        if matched_keyword:
            return True, {
                "rescue_reason": "player_notice_keyword",
                "matched_word": matched_keyword,
            }
    if category == "ドラフト・育成" and "２軍" in text:
        return True, {
            "rescue_reason": "zenkaku_2gun",
            "matched_word": "２軍",
        }
    if category == "ドラフト・育成" and any(keyword in text for keyword in ("二軍", "2軍", "ファーム", "昇格", "支配下", "本塁打", "好投", "猛打賞", "マルチ", "適時打", "先発")):
        return True, None
    if category == "試合速報":
        matched_keyword = _first_matching_keyword(text, SOCIAL_GAME_NOTICE_RESCUE_KEYWORDS)
        if matched_keyword:
            return True, {
                "rescue_reason": "game_notice_keyword",
                "matched_word": matched_keyword,
            }
    if category == "試合速報" and any(keyword in text for keyword in ("先発", "登録", "昇格", "抹消", "公示", "打順", "オーダー", "ベンチ入り")):
        return True, None
    if category == "コラム":
        rescue_reason, matched_word = _match_social_column_rescue(text)
        if rescue_reason and matched_word:
            return True, {
                "rescue_reason": rescue_reason,
                "matched_word": matched_word,
            }
    if category == "補強・移籍" and any(keyword in text for keyword in ("獲得", "移籍", "トレード", "加入", "退団")):
        return True, None
    if trusted_source:
        matched_signal = _trusted_social_signal_match(text, category, article_subtype)
        if matched_signal:
            return True, {
                "rescue_reason": "trusted_social_source",
                "matched_word": matched_signal,
            }
    return False, None


def _is_authoritative_social_entry_worthy(title: str, summary: str, category: str, article_subtype: str) -> bool:
    worthy, _rescue_meta = _evaluate_authoritative_social_entry(title, summary, category, article_subtype)
    return worthy


def _log_sns_weak_rescue(
    logger: logging.Logger,
    source_url: str,
    title: str,
    rescue_meta: dict | None,
) -> None:
    if not rescue_meta:
        return
    payload = {
        "event": "sns_weak_rescued",
        "rescue_reason": rescue_meta.get("rescue_reason", ""),
        "source_url": source_url,
        "title": title,
        "matched_word": rescue_meta.get("matched_word", ""),
    }
    logger.info(json.dumps(payload, ensure_ascii=False))

# ──────────────────────────────────────────────────────────
# タイトル生成（投稿内容の先頭40字）
# ──────────────────────────────────────────────────────────
def make_title(entry) -> str:
    text = entry.get("title", "") or entry.get("summary", "")
    # HTMLタグ除去
    import re
    text = re.sub(r"<[^>]+>", "", text).strip()
    text = text[:40].strip()
    return text if text else f"X投稿 {datetime.now().strftime('%Y-%m-%d')}"


def _prepare_source_title_context(entry_title_clean: str, entry: dict | None = None) -> tuple[str, str]:
    raw_title = entry_title_clean.strip() if entry_title_clean else make_title(entry or {})
    raw_title = _strip_html(raw_title).strip()
    preview_title = raw_title[:40].strip() if raw_title else ""
    return raw_title, preview_title or raw_title


def _clean_display_title_text(text: str) -> str:
    clean = _strip_html(text or "")
    clean = _re.sub(r"^【[^】]+】", "", clean).strip()
    clean = _re.sub(r"\s+", " ", clean)
    return clean.strip("。 ")


def _short_subject_name(title: str, summary: str, category: str) -> str:
    subject = _extract_subject_label(title, summary, category)
    return _re.sub(r"(投手|捕手|内野手|外野手|監督|コーチ)$", "", subject).strip()


def _trim_display_title(text: str, max_chars: int = 38) -> str:
    clean = _re.sub(r"\s+", " ", (text or "")).strip("。 ")
    if len(clean) <= max_chars:
        return clean
    return clean[:max_chars].rstrip(" ・、。") + "…"


def _build_title_player_name_backfill_metadata(
    source_title: str,
    summary: str,
    category: str,
    article_subtype: str,
    *,
    manager_subject: str = "",
    notice_subject: str = "",
) -> dict[str, str]:
    metadata: dict[str, str] = {}
    if manager_subject and manager_subject not in {"首脳陣", "巨人"}:
        speaker = _re.sub(r"(監督|コーチ)$", "", manager_subject).strip()
        if speaker:
            metadata["speaker"] = speaker
        if manager_subject.endswith("監督"):
            metadata["role"] = "監督"
        elif "コーチ" in manager_subject:
            metadata["role"] = "コーチ"
        return metadata

    player_name = ""
    if notice_subject and notice_subject not in {"巨人", "選手", "出場選手"}:
        player_name = notice_subject
    else:
        player_name = _compact_subject_label(source_title, summary, category)
    if player_name and player_name not in {"巨人", "選手", "首脳陣"}:
        metadata["player_name"] = player_name

    role_label = _extract_player_role_label(source_title, summary)
    if role_label and not role_label.startswith("この"):
        for suffix in PLAYER_ROLE_SUFFIXES:
            if role_label.endswith(suffix):
                metadata["role"] = "投手" if suffix == "投手" else "選手"
                break
    if "role" not in metadata and article_subtype in {"lineup", "postgame", "pregame", "player", "notice", "recovery", "farm"}:
        metadata["role"] = "選手"
    if metadata.get("player_name") and any(marker in f"{source_title} {summary}" for marker in ("コメント", "談話", "一問一答", "発言", "語った", "話した")):
        metadata["speaker"] = metadata["player_name"]
    return metadata


def _log_title_player_name_unresolved(
    logger: logging.Logger,
    *,
    source_url: str,
    source_name: str,
    category: str,
    article_subtype: str,
    source_title: str,
    rewritten_title: str,
) -> None:
    payload = {
        "event": "title_player_name_review",
        "reason": "title_player_name_unresolved",
        "source_url": source_url,
        "source_name": source_name,
        "category": category,
        "article_subtype": article_subtype,
        "source_title": source_title,
        "candidate_title": rewritten_title,
    }
    logger.warning(json.dumps(payload, ensure_ascii=False))


def _apply_title_player_name_backfill(
    *,
    rewritten_title: str,
    source_title: str,
    source_body: str,
    summary: str,
    category: str,
    article_subtype: str,
    manager_subject: str = "",
    notice_subject: str = "",
    logger: logging.Logger | None = None,
    source_name: str = "",
    source_url: str = "",
) -> tuple[str, str]:
    metadata = _build_title_player_name_backfill_metadata(
        source_title,
        summary,
        category,
        article_subtype,
        manager_subject=manager_subject,
        notice_subject=notice_subject,
    )
    result = backfill_title_player_name(
        existing_title=rewritten_title,
        source_title=source_title,
        body=source_body,
        summary=summary,
        metadata=metadata,
    )
    final_title = _trim_display_title(result.title or rewritten_title)
    comparison_title = source_title
    if result.review_reason == "title_player_name_unresolved":
        comparison_title = final_title
        if logger is not None:
            _log_title_player_name_unresolved(
                logger,
                source_url=source_url,
                source_name=source_name,
                category=category,
                article_subtype=article_subtype,
                source_title=source_title,
                rewritten_title=final_title,
            )
    return final_title, comparison_title


RAINOUT_SLIDE_TITLE_RE = _re.compile(r"(?:雨天中止|雨で中止).*(?:スライド登板|先発予定)|(?:スライド登板).*(?:雨天中止|先発予定)")
FARM_LINEUP_TITLE_RE = _re.compile(r"(?:二軍|２軍|2軍|ファーム).*(?:スタメン|オーダー|打順|1⃣|2⃣|3⃣|4⃣|1番|2番|3番|4番)|(?:スタメン|オーダー|打順|1⃣|2⃣|3⃣|4⃣|1番|2番|3番|4番).*(?:二軍|２軍|2軍|ファーム)")
FARM_RESULT_TITLE_RE = _re.compile(r"(?:二軍|２軍|2軍|ファーム).*(?:\d+\s*[-－]\s*\d+|勝利|白星|敗戦|本塁打|無失点|猛打賞|マルチ)")
PLAYER_DEREGISTER_TITLE_RE = _re.compile(r"(?:出場選手)?登録を?抹消|登録抹消")
PLAYER_REGISTER_TITLE_RE = _re.compile(r"(?:出場選手)?登録|一軍登録|再登録")
PLAYER_RETURN_TITLE_RE = _re.compile(r"実戦復帰|復帰(?:へ前進|見込み|予定|間近)?")
PLAYER_JOIN_TITLE_RE = _re.compile(r"(?:一軍|チーム)?合流|昇格")
TITLE_VENUE_MARKERS = (
    "甲子園",
    "東京ドーム",
    "ジャイアンツ球場",
    "神宮",
    "横浜",
    "ナゴヤ",
    "バンテリン",
    "マツダ",
    "ZOZOマリン",
    "PayPay",
    "楽天モバイル",
    "京セラ",
    "エスコン",
    "しずてつスタジアム草薙",
)


def _extract_title_opponent(source_text: str) -> str:
    for marker in NPB_TEAM_MARKERS:
        if marker in {"巨人", "読売ジャイアンツ"}:
            continue
        if marker in source_text:
            return marker
    return ""


def _extract_title_venue(source_text: str) -> str:
    for marker in TITLE_VENUE_MARKERS:
        if marker in source_text:
            return marker
    return ""


def _has_pregame_numeric_hint(source_text: str) -> bool:
    return bool(RECORD_TOKEN_RE.search(source_text) or LABELED_DECIMAL_TOKEN_RE.search(source_text))


def _has_streaming_hint(source_text: str) -> bool:
    return any(marker in source_text for marker in ("配信中", "アーカイブ", "GIANTS TV", "Giants TV", "GIANTS_TV"))


def _extract_game_subject_fallback(source_text: str) -> str:
    patterns = (
        r"([一-龥々ァ-ヴー]{2,6})(?:投手|捕手|選手)?(?:\d+日)?スライド登板",
        r"([一-龥々ァ-ヴー]{2,6})(?:投手|捕手|選手)?先発",
    )
    for pattern in patterns:
        for match in _re.finditer(pattern, source_text):
            candidate = match.group(1).strip()
            if (
                not candidate
                or candidate in {"巨人", "読売ジャイアンツ"}
                or candidate in {"予告先発", "先発"}
                or candidate in NPB_TEAM_MARKERS
                or candidate in TITLE_VENUE_MARKERS
                or candidate.endswith("球場")
            ):
                continue
            return candidate
    return ""


def _normalize_game_story_subject(subject: str) -> str:
    normalized = (subject or "").strip()
    for marker in NPB_TEAM_MARKERS:
        normalized = _re.sub(rf"^{_re.escape(marker)}[・･]?", "", normalized)
    normalized = _re.sub(r"(投手|捕手|内野手|外野手|選手)$", "", normalized).strip()
    if (
        not normalized
        or normalized in {"巨人", "選手", "先発", "予告", "登板"}
        or any(marker in normalized for marker in ("ブルペン", "打線", "ベンチ"))
    ):
        return ""
    return normalized


def _rewrite_display_title_with_template(title: str, summary: str, category: str, has_game: bool) -> tuple[str, str]:
    clean_title = _clean_display_title_text(title)
    clean_summary = _strip_html(summary or "").strip()
    source_text = _strip_html(f"{title} {summary}")
    subject = _short_subject_name(title, summary, category) or "巨人"
    status_subject = subject
    generic_player_status_subject = ""
    if category == "選手情報":
        role_label = _extract_player_role_label(title, summary)
        if (
            role_label
            and role_label.endswith("選手")
            and not role_label.startswith("この")
            and role_label.startswith(subject)
            and f"{subject}選手" in source_text
        ):
            generic_player_status_subject = role_label
    notice_subject = ""
    notice_type = ""
    if category == "選手情報" and _is_notice_template_story(title, summary, category):
        notice_subject, notice_type = _extract_notice_subject_and_type(title, summary)
        if notice_subject:
            subject = notice_subject
            status_subject = notice_subject
        if generic_player_status_subject and notice_subject and generic_player_status_subject.startswith(notice_subject):
            status_subject = generic_player_status_subject
    if subject in TITLE_VENUE_MARKERS or subject.endswith("球場") or subject in {"予告先発", "先発"}:
        subject = "巨人"
        status_subject = subject
    if category == "試合速報" and subject == "巨人":
        player_subject = _compact_subject_label(title, summary, "選手情報")
        if player_subject and player_subject not in TITLE_VENUE_MARKERS and not player_subject.endswith("球場"):
            subject = player_subject
            status_subject = player_subject
        if subject == "巨人":
            fallback_subject = _extract_game_subject_fallback(source_text)
            if fallback_subject:
                subject = fallback_subject
                status_subject = fallback_subject
    manager_display_subject = subject
    if category == "首脳陣":
        manager_label = _extract_subject_label(title, summary, category)
        if manager_label not in {"", "首脳陣", "巨人"}:
            subject = _re.sub(r"(監督|コーチ)$", "", manager_label).strip()
            manager_display_subject = manager_label
    quote = _extract_quote_phrases(f"{title}\n{summary}", max_phrases=1)
    quote_text = quote[0] if quote else ""
    subtype = _detect_article_subtype(title, summary, category, has_game)
    opponent = _extract_title_opponent(source_text)
    venue = _extract_title_venue(source_text)
    game_subject = _normalize_game_story_subject(subject) if category == "試合速報" else ""

    def _result(text: str, template_key: str, max_chars: int = 38) -> tuple[str, str]:
        return _trim_display_title(text, max_chars=max_chars), template_key

    if category == "選手情報":
        if "フォーム" in source_text or "助言" in source_text or "修正" in source_text:
            return _result(f"{subject}、フォーム変更 関連情報", "player_mechanics_generic")
        if PLAYER_DEREGISTER_TITLE_RE.search(source_text):
            return _result(f"{status_subject}、登録抹消 関連情報", "player_status_deregister")
        if PLAYER_JOIN_TITLE_RE.search(source_text):
            return _result(f"{status_subject}、一軍合流 関連情報", "player_status_join")
        if PLAYER_REGISTER_TITLE_RE.search(source_text):
            if notice_type in {"一軍登録", "再登録"}:
                return _result(f"{status_subject}、{notice_type} 関連情報", "player_status_register")
            return _result(f"{status_subject}、登録に関する関連情報", "player_status_register")
        if PLAYER_RETURN_TITLE_RE.search(source_text) or "昇格" in source_text or "一軍" in source_text or "復帰" in source_text:
            if generic_player_status_subject:
                status_subject = generic_player_status_subject
            return _result(f"{status_subject}、昇格・復帰 関連情報", "player_status_return")
        if quote_text:
            return _result(f"{subject}「{quote_text}」 関連発言", "player_quote")
        return _result(f"{subject}の現状整理 関連情報", "player_generic")

    if category == "首脳陣":
        if quote_text and ("若手" in source_text or "競争" in source_text):
            return _result(
                f"{manager_display_subject}「{quote_text}」 若手起用で序列はどう動くか",
                "manager_quote_youth",
                max_chars=40,
            )
        if quote_text and ("スタメン" in source_text or "打順" in source_text or "起用" in source_text):
            return _result(f"{manager_display_subject}「{quote_text}」 スタメン関連発言", "manager_quote_lineup")
        if quote_text:
            return _result(f"{manager_display_subject}「{quote_text}」 ベンチ関連発言", "manager_quote_generic")
        return _result(f"{subject}コメント整理 ベンチ関連の発言ポイント", "manager_generic")

    if category == "試合速報":
        if "スライド登板" in source_text or RAINOUT_SLIDE_TITLE_RE.search(source_text):
            if "雨天中止" in source_text or "雨で中止" in source_text:
                return _result(f"{subject}、雨天中止スライド登板 関連情報", "game_rainout_slide_rainout")
            if venue:
                return _result(f"{subject}、{venue}スライド登板 関連情報", "game_rainout_slide_venue")
            if opponent:
                return _result(f"{subject}、{opponent}戦スライド登板 関連情報", "game_rainout_slide_opponent")
            return _result(f"{subject}、スライド登板 関連情報", "game_rainout_slide_generic")
        if subtype == "lineup":
            body = clean_title.replace("今日の", "").replace("スタメン発表", "").replace("発表", "").strip()
            capped = body[:25].rstrip()
            if capped:
                return _result(f"巨人スタメン {capped}", "game_lineup")
            return _result("巨人スタメン", "game_lineup")
        if subtype == "live_update":
            state_match = _re.search(r"(\d+回[表裏]?)", source_text)
            score = SCORE_TOKEN_RE.search(source_text)
            state_label = state_match.group(1) if state_match else "途中経過"
            if any(marker in source_text for marker in ("勝ち越し", "逆転")) and score:
                return _result(f"巨人{state_label} {score.group(0)} どこで流れが変わったか", "game_live_swing")
            if "同点" in source_text and score:
                return _result(f"巨人{state_label} {score.group(0)} 同点の試合状況", "game_live_tie")
            if score:
                return _result(f"巨人{state_label} {score.group(0)} 途中経過のポイント", "game_live_score")
            return _result(f"巨人{state_label} 途中経過のポイント", "game_live_generic")
        if subtype == "postgame":
            score = SCORE_TOKEN_RE.search(source_text)
            if any(marker in source_text for marker in ("完封負け", "0封負け", "打線が沈黙", "攻略できず")):
                base = f"巨人{opponent}戦 打線沈黙 試合内容の整理" if opponent else "巨人戦 打線沈黙 試合内容の整理"
                return _result(base, "game_postgame_shutout")
            if any(marker in source_text for marker in ("決勝打", "サヨナラ", "逆転")):
                base = f"巨人{opponent}戦 終盤の一打で動いた試合" if opponent else "巨人戦 終盤の一打で動いた試合"
                return _result(base, "game_postgame_clutch")
            if score and any(marker in source_text for marker in ("本日のヒーロー", "HERO IS HERE", "ヒーロー")):
                return _result(f"巨人{score.group(0)} 試合を決めたヒーロー", "game_postgame_hero")
            if game_subject:
                if "一問一答" in source_text or quote_text:
                    base = f"巨人{opponent}戦 {game_subject}の試合後発言整理" if opponent else f"巨人戦 {game_subject}の試合後発言整理"
                    return _result(base, "game_postgame_subject_comment")
                if any(marker in source_text for marker in ("強み", "投球術", "分析")):
                    base = f"巨人{opponent}戦 {game_subject}の強み 試合後の整理" if opponent else f"巨人戦 {game_subject}の強み 試合後の整理"
                    return _result(base, "game_postgame_subject_analysis")
                if any(marker in source_text for marker in ("勝目", "勝利", "白星", "好投", "快投", "本塁打", "打点", "猛打賞", "連勝")):
                    base = f"巨人{opponent}戦 {game_subject}、試合での見せ場" if opponent else f"巨人戦 {game_subject}、試合での見せ場"
                    return _result(base, "game_postgame_subject")
            if any(marker in source_text for marker in ("とっておきメモ", "証言")):
                base = f"巨人{opponent}戦 勝利を支えた材料の整理" if opponent else "巨人戦 勝利を支えた材料の整理"
                return _result(base, "game_postgame_supporting_point")
            if score:
                if any(marker in source_text for marker in ("敗れ", "敗戦", "黒星")):
                    return _result(f"巨人{score.group(0)} 敗戦の分岐点 試合の流れ", "game_postgame_loss")
                if any(marker in source_text for marker in ("勝利", "白星", "連勝")):
                    return _result(f"巨人{score.group(0)} 勝利の分岐点 試合の流れ", "game_postgame_win")
                return _result(f"巨人{score.group(0)} 試合の流れを分けたポイント", "game_postgame_score")
            if opponent:
                return _result(f"巨人{opponent}戦 試合の流れを分けたポイント", "game_postgame_opponent")
            return _result("巨人戦 試合の流れを分けたポイント", "game_postgame_generic")
        if subject not in {"", "巨人", "選手", "予告", "先発", "登板"} and any(marker in source_text for marker in ("予告先発", "先発", "登板")):
            if opponent:
                return _result(f"巨人{opponent}戦 {subject}先発 試合前情報", "game_pregame_subject_starter")
            return _result(f"巨人戦 {subject}先発 試合前情報", "game_pregame_subject_starter")
        if "予告先発" in source_text and _has_pregame_numeric_hint(source_text):
            if opponent:
                return _result(f"巨人{opponent}戦 予告先発 関連数字情報", "game_pregame_numeric")
            return _result("巨人戦 予告先発 関連数字情報", "game_pregame_numeric")
        if any(marker in source_text for marker in ("初打席", "プロ初")):
            if opponent:
                return _result(f"巨人{opponent}戦 初打席の注目選手", "game_pregame_first_at_bat")
            return _result("巨人戦 初打席の注目選手情報", "game_pregame_first_at_bat")
        if game_subject:
            if opponent:
                return _result(f"巨人{opponent}戦 {game_subject}に関する試合前情報", "game_pregame_subject")
            return _result(f"巨人戦 {game_subject}に関する試合前情報", "game_pregame_subject")
        if venue:
            if opponent:
                return _result(f"巨人{opponent}戦 {venue}に関する試合前情報", "game_pregame_venue")
            return _result(f"巨人戦 {venue}に関する試合前情報", "game_pregame_venue")
        if opponent:
            return _result(f"巨人{opponent}戦 当日カードの試合前情報", "game_pregame_opponent")
        return _result("巨人戦 当日カードの試合前情報", "game_pregame_generic")

    if category == "補強・移籍":
        if "外国人" in source_text:
            return _result("巨人の新外国人補強 関連情報", "reinforcement_foreign")
        if "トレード" in source_text or "移籍" in source_text:
            return _result("巨人の補強・移籍 最新関連情報", "reinforcement_trade")
        return _result("巨人補強の整理 関連トピック", "reinforcement_generic")

    if category == "ドラフト・育成":
        if subtype == "farm_lineup" or FARM_LINEUP_TITLE_RE.search(source_text):
            return _result("巨人二軍スタメン 当日カード試合前情報", "farm_lineup")
        score = SCORE_TOKEN_RE.search(source_text)
        if FARM_RESULT_TITLE_RE.search(source_text) and score:
            if _has_streaming_hint(source_text):
                return _result(f"巨人二軍 {score.group(0)} 配信試合のポイント", "farm_result_stream")
            if "降雨コールド" in source_text:
                return _result(f"巨人二軍 {score.group(0)} 降雨コールドのポイント", "farm_result_rainout")
            return _result(f"巨人二軍 {score.group(0)} 結果のポイント", "farm_result_score")

    return _result(clean_title or "巨人ニュース", "fallback_clean_title")


def rewrite_display_title(title: str, summary: str, category: str, has_game: bool) -> str:
    rewritten_title, _template_key = _rewrite_display_title_with_guard(
        title,
        summary,
        category,
        has_game,
    )
    return rewritten_title


def _log_title_template_selected(
    logger: logging.Logger,
    source_url: str,
    original_title: str,
    rewritten_title: str,
    template_key: str,
    category: str,
    article_subtype: str,
) -> None:
    payload = {
        "event": "title_template_selected",
        "source_url": source_url,
        "category": category,
        "article_subtype": article_subtype,
        "template": template_key,
        "original_title": original_title,
        "rewritten_title": rewritten_title,
    }
    logger.info(json.dumps(payload, ensure_ascii=False))


def _log_title_validator_reroll(
    logger: logging.Logger,
    *,
    source_url: str,
    category: str,
    article_subtype: str,
    fail_axes: list[str],
    inferred_subtype: str,
    expected_first_block: str,
    candidate_title: str,
    rerolled_title: str,
) -> None:
    payload = {
        "event": "title_validator_reroll",
        "source_url": source_url,
        "category": category,
        "article_subtype": article_subtype,
        "fail_axis": fail_axes,
        "inferred_subtype": inferred_subtype,
        "expected_first_block": expected_first_block,
        "candidate_title": candidate_title,
        "rerolled_title": rerolled_title,
    }
    logger.warning(json.dumps(payload, ensure_ascii=False))


def _rewrite_display_title_with_guard(
    title: str,
    summary: str,
    category: str,
    has_game: bool,
    *,
    article_subtype: str = "",
    logger: logging.Logger | None = None,
    source_url: str = "",
) -> tuple[str, str]:
    resolved_subtype = article_subtype or _detect_article_subtype(title, summary, category, has_game)
    rewritten_title, template_key = _rewrite_display_title_with_template(title, summary, category, has_game)
    if not _title_validator_supports_subtype(resolved_subtype):
        return rewritten_title, template_key

    validation = _validate_title_candidate(rewritten_title, resolved_subtype)
    if validation["ok"]:
        return rewritten_title, template_key

    rerolled_title = _trim_display_title(_build_title_reroll_title(rewritten_title, resolved_subtype))
    rerolled_validation = _validate_title_candidate(rerolled_title, resolved_subtype)
    if not rerolled_validation["ok"]:
        rerolled_title = _trim_display_title(_build_title_reroll_title("", resolved_subtype))

    if logger is not None:
        _log_title_validator_reroll(
            logger,
            source_url=source_url,
            category=category,
            article_subtype=resolved_subtype,
            fail_axes=list(validation["fail_axes"]),
            inferred_subtype=str(validation.get("inferred_subtype") or ""),
            expected_first_block=str(validation.get("expected_first_block") or ""),
            candidate_title=rewritten_title,
            rerolled_title=rerolled_title,
        )

    return rerolled_title, f"{template_key}_title_reroll"


def _log_body_validator_reroll(
    logger: logging.Logger,
    *,
    source_url: str,
    category: str,
    article_subtype: str,
    fail_axes: list[str],
    expected_first_block: str,
    actual_first_block: str,
    missing_required_blocks: list[str],
    actual_block_order: list[str],
) -> None:
    payload = {
        "event": "body_validator_reroll",
        "source_url": source_url,
        "category": category,
        "article_subtype": article_subtype,
        "fail_axis": fail_axes,
        "expected_first_block": expected_first_block,
        "actual_first_block": actual_first_block,
        "missing_required_blocks": missing_required_blocks,
        "actual_block_order": actual_block_order,
    }
    logger.warning(json.dumps(payload, ensure_ascii=False))


def _log_body_validator_fail(
    logger: logging.Logger,
    *,
    source_url: str,
    category: str,
    article_subtype: str,
    fail_axes: list[str],
    expected_first_block: str,
    actual_first_block: str,
    has_source_block: bool,
    stop_reason: str = "",
) -> None:
    payload = {
        "event": "body_validator_fail",
        "source_url": source_url,
        "category": category,
        "article_subtype": article_subtype,
        "fail_axis": fail_axes,
        "expected_first_block": expected_first_block,
        "actual_first_block": actual_first_block,
        "has_source_block": has_source_block,
    }
    if stop_reason:
        payload["stop_reason"] = stop_reason
    logger.warning(json.dumps(payload, ensure_ascii=False))


def _log_manager_body_template_applied(
    logger: logging.Logger,
    post_id: int,
    title: str,
    quote_count: int,
    section_count: int,
    template_version: str = MANAGER_BODY_TEMPLATE_VERSION,
) -> None:
    payload = {
        "event": "manager_body_template_applied",
        "post_id": post_id,
        "title": title,
        "quote_count": quote_count,
        "section_count": section_count,
        "template_version": template_version,
    }
    logger.info(json.dumps(payload, ensure_ascii=False))


def _log_game_body_template_applied(
    logger: logging.Logger,
    post_id: int,
    title: str,
    article_subtype: str,
    section_count: int,
    numeric_count: int,
    name_count: int,
    template_version: str = GAME_BODY_TEMPLATE_VERSION,
) -> None:
    payload = {
        "event": "game_body_template_applied",
        "post_id": post_id,
        "title": title,
        "subtype": article_subtype,
        "section_count": section_count,
        "numeric_count": numeric_count,
        "name_count": name_count,
        "template_version": template_version,
    }
    logger.info(json.dumps(payload, ensure_ascii=False))


def _log_farm_body_template_applied(
    logger: logging.Logger,
    post_id: int,
    title: str,
    article_subtype: str,
    section_count: int,
    numeric_count: int,
    is_drafted_player: bool,
    template_version: str = FARM_BODY_TEMPLATE_VERSION,
) -> None:
    payload = {
        "event": "farm_body_template_applied",
        "post_id": post_id,
        "title": title,
        "subtype": article_subtype,
        "section_count": section_count,
        "numeric_count": numeric_count,
        "is_drafted_player": is_drafted_player,
        "template_version": template_version,
    }
    logger.info(json.dumps(payload, ensure_ascii=False))


def _log_notice_body_template_applied(
    logger: logging.Logger,
    post_id: int,
    title: str,
    notice_type: str,
    section_count: int,
    has_player_name: bool,
    has_numeric_record: bool,
    template_version: str = NOTICE_BODY_TEMPLATE_VERSION,
) -> None:
    payload = {
        "event": "notice_body_template_applied",
        "post_id": post_id,
        "title": title,
        "notice_type": notice_type,
        "section_count": section_count,
        "has_player_name": has_player_name,
        "has_numeric_record": has_numeric_record,
        "template_version": template_version,
    }
    logger.info(json.dumps(payload, ensure_ascii=False))


def _log_recovery_body_template_applied(
    logger: logging.Logger,
    post_id: int,
    title: str,
    injury_part: str,
    return_timing: str,
    section_count: int,
    template_version: str = RECOVERY_BODY_TEMPLATE_VERSION,
) -> None:
    payload = {
        "event": "recovery_body_template_applied",
        "post_id": post_id,
        "title": title,
        "injury_part": injury_part,
        "return_timing": return_timing,
        "section_count": section_count,
        "template_version": template_version,
    }
    logger.info(json.dumps(payload, ensure_ascii=False))


def _log_social_body_template_applied(
    logger: logging.Logger,
    post_id: int,
    title: str,
    final_category: str,
    source_type_indicator: str,
    section_count: int,
    quote_count: int,
    template_version: str = SOCIAL_BODY_TEMPLATE_VERSION,
) -> None:
    payload = {
        "event": "social_body_template_applied",
        "post_id": post_id,
        "title": title,
        "final_category": final_category,
        "source_type_indicator": source_type_indicator,
        "section_count": section_count,
        "quote_count": quote_count,
        "template_version": template_version,
    }
    logger.info(json.dumps(payload, ensure_ascii=False))


def _log_media_xpost_embedded(
    logger: logging.Logger,
    post_id: int,
    title: str,
    source_type: str,
    media_handle: str,
    media_url: str,
    quote_account: str = "",
    embed_section_type: str = "",
    match_reason: str = "",
    match_score: int = 0,
    quote_index: int = 1,
    quote_count_in_article: int = 1,
    position: str = MEDIA_XPOST_POSITION,
) -> None:
    payload = {
        "event": "media_xpost_embedded",
        "post_id": post_id,
        "title": title,
        "source_type": source_type,
        "media_handle": media_handle,
        "quote_account": quote_account or media_handle,
        "media_url": media_url,
        "embed_section_type": embed_section_type,
        "match_reason": match_reason,
        "match_score": match_score,
        "quote_index": quote_index,
        "quote_count_in_article": quote_count_in_article,
        "position": position,
    }
    logger.info(json.dumps(payload, ensure_ascii=False))


def _log_media_xpost_evaluated(
    logger: logging.Logger,
    post_id: int,
    title: str,
    category: str,
    article_subtype: str,
    selector_type: str,
    is_target: bool,
) -> None:
    payload = {
        "event": "media_xpost_evaluated",
        "post_id": post_id,
        "title": title,
        "category": category,
        "article_subtype": article_subtype,
        "selector_type": selector_type,
        "is_target": bool(is_target),
    }
    logger.info(json.dumps(payload, ensure_ascii=False))


def _log_media_xpost_skipped(
    logger: logging.Logger,
    post_id: int,
    title: str,
    category: str,
    article_subtype: str,
    skip_meta: dict[str, object],
) -> None:
    payload = {
        "event": "media_xpost_skipped",
        "post_id": post_id,
        "title": title,
        "category": category,
        "article_subtype": article_subtype,
        "skip_reason": skip_meta.get("skip_reason", "other"),
        "pool_size_checked": int(skip_meta.get("pool_size_checked", 0) or 0),
        "best_candidate_score": skip_meta.get("best_candidate_score"),
        "best_candidate_handle": skip_meta.get("best_candidate_handle", ""),
        "best_candidate_age_hours": skip_meta.get("best_candidate_age_hours"),
    }
    logger.info(json.dumps(payload, ensure_ascii=False))


def _log_x_post_ai_generated(
    logger: logging.Logger,
    post_id: int,
    category: str,
    article_subtype: str,
    ai_mode: str,
    generated_length: int,
    fallback_used: bool,
    preview_text: str,
) -> None:
    payload = {
        "event": "x_post_ai_generated",
        "post_id": post_id,
        "category": category,
        "article_subtype": article_subtype,
        "ai_mode": ai_mode,
        "generated_length": generated_length,
        "fallback_used": bool(fallback_used),
        "preview_text": preview_text,
    }
    logger.info(json.dumps(payload, ensure_ascii=False))


def _log_x_post_ai_failed(
    logger: logging.Logger,
    post_id: int,
    category: str,
    error_type: str,
    fallback_used: bool,
    article_subtype: str = "",
) -> None:
    payload = {
        "event": "x_post_ai_failed",
        "post_id": post_id,
        "category": category,
        "article_subtype": article_subtype,
        "error_type": error_type or "unknown",
        "fallback_used": bool(fallback_used),
    }
    logger.info(json.dumps(payload, ensure_ascii=False))


def _log_publish_gate_skipped(
    logger: logging.Logger,
    post_id: int,
    title: str,
    article_subtype: str,
    category: str,
    reason: str,
) -> None:
    payload = {
        "event": reason,
        "skip_reason": reason,
        "post_id": post_id,
        "title": title,
        "article_subtype": article_subtype,
        "category": category,
    }
    logger.info(json.dumps(payload, ensure_ascii=False))


def _log_publish_blocked_by_quality_guard(
    logger: logging.Logger,
    post_id: int,
    title: str,
    article_subtype: str,
    category: str,
    quality_guard: dict[str, object],
) -> None:
    payload = {
        "event": "publish_blocked_by_quality_guard",
        "post_id": post_id,
        "title": title,
        "article_subtype": article_subtype,
        "category": category,
        "reasons": list(quality_guard.get("reasons") or []),
        "core_char_count": int(quality_guard.get("core_char_count") or 0),
        "min_chars": int(quality_guard.get("min_chars") or 0),
    }
    leak_markers = [marker for marker in quality_guard.get("leak_markers") or [] if marker]
    if leak_markers:
        payload["leak_markers"] = leak_markers
    logger.info(json.dumps(payload, ensure_ascii=False))


def _log_featured_media_observation_missing(
    logger: logging.Logger,
    post_id: int,
    title: str,
    article_subtype: str,
    category: str,
    primary_url: str = "",
    candidate_count: int = 0,
    source_type: str = "",
) -> None:
    payload = {
        "event": "featured_media_observation_missing",
        "observation_only": True,
        "post_id": post_id,
        "title": title,
        "article_subtype": article_subtype,
        "category": category,
    }
    if primary_url:
        payload["primary_url"] = primary_url
    if candidate_count:
        payload["candidate_count"] = candidate_count
    if source_type:
        payload["source_type"] = source_type
    logger.info(json.dumps(payload, ensure_ascii=False))


def _log_x_post_subtype_skipped(
    logger: logging.Logger,
    post_id: int,
    title: str,
    category: str,
    article_subtype: str,
    reason: str,
) -> None:
    payload = {
        "event": "x_post_subtype_skipped",
        "post_id": post_id,
        "title": title,
        "category": category,
        "article_subtype": article_subtype,
        "reason": reason,
    }
    logger.info(json.dumps(payload, ensure_ascii=False))


def _build_x_post_preview_for_observation(
    *,
    logger: logging.Logger,
    history: dict,
    today_str: str,
    x_post_daily_limit: int,
    post_id: int,
    title: str,
    article_url: str,
    category: str,
    summary: str,
    content_html: str,
    article_subtype: str,
    source_type: str,
    source_name: str,
) -> tuple[str, dict]:
    if source_type not in {"news", "social_news"}:
        return "", {}
    if article_subtype == "live_update" and not x_post_for_live_update_enabled():
        return "", {}

    requested_ai_mode = resolve_effective_x_post_ai_mode(category)
    if requested_ai_mode == "none":
        return "", {}

    generation_key = f"x_ai_generation_count_{today_str}"
    generation_count = int(history.get(generation_key, 0) or 0)
    if generation_count >= x_post_daily_limit:
        preview_text, meta = build_x_post_text_with_meta(
            title,
            article_url,
            category,
            summary=summary,
            content_html=content_html,
            article_subtype=article_subtype,
            source_type=source_type,
            source_name=source_name,
            ai_mode_override="none",
        )
        meta["requested_ai_mode"] = requested_ai_mode
        meta["fallback_used"] = True
        meta["failure_reason"] = "daily_limit_reached"
        meta["generated_length"] = len(preview_text.replace(article_url, "x" * 23)) if article_url else len(preview_text)
        _log_x_post_ai_failed(
            logger,
            post_id,
            category,
            "daily_limit_reached",
            True,
            article_subtype=meta.get("article_subtype", article_subtype),
        )
        _log_x_post_ai_generated(
            logger,
            post_id,
            category,
            meta.get("article_subtype", article_subtype),
            requested_ai_mode,
            int(meta.get("generated_length", 0) or 0),
            True,
            preview_text,
        )
        return preview_text, meta

    preview_text, meta = build_x_post_text_with_meta(
        title,
        article_url,
        category,
        summary=summary,
        content_html=content_html,
        article_subtype=article_subtype,
        source_type=source_type,
        source_name=source_name,
    )
    if meta.get("ai_attempted"):
        history[generation_key] = generation_count + 1
    if meta.get("failure_reason"):
        _log_x_post_ai_failed(
            logger,
            post_id,
            category,
            str(meta.get("failure_reason", "")),
            bool(meta.get("fallback_used")),
            article_subtype=meta.get("article_subtype", article_subtype),
        )
    _log_x_post_ai_generated(
        logger,
        post_id,
        category,
        meta.get("article_subtype", article_subtype),
        meta.get("effective_ai_mode", requested_ai_mode) or requested_ai_mode,
        int(meta.get("generated_length", 0) or 0),
        bool(meta.get("fallback_used")),
        preview_text,
    )
    return preview_text, meta


def _counter_to_plain_dict(counter: Counter) -> dict[str, int]:
    return {key: counter[key] for key in sorted(counter) if counter[key]}


def _matching_giants_keywords(text: str) -> list[str]:
    return [keyword for keyword in GIANTS_KEYWORDS if keyword in (text or "")]


def _skip_reasons_with_samples(
    skip_reason_counts: Counter,
    *,
    not_giants_related_sample_titles: list[str] | None = None,
    skip_reason_sample_titles: dict[str, list[str]] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = _counter_to_plain_dict(skip_reason_counts)
    if not_giants_related_sample_titles:
        payload["not_giants_related_sample_titles"] = not_giants_related_sample_titles[:3]
    for reason, titles in sorted((skip_reason_sample_titles or {}).items()):
        if titles:
            payload[f"{reason}_sample_titles"] = titles[:3]
    return payload


def _append_skip_reason_sample(
    sample_titles: dict[str, list[str]],
    reason: str,
    title: str,
    *,
    limit: int = 3,
) -> None:
    clean = (title or "").strip()
    if not clean:
        return
    bucket = sample_titles.setdefault(reason, [])
    if clean in bucket or len(bucket) >= limit:
        return
    bucket.append(clean[:80])


def _log_not_giants_related_skip(
    logger: logging.Logger,
    *,
    title: str,
    post_url: str,
    source_name: str,
    detected_keywords: list[str],
):
    payload = {
        "event": "not_giants_related_skip",
        "title": title,
        "post_url": post_url,
        "source_name": source_name,
        "detected_keywords": detected_keywords,
    }
    logger.info(json.dumps(payload, ensure_ascii=False))

# ──────────────────────────────────────────────────────────
# X投稿URLを取得（twitter.com形式に統一）
# ──────────────────────────────────────────────────────────
def get_post_url(entry) -> str:
    url = entry.get("link", "")
    return url.replace("https://x.com/", "https://twitter.com/")

# ──────────────────────────────────────────────────────────
# メイン処理
# ──────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="RSSHub経由でX投稿を取得してWP下書き生成")
    parser.add_argument("--dry-run", action="store_true", help="WP投稿せず結果を表示のみ")
    parser.add_argument("--draft-only", action="store_true", help="WordPressに下書きだけ作成し、公開とX投稿を行わない")
    parser.add_argument("--limit", type=int, default=10, help="1回の実行で公開する最大記事数（デフォルト10）")
    parser.add_argument("--article-ai-mode", choices=["auto", "grok", "gemini", "none"], help="この実行に限り記事AIのモードを上書きする")
    args = parser.parse_args()

    logger = setup_logger()

    # 多重起動防止ロック
    lock_file = ROOT / "logs" / "rss_fetcher.lock"
    if lock_file.exists():
        logger.warning("=== 既に実行中のため終了（ロックファイルあり） ===")
        return
    lock_file.touch()
    try:
        _main(args, logger)
    finally:
        lock_file.unlink(missing_ok=True)


def _check_giants_game_today_yahoo() -> tuple:
    game_id, opponent, venue = _find_today_giants_game_info_yahoo()
    return bool(game_id), opponent, venue


def check_giants_game_today() -> tuple:
    """巨人の今日の試合があるか確認。(has_game: bool, opponent: str, venue: str) を返す。
    取得失敗時は (False, "", "") を返してフェイルクローズに倒す。"""
    import urllib.request as _ur
    from datetime import date
    import re as _re
    logger = logging.getLogger("rss_fetcher")

    yahoo_has_game, yahoo_opponent, yahoo_venue = _check_giants_game_today_yahoo()
    if yahoo_has_game:
        return yahoo_has_game, yahoo_opponent, yahoo_venue

    today = date.today()
    today_str = today.strftime("%Y-%m-%d")
    # NPB公式 月別日程ページ (4月なら schedule_04_detail.html)
    month_str = today.strftime("%m")
    url = f"https://npb.jp/games/{today.year}/schedule_{month_str}_detail.html"

    try:
        req = _ur.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with _ur.urlopen(req, timeout=10) as res:
            html = res.read().decode("utf-8", errors="ignore")

        # 今日の日付セクションを探す（NPBページは "M/D" 形式で日付が入る）
        # 巨人＝「読売」「Giants」「G」のいずれかが同じ行/セクションにあるか確認
        # 日付は例: "4/13" or "4月13日"
        day_pattern = f"{today.month}/{today.day}"
        day_pattern2 = f"{today.month}月{today.day}日"

        # ページ全体を日付ブロックに分割
        # 簡易：今日の日付文字列の前後500文字に巨人関連語があるか
        for pat in [day_pattern, day_pattern2]:
            idx = html.find(pat)
            while idx != -1:
                block = html[max(0, idx-50):idx+600]
                block_text = _re.sub(r'<[^>]+>', '', block)
                if any(kw in block_text for kw in ["読売", "Giants", "ジャイアンツ", "巨人"]):
                    # 中止・オフを除外
                    if any(ng in block_text for ng in ["中止", "オフ", "休み", "ノーゲーム"]):
                        return False, "", ""
                    # 対戦相手と球場を抽出（あれば）
                    opp_m = _re.search(r'(?:vs\.|対)\s*([^\s<&]{2,6})', block_text)
                    venue_m = _re.search(r'(東京ドーム|神宮|横浜|ナゴヤ|甲子園|マツダ|PayPay|バンテリン|ほっと|ZOZOマリン)', block_text)
                    opponent = opp_m.group(1) if opp_m else ""
                    venue    = venue_m.group(1) if venue_m else ""
                    return True, opponent, venue
                idx = html.find(pat, idx + 1)

        # 巨人戦が見つからなければ試合なし
        return False, "", ""

    except Exception as e:
        logger.warning("試合日チェック失敗（フェイルクローズ）: %s", e)
        return False, "", ""


def _main(args, logger):
    logger.info(f"=== rss_fetcher 開始 {'[DRY RUN]' if args.dry_run else ''} ===")

    # 今日の巨人戦有無を確認（試合なしの日は試合記事プロンプトを使わない）
    has_game, opponent, venue = check_giants_game_today()
    if has_game:
        logger.info(f"本日の巨人戦あり{(' vs ' + opponent) if opponent else ''}{(' @' + venue) if venue else ''}")
    else:
        logger.info("本日の巨人戦なし → 選手・コラム記事モードで実行")

    # 設定読み込み
    with open(RSS_SOURCES_FILE, encoding="utf-8") as f:
        sources = json.load(f)
    with open(KEYWORDS_FILE, encoding="utf-8") as f:
        keywords = json.load(f)

    history = load_history()

    if not args.dry_run:
        wp = WPClient()

    total = skip_dup = skip_filter = success = error = 0
    skip_reason_counts: Counter[str] = Counter()
    prepared_category_counts: Counter[str] = Counter()
    prepared_subtype_counts: Counter[str] = Counter()
    created_category_counts: Counter[str] = Counter()
    created_subtype_counts: Counter[str] = Counter()
    publish_skip_reason_counts: Counter[str] = Counter()
    publish_observation_counts: Counter[str] = Counter()
    x_skip_reason_counts: Counter[str] = Counter()
    skip_reason_sample_titles: dict[str, list[str]] = {}
    import time

    x_post_daily_limit = get_x_post_daily_limit()
    today_str = datetime.now().strftime("%Y-%m-%d")
    x_post_count = history.get(f"x_post_count_{today_str}", 0)
    x_ai_generation_count = history.get(f"x_ai_generation_count_{today_str}", 0)
    prepared_entries = []
    media_quote_pool = []
    entry_index = 0
    not_giants_related_info_count = 0
    not_giants_related_sample_titles: list[str] = []

    for source_rank, source in enumerate(sources):
        name        = source["name"]
        url         = source["url"]
        source_type = source.get("type", "news")
        raw_source_role = source.get("role")
        if isinstance(raw_source_role, list):
            source_roles = {
                str(role).strip()
                for role in raw_source_role
                if str(role).strip()
            }
        elif isinstance(raw_source_role, str) and raw_source_role.strip():
            source_roles = {raw_source_role.strip()}
        else:
            source_roles = {"article_source"}
        prepared_source_roles = sorted(source_roles)
        should_add_to_media_quote_pool = bool(source_roles & {"media_quote_pool", "media_quote_only"})
        should_articleize = "media_quote_only" not in source_roles
        logger.info(f"取得中: {name} ({url})")

        try:
            if source_type == "yahoo_realtime":
                keyword = url.replace("yahoo_realtime://", "")
                entries = fetch_yahoo_realtime_entries(keyword)
            else:
                feed    = feedparser.parse(url)
                entries = feed.entries
        except Exception as e:
            logger.error(f"フィード取得失敗 {name}: {e}")
            error += 1
            continue

        logger.info(f"  {len(entries)}件取得")
        total += len(entries)

        for entry in entries:
            post_url = get_post_url(entry)
            source_handle = _extract_handle_from_tweet_url(post_url)
            entry_title_raw = (entry.get("title", "") or "").strip()
            entry_summary_raw = entry.get("summary", "") or entry.get("description", "")
            if source_type == "social_news":
                entry_title_clean = _clean_social_entry_text(entry_title_raw)
                entry_summary_clean = _clean_social_entry_text(entry_summary_raw)
                if _is_polluted_social_entry(
                    entry_title_raw,
                    entry_summary_raw,
                    source_name=name,
                    post_url=post_url,
                ):
                    logger.debug(f"  [SKIP:SNS汚染] {entry_title_raw[:40]}")
                    skip_filter += 1
                    skip_reason_counts["sns_polluted"] += 1
                    continue
            else:
                entry_title_clean = entry_title_raw
                entry_summary_clean = entry_summary_raw
            title_text = f"{entry_title_clean} {entry_summary_clean}".strip()
            source_trust = (
                _source_trust_classify_handle(source_handle)
                if source_handle
                else _source_trust_classify_url(post_url)
            )
            logger.info(
                "  [SOURCE] url=%s source_trust=%s source_id=%s",
                post_url,
                source_trust,
                _source_id_key(post_url),
            )

            import re as _re2
            entry_title_norm = _re2.sub(r"[\s　【】「」『』〔〕（）()・\-_]", "", entry_title_clean).lower()
            if _is_history_duplicate(post_url, entry_title_norm, history):
                logger.debug(f"  [SKIP:履歴重複] {entry_title_clean[:50]}")
                skip_dup += 1
                skip_reason_counts["history_duplicate"] += 1
                _append_skip_reason_sample(skip_reason_sample_titles, "history_duplicate", entry_title_clean or post_url)
                continue

            published_at = _entry_published_datetime(entry)
            if not published_at:
                logger.debug(f"  [SKIP:日付なし] {post_url}")
                skip_filter += 1
                skip_reason_counts["missing_published_at"] += 1
                continue

            if should_add_to_media_quote_pool:
                media_quote_pool.append({
                    "source_name": name,
                    "source_type": source_type,
                    "source_roles": prepared_source_roles,
                    "source_url": post_url,
                    "title": entry_title_clean,
                    "summary": entry_summary_clean,
                    "created_at": published_at,
                })
            if not should_articleize:
                continue

            giants_signal_text = title_text
            if source_type == "social_news":
                giants_signal_text = " ".join(
                    part
                    for part in (entry_title_raw, entry_summary_raw, entry_title_clean, entry_summary_clean)
                    if part
                )

            if not is_giants_related(giants_signal_text, source_name=name, post_url=post_url):
                logger.debug(f"  [SKIP:フィルタ] {post_url}")
                if len(not_giants_related_sample_titles) < 3:
                    not_giants_related_sample_titles.append(entry_title_clean[:80] or post_url)
                if not_giants_related_info_count < 5:
                    _log_not_giants_related_skip(
                        logger,
                        title=entry_title_clean[:160],
                        post_url=post_url,
                        source_name=name,
                        detected_keywords=_matching_giants_keywords(giants_signal_text),
                    )
                    not_giants_related_info_count += 1
                skip_filter += 1
                skip_reason_counts["not_giants_related"] += 1
                continue

            category = classify_category(title_text, keywords)
            raw_title, title_preview = _prepare_source_title_context(entry_title_clean, entry)
            title = raw_title
            summary  = entry_summary_clean
            # Observation only; later consumers decide whether to use normalized outputs.
            _, category_guard_warnings = _tc_validate_category(category)
            _, tag_guard_warnings = _tc_validate_tags(prepared_source_roles)
            tag_category_warnings = category_guard_warnings + tag_guard_warnings
            if tag_category_warnings:
                logger.info(
                    "  [CLASSIFY_OBSERVE] %s → %s tag_category_warnings=%s",
                    title_preview[:40],
                    category,
                    json.dumps(tag_category_warnings, ensure_ascii=False),
                )
            entry_has_game = infer_article_has_game(title, summary, category, has_game)
            if _should_skip_stale_postgame_entry(category, title, summary, published_at, max_age_hours=36):
                logger.debug(f"  [SKIP:postgame古い] {title_preview[:40]}")
                skip_filter += 1
                skip_reason_counts["stale_postgame"] += 1
                _append_skip_reason_sample(skip_reason_sample_titles, "stale_postgame", title)
                continue
            if _should_skip_stale_player_status_entry(category, title, summary, published_at):
                logger.debug(f"  [SKIP:player_status古い] {title_preview[:40]}")
                skip_filter += 1
                skip_reason_counts["stale_player_status"] += 1
                _append_skip_reason_sample(skip_reason_sample_titles, "stale_player_status", title)
                continue

            if source_type in {"news", "social_news"}:
                if _is_promotional_video_entry(entry_title_clean, summary):
                    logger.debug(f"  [SKIP:動画プロモ] {title_preview[:40]}")
                    skip_filter += 1
                    skip_reason_counts["video_promo"] += 1
                    _append_skip_reason_sample(skip_reason_sample_titles, "video_promo", title)
                    continue
                article_subtype = _detect_article_subtype(title, summary, category, entry_has_game)
                if article_subtype == "live_update" and not ENABLE_LIVE_UPDATE_ARTICLES:
                    logger.debug(f"  [SKIP:途中経過停止中] {title_preview[:40]}")
                    skip_filter += 1
                    skip_reason_counts["live_update_disabled"] += 1
                    _append_skip_reason_sample(skip_reason_sample_titles, "live_update_disabled", title)
                    continue
                has_comment = "「" in title_text
                if source_type == "news":
                    allow_commentless_news = article_subtype in {"lineup", "farm_lineup", "postgame"}
                    if not has_comment and not allow_commentless_news:
                        logger.debug(f"  [SKIP:コメントなし] {title_preview[:40]}")
                        skip_filter += 1
                        skip_reason_counts["comment_required"] += 1
                        _append_skip_reason_sample(skip_reason_sample_titles, "comment_required", title)
                        continue
                else:
                    worthy, rescue_meta = _evaluate_authoritative_social_entry(
                        title,
                        summary,
                        category,
                        article_subtype,
                        source_name=name,
                        source_handle=source_handle,
                    )
                    if rescue_meta:
                        _log_sns_weak_rescue(logger, post_url, title, rescue_meta)
                    if not worthy:
                        logger.debug(f"  [SKIP:SNS弱い] {title_preview[:40]}")
                        skip_filter += 1
                        skip_reason_counts["social_too_weak"] += 1
                        _append_skip_reason_sample(skip_reason_sample_titles, "social_too_weak", title)
                        continue

            logger.info(f"  [HIT] {title_preview[:40]} → {category}")
            prepared_category_counts[category] += 1
            if source_type in {"news", "social_news"}:
                prepared_subtype_counts[article_subtype] += 1
            prepared_entries.append({
                "entry_index": entry_index,
                "source_rank": source_rank,
                "source_name": name,
                "source_type": source_type,
                "source_roles": prepared_source_roles,
                "entry": entry,
                "post_url": post_url,
                "title_text": title_text,
                "raw_title": raw_title,
                "category": category,
                "title": title,
                "summary": summary,
                "entry_title_norm": entry_title_norm,
                "entry_has_game": entry_has_game,
                "published_at": published_at,
                "published_day": _entry_day_key(entry),
                "history_urls": [post_url],
                "history_title_norms": [entry_title_norm] if entry_title_norm else [],
            })
            entry_index += 1

    prepared_entries = _aggregate_lineup_candidates(prepared_entries)

    yahoo_game_status = {}
    if has_game:
        try:
            yahoo_game_status = fetch_today_giants_game_status_from_yahoo()
        except Exception as e:
            logger.warning("Yahoo試合固定ページ取得失敗: %s", e)
            yahoo_game_status = {}

    if has_game and yahoo_game_status:
        filtered_prepared_entries = []
        for item in prepared_entries:
            if _should_skip_started_pregame_entry(
                item["category"],
                item["title"],
                item["summary"],
                item.get("entry_has_game", True),
                yahoo_game_status,
            ):
                _log_pregame_started_skip(
                    item["title"],
                    item.get("summary", ""),
                    item.get("post_url", ""),
                    yahoo_game_status,
                )
                skip_filter += 1
                skip_reason_counts["pregame_started"] += 1
                _append_skip_reason_sample(skip_reason_sample_titles, "pregame_started", item["title"])
                continue
            filtered_prepared_entries.append(item)
        prepared_entries = filtered_prepared_entries

    live_update_reason = ""
    game_id_for_live = yahoo_game_status.get("game_id", "")
    if has_game and yahoo_game_status and not yahoo_game_status.get("ended") and game_id_for_live:
        previous_live_state = _load_live_game_state(history, game_id_for_live)
        live_update_reason = _detect_live_update_reason(yahoo_game_status, previous_live_state)

    if has_game and not yahoo_game_status.get("ended") and not _has_primary_lineup_candidate(prepared_entries):
        try:
            yahoo_lineup_rows = fetch_today_giants_lineup_stats_from_yahoo()
        except Exception as e:
            logger.warning("Yahooスタメン固定ページ取得失敗: %s", e)
            yahoo_lineup_rows = []
        synthetic_lineup = _build_yahoo_lineup_candidate(opponent, venue, yahoo_lineup_rows, entry_index)
        if synthetic_lineup and not any(history.get(url) for url in synthetic_lineup.get("history_urls", [])):
            logger.info("  [HIT] Yahoo固定ページからスタメン補完 → 試合速報")
            prepared_category_counts["試合速報"] += 1
            prepared_subtype_counts["lineup"] += 1
            prepared_entries.append(synthetic_lineup)
            prepared_entries = sorted(prepared_entries, key=lambda item: item.get("entry_index", 0))

    if ENABLE_LIVE_UPDATE_ARTICLES and has_game and live_update_reason and not _has_primary_live_candidate(prepared_entries):
        synthetic_live = _build_yahoo_live_update_candidate(opponent, venue, yahoo_game_status, entry_index, live_update_reason)
        if synthetic_live and not any(history.get(url) for url in synthetic_live.get("history_urls", [])):
            logger.info("  [HIT] Yahoo固定ページから途中経過補完 → 試合速報 (%s)", live_update_reason)
            prepared_category_counts["試合速報"] += 1
            prepared_subtype_counts["live_update"] += 1
            prepared_entries.append(synthetic_live)
            prepared_entries = sorted(prepared_entries, key=lambda item: item.get("entry_index", 0))

    if has_game and yahoo_game_status.get("ended") and not _has_primary_postgame_candidate(prepared_entries):
        synthetic_postgame = _build_yahoo_postgame_candidate(opponent, venue, yahoo_game_status, entry_index)
        if synthetic_postgame and not any(history.get(url) for url in synthetic_postgame.get("history_urls", [])):
            logger.info("  [HIT] Yahoo固定ページから試合後補完 → 試合速報")
            prepared_category_counts["試合速報"] += 1
            prepared_subtype_counts["postgame"] += 1
            prepared_entries.append(synthetic_postgame)
            prepared_entries = sorted(prepared_entries, key=lambda item: item.get("entry_index", 0))

    if has_game and game_id_for_live:
        _save_live_game_state(history, game_id_for_live, yahoo_game_status)
        persist_history(history)

    prepared_entries = _prioritize_prepared_entries_for_creation(prepared_entries)
    prepared_entries = _annotate_duplicate_guard_contexts(prepared_entries)
    same_fire_source_urls: set[str] = set()
    same_fire_title_sources: dict[str, set[str]] = {}

    for item in prepared_entries:
        if success >= args.limit:
            logger.info(f"上限{args.limit}件に達したため終了")
            break

        source_type = item["source_type"]
        category = item["category"]
        title = item["title"]
        raw_title = item.get("raw_title") or title
        summary = item["summary"]
        post_url = item["post_url"]
        source_name = item["source_name"]
        entry_title_norm = item.get("entry_title_norm", "")
        entry_has_game = item["entry_has_game"]
        source_day_label = _format_source_day_label(item.get("published_at"))
        title_article_subtype = _detect_article_subtype(raw_title, summary, category, entry_has_game)

        if item.get("merged_source_count", 0) > 1:
            logger.info(f"  [統合] {title[:40]} ← {item['merged_source_count']}ソース")

        if source_type in {"news", "social_news"}:
            source_fact_block, source_fact_block_length = _source_fact_block_metrics(
                raw_title,
                summary,
                source_type=source_type,
                entry=item.get("entry"),
            )
            thin_source_min_chars = _thin_source_fact_block_min_chars(source_type)
            if _is_thin_source_fact_block(source_type, source_fact_block_length):
                if _should_skip_thin_source_fact_block(
                    draft_only=bool(args.draft_only),
                    source_type=source_type,
                    source_fact_block_length=source_fact_block_length,
                ):
                    logger.info(
                        json.dumps(
                            {
                                "event": "article_skipped_thin_source",
                                "title": raw_title,
                                "post_url": post_url,
                                "category": category,
                                "article_subtype": title_article_subtype,
                                "source_type": source_type,
                                "source_fact_block_length": source_fact_block_length,
                                "min_chars": thin_source_min_chars,
                            },
                            ensure_ascii=False,
                        )
                    )
                    skip_filter += 1
                    skip_reason_counts["thin_source_fact_block"] += 1
                    _append_skip_reason_sample(skip_reason_sample_titles, "thin_source_fact_block", raw_title)
                    continue
                _log_draft_observed_thin_source(
                    logger,
                    title=raw_title,
                    post_url=post_url,
                    category=category,
                    article_subtype=title_article_subtype,
                    source_type=source_type,
                    source_fact_block_length=source_fact_block_length,
                    min_chars=thin_source_min_chars,
                )
            if args.dry_run:
                draft_title, title_template_key = _rewrite_display_title_with_guard(
                    raw_title,
                    summary,
                    category,
                    entry_has_game,
                    article_subtype=title_article_subtype,
                    logger=logger,
                    source_url=post_url,
                )
                draft_title, _comparison_title = _apply_title_player_name_backfill(
                    rewritten_title=draft_title,
                    source_title=raw_title,
                    source_body=summary,
                    summary=summary,
                    category=category,
                    article_subtype=title_article_subtype,
                    manager_subject="",
                    notice_subject="",
                    logger=logger,
                    source_name=source_name,
                    source_url=post_url,
                )
                _log_title_template_selected(logger, post_url, raw_title, draft_title, title_template_key, category, title_article_subtype)
                print(f"  DRY: [{category}] {draft_title[:50]}")
                print(f"       {post_url}")
                success += 1
                continue
            effective_story_category = _resolve_article_generation_category(category, raw_title, summary)
            special_story_kind = (
                _detect_player_special_template_kind(raw_title, summary)
                if effective_story_category == "選手情報"
                else ""
            )
            media_story_kind = special_story_kind
            manager_subject = ""
            manager_aliases: list[str] = []
            notice_subject = ""
            notice_type = ""
            player_aliases: list[str] = []
            if special_story_kind == "player_notice":
                notice_subject, notice_type = _extract_notice_subject_and_type(raw_title, summary)
                family_alias = _player_family_name_alias(raw_title, summary, "選手情報")
                player_aliases = _dedupe_preserve_order([alias for alias in [notice_subject, family_alias] if alias])
            elif category == "首脳陣" and title_article_subtype == "manager":
                media_story_kind = "manager_quote"
                manager_subject = _extract_subject_label(raw_title, summary, "首脳陣")
                compact_manager_subject = _re.sub(r"(監督|コーチ)$", "", manager_subject).strip()
                manager_aliases = _dedupe_preserve_order(
                    [
                        alias
                        for alias in [manager_subject, compact_manager_subject]
                        if alias and alias not in {"首脳陣", "巨人"}
                    ]
                )
            topic_aliases = _dedupe_preserve_order(player_aliases or manager_aliases)
            if not topic_aliases:
                compact_subject = _compact_subject_label(raw_title, summary, effective_story_category)
                if compact_subject and compact_subject not in {"巨人", "選手", "首脳陣"}:
                    topic_aliases.append(compact_subject)
                family_alias_for_topic = _player_family_name_alias(raw_title, summary, effective_story_category)
                if family_alias_for_topic:
                    topic_aliases.append(family_alias_for_topic)
                topic_aliases = _dedupe_preserve_order(topic_aliases)
            media_quote_max_count = 1
            if media_story_kind in {"player_notice", "manager_quote"}:
                media_quote_max_count = 2
            elif source_type == "social_news" and category in {"試合速報", "選手情報", "首脳陣"}:
                media_quote_max_count = 2

            media_quote_evaluation = evaluate_media_quote_selection(
                {
                    "source_type": source_type,
                    "source_url": post_url,
                    "source_name": source_name,
                    "created_at": item.get("published_at").isoformat() if item.get("published_at") else "",
                    "story_kind": media_story_kind,
                    "player_name": notice_subject,
                    "player_aliases": player_aliases,
                    "notice_type": notice_type,
                    "manager_name": manager_subject,
                    "manager_aliases": manager_aliases,
                    "article_subtype": title_article_subtype,
                    "category": category,
                    "topic_aliases": topic_aliases,
                },
                max_count=media_quote_max_count,
                media_quote_pool=media_quote_pool,
            )
            media_quotes = media_quote_evaluation["quotes"]
            if source_type == "news":
                _article_images = fetch_article_images(post_url, max_images=3)
            else:
                _article_images = _extract_entry_image_urls(item.get("entry", {}), post_url, max_images=3)
                if not _article_images:
                    _article_images = fetch_article_images(post_url, max_images=3)
            _article_images = _filter_image_candidates(_article_images, post_url, logger)
            _article_images = _refetch_article_images_if_empty(_article_images, post_url, logger, max_images=3)
            _article_images = _ensure_story_featured_images(
                _article_images,
                raw_title,
                summary,
                category,
                title_article_subtype,
                source_url=post_url,
                logger=logger,
            )
            _og_url  = _article_images[0] if _article_images else ""
            draft_title, title_template_key = _rewrite_display_title_with_guard(
                raw_title,
                summary,
                category,
                entry_has_game,
                article_subtype=title_article_subtype,
                logger=logger,
                source_url=post_url,
            )
            draft_title, comparison_title = _apply_title_player_name_backfill(
                rewritten_title=draft_title,
                source_title=raw_title,
                source_body=summary,
                summary=summary,
                category=category,
                article_subtype=title_article_subtype,
                manager_subject=manager_subject,
                notice_subject=notice_subject,
                logger=logger,
                source_name=source_name,
                source_url=post_url,
            )
            weak_title_fallback = _maybe_route_weak_generated_title_review(
                article_subtype=title_article_subtype,
                rewritten_title=draft_title,
                original_title=comparison_title,
                source_name=source_name,
                logger=logger,
            )
            if isinstance(weak_title_fallback, _WeakTitleReviewFallback):
                skip_filter += 1
                skip_reason_counts["post_gen_validate"] += 1
                _append_skip_reason_sample(skip_reason_sample_titles, "post_gen_validate", draft_title)
                _log_article_skipped_post_gen_validate(
                    logger,
                    title=draft_title,
                    post_url=post_url,
                    category=category,
                    article_subtype=title_article_subtype,
                    fail_axes=[f"weak_generated_title:{weak_title_fallback.reason}"],
                    stop_reason="weak_generated_title_review",
                )
                continue
            weak_subject_fallback = _maybe_route_weak_subject_title_review(
                article_subtype=title_article_subtype,
                rewritten_title=draft_title,
                original_title=comparison_title,
                source_name=source_name,
                logger=logger,
                speaker_name=manager_subject or notice_subject,
            )
            if isinstance(weak_subject_fallback, _WeakTitleReviewFallback):
                skip_filter += 1
                skip_reason_counts["post_gen_validate"] += 1
                _append_skip_reason_sample(skip_reason_sample_titles, "post_gen_validate", draft_title)
                _log_article_skipped_post_gen_validate(
                    logger,
                    title=draft_title,
                    post_url=post_url,
                    category=category,
                    article_subtype=title_article_subtype,
                    fail_axes=[f"weak_subject_title:{weak_subject_fallback.reason}"],
                    stop_reason="weak_subject_title_review",
                )
                continue
            _log_title_template_selected(logger, post_url, raw_title, draft_title, title_template_key, category, title_article_subtype)
            content, ai_body_for_x = build_news_block(
                title,
                summary,
                post_url,
                source_name,
                category,
                _og_url,
                0,
                extra_images=_article_images[1:],
                has_game=entry_has_game,
                article_ai_mode_override=args.article_ai_mode,
                source_links=item.get("source_links"),
                source_day_label=source_day_label,
                source_type=source_type,
                media_quotes=media_quotes,
                source_entry=item.get("entry"),
                duplicate_guard_context=item.get("duplicate_guard_context"),
            )
            duplicate_guard_context = item.get("duplicate_guard_context")
            if isinstance(duplicate_guard_context, dict) and duplicate_guard_context.get("guard_outcome") == "skip":
                skip_filter += 1
                skip_reason_counts["duplicate_news_pre_gemini_skip"] += 1
                _append_skip_reason_sample(skip_reason_sample_titles, "duplicate_news_pre_gemini_skip", draft_title)
                continue
            strict_review_reason = (
                str(duplicate_guard_context.get("postgame_strict_review_reason") or "").strip()
                if isinstance(duplicate_guard_context, dict)
                else ""
            )
            if strict_review_reason:
                skip_filter += 1
                skip_reason_counts["post_gen_validate"] += 1
                _append_skip_reason_sample(skip_reason_sample_titles, "post_gen_validate", draft_title)
                _log_article_skipped_post_gen_validate(
                    logger,
                    title=draft_title,
                    post_url=post_url,
                    category=category,
                    article_subtype=title_article_subtype,
                    fail_axes=["postgame_strict_review"],
                    stop_reason=f"postgame_strict:{strict_review_reason}",
                )
                continue
            manager_quote_zero_review_reason = (
                str(duplicate_guard_context.get("manager_quote_zero_review_reason") or "").strip()
                if isinstance(duplicate_guard_context, dict)
                else ""
            )
            if manager_quote_zero_review_reason:
                skip_filter += 1
                skip_reason_counts["post_gen_validate"] += 1
                _append_skip_reason_sample(skip_reason_sample_titles, "post_gen_validate", draft_title)
                _log_article_skipped_post_gen_validate(
                    logger,
                    title=draft_title,
                    post_url=post_url,
                    category=category,
                    article_subtype=title_article_subtype,
                    fail_axes=["manager_quote_zero_review"],
                    stop_reason=f"manager_quote_zero_review:{manager_quote_zero_review_reason}",
                )
                continue
            fact_conflict_source_refs = {
                "title": draft_title,
                "source_title": raw_title,
                "source_summary": summary,
                "summary": summary,
                "source_name": source_name,
                "source_url": post_url,
                "source_type": source_type,
                "source_links": item.get("source_links"),
                "game_id": item.get("game_id"),
                "scoreline": item.get("scoreline") or item.get("score") or "",
                "team_result": item.get("team_result") or "",
                "opponent": item.get("opponent") or "",
            }
            body_contract_validate = _validate_body_candidate(
                ai_body_for_x,
                title_article_subtype,
                rendered_html=content,
                source_context=fact_conflict_source_refs,
            )
            if not body_contract_validate["ok"]:
                skip_filter += 1
                skip_reason_counts["body_contract_validate"] += 1
                _append_skip_reason_sample(skip_reason_sample_titles, "body_contract_validate", draft_title)
                if body_contract_validate["action"] == "fail":
                    _log_body_validator_fail(
                        logger,
                        source_url=post_url,
                        category=category,
                        article_subtype=title_article_subtype,
                        fail_axes=list(body_contract_validate["fail_axes"]),
                        expected_first_block=str(body_contract_validate.get("expected_first_block") or ""),
                        actual_first_block=str(body_contract_validate.get("actual_first_block") or ""),
                        has_source_block=bool(body_contract_validate.get("has_source_block", False)),
                        stop_reason=str(body_contract_validate.get("stop_reason") or ""),
                    )
                else:
                    _log_body_validator_reroll(
                        logger,
                        source_url=post_url,
                        category=category,
                        article_subtype=title_article_subtype,
                        fail_axes=list(body_contract_validate["fail_axes"]),
                        expected_first_block=str(body_contract_validate.get("expected_first_block") or ""),
                        actual_first_block=str(body_contract_validate.get("actual_first_block") or ""),
                        missing_required_blocks=list(body_contract_validate.get("missing_required_blocks") or []),
                        actual_block_order=list(body_contract_validate.get("actual_block_order") or []),
                    )
                continue
            post_gen_validate = _evaluate_post_gen_validate(
                ai_body_for_x,
                article_subtype=title_article_subtype,
                title=draft_title,
                source_refs=fact_conflict_source_refs,
            )
            if not post_gen_validate["ok"]:
                skip_filter += 1
                skip_reason_counts["post_gen_validate"] += 1
                _append_skip_reason_sample(skip_reason_sample_titles, "post_gen_validate", draft_title)
                _log_article_skipped_post_gen_validate(
                    logger,
                    title=draft_title,
                    post_url=post_url,
                    category=category,
                    article_subtype=title_article_subtype,
                    fail_axes=list(post_gen_validate["fail_axes"]),
                    stop_reason=str(post_gen_validate.get("stop_reason") or ""),
                )
                continue
        else:
            content = build_oembed_block(post_url)
            ai_body_for_x = ""
            draft_title = title
            _log_title_template_selected(logger, post_url, raw_title, draft_title, "oembed_passthrough", category, title_article_subtype)
            if args.dry_run:
                print(f"  DRY: [{category}] {draft_title[:50]}")
                print(f"       {post_url}")
                success += 1
                continue

        try:
            _log_title_collision_if_needed(logger, history, post_url, draft_title)
            cats = _resolve_draft_category_ids(wp, category, logger)

            featured_media = 0
            if source_type in {"news", "social_news"}:
                featured_media = _upload_featured_media_with_fallback(
                    wp,
                    _article_images,
                    post_url,
                    logger,
                )

            post_id = _create_draft_with_same_fire_guard(
                wp,
                logger,
                same_fire_source_urls,
                same_fire_title_sources,
                draft_title,
                content,
                cats,
                post_url,
                featured_media=featured_media,
            )
            effective_featured_media = _resolve_effective_featured_media(wp, post_id, featured_media, logger)
            draft_post_data = wp.get_post(post_id)
            draft_article_url = draft_post_data.get("link", "") or post_url
            success += 1
            _record_duplicate_guard_success(item.get("duplicate_guard_context"), post_id)
            created_category_counts[category] += 1
            created_subtype_counts[title_article_subtype] += 1
            _log_media_xpost_evaluated(
                logger,
                post_id,
                draft_title,
                category,
                title_article_subtype,
                media_quote_evaluation.get("selector_type", "none"),
                bool(media_quote_evaluation.get("is_target")),
            )
            if media_quote_evaluation.get("skip_meta"):
                _log_media_xpost_skipped(
                    logger,
                    post_id,
                    draft_title,
                    category,
                    title_article_subtype,
                    media_quote_evaluation["skip_meta"],
                )
            if media_quotes:
                total_media_quotes = len(media_quotes[:2])
                for quote_index, media_quote in enumerate(media_quotes[:2], start=1):
                    _log_media_xpost_embedded(
                        logger,
                        post_id,
                        draft_title,
                        source_type,
                        media_quote.get("handle", ""),
                        media_quote.get("url", ""),
                        quote_account=media_quote.get("quote_account", ""),
                        embed_section_type=media_quote.get("section_label", ""),
                        match_reason=media_quote.get("match_reason", ""),
                        match_score=int(media_quote.get("match_score", 0) or 0),
                        quote_index=quote_index,
                        quote_count_in_article=total_media_quotes,
                    )
            if source_type == "social_news" and not _social_source_prefers_structured_template(category, title_article_subtype):
                _log_social_body_template_applied(
                    logger,
                    post_id,
                    draft_title,
                    category,
                    _infer_social_source_indicator(source_name, tweet_url=post_url),
                    _social_section_count(ai_body_for_x),
                    _social_quote_count(raw_title, summary, ai_body_for_x),
                )
            if category == "首脳陣" and title_article_subtype == "manager":
                _log_manager_body_template_applied(
                    logger,
                    post_id,
                    draft_title,
                    _manager_quote_count(raw_title, summary),
                    _manager_section_count(ai_body_for_x),
                )
            if category == "試合速報" and _is_game_template_subtype(title_article_subtype):
                _log_game_body_template_applied(
                    logger,
                    post_id,
                    draft_title,
                    title_article_subtype,
                    _game_section_count(ai_body_for_x, title_article_subtype),
                    _game_numeric_count(raw_title, summary, ai_body_for_x),
                    _game_name_count(raw_title, summary, ai_body_for_x),
                )
            if category == "ドラフト・育成" and _is_farm_template_subtype(title_article_subtype):
                _log_farm_body_template_applied(
                    logger,
                    post_id,
                    draft_title,
                    title_article_subtype,
                    _farm_section_count(ai_body_for_x, title_article_subtype),
                    _farm_numeric_count(raw_title, summary, ai_body_for_x),
                    _farm_is_drafted_player_story(raw_title, summary),
                )
            if _is_recovery_template_story(raw_title, summary, effective_story_category):
                recovery_subject = _extract_recovery_subject(raw_title, summary)
                _log_recovery_body_template_applied(
                    logger,
                    post_id,
                    draft_title,
                    _extract_recovery_injury_part(raw_title, summary, recovery_subject),
                    _extract_recovery_return_timing(raw_title, summary, recovery_subject),
                    _recovery_section_count(ai_body_for_x),
                )
            if _is_notice_template_story(raw_title, summary, effective_story_category):
                _notice_subject, notice_type = _extract_notice_subject_and_type(raw_title, summary)
                _log_notice_body_template_applied(
                    logger,
                    post_id,
                    draft_title,
                    notice_type or _extract_notice_type_label(f"{raw_title} {summary}") or "公示",
                    _notice_section_count(ai_body_for_x),
                    _notice_has_player_name(ai_body_for_x, raw_title, summary),
                    _notice_has_numeric_record(ai_body_for_x),
                )
            tweet_preview_text, tweet_preview_meta = _build_x_post_preview_for_observation(
                logger=logger,
                history=history,
                today_str=today_str,
                x_post_daily_limit=x_post_daily_limit,
                post_id=post_id,
                title=draft_title,
                article_url=draft_article_url,
                category=category,
                summary=ai_body_for_x or summary,
                content_html=content,
                article_subtype=title_article_subtype,
                source_type=source_type,
                source_name=source_name,
            )
            time.sleep(1)

            publish_gate_subtype = resolve_publish_gate_subtype(
                raw_title,
                summary,
                category,
                title_article_subtype,
                source_type,
            )
            publish_observation_reasons = get_publish_observation_reasons(
                source_type=source_type,
                draft_only=args.draft_only,
                featured_media=effective_featured_media,
            )
            for reason in publish_observation_reasons:
                publish_observation_counts[reason] += 1
            if "featured_media_observation_missing" in publish_observation_reasons:
                _log_featured_media_observation_missing(
                    logger,
                    post_id,
                    draft_title,
                    publish_gate_subtype,
                    category,
                    primary_url=_og_url,
                    candidate_count=len(_article_images),
                    source_type=source_type,
                )
            publish_skip_reasons = get_publish_skip_reasons(
                source_type=source_type,
                draft_only=args.draft_only,
                featured_media=effective_featured_media,
                article_subtype=publish_gate_subtype,
            )
            if source_type in {"news", "social_news"} and not args.draft_only:
                quality_guard = _evaluate_publish_quality_guard(
                    content_html=content,
                    article_subtype=publish_gate_subtype,
                )
                if not quality_guard["ok"]:
                    publish_skip_reasons.extend(list(quality_guard["reasons"]))
                    _log_publish_blocked_by_quality_guard(
                        logger,
                        post_id,
                        draft_title,
                        publish_gate_subtype,
                        category,
                        quality_guard,
                    )
            for reason in publish_skip_reasons:
                publish_skip_reason_counts[reason] += 1
            if "publish_disabled_for_subtype" in publish_skip_reasons:
                _log_publish_gate_skipped(
                    logger,
                    post_id,
                    draft_title,
                    publish_gate_subtype,
                    category,
                    "publish_disabled_for_subtype",
                )
            if "live_update_publish_disabled" in publish_skip_reasons:
                _log_publish_gate_skipped(
                    logger,
                    post_id,
                    draft_title,
                    publish_gate_subtype,
                    category,
                    "live_update_publish_disabled",
                )
            if publish_skip_reasons:
                logger.info(f"  [下書き止め] post_id={post_id} reason={','.join(publish_skip_reasons)}")
                published = False
            else:
                published = finalize_post_publication(
                    wp,
                    post_id,
                    post_url,
                    history,
                    entry_title_norm,
                    logger,
                    draft_only=False,
                )
            persist_processed_entry_history(
                history,
                item.get("history_urls", [post_url]),
                item.get("history_title_norms", [entry_title_norm] if entry_title_norm else []),
                rewritten_title=draft_title,
                original_title=raw_title,
                published=published,
                publish_skip_reasons=publish_skip_reasons,
            )

            article_url = ""
            if published:
                wp_post_data = wp.get_post(post_id)
                article_url = wp_post_data.get("link", "")

            x_skip_reasons = get_auto_tweet_skip_reasons(
                source_type=source_type,
                category=category,
                article_subtype=publish_gate_subtype,
                draft_only=args.draft_only,
                x_post_count=x_post_count,
                x_post_daily_limit=x_post_daily_limit,
                featured_media=effective_featured_media,
                published=published,
                article_url=article_url,
            )
            for reason in x_skip_reasons:
                x_skip_reason_counts[reason] += 1
            if "x_post_disabled_for_subtype" in x_skip_reasons:
                _log_x_post_subtype_skipped(
                    logger,
                    post_id,
                    draft_title,
                    category,
                    publish_gate_subtype,
                    "x_post_disabled_for_subtype",
                )

            if not x_skip_reasons:
                try:
                    import tweepy
                    from dotenv import load_dotenv
                    load_dotenv(ROOT / ".env")
                    if tweet_preview_text:
                        tweet_text = tweet_preview_text
                        if draft_article_url and article_url and draft_article_url != article_url:
                            tweet_text = tweet_text.replace(draft_article_url, article_url, 1)
                    else:
                        tweet_text = build_x_post_text(
                            draft_title,
                            article_url,
                            category,
                            summary=ai_body_for_x or summary,
                            content_html=content,
                            article_subtype=title_article_subtype,
                            source_type=source_type,
                            source_name=source_name,
                        )
                    x_client = tweepy.Client(
                        bearer_token=os.environ.get("X_BEARER_TOKEN"),
                        consumer_key=os.environ.get("X_API_KEY"),
                        consumer_secret=os.environ.get("X_API_SECRET"),
                        access_token=os.environ.get("X_ACCESS_TOKEN"),
                        access_token_secret=os.environ.get("X_ACCESS_TOKEN_SECRET"),
                    )
                    resp = x_client.create_tweet(text=tweet_text)
                    tweet_id = resp.data["id"]
                    x_post_count += 1
                    history[f"x_post_count_{today_str}"] = x_post_count
                    persist_history(history)
                    logger.info(f"  [公開+X投稿] post_id={post_id} tweet_id={tweet_id} 本日{x_post_count}/{x_post_daily_limit}件")
                except Exception as xe:
                    logger.warning(f"  [X投稿失敗] post_id={post_id} {xe}")
                    logger.info(f"  [公開済み] post_id={post_id}")
            else:
                if published:
                    logger.info(f"  [X投稿スキップ] post_id={post_id} reason={','.join(x_skip_reasons)}")
                    logger.info(f"  [公開] post_id={post_id} image={'あり' if effective_featured_media else 'なし'}")
                else:
                    logger.info(
                        f"  [下書き維持] post_id={post_id} reason={','.join(publish_skip_reasons)} "
                        f"image={'あり' if effective_featured_media else 'なし'}"
                    )

        except Exception as e:
            logger.error(f"  [ERROR] 公開失敗: {e}")
            error += 1

    logger.info(
        f"=== 完了: 取得={total} / 投稿={success} / 重複スキップ={skip_dup} "
        f"/ フィルタスキップ={skip_filter} / エラー={error} ==="
    )
    logger.info(
        json.dumps(
            {
                "event": "rss_fetcher_run_summary",
                "dry_run": bool(args.dry_run),
                "draft_only": bool(args.draft_only),
                "has_game": bool(has_game),
                "opponent": opponent,
                "venue": venue,
                "entry_limit": args.limit,
                "total_entries": total,
                "drafts_created": success,
                "skip_duplicate": skip_dup,
                "skip_filter": skip_filter,
                "error_count": error,
                "x_post_count": x_post_count,
                "x_post_daily_limit": x_post_daily_limit,
                "x_ai_generation_count": history.get(f"x_ai_generation_count_{today_str}", x_ai_generation_count),
                "x_ai_generation_limit": x_post_daily_limit,
            },
            ensure_ascii=False,
        )
    )
    logger.info(
        json.dumps(
            {
                "event": "rss_fetcher_flow_summary",
                "skip_reasons": _skip_reasons_with_samples(
                    skip_reason_counts,
                    not_giants_related_sample_titles=not_giants_related_sample_titles,
                    skip_reason_sample_titles=skip_reason_sample_titles,
                ),
                "prepared_category_counts": _counter_to_plain_dict(prepared_category_counts),
                "prepared_subtype_counts": _counter_to_plain_dict(prepared_subtype_counts),
                "created_category_counts": _counter_to_plain_dict(created_category_counts),
                "created_subtype_counts": _counter_to_plain_dict(created_subtype_counts),
                "publish_skip_reason_counts": _counter_to_plain_dict(publish_skip_reason_counts),
                "publish_observation_counts": _counter_to_plain_dict(publish_observation_counts),
                "x_skip_reason_counts": _counter_to_plain_dict(x_skip_reason_counts),
                "x_ai_generation_count": history.get(f"x_ai_generation_count_{today_str}", x_ai_generation_count),
                "x_ai_generation_limit": x_post_daily_limit,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
