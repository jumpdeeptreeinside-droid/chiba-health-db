# Mac復旧手順書

新しいMacでCrossHealth Healthcare DBの開発環境をゼロから構築する手順。

## 1. 基本ツールのインストール

```bash
# Homebrew
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# 基本パッケージ
brew install python git git-lfs gh sqlite

# Git LFS初期化
git lfs install
```

## 2. GitHubからクローン

```bash
gh auth login
gh repo clone jumpdeeptreeinside-droid/chiba-health-db ~/chiba-health-db
cd ~/chiba-health-db
git lfs pull  # crosshealth.db をダウンロード
```

## 3. Python環境

```bash
pip3 install requests beautifulsoup4 pandas streamlit folium geocoder
pip3 install anthropic google-generativeai
```

## 4. .env の設定

```bash
cp config/.env.example .env
# エディタで .env を開き、APIキーを設定:
#   GEMINI_API_KEY=...
#   GOOGLE_MAPS_API_KEY=...
```

APIキーの取得先:
- Gemini: https://aistudio.google.com/apikey
- Google Maps: https://console.cloud.google.com/apis/credentials

## 5. Claude Code のインストール

```bash
# Claude Code CLI
npm install -g @anthropic-ai/claude-code
# または
brew install claude

# 認証
claude auth login
```

## 6. Watcher + LaunchAgent の設定

Claude Watcherは、`inbox/claude_tasks/` にタスクファイルが追加されると自動でClaude Codeを実行する仕組み。

```bash
# Watcher スクリプトを配置
mkdir -p ~/bin
cp config/claude_watcher.py ~/bin/
cp config/run_watcher.sh ~/bin/
chmod +x ~/bin/run_watcher.sh

# LaunchAgent 登録（Mac起動時に自動実行）
cp config/com.crosshealth.watcher.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.crosshealth.watcher.plist

# 動作確認
launchctl list | grep crosshealth
```

## 7. ngrok + Streamlit の設定

```bash
# ngrok（外部公開用）
brew install ngrok
ngrok config add-authtoken YOUR_NGROK_TOKEN

# Streamlit起動テスト
streamlit run app.py --server.port 8501

# 別ターミナルで ngrok 起動
ngrok http 8501
```

## 8. 都道府県別DBの復元（オプション）

統合DB（crosshealth.db）はリポジトリに含まれるが、都道府県別の個別DBを再構築する場合:

```bash
# 千葉県
mkdir -p ~/chiba_pdf_db
cd ~/chiba_pdf_db
python3 ~/chiba-health-db/scripts/build_prefecture.py --pref 12

# 全県一括
for code in $(seq -w 1 47); do
  python3 ~/chiba-health-db/scripts/build_prefecture.py --pref $code
done
```

## 9. 動作確認チェックリスト

```bash
# DB が存在し、テーブルが読めること
sqlite3 crosshealth.db "SELECT name, region FROM prefectures LIMIT 5;"

# 全テーブルにデータがあること
sqlite3 crosshealth.db "SELECT 'pharmacies', count(*) FROM pharmacies
  UNION ALL SELECT 'medical_facilities', count(*) FROM medical_facilities
  UNION ALL SELECT 'population_mesh', count(*) FROM population_mesh
  UNION ALL SELECT 'documents', count(*) FROM documents;"

# Watcher が動作していること
launchctl list | grep crosshealth

# Claude Code が認証済みであること
claude --version
```

## トラブルシューティング

- **git lfs pull でタイムアウト**: `GIT_LFS_SKIP_SMUDGE=1 git clone ...` でクローン後、`git lfs pull` を別途実行
- **LaunchAgent が起動しない**: `launchctl unload` → `launchctl load` で再登録。ログは `~/Library/Logs/claude_watcher.log`
- **.env が見つからない**: プロジェクトルートに `.env` を配置（`config/.env.example` からコピー）
