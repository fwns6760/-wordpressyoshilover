"""Persist corroborated salary history, then refresh only existing salary pages."""
from __future__ import annotations

import copy
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

from src.salary_contract_source import collect_contracts, normalize_name

JST = timezone(timedelta(hours=9))
STATE_OBJECT = "data_site/salary/ledger-v1.json"
MAX_STATE_BYTES = 2 * 1024 * 1024
BASE_DATA = Path(__file__).resolve().parents[1] / "config" / "giants_salary.json"


def canonical_salary_data(baked):
    """Collapse identical aliases only when the established slug map identifies one record."""
    from src.data_site_slug import player_slug
    data = copy.deepcopy(baked)
    groups = {}
    for player in data["players"]:
        groups.setdefault(normalize_name(player["name"]), []).append(player)
    remove = set()
    for players in groups.values():
        canonical = {player_slug(p["name"]) for p in players}
        preferred = [p for p in players if p["slug"] in canonical]
        if (len(players) > 1 and len(canonical) == 1 and len(preferred) == 1
                and all(p["years"] == preferred[0]["years"] for p in players)):
            remove.update(p["slug"] for p in players if p is not preferred[0])
    data["players"] = [p for p in data["players"] if p["slug"] not in remove]
    return data


def state_blob(client=None):
    from google.cloud import storage
    bucket = os.environ.get("INSIGHT_GCS_BUCKET", "").strip()
    if not bucket:
        raise RuntimeError("salary history bucket not configured")
    return (client or storage.Client()).bucket(bucket).blob(STATE_OBJECT)


def load_state(blob):
    from google.api_core.exceptions import NotFound
    try:
        blob.reload(timeout=20)
    except NotFound:
        return {"schema_version": 1, "entries": {}, "reviews": {}}, 0
    if blob.size is None or blob.size > MAX_STATE_BYTES:
        raise ValueError("salary history exceeds size limit")
    generation = int(blob.generation)
    state = json.loads(blob.download_as_bytes(if_generation_match=generation, timeout=20))
    if state.get("schema_version") != 1 or not isinstance(state.get("entries"), dict):
        raise ValueError("invalid salary history schema")
    for years in state["entries"].values():
        if not isinstance(years, dict):
            raise ValueError("invalid salary history years")
        for year, entry in years.items():
            amount = entry.get("salary_man")
            if entry.get("year") != int(year) or type(amount) is not int or not 1 <= amount <= 300000:
                raise ValueError("invalid salary history amount/year")
            sources = entry.get("sources", [])
            domains = {urlparse(s.get("url", "")).hostname for s in sources}
            if (entry.get("team") != "巨人" or domains != {"www.my-favorite-giants.net", "baseball.yahoo.co.jp"}
                    or any(s.get("salary_man") != amount for s in sources)):
                raise ValueError("unverified salary history")
    return state, generation


def save_state(blob, state, generation):
    payload = json.dumps(state, ensure_ascii=False, sort_keys=True)
    if len(payload.encode()) > MAX_STATE_BYTES:
        raise ValueError("salary history exceeds size limit")
    blob.upload_from_string(payload, content_type="application/json", if_generation_match=generation, timeout=20)
    return int(blob.generation)


def merge_observations(baked, state, observed):
    result = copy.deepcopy(state)
    by_name = {}
    for player in baked["players"]:
        name = normalize_name(player["name"])
        if name in by_name:
            # Ambiguous canonical names must never acquire another player's salary.
            by_name[name] = None
        else:
            by_name[name] = player["slug"]
    accepted, changed, unmapped = [], [], []
    for name, entry in observed["verified"].items():
        slug = by_name.get(name)
        if not slug:
            unmapped.append(name)
            continue
        accepted.append(slug)
        years = result["entries"].setdefault(slug, {})
        year = str(entry["year"])
        previous = years.get(year)
        if previous is not None and previous["salary_man"] == entry["salary_man"]:
            continue
        updated = copy.deepcopy(entry)
        updated["verified_on"] = observed["checked_on"]
        if previous:
            updated["revisions"] = previous.get("revisions", []) + [{
                "salary_man": previous["salary_man"], "verified_on": previous["verified_on"],
                "sources": previous["sources"]}]
        years[year] = updated
        changed.append(slug)
    result.update(target_year=observed["target_year"], checked_on=observed["checked_on"],
                  reviews=observed["held"], unmapped=unmapped)
    return result, {"accepted": len(accepted), "changed": len(changed),
                    "held": len(observed["held"]), "unmapped": unmapped}


def hydrate_data(baked, state):
    data = copy.deepcopy(baked)
    target = state.get("target_year")
    if not target:
        return data
    data.setdefault("_meta", {})["salary_auto"] = {
        "target_year": target, "checked_on": state.get("checked_on", "")}
    for player in data["players"]:
        by_year = {str(y["year"]): y for y in player["years"]}
        # Archived years survive every run, including January and source outages.
        for year, entry in state["entries"].get(player["slug"], {}).items():
            by_year[year] = copy.deepcopy(entry)
        player["years"] = sorted(by_year.values(), key=lambda y: y["year"])
        if player.get("active") is not False:
            player["salary_target_year"] = target
            player["salary_update_status"] = (
                "review" if normalize_name(player["name"]) in state.get("reviews", {})
                else "verified" if str(target) in by_year else "pending")
    return data


def load_persisted_data(baked):
    baked = canonical_salary_data(baked)
    if not os.environ.get("INSIGHT_GCS_BUCKET"):
        return baked
    state, _ = load_state(state_blob())
    return hydrate_data(baked, state)


def _session(auth):
    session = requests.Session()
    session.auth = auth
    session.headers["Accept-Encoding"] = "gzip, deflate"
    return session


def publish_salary_pages(base, auth, cluster_id, data):
    from src.data_site_template_salary import (
        render_salary_index_html, render_salary_index_title, render_salary_index_excerpt,
        render_salary_player_html, render_salary_player_title, render_salary_player_excerpt,
    )
    session = _session(auth)
    response = session.get(base + "/wp-json/wp/v2/pages", params={
        "slug": "salary", "parent": cluster_id, "context": "edit", "status": "publish"}, timeout=25)
    response.raise_for_status()
    indexes = [p for p in response.json() if p["slug"] == "salary" and p["parent"] == cluster_id]
    if len(indexes) != 1:
        raise ValueError("existing salary index not found")
    index = indexes[0]
    existing = {}
    for number in range(1, 5):
        response = session.get(base + "/wp-json/wp/v2/pages", params={
            "parent": index["id"], "status": "publish", "context": "edit",
            "per_page": 100, "page": number}, timeout=35)
        response.raise_for_status()
        for page in response.json():
            if page["slug"] in existing:
                raise ValueError("ambiguous salary page slug")
            existing[page["slug"]] = page
        if number >= int(response.headers.get("X-WP-TotalPages", "1")):
            break
    else:
        raise ValueError("unexpected salary page count")

    # The daily lane owns existing pages only. Unpublished players must not create
    # dead links in the index or block every other player's renewal.
    publish_data = copy.deepcopy(data)
    skipped = [p["slug"] for p in data["players"] if p["slug"] not in existing]
    publish_data["players"] = [p for p in data["players"] if p["slug"] in existing]
    if not any(p.get("active") is not False for p in publish_data["players"]):
        raise ValueError("no existing active salary pages")

    def update(page, title, content, excerpt):
        payload = {"title": title, "content": content, "excerpt": excerpt}
        if all(page[k].get("raw") == v for k, v in payload.items()):
            return "unchanged"
        s = _session(auth)
        url = base + "/wp-json/wp/v2/pages/" + str(page["id"])
        fresh = s.get(url, params={"context": "edit"}, timeout=25)
        fresh.raise_for_status()
        current = fresh.json()
        if any(current[k].get("raw") != page[k].get("raw") for k in payload):
            raise ValueError("concurrent salary page edit")
        response = s.post(url, json=payload, timeout=35)
        response.raise_for_status()
        after = response.json()
        if any(after.get(k, {}).get("raw") != v for k, v in payload.items()):
            response = s.get(url, params={"context": "edit"}, timeout=25)
            response.raise_for_status()
            after = response.json()
        if any(after.get(k, {}).get("raw") != v for k, v in payload.items()):
            raise ValueError("salary publication readback mismatch")
        for field in ("id", "parent", "slug", "status", "date", "date_gmt", "link"):
            if after[field] != page[field]:
                raise ValueError("salary page identity changed")
        return "updated"

    def publish(player):
        page = existing.get(player["slug"])
        if page is None:
            return {"slug": player["slug"], "status": "missing_page"}
        try:
            status = update(page, render_salary_player_title(player), render_salary_player_html(player),
                            render_salary_player_excerpt(player))
            return {"slug": player["slug"], "status": status}
        except Exception as exc:
            return {"slug": player["slug"], "status": "failed", "error": type(exc).__name__}

    players = [p for p in publish_data["players"] if p.get("active") is not False]
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(pool.map(publish, players))
    failed = [p for p in results if p["status"] in ("failed", "missing_page")]
    index_status = "deferred" if failed else update(index, render_salary_index_title(publish_data),
        render_salary_index_html(publish_data), render_salary_index_excerpt(publish_data))
    return {"ok": not failed, "updated_pages": sum(r["status"] == "updated" for r in results),
            "unchanged_pages": sum(r["status"] == "unchanged" for r in results),
            "failed": failed, "skipped_no_page": skipped, "index": index_status}


def refresh_salary(base, auth, cluster_id, *, now=None, client=None, collector=collect_contracts, publisher=publish_salary_pages):
    now = now or datetime.now(JST)
    blob = state_blob(client)
    state, generation = load_state(blob)
    lease = state.get("lease") or {}
    if lease.get("until") and datetime.fromisoformat(lease["until"]) > now:
        print("[salary-auto] another refresh holds the history lease; skip")
        return True
    observed = collector(now.date())  # A source failure causes no state or WP writes.
    baked = canonical_salary_data(json.loads(BASE_DATA.read_text(encoding="utf-8")))
    updated, counts = merge_observations(baked, state, observed)
    updated["lease"] = {"owner": uuid.uuid4().hex, "until": (now+timedelta(minutes=6)).isoformat()}
    generation = save_state(blob, updated, generation)  # CAS and persistence must succeed before WP writes.
    result = {"ok": False, "error": "publication_not_completed"}
    try:
        data = hydrate_data(baked, updated)
        from src.data_site_template_salary import _reconcile_actives_with_roster
        _reconcile_actives_with_roster(data)
        result = publisher(base, auth, cluster_id, data)
        return bool(result["ok"])
    finally:
        updated.pop("lease", None)
        updated["last_run"] = {"at": now.isoformat(), **counts, **result}
        save_state(blob, updated, generation)
        print("[salary-auto] " + json.dumps({"target_year": observed["target_year"],
              "source_requests": observed["source_requests"], **counts, **result}, ensure_ascii=False))
