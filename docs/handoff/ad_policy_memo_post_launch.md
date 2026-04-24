# 広告 (AdSense) 運用後方針メモ

**記録日**: 2026-04-24
**発行**: Claude Code (front owner)、よしひろさん指示「広告に関しては運用後方針を考えるから記録しといて」

## 現状 (非公開プレビュー中)

`src/custom.css` で **AdSense 全殺し** している。以下のルールが `!important` で効いている:

```css
ins.adsbygoogle,
.adsbygoogle,
ins[data-ad-client],
.google-auto-placed,
div[id^="google_ads_"],
div[id^="aswift_"],
iframe[id^="google_ads_iframe"],
iframe[src*="googleads"],
iframe[src*="googlesyndication"],
iframe[src*="doubleclick"],
iframe[src*="adservice.google"],
[data-google-query-id],
[data-ad-slot],
.google-vignette,
div[data-anchor-status],
div[data-adbreak-test],
[aria-label="Advertisement"],
[aria-label="広告"],
/* ... anchor-top / anchor-bottom 系も全消し */
{
  display: none !important;
  visibility: hidden !important;
  height: 0 !important;
  ...
}
```

## 公開時の 3 パターン想定

### パターン A: 広告を UI 優先で抑える (よしひろさん好み寄り)
- AdSense 管理画面:
  - Auto ads density = **Low**
  - Anchor ads → **OFF**
  - Vignette ads (全画面 interstitial) → **OFF**
  - In-page ads のみ残す
- CSS:
  - 全殺しルールを削除 or 「anchor / vignette のみ kill」に限定
  - `ins.adsbygoogle { max-height: 320px }` の cap は残す
- **結果**: 記事中に静的な広告が最大 3 個、画面上下 追従なし、全画面遷移なし
- **収益影響**: 自動広告に比べて 30-40% 減だが UX 保たれる

### パターン B: 通常 UX + 自動広告フル稼働 (収益重視)
- AdSense 自動広告全部 ON
- CSS の広告 kill 全削除
- **結果**: 自動広告フル、anchor bottom + vignette 登場
- **収益影響**: MAX

### パターン C: 広告 完全 OFF (サブスク化等)
- AdSense 未使用
- CSS 全殺し維持
- 他収益: メンバーシップ / Amazon affiliate / X プレミアム等
- **結果**: 収益 ≒ 0、UX 最高

## Claude Code 側で即できる switch

### A 方針への切替 commands

```bash
# CSS 側の広告 kill を部分的に unlock
# src/custom.css 内の "AdSense 全殺し" section を "anchor-top + vignette + 4 個以上" に限定
```

具体的には `src/custom.css` の line ~1991 (現) の巨大 selector を以下へ圧縮:
```css
/* anchor-top のみ残して殺す */
body > [id^="aswift_"][style*="top"],
body > [id^="aswift_"][style*="bottom"],
body > [data-google-query-id][style*="top"],
.google-vignette {
  display: none !important;
}
/* 記事内 ad は 4 個目以降のみ殺す、3 個までは表示 */
.post_content ins.adsbygoogle:nth-of-type(n+4),
.entry-content ins.adsbygoogle:nth-of-type(n+4) {
  display: none !important;
}
```

### B 方針
```bash
# src/custom.css から全殺し section 完全削除 + REST PUT
```

### C 方針
現状維持。`body.yoshi-unpublished` bar だけ外す。

## 決定フローチャート(運用後判断)

```
公開後 1 週間の analytics 見て:
  広告 UX 苦情 / 直帰率 UP / PV 減 → A 方針へ (密度下げる)
  広告 影響なし / 収益 OK    → B 方針維持 or C から復活
  収益重視で他マネタイズあり → C 方針
```

## 切替時 Claude Code への指示文例

> 「広告方針 A で」
> 「広告方針 B で」
> 「広告方針 C で」

→ Claude Code が `src/custom.css` を該当状態に編集 + REST PUT で live 反映。user 作業 0。

## 関連 CSS 現行箇所 (ref)

- 全殺し: `src/custom.css` line ~1991–2040
- anchor-top kill: line ~2080–2100
- anchor-bottom kill: line ~2115–2135
- スポンサーリンク ::before label: line ~1970

## 関連 commit

- `7e3ec89`: 非公開前提で広告全殺し
- `c198f14`: 画面上 anchor kill 強化
- `a15da12`: anchor top display:none に戻す (user 判断)
- `77a7be1`: anchor-bottom + inline ad 280px cap
