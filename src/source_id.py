import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_FOLDABLE_SUBDOMAINS = {"www", "m", "amp", "news"}
_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "ref",
    "ref_src",
    "refsrc",
}
_X_HOSTS = {"x.com", "twitter.com"}


def _fold_host(host: str) -> str:
    labels = [label for label in host.split(".") if label]
    while len(labels) > 2 and labels[0] in _FOLDABLE_SUBDOMAINS:
        labels = labels[1:]
    return ".".join(labels)


def _split_url(url: str):
    text = url.strip()
    if not text:
        return text, None
    parsed = urlsplit(text)
    if parsed.netloc:
        return text, parsed
    if text.startswith("//"):
        parsed = urlsplit(f"https:{text}")
        if parsed.netloc:
            return text, parsed
    return text, None


def _normalized_netloc(parsed) -> str:
    host = _fold_host((parsed.hostname or "").lower())
    if not host:
        return ""
    if parsed.port and parsed.port != 443:
        return f"{host}:{parsed.port}"
    return host


def _is_tracking_key(key: str) -> bool:
    lowered = key.lower()
    return lowered.startswith("utm_") or lowered in _TRACKING_QUERY_KEYS


def normalize_url(url: str) -> str:
    """Return a normalized URL-like string for dedup keys."""
    text, parsed = _split_url(url)
    if parsed is None:
        return text
    pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not _is_tracking_key(key)
    ]
    query = urlencode(sorted(pairs))
    path = parsed.path.rstrip("/")
    return urlunsplit(("https", _normalized_netloc(parsed), path, query, ""))


def source_id(url: str) -> str:
    """Return a source-specific identity key."""
    normalized = normalize_url(url)
    _, parsed = _split_url(normalized)
    if parsed is None:
        return normalized
    host = _fold_host((parsed.hostname or "").lower())
    if host not in _X_HOSTS:
        return normalized
    match = re.search(r"/status(?:es)?/([0-9]+)", parsed.path, flags=re.IGNORECASE)
    if match:
        return f"x:{match.group(1).lower()}"
    parts = [part.lower() for part in parsed.path.split("/") if part]
    handle = parts[0] if parts else ""
    path_tail = "/".join(parts[1:])
    if handle and path_tail:
        return f"x:{handle}:{path_tail}"
    if handle:
        return f"x:{handle}"
    return "x:"
