#!/bin/bash
# URL → 記事作成+公開
# post_id → 既存の下書きを公開
#
# 例:
#   ./publish_post.sh https://hochi.news/articles/xxxxx.html
#   ./publish_post.sh https://hochi.news/articles/xxxxx.html 選手情報
#   ./publish_post.sh 61336

ARG=$1
CATEGORY=${2:-試合速報}

if [ -z "$ARG" ]; then
  echo "使い方: $0 <URL or post_id> [カテゴリ]"
  exit 1
fi

python3 - "$ARG" "$CATEGORY" << 'PYEOF'
import sys, os, re, requests
from pathlib import Path
from requests.auth import HTTPBasicAuth

ROOT = Path('.')
_vendor = str(ROOT / 'vendor')
if os.path.isdir(_vendor) and _vendor not in sys.path:
    sys.path.insert(0, _vendor)

from dotenv import load_dotenv
load_dotenv(ROOT / '.env')

WP_URL     = os.environ['WP_URL']
auth       = HTTPBasicAuth(os.environ['WP_USER'], os.environ['WP_APP_PASSWORD'])
GEMINI_KEY = os.environ.get('GEMINI_API_KEY', '')
AUTO_CAT_ID = 673
CATEGORY_IDS = {
    '試合速報': 663, '選手情報': 664, '首脳陣': 665,
    '補強・移籍': 668, '球団情報': 669, 'コラム': 670,
}

arg      = sys.argv[1]
category = sys.argv[2]

# post_idなら既存の下書きにGemini本文を生成して公開
if arg.isdigit():
    post = requests.get(f'{WP_URL}/wp-json/wp/v2/posts/{arg}', auth=auth).json()
    title    = post.get('title', {}).get('rendered', '')
    category = post.get('categories', [670])
    print(f'タイトル: {title}')
    print('本文生成中...')
    content = f'<p>{title}</p>'
    if GEMINI_KEY:
        try:
            prompt = f"""あなたは読売ジャイアンツの熱狂的なファンブロガー兼データアナリストです。
以下のニュースについて、データと統計を豊富に使った詳細なブログ記事を日本語で書いてください。

タイトル: {title}

【必須要素】
1. 対象選手・チームの今季成績データ（打率・OPS・防御率・WHIP等、具体的な数字）
2. 昨季との比較データ（成長・変化を数字で示す）
3. チーム内・リーグ内での位置づけ（他選手との比較）
4. セイバーメトリクス指標（wRC+・WAR・FIP等）を1〜2個使う
5. 今後の展望・課題を具体的に
6. ファン目線の感情・期待・応援コメント

【構成】
・見出し4〜5個（【】か■で始める）
・各セクション2〜3段落
・600〜800文字
・数字はWeb検索で確認できたものだけ使う（推測・記憶で書かない）
・最後は「みなさんの意見はコメントで！」で締める
・確実にわかる事実だけ断言し、不確かな数字は「〜とみられる」「〜程度」と明示する
・HTMLタグなし・本文のみ出力"""
            resp = requests.post(
                f'https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GEMINI_KEY}',
                json={'contents': [{'parts': [{'text': prompt}]}], 'generationConfig': {'maxOutputTokens': 2048}},
                timeout=20
            )
            text = resp.json()['candidates'][0]['content']['parts'][0]['text'].strip()
            blocks = ''
            for line in text.split('\n'):
                line = line.strip()
                if not line: continue
                if line.startswith('【') or line.startswith('■'):
                    blocks += f'<!-- wp:heading {{"level":3}} -->\n<h3>{line}</h3>\n<!-- /wp:heading -->\n\n'
                else:
                    blocks += f'<!-- wp:paragraph -->\n<p>{line}</p>\n<!-- /wp:paragraph -->\n\n'
            content = blocks.strip()
        except Exception as e:
            print(f'Gemini失敗: {e}')
    resp = requests.post(f'{WP_URL}/wp-json/wp/v2/posts/{arg}', auth=auth, json={'status': 'publish', 'content': content})
    d = resp.json()
    print(f'公開完了: post_id={d.get("id")} {d.get("link")}')
    sys.exit(0)

source_url = arg

# OG情報取得
print(f'取得中: {source_url}')
try:
    html = requests.get(source_url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'}).text
    m = re.search(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', html)
    if not m:
        m = re.search(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']', html)
    og_image = m.group(1) if m else None
    mt = re.search(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', html)
    title = mt.group(1) if mt else source_url
except Exception as e:
    print(f'取得失敗: {e}'); sys.exit(1)

print(f'タイトル: {title}')

# アイキャッチ
featured_media = 0
if og_image:
    try:
        data  = requests.get(og_image, timeout=10).content
        fname = og_image.split('?')[0].split('/')[-1] or 'thumbnail.jpg'
        resp  = requests.post(
            f'{WP_URL}/wp-json/wp/v2/media', auth=auth,
            headers={'Content-Disposition': f'attachment; filename="{fname}"', 'Content-Type': 'image/jpeg'},
            data=data
        )
        if resp.status_code in (200, 201):
            featured_media = resp.json().get('id', 0)
    except Exception as e:
        print(f'画像アップロード失敗: {e}')
print(f'アイキャッチ: {"media_id=" + str(featured_media) if featured_media else "なし"}')

# Gemini CLIで本文生成（検索付きPro）
print('本文生成中（Gemini CLI）...')
import subprocess
gemini_prompt = f"""あなたは読売ジャイアンツの熱狂的なファンブロガー兼データアナリストです。
以下のニュースについて、データと統計を豊富に使った詳細なブログ記事を日本語で書いてください。
必要であればWeb検索して最新の選手成績・データを調べて使ってください。

タイトル: {title}
カテゴリ: {category}
元記事URL: {source_url}

【必須要素】
1. 対象選手・チームの今季成績データ（打率・OPS・防御率・WHIP等、具体的な数字）
2. 昨季との比較データ（成長・変化を数字で示す）
3. チーム内・リーグ内での位置づけ（他選手・他球団との比較）
4. セイバーメトリクス指標（wRC+・WAR・FIP等）を1〜2個使う
5. 今後の展望・課題を具体的に
6. ファン目線の感情・期待・応援コメント

【構成】
・見出し4〜5個（【】か■で始める）
・各セクション2〜3段落
・600〜800文字
・数字はWeb検索で確認できたものだけ使う（推測・記憶で書かない）
・最後は「みなさんの意見はコメントで！」で締める
・確実にわかる事実だけ断言し、不確かな数字は「〜とみられる」「〜程度」と明示する
・HTMLタグなし・本文のみ出力"""

content = f'<p>{title}</p>'
try:
    result = subprocess.run(
        ['gemini', '-p', gemini_prompt],
        capture_output=True, text=True, timeout=60
    )
    text = result.stdout.strip()
    if text:
        blocks = ''
        for line in text.split('\n'):
            line = line.strip()
            if not line: continue
            if line.startswith('【') or line.startswith('■'):
                blocks += f'<!-- wp:heading {{"level":3}} -->\n<h3>{line}</h3>\n<!-- /wp:heading -->\n\n'
            elif 'みなさんの意見はコメントで' in line:
                blocks += '<!-- wp:separator -->\n<hr class="wp-block-separator has-alpha-channel-opacity"/>\n<!-- /wp:separator -->\n\n'
                blocks += f'<!-- wp:buttons {{"layout":{{"type":"flex","justifyContent":"center"}}}} -->\n<div class="wp-block-buttons">\n<!-- wp:button -->\n<div class="wp-block-button"><a class="wp-block-button__link wp-element-button" href="#respond" style="background-color:#F5811F;color:#fff;font-size:1.05em;padding:12px 28px;">💬 {line}</a></div>\n<!-- /wp:button -->\n</div>\n<!-- /wp:buttons -->\n\n'
            else:
                blocks += f'<!-- wp:paragraph -->\n<p>{line}</p>\n<!-- /wp:paragraph -->\n\n'
        content = blocks.strip()
        print('生成完了')
    else:
        print(f'Gemini CLI失敗: {result.stderr[:100]}')
except Exception as e:
    print(f'Gemini CLI失敗: {e}')

# 記事作成+公開
cat_id = CATEGORY_IDS.get(category, 670)
resp = requests.post(
    f'{WP_URL}/wp-json/wp/v2/posts', auth=auth,
    json={
        'title':          title,
        'content':        content,
        'status':         'publish',
        'categories':     [AUTO_CAT_ID, cat_id],
        'featured_media': featured_media or None,
    }
)
d = resp.json()
print(f'\n公開完了: post_id={d.get("id")} {d.get("link")}')
PYEOF
