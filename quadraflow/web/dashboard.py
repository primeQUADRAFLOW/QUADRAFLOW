"""
Webダッシュボード（FastAPI + Jinja2）
エージェントの状態をリアルタイムで監視・操作するUI
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator, TYPE_CHECKING

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

if TYPE_CHECKING:
    from quadraflow.core.agent import Agent
    from quadraflow.core.scheduler import HeartbeatScheduler

logger = logging.getLogger(__name__)

# テンプレートディレクトリ
TEMPLATES_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# グローバル参照
_agents: dict[str, "Agent"] = {}
_scheduler: "HeartbeatScheduler" = None
_event_queue: asyncio.Queue = asyncio.Queue(maxsize=200)


def setup_dashboard(app: FastAPI, agents: dict[str, "Agent"], scheduler: "HeartbeatScheduler"):
    """ダッシュボードをFastAPIアプリに設定する"""
    global _agents, _scheduler
    _agents = agents
    _scheduler = scheduler

    # SSEイベントを各エージェントのログコールバックに登録
    for agent in agents.values():
        agent.add_log_callback(_on_agent_log)


async def _on_agent_log(log):
    """エージェント実行ログをSSEキューに送る"""
    event_data = {
        "type": "log",
        "agent_id": log.agent_id,
        "success": log.success,
        "summary": log.summary[:200] if log.summary else "",
        "finished_at": log.finished_at,
        "error": log.error,
    }
    try:
        _event_queue.put_nowait(json.dumps(event_data, ensure_ascii=False))
    except asyncio.QueueFull:
        pass


def create_dashboard_router():
    """ダッシュボード用のルーターを作成して返す"""
    from fastapi import APIRouter
    router = APIRouter(tags=["dashboard"])

    @router.get("/", response_class=HTMLResponse)
    async def index(request: Request):
        """メインダッシュボード"""
        agents_data = []
        for agent in _agents.values():
            status = agent.get_status_dict()
            agents_data.append(status)

        schedule_info = _scheduler.get_schedule_info() if _scheduler else []

        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "agents": agents_data,
                "schedule": schedule_info,
                "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        )

    @router.get("/agent/{agent_id}", response_class=HTMLResponse)
    async def agent_detail(request: Request, agent_id: str):
        """エージェント詳細ページ"""
        agent = _agents.get(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="エージェントが見つかりません")

        status = agent.get_status_dict()
        logs = [log.to_dict() for log in reversed(agent.execution_logs[-20:])]
        memory = await agent.memory.get_recent(15)

        return templates.TemplateResponse(
            "agent.html",
            {
                "request": request,
                "agent": status,
                "logs": logs,
                "memory": memory,
                "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            },
        )

    @router.post("/agent/{agent_id}/send")
    async def send_message(request: Request, agent_id: str, message: str = Form(...)):
        """エージェントにメッセージを送信する"""
        agent = _agents.get(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="エージェントが見つかりません")

        # バックグラウンドで実行
        asyncio.create_task(agent.run(trigger="dashboard", user_message=message))
        return RedirectResponse(url=f"/agent/{agent_id}?sent=1", status_code=303)

    @router.post("/agent/{agent_id}/trigger")
    async def trigger_agent(agent_id: str):
        """エージェントを即時実行する"""
        if agent_id not in _agents:
            raise HTTPException(status_code=404, detail="エージェントが見つかりません")
        if _scheduler:
            _scheduler.trigger_now(agent_id)
        return RedirectResponse(url=f"/agent/{agent_id}", status_code=303)

    @router.get("/events")
    async def sse_events(request: Request):
        """Server-Sent Events エンドポイント（リアルタイム更新）"""
        async def event_generator() -> AsyncIterator[str]:
            # 接続確認イベント
            yield {
                "event": "connected",
                "data": json.dumps({"message": "SSE接続確立"}),
            }

            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(_event_queue.get(), timeout=30)
                    yield {"event": "agent_event", "data": data}
                except asyncio.TimeoutError:
                    # keepalive
                    yield {
                        "event": "ping",
                        "data": json.dumps({"time": datetime.now().isoformat()}),
                    }

        return EventSourceResponse(event_generator())

    @router.get("/api/status")
    async def api_status():
        """全エージェントのステータスをJSONで返す（ポーリング用）"""
        return {
            "agents": [a.get_status_dict() for a in _agents.values()],
            "schedule": _scheduler.get_schedule_info() if _scheduler else [],
            "time": datetime.now().isoformat(),
        }

    return router
