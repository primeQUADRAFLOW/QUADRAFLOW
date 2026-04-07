"""
メモリシステム
JSONファイルベースの永続メモリ + 簡易キーワード検索
"""

import json
import logging
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class Memory:
    """エージェントのメモリ管理"""

    def __init__(self, agent_id: str, data_dir: str = "./data"):
        self.agent_id = agent_id
        self.memory_dir = Path(data_dir) / "agents" / agent_id / "memory"
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.entries_file = self.memory_dir / "entries.json"
        self._lock = asyncio.Lock()
        self._entries: list[dict] = []
        self._load()

    def _load(self):
        """ディスクからメモリを読み込む"""
        if self.entries_file.exists():
            try:
                with open(self.entries_file, "r", encoding="utf-8") as f:
                    self._entries = json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                logger.warning(f"メモリ読み込みエラー ({self.agent_id}): {e}")
                self._entries = []
        else:
            self._entries = []

    def _save(self):
        """メモリをディスクに保存する"""
        try:
            with open(self.entries_file, "w", encoding="utf-8") as f:
                json.dump(self._entries, f, ensure_ascii=False, indent=2)
        except IOError as e:
            logger.error(f"メモリ保存エラー ({self.agent_id}): {e}")

    async def add(self, content: str, tags: Optional[list[str]] = None, source: str = "heartbeat"):
        """メモリエントリを追加する"""
        async with self._lock:
            entry = {
                "id": len(self._entries),
                "content": content,
                "tags": tags or [],
                "source": source,
                "created_at": datetime.now().isoformat(),
            }
            self._entries.append(entry)
            # 最大1000件で古いものを削除
            if len(self._entries) > 1000:
                self._entries = self._entries[-1000:]
            self._save()
            logger.debug(f"メモリ追加 ({self.agent_id}): {content[:50]}...")

    async def search(self, query: str, limit: int = 5) -> list[dict]:
        """キーワードで過去のメモリを検索する"""
        query_lower = query.lower()
        results = []
        for entry in reversed(self._entries):
            content_lower = entry["content"].lower()
            if any(word in content_lower for word in query_lower.split()):
                results.append(entry)
                if len(results) >= limit:
                    break
        return results

    async def get_recent(self, n: int = 10) -> list[dict]:
        """最近のメモリを取得する"""
        return list(reversed(self._entries[-n:]))

    async def get_summary(self, max_chars: int = 2000) -> str:
        """システムプロンプト用のメモリサマリーを生成する"""
        recent = await self.get_recent(20)
        if not recent:
            return "（まだ記憶はありません）"

        lines = []
        total_chars = 0
        for entry in recent:
            line = f"[{entry['created_at'][:16]}] {entry['content'][:200]}"
            if total_chars + len(line) > max_chars:
                break
            lines.append(line)
            total_chars += len(line)

        return "\n".join(lines)

    async def clear(self):
        """全メモリをクリアする"""
        async with self._lock:
            self._entries = []
            self._save()
