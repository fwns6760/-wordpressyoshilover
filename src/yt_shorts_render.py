"""Pillow/ffmpeg renderer for rights-aware YouTube Shorts.

The renderer creates 1080x1920 static data cards, burns the captions into the
frames, synthesizes or prepares audio/BGM, and lets ffmpeg assemble the MP4.
It never reads or embeds game footage, broadcast screenshots, or third-party
press media. Player images are only loaded when the topic or environment
provides a usable asset URL/path.
"""

from __future__ import annotations

from io import BytesIO
from dataclasses import dataclass
from pathlib import Path
import json
import math
import os
import subprocess
import struct
import wave

import requests
from PIL import Image, ImageDraw

from src.yt_shorts_script import ShortsScript, display_as_of_date
from src.yt_shorts_topic import ShortsTopic


WIDTH = 1080
HEIGHT = 1920
DEFAULT_FRAME_DURATIONS = (2.2, 6.2, 6.4, 6.2, 6.0)
# Ken Burns motion: turn the 5 static cards into moving clips so the Short
# reads as video, not a slideshow (the main "looks AI-mass-produced" tell).
MOTION_FPS = 30
MOTION_OPENING_ZOOM = 1.12
MOTION_ZOOM = 1.08
MOTION_MAX_ZOOM = 1.12  # overscan headroom = the strongest end zoom in use
MOTION_DRIFT_PX = 40
MOTION_FADE_SECONDS = 0.35
DEFAULT_VOICE_STYLE = "dynamic"
DEFAULT_DYNAMIC_AUDIO_FILTER = (
    "highpass=f=85,"
    "acompressor=threshold=-18dB:ratio=3:attack=8:release=90:makeup=5,"
    "equalizer=f=2800:t=q:w=1.1:g=2.5,"
    "loudnorm=I=-16:TP=-1.5:LRA=9"
)

VOICE_STYLE_ENV = "YT_SHORTS_VOICE_STYLE"
VOICE_SPEED_ENV = "YT_SHORTS_VOICE_SPEED_SCALE"
VOICE_INTONATION_ENV = "YT_SHORTS_VOICE_INTONATION_SCALE"
VOICE_VOLUME_ENV = "YT_SHORTS_VOICE_VOLUME_SCALE"
VOICE_PRE_PHONEME_ENV = "YT_SHORTS_VOICE_PRE_PHONEME_LENGTH"
VOICE_POST_PHONEME_ENV = "YT_SHORTS_VOICE_POST_PHONEME_LENGTH"
AUDIO_FILTER_ENV = "YT_SHORTS_AUDIO_FILTER"
FFMPEG_THREADS_ENV = "YT_SHORTS_FFMPEG_THREADS"
FFMPEG_PRESET_ENV = "YT_SHORTS_FFMPEG_PRESET"
BGM_STYLE_ENV = "YT_SHORTS_BGM_STYLE"
BGM_VOLUME_ENV = "YT_SHORTS_BGM_VOLUME"
BGM_BPM_ENV = "YT_SHORTS_BGM_BPM"
PLAYER_IMAGE_ENV = "YT_SHORTS_PLAYER_IMAGE_URL"
DEFAULT_FFMPEG_THREADS = "1"
DEFAULT_FFMPEG_PRESET = "veryfast"
DEFAULT_BGM_STYLE = "pop"
DEFAULT_BGM_VOLUME = 0.11
DEFAULT_BGM_BPM = 132.0
STANDARD_PLAYER_VISUAL_BOX = (24, 268, 1032, 920)
OPENING_PLAYER_VISUAL_BOX = (0, 268, WIDTH, 1040)

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

_PLAYER_IMAGE_CACHE: dict[str, Image.Image | None] = {}


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


def _topic_player_image_url(topic: ShortsTopic) -> str:
    env_url = os.environ.get(PLAYER_IMAGE_ENV, "").strip()
    if env_url:
        return env_url
    raw = topic.raw_item or {}
    # Only the explicit player-photo field is accepted here. Generic
    # article images (featured/image/photo) can be scene photos, logos, or
    # unrelated thumbnails, which makes the Shorts visual unstable.
    return str(raw.get("player_image_url") or "").strip()


def _cover_crop(image: Image.Image, width: int, height: int) -> Image.Image:
    img = image.convert("RGB")
    scale = max(width / img.width, height / img.height)
    resized = img.resize((int(img.width * scale), int(img.height * scale)))
    left = max(0, (resized.width - width) // 2)
    top = max(0, (resized.height - height) // 3)
    return resized.crop((left, top, left + width, top + height))


def _load_player_image(url: str) -> Image.Image | None:
    if not url:
        return None
    if url in _PLAYER_IMAGE_CACHE:
        cached = _PLAYER_IMAGE_CACHE[url]
        return cached.copy() if cached is not None else None
    try:
        if url.startswith(("http://", "https://")):
            response = requests.get(url, timeout=15)
            response.raise_for_status()
            img = Image.open(BytesIO(response.content))
        else:
            img = Image.open(url)
        loaded = img.convert("RGB")
        _PLAYER_IMAGE_CACHE[url] = loaded.copy()
        return loaded
    except Exception:
        _PLAYER_IMAGE_CACHE[url] = None
        return None


def _draw_player_visual(
    canvas: Image.Image,
    draw,
    topic: ShortsTopic,
    *,
    x: int,
    y: int,
    width: int,
    height: int,
) -> None:
    image = _load_player_image(_topic_player_image_url(topic))
    if image is not None:
        cropped = _cover_crop(image, width, height)
        mask = Image.new("L", (width, height), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle((0, 0, width, height), radius=46, fill=255)
        canvas.paste(cropped, (x, y), mask)
        shade = Image.new("RGBA", (width, 140), (0, 0, 0, 176))
        canvas.paste(shade, (x, y + height - 140), shade)
        draw.rounded_rectangle((x, y, x + width, y + height), radius=46, outline="#ffffff", width=5)
        draw.text((x + 36, y + height - 62), topic.player, font=_font(42, bold=True), fill="#ffffff", anchor="lm")
        return

    draw.rounded_rectangle((x, y, x + width, y + height), radius=46, fill="#151515", outline="#ffb36b", width=5)
    for line_y in range(y, y + height, 18):
        alpha = (line_y - y) / max(1, height)
        color = (
            int(32 + alpha * 38),
            int(34 + alpha * 28),
            int(40 + alpha * 20),
        )
        draw.line((x + 8, line_y, x + width - 8, line_y), fill=color, width=4)
    initials = "".join(part[:1] for part in topic.player.replace("　", " ").split()) or topic.player[:2]
    draw.text((x + width // 2, y + height // 2 - 18), initials[:3], font=_font(98, bold=True), fill="#ffb36b", anchor="mm")
    draw.text((x + width // 2, y + height - 86), topic.player, font=_font(40, bold=True), fill="#ffffff", anchor="mm")


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


def _draw_common_chrome(draw, *, label: str, as_of: str = "") -> None:
    draw.rounded_rectangle((64, 64, WIDTH - 64, 164), radius=32, fill="#151515")
    draw.text((96, 116), "YOSHILOVER DATA SHORTS", font=_font(30, bold=True), fill="#ffffff", anchor="lm")
    draw.rounded_rectangle((WIDTH - 312, 88, WIDTH - 94, 140), radius=26, fill="#ff7a1a")
    draw.text((WIDTH - 203, 116), label, font=_font(24, bold=True), fill="#ffffff", anchor="mm")
    date_label = display_as_of_date(as_of)
    if date_label:
        draw.rounded_rectangle((64, 188, WIDTH - 64, 252), radius=28, fill="#fff2e4", outline="#ffb36b", width=2)
        draw.text((96, 220), f"記録日: {date_label}時点", font=_font(28, bold=True), fill="#9a3f00", anchor="lm")


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
    _draw_common_chrome(draw, label=f"{index + 1}/5", as_of=topic.as_of)

    title_font = _font(72, bold=True)
    big_font = _font(150, bold=True)
    mid_font = _font(54, bold=True)
    body_font = _font(42)
    small_font = _font(30)

    if index == 0:
        x, y, w, h = OPENING_PLAYER_VISUAL_BOX
        _draw_player_visual(img, draw, topic, x=x, y=y, width=w, height=h)
        draw.rounded_rectangle((64, 1266, WIDTH - 64, 1536), radius=48, fill="#ffffff", outline="#ffe0bf", width=4)
        draw.text((WIDTH // 2, 1324), "今日の注目データ", font=_font(48, bold=True), fill="#c94700", anchor="ma")
        _draw_centered_lines(draw, _wrap_text(draw, topic.hook, _font(62, bold=True), 840, max_lines=2), 1406, _font(62, bold=True), "#151515", gap=14)
        draw.rounded_rectangle((230, 1474, WIDTH - 230, 1548), radius=37, fill="#151515")
        draw.text((WIDTH // 2, 1511), "数字で見る巨人", font=_font(36, bold=True), fill="#ffffff", anchor="mm")
    elif index == 1:
        x, y, w, h = STANDARD_PLAYER_VISUAL_BOX
        _draw_player_visual(img, draw, topic, x=x, y=y, width=w, height=h)
        draw.rounded_rectangle((104, 1140, WIDTH - 104, 1516), radius=54, fill="#ff7a1a")
        draw.text((WIDTH // 2, 1220), topic.label, font=_font(50, bold=True), fill="#ffffff", anchor="ma")
        draw.text((WIDTH // 2, 1392), topic.value, font=_font(132, bold=True), fill="#ffffff", anchor="mm")
    elif index == 2:
        x, y, w, h = STANDARD_PLAYER_VISUAL_BOX
        _draw_player_visual(img, draw, topic, x=x, y=y, width=w, height=h)
        draw.rounded_rectangle((84, 1140, WIDTH - 84, 1516), radius=48, fill="#151515")
        draw.text((WIDTH // 2, 1208), "ここがポイント", font=_font(48, bold=True), fill="#ffd166", anchor="ma")
        text = topic.note or "今の巨人で見逃せない数字"
        _draw_centered_lines(draw, _wrap_text(draw, text, _font(66, bold=True), 820, max_lines=3), 1300, _font(66, bold=True), "#ffffff", gap=18)
    elif index == 3:
        x, y, w, h = STANDARD_PLAYER_VISUAL_BOX
        _draw_player_visual(img, draw, topic, x=x, y=y, width=w, height=h)
        draw.rounded_rectangle((114, 1140, WIDTH - 114, 1516), radius=48, fill="#ffffff", outline="#f0d3bd", width=4)
        draw.text((WIDTH // 2, 1210), "結果だけでなく", font=_font(54, bold=True), fill="#151515", anchor="ma")
        draw.text((WIDTH // 2, 1284), "流れまで見る", font=_font(54, bold=True), fill="#c94700", anchor="ma")
        body = f"{topic.player}の数字は、次の試合を見る目線を変える材料になります。"
        _draw_centered_lines(draw, _wrap_text(draw, body, _font(38), 780, max_lines=3), 1372, _font(38), "#202020", gap=16)
    else:
        x, y, w, h = STANDARD_PLAYER_VISUAL_BOX
        _draw_player_visual(img, draw, topic, x=x, y=y, width=w, height=h)
        draw.rounded_rectangle((124, 1210, WIDTH - 124, 1516), radius=44, fill="#ffffff", outline="#ffb36b", width=4)
        draw.text((WIDTH // 2, 1288), "続きはヨシラバーで", font=_font(54, bold=True), fill="#c94700", anchor="ma")
        draw.text((WIDTH // 2, 1372), "巨人 注目データ", font=_font(44, bold=True), fill="#151515", anchor="ma")
        draw.text((WIDTH // 2, 1456), "/data/notable?v=yt", font=small_font, fill="#555555", anchor="ma")

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


def write_pop_bgm_wav(
    path: Path | str,
    *,
    duration_seconds: float,
    sample_rate: int = 44100,
    volume: float = DEFAULT_BGM_VOLUME,
    bpm: float = DEFAULT_BGM_BPM,
) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    total_frames = int(math.ceil(duration_seconds * sample_rate))
    beat_seconds = 60.0 / max(60.0, bpm)
    chord_roots = (261.63, 392.00, 440.00, 349.23)
    frames = bytearray()
    volume = max(0.0, min(volume, 0.25))

    for index in range(total_frames):
        t = index / sample_rate
        beat_pos = (t % beat_seconds) / beat_seconds
        bar = int(t / (beat_seconds * 4))
        root = chord_roots[bar % len(chord_roots)]

        sidechain = 0.74 + 0.26 * min(1.0, beat_pos / 0.28)
        pad = (
            math.sin(2 * math.pi * root * t)
            + 0.55 * math.sin(2 * math.pi * root * 1.25 * t)
            + 0.45 * math.sin(2 * math.pi * root * 1.5 * t)
        ) / 2.0
        bass_gate = 1.0 if beat_pos < 0.52 else 0.35
        bass = math.sin(2 * math.pi * (root / 2.0) * t) * bass_gate
        pulse = math.sin(2 * math.pi * root * 2.0 * t) * max(0.0, 1.0 - beat_pos) ** 2
        hat = math.sin(2 * math.pi * 7200.0 * t) * (1.0 if beat_pos > 0.48 else 0.0) * 0.11
        kick = math.sin(2 * math.pi * 58.0 * t) * max(0.0, 1.0 - beat_pos * 8.0) ** 2

        sample = (0.48 * pad * sidechain) + (0.24 * bass) + (0.16 * pulse) + hat + (0.30 * kick)
        envelope = min(1.0, t / 1.1, (duration_seconds - t) / 1.1 if duration_seconds > 1.1 else 1.0)
        value = int(max(-1.0, min(1.0, sample * volume * envelope)) * 32767)
        frames.extend(struct.pack("<h", value))

    with wave.open(str(target), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(bytes(frames))
    return target


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_text(name: str, default: str) -> str:
    raw = os.environ.get(name, "").strip()
    return raw or default


def _voice_style() -> str:
    return (os.environ.get(VOICE_STYLE_ENV, DEFAULT_VOICE_STYLE) or "").strip().lower()


def _apply_voice_style(audio_query: dict, *, style: str | None = None) -> dict:
    """Tune VOICEVOX query params for a less flat sports-news read."""
    resolved_style = (style or _voice_style()).strip().lower()
    if resolved_style in {"", "plain", "none", "off", "0"}:
        return audio_query

    audio_query["speedScale"] = _env_float(VOICE_SPEED_ENV, 1.12)
    audio_query["intonationScale"] = _env_float(VOICE_INTONATION_ENV, 1.22)
    audio_query["volumeScale"] = _env_float(VOICE_VOLUME_ENV, 1.08)
    audio_query["prePhonemeLength"] = _env_float(VOICE_PRE_PHONEME_ENV, 0.06)
    audio_query["postPhonemeLength"] = _env_float(VOICE_POST_PHONEME_ENV, 0.08)
    return audio_query


def _audio_filter_for_style(tts_mode: str) -> str:
    raw_filter = os.environ.get(AUDIO_FILTER_ENV)
    if raw_filter is not None:
        return raw_filter.strip()
    if tts_mode != "voicevox":
        return ""
    style = _voice_style()
    if style in {"", "plain", "none", "off", "0"}:
        return ""
    return DEFAULT_DYNAMIC_AUDIO_FILTER


def _bgm_style() -> str:
    return (os.environ.get(BGM_STYLE_ENV, DEFAULT_BGM_STYLE) or "").strip().lower()


def _bgm_enabled() -> bool:
    return _bgm_style() not in {"", "none", "off", "0", "false"}


def _prepare_bgm(output_dir: Path, *, duration_seconds: float) -> tuple[Path | None, str]:
    style = _bgm_style()
    if not _bgm_enabled():
        return None, style
    if style not in {"pop", "upbeat", "dynamic"}:
        style = DEFAULT_BGM_STYLE
    path = write_pop_bgm_wav(
        output_dir / "bgm.wav",
        duration_seconds=duration_seconds,
        volume=_env_float(BGM_VOLUME_ENV, DEFAULT_BGM_VOLUME),
        bpm=_env_float(BGM_BPM_ENV, DEFAULT_BGM_BPM),
    )
    return path, style


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
    audio_query = _apply_voice_style(query.json())
    synthesis = requests.post(
        f"{base}/synthesis",
        params={"speaker": speaker},
        json=audio_query,
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


def _motion_overscan_size() -> tuple[int, int]:
    """Up-scaled canvas so a slow zoom has room without showing edges."""
    scale = 1.0 + max(0.0, MOTION_MAX_ZOOM - 1.0) + 0.02
    return int(round(WIDTH * scale)), int(round(HEIGHT * scale))


def _build_video_filter_chain(durations: tuple[float, ...], duration_seconds: float) -> tuple[str, str]:
    """Ken Burns (slow zoom + alternating horizontal drift) per still card.

    Each frame becomes a moving clip instead of a held still, so the Short
    reads as video rather than a slideshow. The opening card gets a slightly
    stronger push for a 1-second hook; cards then alternate drift direction
    for visual variety. A short fade in/out bookends the whole sequence.
    """
    over_w, over_h = _motion_overscan_size()
    parts: list[str] = []
    labels: list[str] = []
    for index, duration in enumerate(durations):
        frame_count = max(1, int(round(duration * MOTION_FPS)))
        target_zoom = MOTION_OPENING_ZOOM if index == 0 else MOTION_ZOOM
        # Linear zoom driven by the output frame index ``on`` (d=1 means one
        # output per input frame, so no per-input frame multiplication).
        zoom_step = (target_zoom - 1.0) / frame_count
        drift = MOTION_DRIFT_PX if index % 2 == 0 else -MOTION_DRIFT_PX
        z_expr = f"min(1+{zoom_step:.6f}*on,{target_zoom})"
        x_expr = f"iw/2-(iw/zoom/2)+({drift})*on/{frame_count}"
        y_expr = "ih/2-(ih/zoom/2)"
        parts.append(
            f"[{index}:v]scale={over_w}:{over_h},"
            f"zoompan=z='{z_expr}':d=1:"
            f"x='{x_expr}':y='{y_expr}':s={WIDTH}x{HEIGHT}:fps={MOTION_FPS},setsar=1[v{index}]"
        )
        labels.append(f"[v{index}]")
    concat = "".join(labels) + f"concat=n={len(durations)}:v=1:a=0[vcat]"
    fade_out_start = max(0.0, duration_seconds - MOTION_FADE_SECONDS)
    vout = (
        f"[vcat]format=yuv420p,"
        f"fade=t=in:st=0:d={MOTION_FADE_SECONDS},"
        f"fade=t=out:st={fade_out_start:.3f}:d={MOTION_FADE_SECONDS}[vout]"
    )
    return ";".join(parts) + ";" + concat + ";" + vout, "[vout]"


def compose_video(
    frame_paths: tuple[Path, ...],
    audio_path: Path | str,
    output_mp4: Path | str,
    *,
    durations: tuple[float, ...] = DEFAULT_FRAME_DURATIONS,
    ffmpeg_bin: str = "ffmpeg",
    audio_filter: str = "",
    bgm_path: Path | str | None = None,
) -> Path:
    if len(frame_paths) != len(durations):
        raise ValueError("frame_paths and durations length mismatch")
    duration_seconds = float(sum(durations))
    target = Path(output_mp4)
    target.parent.mkdir(parents=True, exist_ok=True)

    cmd = [ffmpeg_bin, "-y", "-hide_banner", "-loglevel", "error"]
    for path, duration in zip(frame_paths, durations):
        cmd.extend(["-framerate", str(MOTION_FPS), "-loop", "1", "-t", f"{duration:.3f}", "-i", str(path)])
    cmd.extend(["-i", str(audio_path)])
    audio_index = len(frame_paths)
    if bgm_path:
        cmd.extend(["-i", str(bgm_path)])
    bgm_index = audio_index + 1

    video_chain, video_label = _build_video_filter_chain(durations, duration_seconds)
    if bgm_path:
        narration_filter = audio_filter or "anull"
        audio_chain = (
            f"[{audio_index}:a]{narration_filter}[voice];[{bgm_index}:a]volume=1.0[bgm];"
            f"[voice][bgm]amix=inputs=2:duration=longest:dropout_transition=0,"
            f"apad=whole_dur={duration_seconds:.3f}[aout]"
        )
    else:
        narration_filter = audio_filter or "anull"
        audio_chain = f"[{audio_index}:a]{narration_filter},apad=whole_dur={duration_seconds:.3f}[aout]"

    cmd.extend([
        "-filter_complex",
        f"{video_chain};{audio_chain}",
        "-map",
        video_label,
        "-map",
        "[aout]",
        "-t",
        f"{duration_seconds:.3f}",
        "-c:v",
        "libx264",
        "-preset",
        _env_text(FFMPEG_PRESET_ENV, DEFAULT_FFMPEG_PRESET),
        "-threads",
        _env_text(FFMPEG_THREADS_ENV, DEFAULT_FFMPEG_THREADS),
        "-c:a",
        "aac",
        "-movflags",
        "+faststart",
        str(target),
    ])
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
    audio_filter = _audio_filter_for_style(tts_mode)
    bgm_path, bgm_style = _prepare_bgm(out, duration_seconds=duration)
    video_path = compose_video(
        frames,
        audio_path,
        out / "short.mp4",
        ffmpeg_bin=ffmpeg_bin,
        audio_filter=audio_filter,
        bgm_path=bgm_path,
    )
    metadata_path = out / "metadata.json"
    metadata_path.write_text(
        json.dumps(
            {
                "topic_key": topic.topic_key,
                "title": script.title,
                "description": script.description,
                "duration_seconds": duration,
                "tts_mode": tts_mode,
                "voice_style": _voice_style(),
                "audio_filter": audio_filter,
                "bgm_style": bgm_style,
                "bgm_path": str(bgm_path.name) if bgm_path else "",
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
    "DEFAULT_DYNAMIC_AUDIO_FILTER",
    "RenderedShort",
    "compose_video",
    "prepare_audio",
    "render_frames",
    "render_short",
    "synthesize_voicevox",
    "write_pop_bgm_wav",
    "write_silent_wav",
]
