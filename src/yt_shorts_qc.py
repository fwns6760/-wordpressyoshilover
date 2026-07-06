"""yt_shorts_qc — 書き出した MP4 実測ベースの品質ゲート (2026-07-06 user 指示)。

目的は本数を増やすことではなく、名前・読み・尺の品質事故を止めること。
NG の場合は承認 mail に出さず (=公開経路に乗せない)、理由を log + NG 通知 mail に
残して修正候補を出す。尺チェックは台本文字数ではなく **書き出した MP4 の実測秒**。

チェック項目 (user 指定の NG 条件):
1. 想定尺超過 (YT_SHORTS_QC_MAX_SECONDS、default 58.5)
2. 短すぎ = 内容が薄い (YT_SHORTS_QC_MIN_SECONDS、default 15)
3. 音声の途中切れ (narration wav 実測 > MP4 実測 + margin)
4. 締め・ヨシラバー表記が台本に入っていない
5. 末尾の無音が長い / 1 フレームあたりが長すぎる = テンポが悪い
6. TTS に漢字のまま渡っている選手名 (読み辞書 ALL_NAME_READINGS 通過後の残漢字)

kill switch: YT_SHORTS_QC=0 で無効 (default 有効)。
"""

from __future__ import annotations

import logging
import os
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path

LOG = logging.getLogger("yt_shorts_qc")

_DEF_MIN_SECONDS = 15.0
_DEF_MAX_SECONDS = 58.5
_DEF_AUDIO_CUT_MARGIN = 0.35
_DEF_MAX_TRAILING_SILENCE = 6.0
_DEF_MAX_SECONDS_PER_FRAME = 9.0


def qc_enabled() -> bool:
    raw = (os.environ.get("YT_SHORTS_QC") or "").strip().lower()
    if not raw:
        return True
    return raw not in {"0", "false", "no", "off"}


def _env_float(name: str, default: float) -> float:
    raw = (os.environ.get(name) or "").strip()
    try:
        return float(raw) if raw else default
    except ValueError:
        return default


@dataclass(frozen=True)
class ShortsQCReport:
    ok: bool
    issues: tuple[str, ...]
    fixes: tuple[str, ...]
    video_seconds: float
    audio_seconds: float

    def summary(self) -> str:
        head = "QC PASS" if self.ok else "QC NG"
        return (
            f"{head} video={self.video_seconds:.1f}s audio={self.audio_seconds:.1f}s"
            + ("" if self.ok else " | " + " / ".join(self.issues))
        )


def probe_media_seconds(path: Path | str, *, ffprobe_bin: str = "ffprobe") -> float:
    """実ファイルの尺 (秒)。ffprobe → wav fallback。取れなければ 0.0。"""
    p = Path(path)
    if not p.exists():
        return 0.0
    try:
        out = subprocess.run(
            [
                ffprobe_bin, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(p),
            ],
            capture_output=True, text=True, timeout=30, check=True,
        ).stdout.strip()
        return max(0.0, float(out))
    except Exception:  # noqa: BLE001 - wav fallback へ
        pass
    if p.suffix.lower() == ".wav":
        try:
            with wave.open(str(p), "rb") as w:
                rate = w.getframerate()
                return (w.getnframes() / float(rate)) if rate else 0.0
        except Exception:  # noqa: BLE001
            return 0.0
    return 0.0


def _remaining_kanji_names(tts_text: str) -> list[str]:
    """読み辞書通過後の TTS 原稿に漢字のまま残っている登録選手名。

    ALL_NAME_READINGS (baked 全ロースター + 手動 OVERRIDES) の key が残っていれば
    変換漏れ。通常は _apply_name_readings で全置換されるため 0 件のはず。
    """
    try:
        from src.yt_shorts_script import ALL_NAME_READINGS
    except Exception:  # noqa: BLE001
        return []
    return [k for k in ALL_NAME_READINGS if len(k) >= 2 and k in (tts_text or "")]


def evaluate_qc(
    *,
    video_seconds: float,
    audio_seconds: float,
    tts_text: str,
    frame_count: int,
    closing_marker: str = "ヨシラバー",
    min_seconds: float | None = None,
    max_seconds: float | None = None,
) -> ShortsQCReport:
    """純関数の判定部 (テスト可能)。実測値を受け取り NG 理由と修正候補を返す。"""
    min_s = min_seconds if min_seconds is not None else _env_float("YT_SHORTS_QC_MIN_SECONDS", _DEF_MIN_SECONDS)
    max_s = max_seconds if max_seconds is not None else _env_float("YT_SHORTS_QC_MAX_SECONDS", _DEF_MAX_SECONDS)
    cut_margin = _env_float("YT_SHORTS_QC_AUDIO_CUT_MARGIN", _DEF_AUDIO_CUT_MARGIN)
    max_tail = _env_float("YT_SHORTS_QC_MAX_TRAILING_SILENCE", _DEF_MAX_TRAILING_SILENCE)
    max_spf = _env_float("YT_SHORTS_QC_MAX_SECONDS_PER_FRAME", _DEF_MAX_SECONDS_PER_FRAME)

    issues: list[str] = []
    fixes: list[str] = []

    if video_seconds <= 0:
        issues.append("動画尺を実測できない (ffprobe 失敗 or MP4 不在)")
        fixes.append("job image に ffprobe が入っているか / MP4 が書き出せているか確認")
    else:
        if video_seconds > max_s:
            issues.append(f"想定尺超過: 実測 {video_seconds:.1f}s > 上限 {max_s:.1f}s")
            fixes.append("台本を短くする (データ行を減らす / 説明文を1文削る)")
        if video_seconds < min_s:
            issues.append(f"尺が短すぎ: 実測 {video_seconds:.1f}s < 下限 {min_s:.1f}s")
            fixes.append("内容が薄い可能性。topic 選定と台本の中身を確認")
        if audio_seconds > 0 and audio_seconds > video_seconds + cut_margin:
            issues.append(
                f"音声が途中で切れている (narration {audio_seconds:.1f}s > 動画 {video_seconds:.1f}s)"
            )
            fixes.append("台本を短くして音声を動画尺に収める (締めの欠落防止)")
        if audio_seconds > 0 and (video_seconds - audio_seconds) > max_tail:
            issues.append(
                f"末尾の無音が長い ({video_seconds - audio_seconds:.1f}s) = テンポが悪い"
            )
            fixes.append("フレーム尺の伸縮 (fit_durations) と BGM 設定を確認")
        if frame_count > 0 and (video_seconds / frame_count) > max_spf:
            issues.append(
                f"1枚あたり {video_seconds / frame_count:.1f}s で画面が動かずテンポが悪い"
            )
            fixes.append("台本を短くするかフレーム(字幕)を分割して画面替わりを増やす")

    if closing_marker and closing_marker not in (tts_text or ""):
        issues.append("締めのヨシラバー表記が台本に入っていない")
        fixes.append("BRAND_CLOSING_LINE が narration 末尾に入る組み立てか確認")

    leftover = _remaining_kanji_names(tts_text)
    if leftover:
        issues.append("TTS に漢字のまま渡っている選手名: " + ", ".join(leftover[:5]))
        fixes.append("_apply_name_readings の適用漏れ経路を修正 (narration 生成後に適用)")

    # 重複 fix を除去して順序維持
    uniq_fixes = tuple(dict.fromkeys(fixes))
    return ShortsQCReport(
        ok=not issues,
        issues=tuple(issues),
        fixes=uniq_fixes,
        video_seconds=video_seconds,
        audio_seconds=audio_seconds,
    )


def run_qc(rendered, script, *, ffprobe_bin: str = "ffprobe") -> ShortsQCReport:
    """RenderedShort + ShortsScript を実測して判定。"""
    video_seconds = probe_media_seconds(rendered.video_path, ffprobe_bin=ffprobe_bin)
    audio_seconds = probe_media_seconds(rendered.audio_path, ffprobe_bin=ffprobe_bin)
    report = evaluate_qc(
        video_seconds=video_seconds,
        audio_seconds=audio_seconds,
        tts_text=getattr(script, "narration", "") or "",
        frame_count=len(getattr(rendered, "frame_paths", ()) or ()),
    )
    LOG.info("yt_shorts_qc %s", report.summary())
    return report
