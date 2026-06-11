"""Tests for src/tools/data_site_daily_refresh.py (_upsert の変更なしスキップ)。

動かないデータ (交流戦期間外の interleague / シーズン外の open-games 等) を
毎日 WP へ上げ直さないこと (revision 肥大・無駄 write 防止) を検証する。
"""

from __future__ import annotations

from requests.auth import HTTPBasicAuth

from src.tools import data_site_daily_refresh as mod

_BASE = "https://example.com"
_AUTH = HTTPBasicAuth("u", "p")


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload
        self.ok = True
        self.status_code = 200
        self.text = ""

    def raise_for_status(self) -> None:
        pass

    def json(self):
        return self._payload


def _patch_wp(monkeypatch, *, page_id: int, stored_raw: str, posts: list):
    def fake_get(url, params=None, auth=None, timeout=None):
        if url.endswith("/wp-json/wp/v2/pages"):
            return _FakeResp([{"id": page_id, "slug": params["slug"],
                               "parent": 0, "status": "publish"}])
        assert url.endswith(f"/wp-json/wp/v2/pages/{page_id}")
        return _FakeResp({"id": page_id, "content": {"raw": stored_raw}})

    def fake_post(url, json=None, auth=None, timeout=None):
        posts.append((url, json))
        return _FakeResp({"id": page_id, "status": "publish"})

    monkeypatch.setattr(mod.requests, "get", fake_get)
    monkeypatch.setattr(mod.requests, "post", fake_post)


def test_upsert_skips_when_content_unchanged(monkeypatch) -> None:
    posts: list = []
    _patch_wp(monkeypatch, page_id=42, stored_raw="<p>same</p>", posts=posts)
    ok = mod._upsert(_BASE, _AUTH, slug="interleague", title="t",
                     content="<p>same</p>", excerpt="e", parent=0)
    assert ok is True
    assert posts == []  # 変更なし → POST しない


def test_upsert_posts_when_content_changed(monkeypatch) -> None:
    posts: list = []
    _patch_wp(monkeypatch, page_id=42, stored_raw="<p>old</p>", posts=posts)
    ok = mod._upsert(_BASE, _AUTH, slug="interleague", title="t",
                     content="<p>new</p>", excerpt="e", parent=0)
    assert ok is True
    assert len(posts) == 1
    assert posts[0][0].endswith("/wp-json/wp/v2/pages/42")
    assert posts[0][1]["content"] == "<p>new</p>"


def test_upsert_posts_when_raw_fetch_fails(monkeypatch) -> None:
    posts: list = []

    def fake_get(url, params=None, auth=None, timeout=None):
        if url.endswith("/wp-json/wp/v2/pages"):
            return _FakeResp([{"id": 42, "slug": params["slug"],
                               "parent": 0, "status": "publish"}])
        raise RuntimeError("boom")

    def fake_post(url, json=None, auth=None, timeout=None):
        posts.append(url)
        return _FakeResp({"id": 42, "status": "publish"})

    monkeypatch.setattr(mod.requests, "get", fake_get)
    monkeypatch.setattr(mod.requests, "post", fake_post)
    ok = mod._upsert(_BASE, _AUTH, slug="interleague", title="t",
                     content="<p>x</p>", excerpt="e", parent=0)
    assert ok is True
    assert len(posts) == 1  # 比較不能時は従来どおり update に進む (fail-safe)
