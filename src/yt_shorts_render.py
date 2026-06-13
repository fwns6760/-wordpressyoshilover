"""Pillow/ffmpeg renderer for rights-safe YouTube Shorts.

The renderer creates 1080x1920 static data cards, burns the captions into the
frames, synthesizes or prepares audio, and lets ffmpeg assemble the MP4.  It
never reads or embeds game footage, photos, or third-party media.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import math
import os
import subprocess
import wave

import requests

from src.yt_shorts_script import ShortsScript
from src.yt_shorts_topic import ShortsTopic


WIDTH = 1080
HEIGHT = 1920
DEFAULT_FRAME_DURATIONS = (3.0, 14.0, 14.0, 14.0, 15.0)

FONT_CANDIDATES_BOLD = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
)
FONT_CANDIDATES_REGULAR = (
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


@dataclass(frozen=True)
class RenderedShort:
    video_path: Path
    audio_path: Path
    frame_paths: tuple[Path, ...]
    metadata_path: Path
    duration_seconds: float
    tts_mode: str


def _font(size: int, *, bold: bool = False):
    from PIL import ImageFont

    candidates = FONT_CANDIDATES_BOLD if bold else FONT_CANDIDATES_REGULAR
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def _text_width(draw, text: str, font) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _wrap_text(draw, text: str, font, max_width: int, *, max_lines: int = 4) -> list[str]:
    words = list(str(text or ""))
    lines: list[str] = []
    current = ""
    for ch in words:
        candidate = current + ch
        if current and _text_width(draw, candidate, font) > max_width:
            lines.append(current)
            current = ch
            if len(lines) >= max_lines:
                break
        else:
            current = candidate
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    return lines


def _draw_centered_lines(draw, lines: list[str], y: int, font, fill: str, *, gap: int = 12) -> int:
    line_height = font.size + gap
    for line in lines:
        draw.text((WIDTH // 2, y), line, font=font, fill=fill, anchor="ma")
        y += line_height
    return y


def _draw_common_chrome(draw, *, label: str) -> None:
    draw.rounded_rectangle((64, 64, WIDTH - 64, 164), radius=32, fill="#151515")
    draw.text((96, 116), "YOSHILOVER DATA SHORTS", font=_font(30, bold=True), fill="#ffffff", anchor="lm")
    draw.rounded_rectangle((WIDTH - 312, 88, WIDTH - 94, 140), radius=26, fill="#ff7a1a")
    draw.text((WIDTH - 203, 116), label, font=_font(24, bold=True), fill="#ffffff", anchor="mm")


def _draw_footer(draw) -> None:
    draw.rectangle((0, HEIGHT - 168, WIDTH, HEIGHT), fill="#151515")
    draw.rectangle((0, HEIGHT - 168, WIDTH, HEIGHT - 156), fill="#ff7a1a")
    draw.text((72, HEIGHT - 86), "詳しいデータは yoshilover.com/data/notable?v=yt", font=_font(30, bold=True), fill="#ffffff", anchor="lm")


def _frame_background():
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (WIDTH, HEIGHT), "#f7f3ed")
    draw = ImageDraw.Draw(img)
    for y in range(0, HEIGHT, 8):
        ratio = y / HEIGHT
        r = int(247 + (255 - 247) * ratio)
        g = int(243 + (249 - 243) * ratio)
        b = int(237 + (231 - 237) * ratio)
        draw.rectangle((0, y, WIDTH, y + 8), fill=(r, g, b))
    return img, draw


def _draw_frame(topic: ShortsTopic, script: ShortsScript, index: int, path: Path) -> None:
    img, draw = _frame_background()
    _draw_common_chrome(draw, label=f"{index + 1}/5")

    title_font = _font(72, bold=True)
    big_font = _font(150, bold=True)
    mid_font = _font(54, bold=True)
    body_font = _font(42)
    small_font = _font(30)

    if index == 0:
        draw.rounded_rectangle((74, 330, WIDTH - 74, 1030), radius=48, fill="#ffffff", outline="#ffe0bf", width=4)
        draw.text((WIDTH // 2, 410), "今日の注目データ", font=mid_font, fill="#c94700", anchor="ma")
        _draw_centered_lines(draw, _wrap_text(draw, topic.hook, title_font, 820, max_lines=3), 560, title_font, "#151515", gap=18)
        draw.rounded_rectangle((168, 1120, WIDTH - 168, 1220), radius=50, fill="#151515")
        draw.text((WIDTH // 2, 1170), "数字で見る巨人", font=mid_font, fill="#ffffff", anchor="mm")
    elif index == 1:
        draw.text((WIDTH // 2, 360), topic.player, font=title_font, fill="#151515", anchor="ma")
        draw.rounded_rectangle((114, 560, WIDTH - 114, 1040), radius=54, fill="#ff7a1a")
        draw.text((WIDTH // 2, 675), topic.label, font=mid_font, fill="#ffffff", anchor="ma")
        draw.text((WIDTH // 2, 875), topic.value, font=big_font, fill="#ffffff", anchor="mm")
    elif index == 2:
        draw.rounded_rectangle((84, 380, WIDTH - 84, 1160), radius=48, fill="#151515")
        draw.text((WIDTH // 2, 500), "ここがポイント", font=mid_font, fill="#ffd166", anchor="ma")
        text = topic.note or "今の巨人で見逃せない数字"
        _draw_centered_lines(draw, _wrap_text(draw, text, title_font, 820, max_lines=4), 690, title_font, "#ffffff", gap=20)
    elif index == 3:
        draw.text((WIDTH // 2, 360), "結果だけでなく", font=title_font, fill="#151515", anchor="ma")
        draw.text((WIDTH // 2, 470), "流れまで見る", font=title_font, fill="#c94700", anchor="ma")
        draw.rounded_rectangle((114, 690, WIDTH - 114, 1160), radius=48, fill="#ffffff", outline="#f0d3bd", width=4)
        body = f"{topic.player}の数字は、次の試合を見る目線を変える材料になります。"
        _draw_centered_lines(draw, _wrap_text(draw, body, body_font, 780, max_lines=5), 810, body_font, "#202020", gap=20)
    else:
        draw.text((WIDTH // 2, 390), "続きは", font=title_font, fill="#151515", anchor="ma")
        draw.text((WIDTH // 2, 520), "ヨシラバーで", font=title_font, fill="#c94700", anchor="ma")
        draw.rounded_rectangle((124, 720, WIDTH - 124, 1010), radius=44, fill="#ffffff", outline="#ffb36b", width=4)
        draw.text((WIDTH // 2, 810), "巨人 注目データ", font=mid_font, fill="#151515", anchor="ma")
        draw.text((WIDTH // 2, 910), "/data/notable?v=yt", font=small_font, fill="#555555", anchor="ma")

    caption = script.captions[min(index, len(script.captions) - 1)].text
    draw.rounded_rectangle((74, HEIGHT - 340, WIDTH - 74, HEIGHT - 210), radius=36, fill="#ffffff", outline="#f0d3bd", width=3)
    _draw_centered_lines(draw, _wrap_text(draw, caption, _font(38, bold=True), 840, max_lines=2), HEIGHT - 296, _font(38, bold=True), "#151515", gap=10)
    _draw_footer(draw)
    img.save(path, "PNG")


def render_frames(topic: ShortsTopic, script: ShortsScript, output_dir: Path | str) -> tuple[Path, ...]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for index in range(5):
        path = out / f"frame_{index + 1:02d}.png"
        _draw_frame(topic, script, index, path)
        paths.append(path)
    return tuple(paths)


def write_silent_wav(path: Path | str, *, duration_seconds: float, sample_rate: int = 24000) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    total_frames = int(math.ceil(duration_seconds * sample_rate))
    silence = b"\x00\x00" * total_frames
    with wave.open(str(target), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(silence)
    return target


def synthesize_voicevox(
    text: str,
    output_wav: Path | str,
    *,
    base_url: str,
    speaker: int = 13,
    timeout_seconds: int = 90,
) -> Path:
    base = base_url.rstrip("/")
    query = requests.post(
        f"{base}/audio_query",
        params={"text": text, "speaker": speaker},
        timeout=timeout_seconds,
    )
    query.raise_for_status()
    synthesis = requests.post(
        f"{base}/synthesis",
        params={"speaker": speaker},
        json=query.json(),
        timeout=timeout_seconds,
    )
    synthesis.raise_for_status()
    target = Path(output_wav)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(synthesis.content)
    return target


def prepare_audio(
    script: ShortsScript,
    output_wav: Path | str,
    *,
    duration_seconds: float,
    voicevox_base_url: str = "",
    speaker: int = 13,
    allow_silent: bool = False,
) -> tuple[Path, str]:
    if voicevox_base_url.strip():
        return (
            synthesize_voicevox(
                script.narration,
                output_wav,
                base_url=voicevox_base_url.strip(),
                speaker=speaker,
            ),
            "voicevox",
        )
    if allow_silent:
        return (write_silent_wav(output_wav, duration_seconds=duration_seconds), "silent")
    raise RuntimeError("VOICEVOX base URL is required unless allow_silent=True")


def _concat_file_line(path: Path) -> str:
    escaped = str(path.resolve()).replace("'", "'\\''")
    return f"file '{escaped}'"


def compose_video(
    frame_paths: tuple[Path, ...],
    audio_path: Path | str,
    output_mp4: Path | str,
    *,
    durations: tuple[float, ...] = DEFAULT_FRAME_DURATIONS,
    ffmpeg_bin: str = "ffmpeg",
) -> Path:
    if len(frame_paths) != len(durations):
        raise ValueError("frame_paths and durations length mismatch")
    target = Path(output_mp4)
    target.parent.mkdir(parents=True, exist_ok=True)
    concat_path = target.with_suffix(".concat.txt")
    lines: list[str] = []
    for path, duration in zip(frame_paths, durations):
        lines.append(_concat_file_line(path))
        lines.append(f"duration {duration:.3f}")
    lines.append(_concat_file_line(frame_paths[-1]))
    concat_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    cmd = [
        ffmpeg_bin,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_path),
        "-i",
        str(audio_path),
        "-vf",
        "fps=30,format=yuv420p",
        "-shortest",
        "-c:v",
        "libx264",
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(target),
    ]
    subprocess.run(cmd, check=True)
    return target


def render_short(
    topic: ShortsTopic,
    script: ShortsScript,
    output_dir: Path | str,
    *,
    voicevox_base_url: str = "",
    speaker: int = 13,
    allow_silent_tts: bool = False,
    ffmpeg_bin: str = "ffmpeg",
) -> RenderedShort:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    duration = float(sum(DEFAULT_FRAME_DURATIONS))
    frames = render_frames(topic, script, out)
    audio_path, tts_mode = prepare_audio(
        script,
        out / "narration.wav",
        duration_seconds=duration,
        voicevox_base_url=voicevox_base_url,
        speaker=speaker,
        allow_silent=allow_silent_tts,
    )
    video_path = compose_video(frames, audio_path, out / "short.mp4", ffmpeg_bin=ffmpeg_bin)
    metadata_path = out / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "topic_key": topic.topic_key,
                "title": script.title,
                "description": script.description,
                "duration_seconds": duration,
                "tts_mode": tts_mode,
                "frames": [str(path.name) for path in frames],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return RenderedShort(
        video_path=video_path,
        audio_path=audio_path,
        frame_paths=frames,
        metadata_path=metadata_path,
        duration_seconds=duration,
        tts_mode=tts_mode,
    )


__all__ = [
    "DEFAULT_FRAME_DURATIONS",
    "RenderedShort",
    "compose_video",
    "prepare_audio",
    "render_frames",
    "render_short",
    "synthesize_voicevox",
    "write_silent_wav",
]
