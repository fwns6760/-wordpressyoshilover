import re
from typing import Literal


TrustLevel = Literal["primary", "secondary", "rumor", "unknown"]

PRIMARY_DOMAINS = {"giants.jp", "npb.jp"}
SECONDARY_DOMAINS = {"hochi.news", "sanspo.com", "nikkansports.com"}
RUMOR_DOMAINS = {"reddit.com", "redd.it", "ameblo.jp", "blog.livedoor.jp", "note.com"}

PRIMARY_HANDLES = {"tokyogiants", "npb", "yomiuri_giants"}
SECONDARY_HANDLES = {
    "hochi_giants",
    "sanspo_giants",
    "nikkansports",
    "sponichiyakyu",
    "sportshochi",
    "hochi_baseball",
}

SOCIAL_DOMAINS = {"x.com", "twitter.com"}
_SCHEME_RE = re.compile(r"^[a-z][a-z0-9+.-]*://", re.IGNORECASE)


def classify_url(url: str) -> TrustLevel:
    """Classify a source URL by domain or known X handle."""
    host, path = _split_url(url)
    if not host:
        return "unknown"
    if _matches_domain(host, SOCIAL_DOMAINS):
        handle = _first_path_segment(path)
        return classify_handle(handle) if handle else "unknown"
    if _matches_domain(host, PRIMARY_DOMAINS):
        return "primary"
    if _matches_domain(host, SECONDARY_DOMAINS):
        return "secondary"
    if _matches_domain(host, RUMOR_DOMAINS):
        return "rumor"
    return "unknown"


def classify_handle(handle: str) -> TrustLevel:
    """Classify an X handle."""
    normalized = handle.strip().lstrip("@").lower()
    if not normalized:
        return "unknown"
    if normalized in PRIMARY_HANDLES:
        return "primary"
    if normalized in SECONDARY_HANDLES:
        return "secondary"
    return "unknown"


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
