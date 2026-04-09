"""
ハートビートスケジューラー
APSchedulerを使ってエージェントを定期実行する
"""

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.events import EVENT_JOB_EXECUTED, EVENT_JOB_ERROR

from quadraflow.config import parse_heartbeat

if TYPE_CHECKING:
    from quadraflow.core.agent import Agent

logger = logging.getLogger(__name__)


class HeartbeatScheduler:
    """全エージェントのハートビートを管理するスケジューラー"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone="Asia/Tokyo")
        self._agents: dict[str, "Agent"] = {}
        self.scheduler.add_listener(self._on_job_event, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)

    def register_agent(self, agent: "Agent"):
        """エージェントをスケジューラーに登録する"""
        if not agent.config.enabled:
            logger.info(f"エージェント '{agent.id}' は無効なのでスケジュール登録をスキップ")
            return

        interval_seconds = parse_heartbeat(agent.config.heartbeat)
        self._agents[agent.id] = agent

        job = self.scheduler.add_job(
            self._run_agent,
            trigger=IntervalTrigger(seconds=interval_seconds),
            args=[agent.id],
            id=f"heartbeat_{agent.id}",
            name=f"Heartbeat: {agent.name}",
            misfire_grace_time=60,
            coalesce=True,
            max_instances=1,
        )

        # 次回実行時刻をエージェントに設定
        if getattr(job, 'next_run_time', None):
            agent.next_run = job.next_run_time.isoformat()

        logger.info(
            f"エージェント '{agent.id}' をスケジュール登録: "
            f"インターバル={agent.config.heartbeat}（{interval_seconds}秒）"
        )

    async def _run_agent(self, agent_id: str):
        """スケジューラーから呼ばれるエージェント実行"""
        agent = self._agents.get(agent_id)
        if not agent:
            logger.error(f"エージェント '{agent_id}' が見つかりません")
            return

        logger.info(f"ハートビート開始: {agent_id}")
        await agent.run(trigger="heartbeat")

        # 次回実行時刻を更新
        job = self.scheduler.get_job(f"heartbeat_{agent_id}")
        if job and getattr(job, 'next_run_time', None):
            agent.next_run = job.next_run_time.isoformat()

    def _on_job_event(self, event):
        """ジョブイベントリスナー"""
        if event.exception:
            logger.error(f"スケジュールジョブエラー: {event.job_id}: {event.exception}")
        else:
            logger.debug(f"スケジュールジョブ完了: {event.job_id}")

    def start(self):
        """スケジューラーを開始する"""
        if not self.scheduler.running:
            self.scheduler.start()
            logger.info("ハートビートスケジューラー開始")

    def stop(self):
        """スケジューラーを停止する"""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("ハートビートスケジューラー停止")

    def trigger_now(self, agent_id: str):
        """エージェントを即時実行する"""
        job = self.scheduler.get_job(f"heartbeat_{agent_id}")
        if job:
            self.scheduler.modify_job(f"heartbeat_{agent_id}", next_run_time=datetime.now())
            logger.info(f"エージェント '{agent_id}' を即時実行キューに追加")
        else:
            logger.warning(f"エージェント '{agent_id}' のジョブが見つかりません")

    def get_schedule_info(self) -> list[dict]:
        """全エージェントのスケジュール情報を返す"""
        info = []
        for job in self.scheduler.get_jobs():
            agent_id = job.id.replace("heartbeat_", "")
            agent = self._agents.get(agent_id)
            info.append({
                "agent_id": agent_id,
                "agent_name": agent.name if agent else agent_id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "heartbeat": agent.config.heartbeat if agent else "unknown",
            })
        return info
