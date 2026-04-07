"""
エージェント間メッセージングシステム
inbox/outboxパターンでエージェント間通信を実現
"""

import json
import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class Message:
    """エージェント間メッセージ"""

    def __init__(
        self,
        from_agent: str,
        to_agent: str,
        content: str,
        message_type: str = "message",
        metadata: Optional[dict] = None,
    ):
        self.id = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{from_agent}"
        self.from_agent = from_agent
        self.to_agent = to_agent
        self.content = content
        self.message_type = message_type
        self.metadata = metadata or {}
        self.created_at = datetime.now().isoformat()
        self.read = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from_agent": self.from_agent,
            "to_agent": self.to_agent,
            "content": self.content,
            "message_type": self.message_type,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "read": self.read,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Message":
        msg = cls(
            from_agent=d["from_agent"],
            to_agent=d["to_agent"],
            content=d["content"],
            message_type=d.get("message_type", "message"),
            metadata=d.get("metadata", {}),
        )
        msg.id = d["id"]
        msg.created_at = d["created_at"]
        msg.read = d.get("read", False)
        return msg


class MessageBus:
    """
    全エージェント共有のメッセージバス
    各エージェントのinboxをファイルで管理する
    """

    def __init__(self, data_dir: str = "./data"):
        self.data_dir = Path(data_dir)
        self.inbox_dir = self.data_dir / "messaging"
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        # リアルタイム通知用のキュー（agent_id -> asyncio.Queue）
        self._queues: dict[str, asyncio.Queue] = {}

    def _get_inbox_path(self, agent_id: str) -> Path:
        path = self.inbox_dir / agent_id
        path.mkdir(parents=True, exist_ok=True)
        return path / "inbox.json"

    def _load_inbox(self, agent_id: str) -> list[dict]:
        path = self._get_inbox_path(agent_id)
        if not path.exists():
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []

    def _save_inbox(self, agent_id: str, messages: list[dict]):
        path = self._get_inbox_path(agent_id)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(messages, f, ensure_ascii=False, indent=2)

    async def send(self, message: Message):
        """メッセージをエージェントのinboxに送信する"""
        async with self._lock:
            inbox = self._load_inbox(message.to_agent)
            inbox.append(message.to_dict())
            # 最大500件保持
            if len(inbox) > 500:
                inbox = inbox[-500:]
            self._save_inbox(message.to_agent, inbox)
            logger.info(f"メッセージ送信: {message.from_agent} -> {message.to_agent}: {message.content[:50]}")

        # リアルタイムキューに通知
        if message.to_agent in self._queues:
            try:
                self._queues[message.to_agent].put_nowait(message)
            except asyncio.QueueFull:
                pass

    async def get_unread(self, agent_id: str) -> list[Message]:
        """未読メッセージを取得する"""
        async with self._lock:
            inbox = self._load_inbox(agent_id)
            unread = [Message.from_dict(m) for m in inbox if not m.get("read", False)]
            # 既読マーク
            for m in inbox:
                m["read"] = True
            self._save_inbox(agent_id, inbox)
        return unread

    async def get_all(self, agent_id: str, limit: int = 50) -> list[Message]:
        """全メッセージ（最新limit件）を取得する"""
        inbox = self._load_inbox(agent_id)
        return [Message.from_dict(m) for m in inbox[-limit:]]

    def subscribe(self, agent_id: str) -> asyncio.Queue:
        """リアルタイム通知用キューを取得する"""
        if agent_id not in self._queues:
            self._queues[agent_id] = asyncio.Queue(maxsize=100)
        return self._queues[agent_id]

    def unsubscribe(self, agent_id: str):
        """キューを解除する"""
        self._queues.pop(agent_id, None)
