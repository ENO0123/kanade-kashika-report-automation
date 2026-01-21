# Looker Studio レポート自動送信システム

Looker StudioのPDFレポートを毎週自動でSlackの指定チャンネルに送信するシステムです。

## 機能

- Looker Studioのレポートを自動でPDFとしてエクスポート
- Slackの指定チャンネルに自動送信
- **AI解析機能**: Google Gemini APIを使用してPDFを自動解析し、要約コメントを生成（オプション）
- GitHub Actionsによる週次自動実行

## セットアップ

### 1. 必要な環境

- Python 3.11以上
- Google Chrome（またはChromium）
- ChromeDriver

### 2. 依存関係のインストール

```bash
pip install -r requirements.txt
```

### 3. Slack Botの設定

1. [Slack API](https://api.slack.com/apps)でアプリを作成
2. Bot Token Scopesに以下を追加：
   - `files:write`
   - `channels:write`（パブリックチャンネルの場合）
   - `groups:write`（プライベートチャンネルの場合）
3. Botをワークスペースにインストール
4. Botを送信先チャンネルに招待（`/invite @your-bot-name`）

### 4. Google Gemini APIの設定（AI解析機能を使用する場合）

AI解析機能を使用する場合は、Google Gemini APIキーを取得してください：

1. [Google AI Studio](https://makersuite.google.com/app/apikey)でAPIキーを取得
2. GitHub Secretsに`GEMINI_API_KEY`として設定
3. AI解析を無効にする場合は、`ENABLE_AI_ANALYSIS`を`false`に設定（デフォルトは`true`）

**注意**: Gemini APIは無料枠がありますが、使用量に応じて課金される場合があります。詳細は[Google AI Studio](https://makersuite.google.com/app/apikey)を確認してください。

### 5. GitHub Actionsの設定

GitHubリポジトリのSecretsに以下を設定：

1. **LOOKER_STUDIO_URL**: Looker StudioのレポートURL
   - 例: `https://lookerstudio.google.com/reporting/xxxxx`

2. **SLACK_BOT_TOKEN**: Slack Bot Token
   - 形式: `xoxb-xxxxx-xxxxx-xxxxx`

3. **SLACK_CHANNEL**: SlackチャンネルIDまたはチャンネル名
   - チャンネル名の場合: `#reports`
   - チャンネルIDの場合: `C1234567890`
   - チャンネルIDは、チャンネルを右クリック → 「リンクをコピー」で取得できます

4. **GEMINI_API_KEY**（オプション）: Google Gemini APIキー
   - AI解析機能を使用する場合のみ必要
   - 取得方法: [Google AI Studio](https://makersuite.google.com/app/apikey)

5. **ENABLE_AI_ANALYSIS**（オプション）: AI解析を有効にするかどうか
   - `true`（デフォルト）または`false`
   - 設定しない場合は`true`がデフォルト

### 6. ローカル実行（テスト用）

環境変数を設定して実行：

```bash
export LOOKER_STUDIO_URL="https://lookerstudio.google.com/reporting/xxxxx"
export SLACK_BOT_TOKEN="xoxb-xxxxx-xxxxx-xxxxx"
export SLACK_CHANNEL="#reports"
export GEMINI_API_KEY="your-gemini-api-key"  # AI解析を使用する場合
export ENABLE_AI_ANALYSIS="true"  # AI解析を有効にする場合（デフォルト: true）

python report_sender.py
```

または、`.env`ファイルを作成：

```env
LOOKER_STUDIO_URL=https://lookerstudio.google.com/reporting/xxxxx
SLACK_BOT_TOKEN=xoxb-xxxxx-xxxxx-xxxxx
SLACK_CHANNEL=#reports
GEMINI_API_KEY=your-gemini-api-key
ENABLE_AI_ANALYSIS=true
```

## 実行スケジュール

デフォルトでは毎週月曜日の午前9時（JST）に実行されます。

スケジュールを変更する場合は、`.github/workflows/weekly-report.yml`の`cron`設定を編集してください。

## トラブルシューティング

### PDFが正しく生成されない場合

- Looker StudioのレポートURLが正しいか確認
- レポートが公開されているか確認（非公開の場合は認証が必要）
- レポートの読み込みに時間がかかる場合は、`report_sender.py`の待機時間を調整

### Slackに送信できない場合

- Bot Tokenが正しいか確認
- Botがチャンネルに招待されているか確認
- Botに必要な権限（`files:write`など）が付与されているか確認

### ChromeDriverのエラー

- ChromeとChromeDriverのバージョンが一致しているか確認
- `webdriver-manager`を使用する場合は、`report_sender.py`を修正して自動管理を有効化

### AI解析が動作しない場合

- `GEMINI_API_KEY`が正しく設定されているか確認
- APIキーの有効性を確認（[Google AI Studio](https://makersuite.google.com/app/apikey)で確認可能）
- PDFファイルが大きすぎる場合、Gemini APIの制限に達する可能性があります
- `ENABLE_AI_ANALYSIS`が`true`に設定されているか確認

## AI解析機能について

このシステムは、Google Gemini APIを使用してPDFレポートを自動解析し、以下の情報を抽出します：

- レポートの主要な内容・テーマ
- 重要な数値や指標
- 注目すべきポイントやトレンド
- 簡潔なまとめ

AI解析結果は、PDFファイルと一緒にSlackに投稿されます。これにより、Slack Enterprise PlusプランのSlack AIと同様の機能を自動化できます。

**注意**: 
- Gemini APIは無料枠がありますが、使用量に応じて課金される場合があります
- PDFファイルのサイズや複雑さによっては、解析に時間がかかる場合があります
- AI解析を無効にしたい場合は、`ENABLE_AI_ANALYSIS`を`false`に設定してください

## ライセンス

MIT
