import pytest

from src import rss_fetcher


@pytest.fixture(autouse=True)
def stub_related_posts_lookup(monkeypatch, request):
    if request.node.get_closest_marker("enable_related_posts_lookup"):
        return
    monkeypatch.setattr(rss_fetcher, "_find_related_posts_for_article", lambda **kwargs: [])
