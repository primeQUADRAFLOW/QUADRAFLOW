"""
REST APIチャンネル（FastAPI）
外部からエージェントを操作するためのREST API
"""

import logging
from typing import Optional, TYPE_CHECKING
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel

if TYPE_CHECKING:
    from quadraflow.core.agent import Agent
    from quadraflow.core.scheduler import HeartbeatScheduler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["agents"])


# グローバルな参照（main.pyから設定される）
_agents: dict[str, "Agent"] = {}
_scheduler: Optional["HeartbeatScheduler"] = None


def setup(agents: dict[str, "Agent"], scheduler: "HeartbeatScheduler"):
    """APIルーターにエージェントとスケジューラーを設定する"""
    global _agents, _scheduler
    _agents = agents
    _scheduler = scheduler


class MessageRequest(BaseModel):
    content: str
    agent_id: Optional[str] = None


class RunRequest(BaseModel):
    agent_id: str
    message: Optional[str] = None


@router.get("/agents")
async def list_agents():
    """全エージェントの一覧を返す"""
    return {
        "agents": [agent.get_status_dict() for agent in _agents.values()]
    }


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str):
    """エージェントの詳細情報を返す"""
    agent = _agents.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"エージェント '{agent_id}' が見つかりません")
    return agent.get_status_dict()


@router.post("/agents/{agent_id}/run")
async def run_agent(agent_id: str, request: RunRequest, background_tasks: BackgroundTasks):
    """エージェントを非同期実行する"""
    agent = _agents.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"エージェント '{agent_id}' が見つかりません")

    from quadraflow.core.agent import AgentStatus
    if agent.status == AgentStatus.RUNNING:
        raise HTTPException(status_code=409, detail="エージェントは現在実行中です")

    background_tasks.add_task(
        agent.run,
        trigger="api",
        user_message=request.message,
    )
    return {"status": "accepted", "agent_id": agent_id, "message": "実行をキューに追加しました"}


@router.post("/agents/{agent_id}/message")
async def send_message_to_agent(agent_id: str, request: MessageRequest):
    """エージェントにメッセージを送信して応答を同期的に待つ"""
    agent = _agents.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"エージェント '{agent_id}' が見つかりません")

    result = await agent.run(trigger="api_message", user_message=request.content)
    return {"agent_id": agent_id, "response": result}


@router.get("/agents/{agent_id}/logs")
async def get_agent_logs(agent_id: str, limit: int = 20):
    """エージェントの実行ログを返す"""
    agent = _agents.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"エージェント '{agent_id}' が見つかりません")

    logs = [log.to_dict() for log in agent.execution_logs[-limit:]]
    return {"agent_id": agent_id, "logs": list(reversed(logs))}


@router.get("/agents/{agent_id}/memory")
async def get_agent_memory(agent_id: str, n: int = 20):
    """エージェントのメモリを返す"""
    agent = _agents.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"エージェント '{agent_id}' が見つかりません")

    entries = await agent.memory.get_recent(n)
    return {"agent_id": agent_id, "memory": entries}


@router.get("/schedule")
async def get_schedule():
    """スケジュール情報を返す"""
    if not _scheduler:
        return {"schedules": []}
    return {"schedules": _scheduler.get_schedule_info()}


@router.post("/agents/{agent_id}/trigger")
async def trigger_agent(agent_id: str):
    """エージェントのハートビートを即時トリガーする"""
    if not _scheduler:
        raise HTTPException(status_code=503, detail="スケジューラーが起動していません")

    if agent_id not in _agents:
        raise HTTPException(status_code=404, detail=f"エージェント '{agent_id}' が見つかりません")

    _scheduler.trigger_now(agent_id)
    return {"status": "triggered", "agent_id": agent_id}


@router.get("/health")
async def health():
    """ヘルスチェック"""
    return {
        "status": "ok",
        "agents": len(_agents),
        "scheduler_running": _scheduler.scheduler.running if _scheduler else False,
    }
