# QUADRAFLOW（日本語ドキュメント）

YAMLファイル1つで動く自律AIエージェントシステム

---

## 概要

QUADRAFLOWは、設定ファイル1つで複数のAIエージェントを自律稼働させることができるOSSシステムです。

- **ハートビート式**: 誰も命令しなくても、エージェントが定期的に自分で動く
- **エージェント間通信**: inbox/outboxでエージェント同士がメッセージを送り合う
- **LLM切替自由**: Ollama（ローカル）からGroq/OpenAI/Geminiまで設定1行で切替
- **Webダッシュボード**: ブラウザでリアルタイム監視
- **Telegram連携**: スマホからエージェントを操作

---

## クイックスタート

```bash
git clone https://github.com/primeQUADRAFLOW/quadraflow.git
cd quadraflow
pip install -r requirements.txt

# 設定ファイルを生成
python main.py init

# quadraflow.yaml を編集してLLM設定を入れる

# 起動
python main.py start
```

http://localhost:8765 でダッシュボードを確認できます。

---

## 設定例（Ollama・完全ローカル）

```yaml
llm:
  provider: ollama
  model: gemma2:2b
  base_url: http://localhost:11434/v1

agents:
  - id: researcher
    name: "リサーチャー"
    heartbeat: 60m
    tools: [web_search, file_write]
    prompt: "最新のAIニュースをリサーチしてレポートを書く"

  - id: writer
    name: "ライター"
    heartbeat: 120m
    tools: [file_read, file_write]
    prompt: "リサーチャーのレポートを読んでブログ記事を書く"
```

---

## 対応LLMプロバイダー

| プロバイダー | 設定値 | 特徴 |
|-------------|--------|------|
| Ollama | `ollama` | ローカル・無料・プライバシー重視 |
| Groq | `groq` | 高速・無料枠あり |
| OpenAI | `openai` | 高品質・従量課金 |
| Anthropic | `anthropic` | Claude・高品質 |
| Gemini | `gemini` | Google・無料枠あり |
| OpenRouter | `openrouter` | 多数のモデルをAPI統一で利用 |

---

## CLIコマンド

```bash
# 起動
python main.py start

# 設定ファイル検証
python main.py validate --config quadraflow.yaml

# サンプル設定生成
python main.py init

# ポート・ホスト指定
python main.py start --host 0.0.0.0 --port 9000
```

---

## REST API

```bash
# エージェント一覧
GET /api/v1/agents

# エージェントを即時実行
POST /api/v1/agents/{agent_id}/trigger

# エージェントにメッセージ送信（同期応答）
POST /api/v1/agents/{agent_id}/message
{"content": "最新のニュースは？"}

# 実行ログ取得
GET /api/v1/agents/{agent_id}/logs

# ヘルスチェック
GET /api/v1/health
```

---

## Telegramコマンド

| コマンド | 説明 |
|---------|------|
| `/start` | エージェント一覧と使い方を表示 |
| `/status` | 全エージェントのステータス確認 |
| `/run [id]` | エージェントを即時実行 |
| `/ask [id] [質問]` | エージェントに質問して返答を受け取る |
| テキスト送信 | 最初のエージェントが応答 |

---

## Dockerで起動

```bash
# 設定ファイルを用意
cp examples/quadraflow.yaml ./quadraflow.yaml

# 起動
docker-compose up -d

# ログ確認
docker-compose logs -f quadraflow
```

---

## ライセンス

MIT License
