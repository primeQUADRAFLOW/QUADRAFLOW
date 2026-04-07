FROM python:3.11-slim

# 作業ディレクトリ
WORKDIR /app

# システム依存パッケージ
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python依存パッケージを先にインストール（レイヤーキャッシュ利用）
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ソースコードをコピー
COPY . .

# データディレクトリ作成
RUN mkdir -p /app/data /app/workspace

# ヘルスチェック
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8765/api/v1/health || exit 1

# ポート公開
EXPOSE 8765

# エントリーポイント
CMD ["python", "main.py", "start", "--config", "/app/config/quadraflow.yaml"]
