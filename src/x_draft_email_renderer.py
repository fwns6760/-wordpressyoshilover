"""Content renderer for X draft email candidates (ticket 065-B1)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


FIELD_ORDER = (
    "recommended_account",
    "source_tier",
    "safe_fact",
    "official_draft",
    "official_alt",
    "inner_angle",
    "risk_note",
    "source_ref",
)

VALID_ACCOUNTS = frozenset({"official", "inner"})
VALID_SOURCE_TIERS = frozenset({"fact", "topic", "reaction"})


@dataclass(frozen=True)
class XDraftEmailCandidate:
    recommended_account: str
    source_tier: str
    safe_fact: str
    official_draft: str
    official_alt: str
    inner_angle: str
    risk_note: str
    source_ref: str

    def to_dict(self) -> dict[str, str]:
        """Return the public eight-field payload in fixed contract order."""
        return {field: str(getattr(self, field)) for field in FIELD_ORDER}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _one_line(value: Any) -> str:
    return " ".join(_text(value).split())


def _source_tier(article: Mapping[str, Any]) -> str:
    tier = _text(article.get("source_tier")).lower()
    return tier if tier in VALID_SOURCE_TIERS else "topic"


def _recommended_account(article: Mapping[str, Any], source_tier: str) -> str:
    account = _text(article.get("recommended_account")).lower()
    if account in VALID_ACCOUNTS:
        return account
    return "official" if source_tier == "fact" else "inner"


def _published_url(article: Mapping[str, Any]) -> str:
    for key in ("published_url", "canonical_url", "public_url", "url"):
        value = _text(article.get(key))
        if value:
            return value
    return ""


def _source_ref(article: Mapping[str, Any], public_url: str) -> str:
    return _text(article.get("source_ref") or article.get("source_url") or public_url)


def _safe_fact(article: Mapping[str, Any], source_tier: str) -> str:
    explicit = _one_line(article.get("safe_fact") or article.get("fact"))
    if explicit:
        return explicit

    topic = _one_line(article.get("topic") or article.get("headline") or article.get("title"))
    reaction = _one_line(article.get("reaction"))
    if source_tier == "topic":
        if topic:
            return f"{topic} が話題化しています。一次情報での事実確認は未完了です。"
        return "話題化の起点は確認できますが、一次情報での事実確認は未完了です。"
    if source_tier == "reaction":
        if reaction:
            return f"SNS上で「{reaction}」という反応が見られます。事実断定の根拠には使いません。"
        return "SNS上の反応が見られます。事実断定の根拠には使いません。"
    return topic


def _risk_note(article: Mapping[str, Any], source_tier: str) -> str:
    explicit = _one_line(article.get("risk_note"))
    if explicit:
        return explicit
    if source_tier == "topic":
        return "topic source 単独のため、公式投稿前に primary trust source で再確認する。"
    if source_tier == "reaction":
        return "reaction source 単独のため、事実断定や勝敗・公示・故障の根拠にしない。"
    return ""


def _title(article: Mapping[str, Any]) -> str:
    return _one_line(article.get("article_title") or article.get("title"))


def _join_post_lines(*parts: str) -> str:
    return "\n".join(part for part in parts if part)


def _official_draft(article: Mapping[str, Any], source_tier: str, safe_fact: str, public_url: str) -> str:
    title = _title(article)
    if source_tier == "fact":
        return _join_post_lines(safe_fact, title, public_url)
    return _join_post_lines(
        "一次確認待ちの話題です。公式投稿前に事実確認してください。",
        title,
        public_url,
    )


def _official_alt(article: Mapping[str, Any], source_tier: str, safe_fact: str, public_url: str) -> str:
    title = _title(article)
    if source_tier == "fact":
        if title and public_url:
            return _join_post_lines(f"{title}。{safe_fact}", public_url)
        return _join_post_lines(f"確認済み情報: {safe_fact}", public_url)
    return _join_post_lines(
        "公式で触れる場合は、一次ソース確認後に短く紹介する。",
        title,
        public_url,
    )


def _inner_angle(article: Mapping[str, Any], source_tier: str) -> str:
    explicit = _one_line(article.get("inner_angle"))
    if explicit:
        return explicit
    if source_tier == "fact":
        return "ファン目線では、この情報をどう受け止めるかを短く添える。事実説明は公式欄に任せる。"
    if source_tier == "topic":
        return "確認待ちの話題として、気になる点や続報待ちの温度感だけを出す。断定は避ける。"
    return "反応の盛り上がりを拾いつつ、事実ではなく受け止めとして書く。断定は避ける。"


def render_x_draft_email_candidate(article: Mapping[str, Any]) -> XDraftEmailCandidate:
    """Build one eight-field X draft email candidate from fixture metadata."""
    source_tier = _source_tier(article)
    public_url = _published_url(article)
    safe_fact = _safe_fact(article, source_tier)
    return XDraftEmailCandidate(
        recommended_account=_recommended_account(article, source_tier),
        source_tier=source_tier,
        safe_fact=safe_fact,
        official_draft=_official_draft(article, source_tier, safe_fact, public_url),
        official_alt=_official_alt(article, source_tier, safe_fact, public_url),
        inner_angle=_inner_angle(article, source_tier),
        risk_note=_risk_note(article, source_tier),
        source_ref=_source_ref(article, public_url),
    )
