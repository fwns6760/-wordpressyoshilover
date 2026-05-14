"""既存 publish 記事の SVG block を class-based → inline-style に一括変換.

WP wpautop fix(2026-05-14)。SVG 内 <style> が </p><p> 挿入の trigger だったため、
本文 raw を取得 → <style> block 削除 + class="X" → style="Y" 置換 → POST update。
"""
import os
import re
import sys
import time

sys.path.insert(0, "src")
import requests

from wp_client import WPClient

CLASS_TO_STYLE = {
    "t": "font-size:18px;font-weight:bold;fill:#222",
    "st": "font-size:12px;fill:#555",
    "lb": "font-size:13px;fill:#333",
    "v": "font-size:13px;font-weight:bold;fill:#fff",
    "vo": "font-size:13px;fill:#222",
    "fb": "fill:#c0392b",
    "nb": "fill:#7faed5",
    "fl": "font-size:13px;font-weight:bold;fill:#c0392b",
    "ax": "stroke:#999;stroke-width:1;fill:none",
}

POST_IDS = [
    67559, 67558, 67557, 67556, 67555,
    67551, 67550,
    67399, 67398, 67397,
    67408, 67407, 67406,
    67402, 67401, 67400, 67329,
]


def patch_svg_block(content: str) -> str:
    def repl_svg(m: re.Match) -> str:
        block = m.group(0)
        block = re.sub(r"<style>[^<]*</style>", "", block)

        def repl_class(cm: re.Match) -> str:
            cls = cm.group(1).strip()
            style = CLASS_TO_STYLE.get(cls)
            if style is None:
                return cm.group(0)
            return f'style="{style}"'

        block = re.sub(r'class="([^"]+)"', repl_class, block)
        block = re.sub(r"\s*\n\s*", "", block)
        return block

    return re.sub(r"<svg[\s\S]*?</svg>", repl_svg, content)


def main():
    wp = WPClient()
    auth = (os.environ["WP_USER"], os.environ["WP_APP_PASSWORD"])
    for pid in POST_IDS:
        url = f"{wp.base_url}/wp-json/wp/v2/posts/{pid}?context=edit"
        r = requests.get(url, auth=auth, timeout=30)
        if r.status_code != 200:
            print(f"GET {pid} fail {r.status_code}")
            continue
        data = r.json()
        raw = data.get("content", {}).get("raw", "")
        if "<svg" not in raw:
            print(f"{pid} no svg, skip")
            continue
        if "<style>" not in raw:
            print(f"{pid} already inline, skip")
            continue
        new_raw = patch_svg_block(raw)
        if new_raw == raw:
            print(f"{pid} no change")
            continue
        upd = requests.post(
            f"{wp.base_url}/wp-json/wp/v2/posts/{pid}",
            auth=auth,
            json={"content": new_raw},
            timeout=30,
        )
        if upd.status_code in (200, 201):
            print(f"{pid} patched")
        else:
            print(f"{pid} update fail {upd.status_code}: {upd.text[:120]}")
        time.sleep(0.3)


if __name__ == "__main__":
    main()
