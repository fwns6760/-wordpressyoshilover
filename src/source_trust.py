import re
from dataclasses import dataclass
from typing import Literal


TrustLevel = Literal["primary", "secondary", "rumor", "unknown"]
SourceFamily = Literal[
    "giants_official",
    "npb_official",
    "hochi",
    "nikkansports",
    "sponichi",
    "sanspo",
    "daily",
    "yomiuri_online",
    "yahoo_news_aggregator",
    "unknown",
]
FamilyTrustLevel = Literal["high", "mid-high", "mid", "unknown"]


@dataclass(frozen=True)
class SourceProfile:
    family: SourceFamily
    trust: TrustLevel
    family_trust: FamilyTrustLevel
    domains: tuple[str, ...] = ()
    handles: tuple[str, ...] = ()


TRUSTED_SOURCE_PROFILES = (
    SourceProfile(
        family="giants_official",
        trust="primary",
        family_trust="high",
        domains=("giants.jp",),
        handles=("tokyogiants", "yomiuri_giants"),
    ),
    SourceProfile(
        family="npb_official",
        trust="primary",
        family_trust="high",
        domains=("npb.jp", "npb.or.jp"),
        handles=("npb",),
    ),
    SourceProfile(
        family="hochi",
        trust="secondary",
        family_trust="mid",
        domains=("hochi.news", "hochi.co.jp", "sports.hochi.co.jp"),
        handles=("hochi_giants", "sportshochi", "hochi_baseball"),
    ),
    SourceProfile(
        family="nikkansports",
        trust="secondary",
        family_trust="mid",
        domains=("nikkansports.com",),
        handles=("nikkansports",),
    ),
    SourceProfile(
        family="sponichi",
        trust="secondary",
        family_trust="mid",
        domains=("sponichi.co.jp",),
        handles=("sponichiyakyu",),
    ),
    SourceProfile(
        family="sanspo",
        trust="secondary",
        family_trust="mid",
        domains=("sanspo.com",),
        handles=("sanspo_giants",),
    ),
    SourceProfile(
        family="daily",
        trust="secondary",
        family_trust="mid",
        domains=("daily.co.jp",),
    ),
    SourceProfile(
        family="yomiuri_online",
        trust="secondary",
        family_trust="mid-high",
        domains=("yomiuri.co.jp",),
    ),
    SourceProfile(
        family="yahoo_news_aggregator",
        trust="secondary",
        family_trust="mid",
        domains=("news.yahoo.co.jp",),
    ),
)

PRIMARY_DOMAINS = {
    domain
    for profile in TRUSTED_SOURCE_PROFILES
    if profile.trust == "primary"
    for domain in profile.domains
}
SECONDARY_DOMAINS = {
    domain
    for profile in TRUSTED_SOURCE_PROFILES
    if profile.trust == "secondary"
    for domain in profile.domains
}
RUMOR_DOMAINS = {"reddit.com", "redd.it", "ameblo.jp", "blog.livedoor.jp", "note.com"}

PRIMARY_HANDLES = {
    handle
    for profile in TRUSTED_SOURCE_PROFILES
    if profile.trust == "primary"
    for handle in profile.handles
}
SECONDARY_HANDLES = {
    handle
    for profile in TRUSTED_SOURCE_PROFILES
    if profile.trust == "secondary"
    for handle in profile.handles
}
FAMILY_TRUST_LEVELS = {profile.family: profile.family_trust for profile in TRUSTED_SOURCE_PROFILES}

SOCIAL_DOMAINS = {"x.com", "twitter.com"}
_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)


def classify_url(url: str) -> TrustLevel:
    """Classify a source URL by domain or known X handle."""
    source = _resolve_source(url)
    return source.trust if source else "unknown"


def classify_handle(handle: str) -> TrustLevel:
    """Classify an X handle."""
    profile = _find_profile_by_handle(handle)
    return profile.trust if profile else "unknown"


def classify_url_family(url: str) -> SourceFamily:
    """Return the normalized source family for a URL or X status URL."""
    source = _resolve_source(url)
    return source.family if source else "unknown"


def classify_handle_family(handle: str) -> SourceFamily:
    """Return the normalized source family for an X handle."""
    profile = _find_profile_by_handle(handle)
    return profile.family if profile else "unknown"


def get_family_trust_level(family: str) -> FamilyTrustLevel:
    """Return the registry trust level for one normalized source family."""
    return FAMILY_TRUST_LEVELS.get(str(family or "").strip(), "unknown")


def _resolve_source(url: str) -> SourceProfile | None:
    host, path = _split_url(url)
    if not host:
        return None
    if _matches_domain(host, SOCIAL_DOMAINS):
        handle = _first_path_segment(path)
        return _find_profile_by_handle(handle) if handle else None
    profile = _find_profile_by_host(host)
    if profile:
        return profile
    if _matches_domain(host, RUMOR_DOMAINS):
        return SourceProfile(family="unknown", trust="rumor", family_trust="unknown")
    return None


def _find_profile_by_host(host: str) -> SourceProfile | None:
    for profile in TRUSTED_SOURCE_PROFILES:
        if _matches_domain(host, set(profile.domains)):
            return profile
    return None


def _find_profile_by_handle(handle: str) -> SourceProfile | None:
    normalized = handle.strip().lstrip("@").lower()
    if not normalized:
        return None
    for profile in TRUSTED_SOURCE_PROFILES:
        if normalized in profile.handles:
            return profile
    return None


def _split_url(url: str) -> tuple[str, str]:
    raw = _SCHEME_RE.sub("", url.strip())
    if not raw:
        return "", ""

    raw = raw.split("#", 1)[0]
    if "/" in raw:
        host, path = raw.split("/", 1)
        path = "/" + path
    else:
        host, path = raw, ""

    host = host.split("?", 1)[0]
    if "@" in host:
        host = host.rsplit("@", 1)[-1]
    if ":" in host:
        host = host.split(":", 1)[0]
    return host.strip().strip(".").lower(), path


def _matches_domain(host: str, domains: set[str]) -> bool:
    for domain in domains:
        if host == domain or host.endswith("." + domain):
            return True
    return False


def _first_path_segment(path: str) -> str:
    cleaned = path.split("?", 1)[0].split("#", 1)[0].strip("/")
    if not cleaned:
        return ""
    return cleaned.split("/", 1)[0]
