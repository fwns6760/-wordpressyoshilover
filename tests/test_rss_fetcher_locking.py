import json
import os
import uuid
from argparse import Namespace
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock

import pytest

from src import rss_fetcher

FIXED_TIME = 1_800_000_000
FIXED_PID = 4242
FIXED_RUN_ID = uuid.UUID("12345678-1234-5678-1234-567812345678")
NOW_ISO = datetime.fromtimestamp(FIXED_TIME, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _iso_before(seconds: int) -> str:
    return datetime.fromtimestamp(FIXED_TIME - seconds, timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _event(logger: Mock, name: str) -> dict:
    for method in ("info", "warning", "error"):
        for call in getattr(logger, method).call_args_list:
            payload = json.loads(call.args[0])
            if payload["event"] == name:
                return payload
    raise AssertionError(f"event not found: {name}")


def _seed_lock(lock_file: Path, **overrides) -> dict:
    payload = {
        "run_id": "seed-run",
        "started_at": NOW_ISO,
        "updated_at": NOW_ISO,
        "pid": 9999,
        "hostname": "seed-host",
        "revision": "seed-revision",
        "timeout_seconds": 285,
        "lock_version": 1,
    }
    payload.update(overrides)
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    lock_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


@pytest.fixture
def harness(tmp_path, monkeypatch):
    lock_file = tmp_path / "logs" / "rss_fetcher.lock"
    logger = Mock()
    alive, write_calls, atexit_callbacks, signal_handlers = set(), [], [], {}
    original_write_text = Path.write_text

    def fake_kill(pid: int, _sig: int):
        if pid in alive:
            return None
        raise ProcessLookupError(pid)

    def wrapped_write_text(self, data, *args, **kwargs):
        write_calls.append((Path(self), data))
        return original_write_text(self, data, *args, **kwargs)

    def fake_signal(sig, handler):
        previous = signal_handlers.get(sig, "SIG_DFL")
        signal_handlers[sig] = handler
        return previous

    monkeypatch.setattr(rss_fetcher.time, "time", lambda: FIXED_TIME)
    monkeypatch.setattr(rss_fetcher, "_lock_timestamp_now", lambda: NOW_ISO)
    monkeypatch.setattr(rss_fetcher.os, "kill", fake_kill)
    monkeypatch.setattr(Path, "write_text", wrapped_write_text)
    monkeypatch.setattr(rss_fetcher.signal, "getsignal", lambda sig: signal_handlers.get(sig, "SIG_DFL"))
    monkeypatch.setattr(rss_fetcher.signal, "signal", fake_signal)
    monkeypatch.setattr(rss_fetcher.atexit, "register", lambda callback: atexit_callbacks.append(callback) or callback)
    monkeypatch.setattr(rss_fetcher, "ROOT", tmp_path)
    monkeypatch.setattr(rss_fetcher, "setup_logger", lambda: logger)
    monkeypatch.setattr(rss_fetcher.os, "getpid", lambda: FIXED_PID)
    monkeypatch.setattr(rss_fetcher.socket, "gethostname", lambda: "test-host")
    monkeypatch.setattr(rss_fetcher.uuid, "uuid4", lambda: FIXED_RUN_ID)
    monkeypatch.setattr(
        rss_fetcher.argparse.ArgumentParser,
        "parse_args",
        lambda _self: Namespace(dry_run=True, draft_only=False, limit=10, article_ai_mode=None),
    )
    monkeypatch.setenv("K_REVISION", "rev-test")

    state = {
        "lock_file": lock_file,
        "logger": logger,
        "alive": alive,
        "write_calls": write_calls,
        "atexit_callbacks": atexit_callbacks,
        "signal_handlers": signal_handlers,
    }

    def run(main_impl=None):
        main_mock = Mock(side_effect=main_impl)
        monkeypatch.setattr(rss_fetcher, "_main", main_mock)
        state["main_mock"] = main_mock
        rss_fetcher.main()
        return main_mock

    state["run"] = run
    return state


def test_acquire_writes_structured_metadata_when_no_lock(harness):
    observed = {}

    def main_impl(_args, _logger):
        observed["payload"] = json.loads(harness["lock_file"].read_text(encoding="utf-8"))

    harness["run"](main_impl)
    payload = observed["payload"]
    assert (
        payload["run_id"],
        payload["started_at"],
        payload["updated_at"],
        payload["pid"],
        payload["hostname"],
        payload["revision"],
        payload["timeout_seconds"],
        payload["lock_version"],
    ) == (FIXED_RUN_ID.hex, NOW_ISO, NOW_ISO, FIXED_PID, "test-host", "rev-test", 840, 1)
    assert harness["main_mock"].call_count == 1 and not harness["lock_file"].exists()
    assert harness["write_calls"][-1][0] == harness["lock_file"]
    assert _event(harness["logger"], "rss_fetcher_lock_acquired")["ttl_seconds"] == 1680


def test_skip_when_fresh_lock_with_live_pid(harness):
    seed = _seed_lock(harness["lock_file"], run_id="live-run", pid=7777)
    harness["alive"].add(7777)
    harness["run"]()
    skip = _event(harness["logger"], "rss_fetcher_lock_skip")
    assert harness["main_mock"].call_count == 0
    assert json.loads(harness["lock_file"].read_text(encoding="utf-8")) == seed
    assert (
        skip["reason"],
        skip["lock_run_id"],
        skip["current_run_id"],
        skip["lock_pid"],
        skip["lock_pid_alive"],
        skip["ttl_seconds"],
        skip["severity"],
    ) == ("fresh_lock", "live-run", FIXED_RUN_ID.hex, 7777, True, 900, "WARNING")
    assert harness["atexit_callbacks"] == []


def test_remove_when_stale_lock_ttl_expired_and_pid_dead(harness):
    _seed_lock(harness["lock_file"], run_id="stale-old", pid=8888, started_at=_iso_before(901), updated_at=_iso_before(901))
    harness["run"]()
    stale = _event(harness["logger"], "rss_fetcher_stale_lock_removed")
    assert harness["main_mock"].call_count == 1 and not harness["lock_file"].exists()
    assert (
        stale["reason"],
        stale["stale_run_id"],
        stale["lock_age_seconds"],
        stale["lock_pid"],
        stale["ttl_seconds"],
        stale["severity"],
    ) == ("pid_dead", "stale-old", 901, 8888, 900, "ERROR")


def test_remove_when_stale_lock_pid_dead_within_ttl(harness):
    _seed_lock(harness["lock_file"], run_id="dead-recent", pid=9998, started_at=_iso_before(30), updated_at=_iso_before(30))
    harness["run"]()
    stale = _event(harness["logger"], "rss_fetcher_stale_lock_removed")
    assert harness["main_mock"].call_count == 1 and not harness["lock_file"].exists()
    assert (stale["reason"], stale["lock_age_seconds"]) == ("pid_dead", 30)


def test_skip_when_corrupt_recent_lock(harness):
    harness["lock_file"].parent.mkdir(parents=True, exist_ok=True)
    harness["lock_file"].write_text("{corrupt", encoding="utf-8")
    os.utime(harness["lock_file"], (FIXED_TIME, FIXED_TIME))
    harness["run"]()
    skip = _event(harness["logger"], "rss_fetcher_lock_skip")
    assert harness["main_mock"].call_count == 0 and harness["lock_file"].exists()
    assert (skip["reason"], skip["lock_pid"], skip["severity"]) == ("corrupt_recent", "unknown", "WARNING")


def test_remove_when_corrupt_old_lock(harness):
    harness["lock_file"].parent.mkdir(parents=True, exist_ok=True)
    harness["lock_file"].write_text("{corrupt", encoding="utf-8")
    stale_time = FIXED_TIME - 1681
    os.utime(harness["lock_file"], (stale_time, stale_time))
    harness["run"]()
    stale = _event(harness["logger"], "rss_fetcher_stale_lock_removed")
    assert harness["main_mock"].call_count == 1 and not harness["lock_file"].exists()
    assert (stale["reason"], stale["lock_age_seconds"], stale["lock_pid"]) == ("corrupt_old", 1681, "unknown")


def test_finally_releases_owned_lock_on_exception(harness):
    def main_impl(_args, _logger):
        assert harness["lock_file"].exists()
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        harness["run"](main_impl)
    released = _event(harness["logger"], "rss_fetcher_lock_released")
    assert not harness["lock_file"].exists()
    assert (released["current_run_id"], released["lock_pid"]) == (FIXED_RUN_ID.hex, FIXED_PID)


def test_does_not_release_other_runs_lock(harness):
    _seed_lock(harness["lock_file"], run_id="other-run", pid=1111)
    cleanup = rss_fetcher._build_lock_cleanup(harness["lock_file"], FIXED_RUN_ID.hex, harness["logger"])
    assert cleanup() is False and harness["lock_file"].exists()


def test_atexit_cleanup_idempotent(harness):
    _seed_lock(harness["lock_file"], run_id=FIXED_RUN_ID.hex, pid=FIXED_PID)
    cleanup = rss_fetcher._build_lock_cleanup(harness["lock_file"], FIXED_RUN_ID.hex, harness["logger"])
    assert cleanup() is True and cleanup() is False and not harness["lock_file"].exists()
    releases = [json.loads(call.args[0]) for call in harness["logger"].info.call_args_list if "rss_fetcher_lock_released" in call.args[0]]
    assert len(releases) == 1
