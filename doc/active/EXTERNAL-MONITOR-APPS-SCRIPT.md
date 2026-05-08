# 外部独立監視 Google Apps Script(B案)

yoshilover インフラと**完全独立**な Google Apps Script から daily ping mail を送る設定。
yoshilover の Cloud Run / publish-notice / Gmail bridge が全部死んでも届く。

## 仕組み

- Google Apps Script が user の Google アカウントから直接 Gmail API で送信
- yoshilover インフラ完全に経由しない
- ¥0(Apps Script + Gmail 個人枠)

## 設定手順(user 作業 10分)

### 1. https://script.google.com/ にアクセス
ログイン後「新しいプロジェクト」

### 2. 以下を貼り付け(Code.gs)

```javascript
function sendDailyExternalPing() {
  const today = Utilities.formatDate(new Date(), 'Asia/Tokyo', 'yyyy-MM-dd HH:mm');
  const subject = `【外部監視】${today} yoshilover 死活ping`;
  const body =
    `これは Google Apps Script からの独立 ping です。\n\n` +
    `このメールが届いているなら:\n` +
    `  ✅ あなたの Gmail 通知は正常\n` +
    `  ✅ 朝のメールが届かない場合 yoshilover 側の問題\n\n` +
    `yoshilover の朝サマリーが届かなかった場合は\n` +
    `Cloud Run / publish-notice の調査が必要です。`;
  GmailApp.sendEmail('fwns6760@gmail.com', subject, body);
}
```

### 3. trigger 設定

左メニュー「トリガー」→「トリガーを追加」
- 関数: `sendDailyExternalPing`
- イベントソース: 時間主導型
- 時間ベースのトリガー: 日タイマー
- 時刻: **午前 6時〜7時**

「保存」→ 初回実行時に Gmail 送信権限を許可

### 4. 動作テスト

エディタ上部「実行」ボタン → 即時 1通自分宛に届けば完了

## 結果

明日朝 06:00 〜 07:00 に **2通届く**:
1. 【朝サマリー】yoshilover 稼働中(yoshilover 経由)
2. 【外部監視】yoshilover 死活ping(GAS 経由・完全独立)

両方届けば全部健全、yoshilover の方だけ来なければ即原因特定可能。
