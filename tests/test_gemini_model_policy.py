from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src import gemini_model_policy as policy


def _jst(hour: int, minute: int = 30) -> datetime:
    return datetime(2026, 6, 13, hour, minute, tzinfo=timezone(timedelta(hours=9)))


def test_selects_primary_inside_default_night_window() -> None:
    assert policy.select_gemini_model(_jst(17), env={}) == "gemini-3.5-flash"
    assert policy.select_gemini_model(_jst(22, 29), env={}) == "gemini-3.5-flash"


def test_selects_flash_lite_outside_default_night_window() -> None:
    assert policy.select_gemini_model(_jst(7), env={}) == "gemini-3.1-flash-lite"
    assert policy.select_gemini_model(_jst(22, 30), env={}) == "gemini-3.1-flash-lite"
    assert policy.select_gemini_model(_jst(23), env={}) == "gemini-3.1-flash-lite"


def test_env_can_override_models_and_window() -> None:
    env = {
        "GEMINI_PRIMARY_MODEL": "primary-custom",
        "GEMINI_FALLBACK_MODEL": "fallback-custom",
        "GEMINI_PRIMARY_HOURS_JST": "22:30-2:00",
    }
    assert policy.select_gemini_model(_jst(23), env=env) == "primary-custom"
    assert policy.select_gemini_model(_jst(22, 29), env=env) == "fallback-custom"
    assert policy.select_gemini_model(_jst(1, 59), env=env) == "primary-custom"
    assert policy.select_gemini_model(_jst(2, 0), env=env) == "fallback-custom"
    assert policy.select_gemini_model(_jst(3), env=env) == "fallback-custom"


def test_legacy_hour_window_still_supported() -> None:
    env = {"GEMINI_PRIMARY_HOURS_JST": "17-23"}
    assert policy.select_gemini_model(_jst(22, 59), env=env) == "gemini-3.5-flash"
    assert policy.select_gemini_model(_jst(23, 0), env=env) == "gemini-3.1-flash-lite"


def test_invalid_window_fails_open_to_primary() -> None:
    assert (
        policy.select_gemini_model(_jst(3), env={"GEMINI_PRIMARY_HOURS_JST": "bad"})
        == "gemini-3.5-flash"
    )
