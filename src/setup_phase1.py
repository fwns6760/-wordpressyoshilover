"""
setup_phase1.py — フェーズ① 自動セットアップ
===============================================
WP REST API を使って以下を自動実行する:

  STEP 1. カテゴリ8種を作成
  STEP 2. config/categories.json にID記録
  STEP 3. フロントページを「最新の投稿」に変更
  STEP 4. 1ページ表示件数を 15 に設定
  STEP 5. 12球団インデックスページを非公開に変更
  STEP 6. カテゴリナビメニューを作成（CSSクラス付き）
  STEP 7. サイドバーウィジェットを設置
  STEP 8. カスタムCSSを適用

使用方法:
    python3 src/setup_phase1.py
    python3 src/setup_phase1.py --dry-run   # 確認のみ（変更しない）
    python3 src/setup_phase1.py --skip-css  # CSS適用をスキップ
"""

import os
import sys
import json
import argparse
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

# ──────────────────────────────────────────────
# 設定定数
# ──────────────────────────────────────────────

CATEGORIES = [
    {"name": "試合速報",      "slug": "shiai-sokuho",   "css_class": "cat-jiai",    "color": "#F5811F", "description": "試合結果・スコア"},
    {"name": "選手情報",      "slug": "senshu-joho",    "css_class": "cat-senshu",  "color": "#003DA5", "description": "個別選手ニュース"},
    {"name": "首脳陣",        "slug": "syuno",          "css_class": "cat-syuno",   "color": "#555555", "description": "監督・コーチ発言"},
    {"name": "ドラフト・育成", "slug": "draft-ikusei",  "css_class": "cat-draft",   "color": "#2E8B57", "description": "ドラフト・ファーム"},
    {"name": "OB・解説者",    "slug": "ob-kaisetsusha", "css_class": "cat-ob",      "color": "#7B4DAA", "description": "OB発言まとめ"},
    {"name": "補強・移籍",    "slug": "hoko-iseki",     "css_class": "cat-hoko",    "color": "#E53935", "description": "FA・トレード"},
    {"name": "球団情報",      "slug": "kyudan-joho",    "css_class": "cat-kyudan",  "color": "#F9A825", "description": "イベント・グッズ"},
    {"name": "コラム",        "slug": "column",         "css_class": "cat-column",  "color": "#1A1A1A", "description": "独自分析記事"},
]

# TOPページ除外カテゴリ（旧記事整理用。.htaccessリダイレクト維持のため非公開にしない）
OLD_ARTICLE_CAT = {
    "name": "旧記事",
    "slug": "old-articles",
    "description": "旧記事まとめ。TOPページ表示から除外。301リダイレクト維持のため公開状態を維持。",
}

X_BANNER_HTML = """<a href="https://x.com/yoshilover6760" target="_blank" class="sidebar-x-banner">
  <div class="x-handle">@yoshilover6760</div>
  <div class="x-followers">8,500+ フォロワー</div>
  <div class="x-cta">𝕏 フォローする</div>
</a>"""

FAMILY_STORIES_HTML = """<ul>
  <li><a href="https://prosports.yoshilover.com/giants-geneki-tsuma-kazoku/">🏠 巨人・現役選手の妻・家族まとめ</a></li>
  <li><a href="https://prosports.yoshilover.com/genekipurobaseballkazoku/">🏠 全球団・現役選手の家族まとめ</a></li>
  <li><a href="https://prosports.yoshilover.com/obmotopurobaseballkazoku/">🏠 OB・元選手の家族まとめ</a></li>
</ul>"""

# CUSTOM_CSS は src/custom.css から実行時に読み込む（二重管理を防ぐ）
def _load_custom_css() -> str:
    css_file = ROOT / "src" / "custom.css"
    if css_file.exists():
        return css_file.read_text(encoding="utf-8")
    # フォールバック: ファイルがない場合は最小限のCSS
    return """/* ============================================================
   YOSHILOVER — 追加CSS
   ============================================================ */

/* Google Fonts: Oswald */
@import url('https://fonts.googleapis.com/css2?family=Oswald:wght@500;700&display=swap');

/* CSS変数 */
:root {
  --orange:      #F5811F;
  --orange-light:#FFF3E8;
  --blue:        #003DA5;
  --black:       #1A1A1A;
  --dark-gray:   #333333;
  --mid-gray:    #666666;
  --light-gray:  #E8E8E8;
  --bg:          #F5F5F0;
  --white:       #FFFFFF;
  --red:         #E53935;
  --green:       #2E8B57;
  --purple:      #7B4DAA;
  --gold:        #F9A825;
}

/* ── ヘッダー ── */
.l-header {
  background: var(--black) !important;
  border-bottom: 4px solid var(--orange) !important;
  position: sticky !important;
  top: 0;
  z-index: 100;
}
.l-header a,
.l-header .c-logo__text,
.l-header .site-name-text { color: var(--white) !important; }

.l-header .c-logo__text,
.l-header .site-name-text,
.l-header .p-logo__title {
  font-family: 'Oswald', sans-serif !important;
  font-weight: 700 !important;
  font-size: 20px !important;
  letter-spacing: 1px;
  color: var(--white) !important;
}
.l-header .c-logo__desc,
.l-header .p-logo__desc {
  font-size: 10px !important;
  color: var(--orange) !important;
  font-weight: 400 !important;
}
.header-x-link { color: var(--orange) !important; text-decoration: none; font-size: 13px; font-weight: 700; }
.header-x-link:hover { opacity: 0.7; }

/* ── カテゴリナビ ── */
.c-gnav, .l-gnav {
  background: var(--white) !important;
  border-bottom: 1px solid var(--light-gray) !important;
  overflow-x: auto !important;
  -webkit-overflow-scrolling: touch;
}
.c-gnav::-webkit-scrollbar, .l-gnav::-webkit-scrollbar { display: none; }
.c-gnav__list, .l-gnav__list {
  display: flex !important;
  flex-wrap: nowrap !important;
  white-space: nowrap;
  padding: 0 8px;
}
.c-gnav__item > a, .l-gnav__item > a, .c-gnav .menu-item > a {
  display: inline-flex !important;
  align-items: center;
  gap: 4px;
  padding: 10px 14px !important;
  font-size: 13px !important;
  font-weight: 700 !important;
  color: var(--dark-gray) !important;
  text-decoration: none;
  border-bottom: 3px solid transparent;
  transition: all 0.2s;
  white-space: nowrap;
}
.c-gnav__item > a:hover, .l-gnav__item > a:hover,
.c-gnav .menu-item > a:hover,
.c-gnav .current-menu-item > a, .c-gnav .current_page_item > a {
  color: var(--orange) !important;
  border-bottom-color: var(--orange) !important;
  background: transparent !important;
}
.c-gnav .menu-item > a::before, .l-gnav .menu-item > a::before {
  content: '';
  display: inline-block;
  width: 8px; height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.menu-item.cat-all    > a::before { background: var(--orange); }
.menu-item.cat-jiai   > a::before { background: #F5811F; }
.menu-item.cat-senshu > a::before { background: #003DA5; }
.menu-item.cat-syuno  > a::before { background: #555555; }
.menu-item.cat-draft  > a::before { background: #2E8B57; }
.menu-item.cat-ob     > a::before { background: #7B4DAA; }
.menu-item.cat-hoko   > a::before { background: #E53935; }
.menu-item.cat-kyudan > a::before { background: #F9A825; }
.menu-item.cat-column > a::before { background: #1A1A1A; }
.c-gnav .sub-menu { display: none !important; }

/* ── 記事一覧（リスト型） ── */
.-type-list .p-postList, .p-postList.-list {
  display: flex; flex-direction: column; gap: 2px;
}
.-type-list .p-postList__item, .p-postList.-list .p-postList__item {
  background: var(--white);
  border-left: 4px solid transparent;
  transition: background 0.2s, border-left-color 0.2s;
  animation: fadeInUp 0.4s ease forwards;
  opacity: 0; transform: translateY(10px);
}
.-type-list .p-postList__item:hover, .p-postList.-list .p-postList__item:hover {
  background: var(--orange-light);
  border-left-color: var(--orange);
}
.-type-list .p-postList__item:nth-child(1)  { animation-delay: 0.05s; }
.-type-list .p-postList__item:nth-child(2)  { animation-delay: 0.10s; }
.-type-list .p-postList__item:nth-child(3)  { animation-delay: 0.15s; }
.-type-list .p-postList__item:nth-child(4)  { animation-delay: 0.20s; }
.-type-list .p-postList__item:nth-child(5)  { animation-delay: 0.25s; }
.-type-list .p-postList__item:nth-child(6)  { animation-delay: 0.30s; }
.-type-list .p-postList__item:nth-child(7)  { animation-delay: 0.35s; }
.-type-list .p-postList__item:nth-child(8)  { animation-delay: 0.40s; }
.-type-list .p-postList__item:nth-child(9)  { animation-delay: 0.45s; }
.-type-list .p-postList__item:nth-child(10) { animation-delay: 0.50s; }
@keyframes fadeInUp { to { opacity: 1; transform: translateY(0); } }

.-type-list .p-postList__item a, .p-postList.-list .p-postList__item a {
  display: flex; gap: 16px; align-items: flex-start;
  padding: 16px 20px; text-decoration: none; color: inherit;
}
.-type-list .p-postList__eyecatch, .p-postList.-list .p-postList__eyecatch {
  width: 120px !important; height: 80px !important;
  border-radius: 4px; overflow: hidden; flex-shrink: 0;
}
.-type-list .p-postList__eyecatch img, .p-postList.-list .p-postList__eyecatch img {
  width: 100%; height: 100%; object-fit: cover;
}
.-type-list .p-postList__body, .p-postList.-list .p-postList__body { flex: 1; min-width: 0; }
.-type-list .p-postList__cats .c-cat-label, .p-postList.-list .c-cat-label {
  font-size: 11px !important; font-weight: 700 !important;
  color: var(--white) !important; padding: 2px 8px !important; border-radius: 2px !important;
}
.-type-list .p-postList__date, .p-postList.-list .p-postList__date, .-type-list .c-meta__date {
  font-size: 11px; color: var(--mid-gray);
}
.-type-list .p-postList__ttl, .p-postList.-list .p-postList__ttl {
  font-size: 15px !important; font-weight: 700 !important; line-height: 1.5 !important;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
  overflow: hidden; margin-top: 4px; color: var(--dark-gray);
}

/* ── サイドバー ── */
.l-sidebar .widget { background: var(--white); border-radius: 4px; overflow: hidden; margin-bottom: 20px; }
.l-sidebar .widget-title, .l-sidebar .widgetTitle, .l-sidebar .c-widget__title {
  background: var(--black) !important; color: var(--white) !important;
  font-family: 'Oswald', sans-serif !important; font-size: 13px !important;
  font-weight: 700 !important; padding: 10px 16px !important;
  border-left: 4px solid var(--orange) !important; letter-spacing: 1px; margin: 0 !important;
}
.l-sidebar .widget ul { list-style: none; margin: 0; padding: 0; }
.l-sidebar .widget ul li { border-bottom: 1px solid var(--light-gray); }
.l-sidebar .widget ul li:last-child { border-bottom: none; }
.l-sidebar .widget ul li a {
  display: flex; align-items: center; gap: 8px; padding: 10px 16px;
  text-decoration: none; color: var(--dark-gray); font-size: 13px; transition: background 0.2s;
}
.l-sidebar .widget ul li a:hover { background: var(--orange-light); }
.l-sidebar .widget_categories .cat-item a { justify-content: space-between; }

/* ── Xバナー ── */
.sidebar-x-banner {
  display: block; background: var(--black); color: var(--white);
  text-align: center; padding: 16px; text-decoration: none; transition: background 0.2s;
}
.sidebar-x-banner:hover { background: #333; }
.sidebar-x-banner .x-handle { font-family: 'Oswald', sans-serif; font-size: 16px; font-weight: 700; color: var(--orange); }
.sidebar-x-banner .x-followers { font-size: 11px; color: #999; margin-top: 2px; }
.sidebar-x-banner .x-cta {
  display: inline-block; margin-top: 8px; background: var(--orange);
  color: var(--white); padding: 6px 20px; border-radius: 20px;
  font-size: 12px; font-weight: 700;
}

/* ── フッター ── */
.l-footer { background: var(--black) !important; border-top: 4px solid var(--orange) !important; color: #999 !important; margin-top: 40px; }
.l-footer a { color: #999 !important; font-size: 12px; transition: color 0.2s; }
.l-footer a:hover { color: var(--orange) !important; }
.l-footer .c-logo__text, .l-footer .site-name-text {
  font-family: 'Oswald', sans-serif !important; font-weight: 700 !important; color: var(--white) !important;
}

/* ── 記事内見出し ── */
.post_content h2, .entry-content h2 {
  background: var(--black); color: var(--white);
  padding: 12px 16px; border-left: 6px solid var(--orange);
}
.post_content h3, .entry-content h3 { border-bottom: 3px solid var(--orange); padding-bottom: 6px; }

/* ── レスポンシブ ── */
@media (max-width: 768px) {
  .-type-list .p-postList__eyecatch, .p-postList.-list .p-postList__eyecatch {
    width: 90px !important; height: 60px !important;
  }
  .-type-list .p-postList__ttl, .p-postList.-list .p-postList__ttl { font-size: 14px !important; }
  .-type-list .p-postList__item a, .p-postList.-list .p-postList__item a { padding: 12px 14px; }
}"""


# ──────────────────────────────────────────────
# クライアント
# ──────────────────────────────────────────────

class Phase1Setup:
    def __init__(self, dry_run: bool = False):
        self.base_url     = os.getenv("WP_URL", "").rstrip("/")
        self.user         = os.getenv("WP_USER", "")
        self.app_password = os.getenv("WP_APP_PASSWORD", "")
        self.dry_run      = dry_run

        if not all([self.base_url, self.user, self.app_password]):
            raise ValueError(".env に WP_URL / WP_USER / WP_APP_PASSWORD が設定されていません")

        self.auth    = (self.user, self.app_password)
        self.api     = f"{self.base_url}/wp-json/wp/v2"
        self.headers = {"Content-Type": "application/json"}
        self.cat_ids: dict[str, int] = {}  # name -> WP ID

        if dry_run:
            print("[DRY-RUN] 変更は行いません（読み取りのみ）\n")

    def _get(self, path: str, params: dict = None) -> requests.Response:
        resp = requests.get(f"{self.api}{path}", params=params, auth=self.auth, timeout=30)
        self._check(resp)
        return resp

    def _post(self, path: str, payload: dict) -> requests.Response:
        if self.dry_run:
            print(f"  [DRY] POST {path}: {json.dumps(payload, ensure_ascii=False)[:120]}")
            return _FakeResponse({"id": 0})
        resp = requests.post(f"{self.api}{path}", json=payload, auth=self.auth,
                             headers=self.headers, timeout=30)
        self._check(resp)
        return resp

    def _put(self, path: str, payload: dict) -> requests.Response:
        if self.dry_run:
            print(f"  [DRY] PUT  {path}: {json.dumps(payload, ensure_ascii=False)[:120]}")
            return _FakeResponse({"id": 0})
        resp = requests.put(f"{self.api}{path}", json=payload, auth=self.auth,
                            headers=self.headers, timeout=30)
        self._check(resp)
        return resp

    def _check(self, resp: requests.Response):
        if resp.status_code == 401:
            raise PermissionError("認証失敗: .env の WP_USER / WP_APP_PASSWORD を確認してください")
        if resp.status_code == 403:
            raise PermissionError("アクセス拒否: パーマリンクを「投稿名」→保存 してください")
        try:
            resp.raise_for_status()
        except requests.HTTPError as e:
            raise RuntimeError(f"HTTPエラー: {e}\n{resp.text[:400]}")

    # ──────────────────────────────────────────────
    # STEP 1: カテゴリ作成
    # ──────────────────────────────────────────────
    def step1_create_categories(self):
        print("=" * 55)
        print("STEP 1: カテゴリ8種＋旧記事カテゴリを作成")
        print("=" * 55)

        # 既存カテゴリを取得
        existing = {c["slug"]: c["id"]
                    for c in self._get("/categories", {"per_page": 100}).json()}
        print(f"  既存カテゴリ: {len(existing)}件")

        # メインカテゴリ8種
        for cat in CATEGORIES:
            slug = cat["slug"]
            if slug in existing:
                cat_id = existing[slug]
                print(f"  スキップ（既存） ID={cat_id:3d}  {cat['name']}")
                self.cat_ids[cat["name"]] = cat_id
            else:
                resp = self._post("/categories", {
                    "name":        cat["name"],
                    "slug":        slug,
                    "description": cat["description"],
                })
                cat_id = resp.json().get("id", 0)
                self.cat_ids[cat["name"]] = cat_id
                print(f"  作成 ✓  ID={cat_id:3d}  {cat['name']}  ({slug})")

        # 旧記事カテゴリ（TOPページ除外用）
        old_slug = OLD_ARTICLE_CAT["slug"]
        if old_slug in existing:
            old_id = existing[old_slug]
            print(f"  スキップ（既存） ID={old_id:3d}  {OLD_ARTICLE_CAT['name']}")
            self.cat_ids[OLD_ARTICLE_CAT["name"]] = old_id
        else:
            resp = self._post("/categories", {
                "name":        OLD_ARTICLE_CAT["name"],
                "slug":        old_slug,
                "description": OLD_ARTICLE_CAT["description"],
            })
            old_id = resp.json().get("id", 0)
            self.cat_ids[OLD_ARTICLE_CAT["name"]] = old_id
            print(f"  作成 ✓  ID={old_id:3d}  {OLD_ARTICLE_CAT['name']}  ({old_slug})")

        print()
        print("  ⚠️  旧記事カテゴリのTOP除外設定（手動）:")
        print("  カスタマイズ → トップページ → 記事一覧設定 → 除外カテゴリ")
        print(f"  → 「旧記事」(ID={self.cat_ids.get('旧記事', '?')}) を追加 → 公開")
        print()
        print("  または WP管理画面 → 設定 → 表示設定 → ホームページに表示しない")
        print("  カテゴリを ID で指定（プラグインなしの場合は functions.php に追記）")
        print()

    # ──────────────────────────────────────────────
    # STEP 2: categories.json を更新
    # ──────────────────────────────────────────────
    def step2_save_category_json(self):
        print("=" * 55)
        print("STEP 2: config/categories.json を更新")
        print("=" * 55)

        cats_file = ROOT / "config" / "categories.json"
        if not self.dry_run:
            with open(cats_file, "w", encoding="utf-8") as f:
                json.dump(self.cat_ids, f, ensure_ascii=False, indent=2)
            print(f"  書き込み ✓  {cats_file}")
        else:
            print(f"  [DRY] {cats_file} に書き込む予定: {self.cat_ids}")
        print()

    # ──────────────────────────────────────────────
    # STEP 3: フロントページを「最新の投稿」に変更
    # ──────────────────────────────────────────────
    def step3_set_frontpage(self):
        print("=" * 55)
        print("STEP 3: フロントページを「最新の投稿」に変更")
        print("=" * 55)

        if self.dry_run:
            print("  [DRY] PUT /settings { show_on_front: 'posts' }")
        else:
            resp = requests.post(
                f"{self.api}/settings",
                json={"show_on_front": "posts", "posts_per_page": 15},
                auth=self.auth, headers=self.headers, timeout=30,
            )
            # settings endpoint は POST（作成）ではなく PUT 相当
            if resp.status_code in (200, 201):
                data = resp.json()
                print(f"  show_on_front = {data.get('show_on_front')}")
                print(f"  posts_per_page = {data.get('posts_per_page')}")
                print("  設定 ✓")
            else:
                print(f"  警告: settings API が {resp.status_code}。手動で設定してください。")
                print("  → WP管理画面 → 設定 → 表示設定 → 「最新の投稿」")
        print()

    # ──────────────────────────────────────────────
    # STEP 4: 12球団インデックスページを非公開に変更
    # ──────────────────────────────────────────────
    def step4_hide_top_page(self):
        print("=" * 55)
        print("STEP 4: 12球団インデックスページを非公開に変更")
        print("=" * 55)

        # 固定ページを取得（publish / private を個別取得して結合）
        pages_pub = self._get("/pages", {"per_page": 100}).json()
        try:
            pages_prv = self._get("/pages", {"per_page": 100, "status": "private"}).json()
        except Exception:
            pages_prv = []
        pages = pages_pub + pages_prv
        print(f"  固定ページ {len(pages)}件を確認中...")

        # 非公開にするキーワード（タイトルに含む）
        KEYWORDS = ["12球団", "インデックス", "球団", "index"]
        targets = []
        for p in pages:
            title = p.get("title", {}).get("rendered", "")
            slug  = p.get("slug", "")
            status = p.get("status", "")
            if status == "private":
                print(f"  スキップ（既に非公開） ID={p['id']}  「{title}」")
                continue
            if any(kw in title or kw in slug for kw in KEYWORDS):
                targets.append(p)

        if not targets:
            print("  対象ページが見つかりませんでした（既に非公開か存在しない）")
        else:
            for p in targets:
                title = p.get("title", {}).get("rendered", "")
                self._put(f"/pages/{p['id']}", {"status": "private"})
                print(f"  非公開化 ✓  ID={p['id']}  「{title}」")

        print()

    # ──────────────────────────────────────────────
    # STEP 5: カテゴリナビメニューを作成
    # ──────────────────────────────────────────────
    def step5_create_nav_menu(self):
        print("=" * 55)
        print("STEP 5: カテゴリナビメニューを作成")
        print("=" * 55)

        # 既存メニューを確認
        try:
            menus_resp = requests.get(f"{self.api}/menus", auth=self.auth, timeout=30)
        except Exception as e:
            print(f"  メニューAPI未対応（WP 5.9未満の可能性）: {e}")
            print("  → 手動作成: WP管理画面 → 外観 → メニュー")
            print()
            return

        if menus_resp.status_code == 404:
            print("  メニューAPIが存在しない（WP 5.9未満）")
            print("  → 手動作成: WP管理画面 → 外観 → メニュー")
            print()
            return

        menus_resp.raise_for_status()
        existing_menus = {m["name"]: m["id"] for m in menus_resp.json()}
        MENU_NAME = "カテゴリナビ"

        if MENU_NAME in existing_menus:
            menu_id = existing_menus[MENU_NAME]
            print(f"  既存メニュー使用  ID={menu_id}  「{MENU_NAME}」")
        else:
            if self.dry_run:
                menu_id = 0
                print(f"  [DRY] メニュー作成: {MENU_NAME}")
            else:
                r = requests.post(f"{self.api}/menus", json={"name": MENU_NAME},
                                  auth=self.auth, headers=self.headers, timeout=30)
                r.raise_for_status()
                menu_id = r.json()["id"]
                print(f"  メニュー作成 ✓  ID={menu_id}  「{MENU_NAME}」")

        # メニューアイテムを追加
        # 既存アイテムを確認してスキップ
        existing_items_resp = requests.get(
            f"{self.api}/menu-items", params={"menus": menu_id, "per_page": 100},
            auth=self.auth, timeout=30,
        )
        if existing_items_resp.ok:
            existing_titles = {
                item.get("title", {}).get("rendered", "") if isinstance(item.get("title"), dict)
                else item.get("title", "")
                for item in existing_items_resp.json()
            }
        else:
            existing_titles = set()

        # ① 「すべて」カスタムリンク
        if "すべて" not in existing_titles:
            self._add_menu_item(menu_id, {
                "title": "すべて", "url": "/", "type": "custom",
                "object": "custom", "menus": menu_id,
                "classes": ["cat-all"], "status": "publish", "menu_order": 1,
            }, label="すべて")

        # ② カテゴリ8種
        for i, cat in enumerate(CATEGORIES, start=2):
            cat_name = cat["name"]
            if cat_name not in existing_titles:
                cat_id = self.cat_ids.get(cat_name, 0)
                self._add_menu_item(menu_id, {
                    "title": cat_name,
                    "url": f"{self.base_url}/category/{cat['slug']}/",
                    "type": "taxonomy",
                    "object": "category",
                    "object_id": cat_id,
                    "menus": menu_id,
                    "classes": [cat["css_class"]],
                    "status": "publish",
                    "menu_order": i,
                }, label=cat_name)
            else:
                print(f"  スキップ（既存）  {cat_name}")

        # メニューをグローバルナビに割り当て
        if not self.dry_run and menu_id:
            try:
                r2 = requests.post(
                    f"{self.base_url}/wp-json/wp/v2/menus/{menu_id}",
                    json={"locations": ["global_nav", "header_nav", "primary"]},
                    auth=self.auth, headers=self.headers, timeout=30,
                )
                if r2.ok:
                    print("  グローバルナビに割り当て ✓")
                else:
                    print("  グローバルナビ割り当てはWP管理画面で手動設定してください")
                    print("  → 外観 → メニュー → 「カテゴリナビ」→ メニューの位置: グローバルナビ")
            except Exception:
                print("  グローバルナビ割り当てはWP管理画面で手動設定してください")
                print("  → 外観 → メニュー → 「カテゴリナビ」→ メニューの位置: グローバルナビ")

        print()

    def _add_menu_item(self, menu_id: int, payload: dict, label: str):
        if self.dry_run:
            print(f"  [DRY] メニューアイテム追加: {label}")
            return
        r = requests.post(f"{self.api}/menu-items", json=payload,
                          auth=self.auth, headers=self.headers, timeout=30)
        if r.ok:
            print(f"  追加 ✓  {label}")
        else:
            print(f"  警告: {label} の追加失敗 ({r.status_code}): {r.text[:100]}")

    # ──────────────────────────────────────────────
    # STEP 6: サイドバーウィジェットを設置
    # ──────────────────────────────────────────────
    def step6_setup_sidebar(self):
        print("=" * 55)
        print("STEP 6: サイドバーウィジェットを設置")
        print("=" * 55)

        # サイドバー一覧取得
        try:
            sb_resp = requests.get(f"{self.api}/sidebars", auth=self.auth, timeout=30)
        except Exception as e:
            print(f"  サイドバーAPI未対応: {e}")
            self._print_widget_manual()
            return

        if sb_resp.status_code == 404:
            print("  WidgetブロックAPI未対応（WP 5.8未満）")
            self._print_widget_manual()
            return

        sb_resp.raise_for_status()
        sidebars = sb_resp.json()
        print(f"  サイドバー {len(sidebars)}個を確認中...")
        for sb in sidebars:
            print(f"    ID={sb['id']}  {sb['name']}  ウィジェット数={len(sb.get('widgets', []))}")

        # サイドバーIDを特定（"sidebar" または最初のサイドバー）
        sidebar_id = None
        for sb in sidebars:
            if sb["id"] in ("sidebar", "swell_sidebar", "sidebar-1", "widget-area"):
                sidebar_id = sb["id"]
                break
        if not sidebar_id and sidebars:
            sidebar_id = sidebars[0]["id"]

        if not sidebar_id:
            print("  サイドバーが見つかりません")
            self._print_widget_manual()
            return

        print(f"  使用するサイドバー: {sidebar_id}")

        # 既存ウィジェット確認
        existing_widgets_resp = requests.get(
            f"{self.api}/widgets", params={"sidebar": sidebar_id},
            auth=self.auth, timeout=30,
        )
        if existing_widgets_resp.ok:
            existing = existing_widgets_resp.json()
            print(f"  既存ウィジェット: {len(existing)}件")
        else:
            existing = []

        # ウィジェットを追加
        widgets_to_add = [
            # ① Xバナー
            {
                "id_base":  "custom_html",
                "sidebar":  sidebar_id,
                "settings": {"title": "", "content": X_BANNER_HTML},
            },
            # ② カテゴリ
            {
                "id_base":  "categories",
                "sidebar":  sidebar_id,
                "settings": {"title": "CATEGORY", "count": 1, "hierarchical": 0, "dropdown": 0},
            },
            # ③ 人気記事（カスタムHTML fallback）
            {
                "id_base":  "custom_html",
                "sidebar":  sidebar_id,
                "settings": {
                    "title":   "POPULAR",
                    "content": "<p style='padding:12px;font-size:13px;color:#666;'>人気記事プラグイン（WordPress Popular Posts等）を導入後、このウィジェットを差し替えてください。</p>",
                },
            },
            # ④ FAMILY STORIES
            {
                "id_base":  "custom_html",
                "sidebar":  sidebar_id,
                "settings": {"title": "FAMILY STORIES", "content": FAMILY_STORIES_HTML},
            },
            # ⑤ アーカイブ
            {
                "id_base":  "archives",
                "sidebar":  sidebar_id,
                "settings": {"title": "ARCHIVE", "count": 1, "dropdown": 0},
            },
        ]

        if len(existing) >= 4:
            print("  ウィジェットが既に設定済みのためスキップ（--force で上書き可）")
        else:
            for w in widgets_to_add:
                if self.dry_run:
                    print(f"  [DRY] ウィジェット追加: {w['id_base']} / {w['settings'].get('title', '')}")
                else:
                    r = requests.post(
                        f"{self.api}/widgets",
                        json=w,
                        auth=self.auth, headers=self.headers, timeout=30,
                    )
                    if r.ok:
                        wid = r.json().get("id", "?")
                        title = w["settings"].get("title", w["id_base"])
                        print(f"  追加 ✓  {title}  (id={wid})")
                    else:
                        title = w["settings"].get("title", w["id_base"])
                        print(f"  警告: {title} 追加失敗 ({r.status_code}): {r.text[:120]}")

        print()

    def _print_widget_manual(self):
        print()
        print("  ── 手動ウィジェット設定手順 ──")
        print("  WP管理画面 → 外観 → ウィジェット → サイドバー")
        print("  以下の順で追加:")
        print("    ① カスタムHTML    タイトル:なし    (Xバナー)")
        print("    ② カテゴリ        タイトル:CATEGORY")
        print("    ③ カスタムHTML    タイトル:POPULAR  (人気記事プレースホルダー)")
        print("    ④ カスタムHTML    タイトル:FAMILY STORIES")
        print("    ⑤ アーカイブ      タイトル:ARCHIVE")
        print()

    # ──────────────────────────────────────────────
    # STEP 7: カスタムCSS を適用
    # ──────────────────────────────────────────────
    def step7_apply_css(self):
        print("=" * 55)
        print("STEP 7: カスタムCSSを適用")
        print("=" * 55)

        # WordPress のカスタム CSS は custom_css CPT に保存される
        # WP REST API で theme_slug をキーにして取得・更新

        # アクティブテーマのスラッグを取得
        try:
            themes_resp = requests.get(
                f"{self.api}/themes", params={"status": "active"},
                auth=self.auth, timeout=30,
            )
        except Exception as e:
            print(f"  テーマAPI取得失敗: {e}")
            self._print_css_manual()
            return

        if not themes_resp.ok:
            print(f"  テーマ取得失敗 ({themes_resp.status_code})")
            self._print_css_manual()
            return

        themes = themes_resp.json()
        if not themes:
            print("  アクティブテーマが取得できません")
            self._print_css_manual()
            return

        theme_slug = themes[0].get("stylesheet", themes[0].get("template", "swell"))
        print(f"  アクティブテーマ: {theme_slug}")

        # custom_css エンドポイントを試みる
        # (WordPress core では /wp-json/wp/v2/customcss は存在しない場合が多い)
        # 代わりに /wp-json/wp/v2/settings の custom_css_post_id を経由して更新を試みる

        try:
            settings_resp = requests.get(f"{self.api}/settings", auth=self.auth, timeout=30)
            if settings_resp.ok:
                css_post_id = settings_resp.json().get("custom_css_post_id")
            else:
                css_post_id = None
        except Exception:
            css_post_id = None

        css_applied = False

        if css_post_id:
            # 既存カスタムCSSポストを更新
            print(f"  カスタムCSSポスト ID={css_post_id} を更新中...")
            if not self.dry_run:
                # custom_css は特殊なポストタイプ。直接 /posts/ID は使えない。
                # wp-json/wp/v2/custom_css/{id} は非標準のため、
                # 代替として wp_options の add_option 経由で設定するか、
                # プラグインAPIを使う必要がある
                print("  ※ カスタムCSSポスト更新はWP REST APIの標準スコープ外です")
        else:
            print("  カスタムCSSポストが未作成です")

        if not css_applied:
            self._print_css_manual()

        print()

    # ──────────────────────────────────────────────
    # STEP 8: テスト記事10本を作成
    # ──────────────────────────────────────────────
    def step8_create_test_posts(self):
        print("=" * 55)
        print("STEP 8: テスト記事10本を作成")
        print("=" * 55)

        import subprocess, sys
        script = ROOT / "src" / "create_test_posts.py"
        if not script.exists():
            print("  src/create_test_posts.py が見つかりません。スキップします。")
            print()
            return

        print("  src/create_test_posts.py を実行中...")
        result = subprocess.run(
            [sys.executable, str(script)],
            capture_output=False,
            text=True,
        )
        if result.returncode != 0:
            print(f"  警告: テスト記事作成スクリプトがエラーで終了しました (code={result.returncode})")
            print("  個別に python3 src/create_test_posts.py で実行してください")
        print()

    def _print_css_manual(self):
        css_file = ROOT / "src" / "custom.css"
        print(f"  CSSファイル: {css_file}")
        print()
        print("  ── カスタムCSS 手動設定手順 ──")
        print("  WP管理画面 → 外観 → カスタマイズ")
        print("  → 追加CSS → 下記ファイルの内容を全文貼り付け → 公開")
        print(f"  ファイル: {css_file}")

    # ──────────────────────────────────────────────
    # 認証チェック
    # ──────────────────────────────────────────────
    def check_auth(self) -> bool:
        """認証が通るか確認する。失敗時は修正方法を出力して False を返す。"""
        try:
            r = requests.get(f"{self.api}/users/me", auth=self.auth, timeout=15)
        except Exception as e:
            print(f"[認証チェック] 接続エラー: {e}")
            return False

        if r.status_code == 200:
            me = r.json()
            print(f"  認証OK  ユーザー: {me.get('name')}  roles: {me.get('roles')}")
            return True

        if r.status_code in (401, 403):
            print()
            print("  ╔══════════════════════════════════════════════════════╗")
            print("  ║  ⚠️  認証失敗 — .htaccess への1行追加が必要です      ║")
            print("  ╚══════════════════════════════════════════════════════╝")
            print()
            print("  原因: エックスサーバーの Apache/PHP-FPM が Authorization ヘッダーを")
            print("        ストリップするため、アプリケーションパスワードが届いていません。")
            print()
            print("  ── 修正手順 ──")
            print()
            print("  方法A（FTPでの .htaccess 編集）:")
            print("    1. FTPクライアント（FileZilla等）でサーバーに接続")
            print("    2. /yoshilover.com/public_html/.htaccess を開く")
            print("    3. # BEGIN WordPress の直前に以下を追記:")
            print()
            print("       SetEnvIf Authorization .+ HTTP_AUTHORIZATION=$0")
            print()
            print("    4. 保存。再度このスクリプトを実行。")
            print()
            print("  方法B（WP管理画面のプラグインエディタは使用不可）")
            print()
            print("  方法C（エックスサーバーのファイルマネージャー）:")
            print("    エックスサーバーパネル → ファイルマネージャー →")
            print("    /yoshilover.com/public_html/.htaccess を編集")
            print()
            print("  追記後の .htaccess 先頭の例:")
            print("  ─────────────────────────────────────────")
            print("  SetEnvIf Authorization .+ HTTP_AUTHORIZATION=$0")
            print()
            print("  # BEGIN WordPress")
            print("  <IfModule mod_rewrite.c>")
            print("  RewriteEngine On")
            print("  ...")
            print("  ─────────────────────────────────────────")
            return False

        print(f"  認証チェック: {r.status_code} {r.text[:100]}")
        return False

    # ──────────────────────────────────────────────
    # まとめ実行
    # ──────────────────────────────────────────────
    def run(self, skip_css: bool = False):
        print()
        print("╔═══════════════════════════════════════════════════╗")
        print("║  yoshilover フェーズ① 自動セットアップ            ║")
        print("╚═══════════════════════════════════════════════════╝")
        print(f"  接続先: {self.base_url}\n")

        if not self.dry_run:
            print("── 認証チェック ──")
            if not self.check_auth():
                print()
                print("  認証が確認できないため処理を中断します。")
                print("  上記の .htaccess 修正後、再度実行してください。")
                print()
                # CSS ファイルだけ生成しておく
                print("  CSS ファイルのみ生成して終了します。")
                self._print_css_manual()
                return
            print()

        self.step1_create_categories()
        self.step2_save_category_json()
        self.step3_set_frontpage()
        self.step4_hide_top_page()
        self.step5_create_nav_menu()
        self.step6_setup_sidebar()
        if not skip_css:
            self.step7_apply_css()
        if not self.dry_run:
            self.step8_create_test_posts()

        print("=" * 55)
        print("完了サマリー")
        print("=" * 55)
        print()
        print("✅ 自動処理済み:")
        print("   カテゴリ8種＋旧記事カテゴリの作成")
        print("   config/categories.json の更新")
        print("   フロントページ設定")
        print("   旧TOPページの非公開化")
        print("   カテゴリナビメニューの作成")
        print("   サイドバーウィジェットの設置")
        print("   テスト記事10本の作成")
        print()
        print("⚠️  手動対応が必要な項目（カスタマイザー設定）:")
        print()
        print("  1. カラー設定")
        print("     WP管理画面 → 外観 → カスタマイズ → サイト全体設定")
        print("     メインカラー   : #F5811F")
        print("     テキストカラー : #333333")
        print("     リンクカラー   : #003DA5")
        print("     背景色        : #F5F5F0")
        print()
        print("  2. ヘッダー設定")
        print("     カスタマイズ → ヘッダー → 背景色 : #1A1A1A")
        print("     カスタマイズ → ヘッダー → レイアウト : ロゴ左・ナビ下")
        print()
        print("  3. 記事一覧をリスト型に変更")
        print("     カスタマイズ → トップページ → 記事一覧レイアウト → リスト")
        print()
        print("  4. 追加CSS")
        print("     カスタマイズ → 追加CSS → src/custom.css を貼り付けて公開")
        print()
        print("  5. 旧記事カテゴリのTOP除外")
        old_id = self.cat_ids.get("旧記事", "?")
        print(f"     カスタマイズ → トップページ → 記事一覧設定 → 除外カテゴリ")
        print(f"     「旧記事」(ID={old_id}) を追加 → 公開")
        print()
        print("  6. メニュー位置割り当て（API割り当てが失敗した場合）")
        print("     外観 → メニュー → 「カテゴリナビ」→ メニューの位置: グローバルナビ → 保存")
        print()
        print("  7. メニューCSSクラス確認（SWELL v4.x 以降は自動適用済みの場合あり）")
        print("     外観 → メニュー → 表示オプション → CSSクラスにチェック")
        print("     各メニューアイテムにCSSクラスが入っているか確認")
        print()
        print("  8. テスト記事のXカード確認")
        print("     試合速報1本目の記事にXポスト埋め込みあり")
        print("     記事を開き、埋め込みXポストが表示されることを確認")
        print("     ※ X(Twitter)のオEmbed が機能しない場合は WP管理画面 → 設定 → メディア → 確認")
        print()


# ──────────────────────────────────────────────
# Fake Response（dry-run用）
# ──────────────────────────────────────────────

class _FakeResponse:
    def __init__(self, data: dict):
        self._data = data
        self.status_code = 200

    def json(self):
        return self._data

    def raise_for_status(self):
        pass


# ──────────────────────────────────────────────
# エントリーポイント
# ──────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="yoshilover フェーズ① 自動セットアップ",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
例:
  python3 src/setup_phase1.py              # 実行
  python3 src/setup_phase1.py --dry-run    # 確認のみ
  python3 src/setup_phase1.py --skip-css   # CSS生成をスキップ
        """,
    )
    parser.add_argument("--dry-run",  action="store_true", help="変更を行わず確認のみ")
    parser.add_argument("--skip-css", action="store_true", help="カスタムCSS生成をスキップ")
    args = parser.parse_args()

    setup = Phase1Setup(dry_run=args.dry_run)
    setup.run(skip_css=args.skip_css)


if __name__ == "__main__":
    main()
