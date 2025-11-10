
# X 自動投稿ボット（ストップ高/安・前場/後場）

## 使い方（超短縮）
1. Xの開発者ポータルでAppを作り、**Read+Write権限**のキー（API Key/Secret, Access Token/Secret）を取得。
2. このリポジトリをGitHubに作成 → `Settings > Secrets and variables > Actions` に以下を登録：
   - `TW_API_KEY`, `TW_API_SECRET`, `TW_ACCESS_TOKEN`, `TW_ACCESS_SECRET`
3. 平日 **11:35 / 15:10（JST）** に自動投稿。手動テストは `Actions > Run workflow`。

### ローカルテスト（任意）
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export TW_API_KEY=xxx TW_API_SECRET=yyy TW_ACCESS_TOKEN=zzz TW_ACCESS_SECRET=www
export SESSION=前場  # or 後場
python bot/main.py
```

※ スクレイピング先の構造変更で動かなくなる場合があります。出典明記・アクセス頻度に配慮してご利用ください。
