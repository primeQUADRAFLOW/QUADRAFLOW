"""
Telegramチャンネル
Telegram Botを通じてエージェントと対話する
"""

import logging
from typing import TYPE_CHECKING

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from quadraflow.config import TelegramConfig

if TYPE_CHECKING:
    from quadraflow.core.agent import Agent

logger = logging.getLogger(__name__)


class TelegramChannel:
    """Telegramチャンネル（Bot）"""

    def __init__(self, config: TelegramConfig, agents: dict[str, "Agent"]):
        self.config = config
        self.agents = agents
        self.app: Application = None
        self._default_agent_id: str = ""
        if agents:
            self._default_agent_id = list(agents.keys())[0]

    def _is_allowed(self, user_id: int) -> bool:
        """許可されたユーザーか確認する"""
        if not self.config.allowed_users:
            return True
        return user_id in self.config.allowed_users

    async def _start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/start コマンドハンドラー"""
        if not self._is_allowed(update.effective_user.id):
            await update.message.reply_text("アクセスが許可されていません。")
            return

        agent_list = "\n".join([f"  - {aid}: {a.name}" for aid, a in self.agents.items()])
        await update.message.reply_text(
            f"QUADRAFLOW Agent System へようこそ！\n\n"
            f"稼働中のエージェント:\n{agent_list}\n\n"
            f"使い方:\n"
            f"  /status - 全エージェントのステータス\n"
            f"  /run [agent_id] - エージェントを即時実行\n"
            f"  /ask [agent_id] [メッセージ] - エージェントに質問\n"
            f"  メッセージを送ると最初のエージェントが応答します"
        )

    async def _status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/status コマンドハンドラー"""
        if not self._is_allowed(update.effective_user.id):
            await update.message.reply_text("アクセスが許可されていません。")
            return

        lines = ["エージェントステータス:\n"]
        for agent_id, agent in self.agents.items():
            status = agent.get_status_dict()
            last_run = status["last_run"][:16] if status["last_run"] else "未実行"
            next_run = status["next_run"][:16] if status["next_run"] else "-"
            emoji = {"idle": "待機", "running": "実行中", "error": "エラー", "disabled": "無効"}
            lines.append(
                f"[{emoji.get(status['status'], status['status'])}] {status['name']}\n"
                f"  最終実行: {last_run}\n"
                f"  次回実行: {next_run}"
            )

        await update.message.reply_text("\n\n".join(lines))

    async def _run_agent(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/run [agent_id] コマンドハンドラー"""
        if not self._is_allowed(update.effective_user.id):
            await update.message.reply_text("アクセスが許可されていません。")
            return

        args = context.args
        if not args:
            agent_id = self._default_agent_id
        else:
            agent_id = args[0]

        agent = self.agents.get(agent_id)
        if not agent:
            await update.message.reply_text(f"エージェント '{agent_id}' が見つかりません。")
            return

        await update.message.reply_text(f"エージェント '{agent.name}' を実行中...")

        try:
            result = await agent.run(trigger="telegram_command")
            # 長すぎる場合は切り詰め（Telegramの上限は4096文字）
            if len(result) > 3800:
                result = result[:3800] + "\n...(以下省略)..."
            await update.message.reply_text(result)
        except Exception as e:
            await update.message.reply_text(f"実行エラー: {e}")

    async def _ask_agent(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/ask [agent_id] [メッセージ] コマンドハンドラー"""
        if not self._is_allowed(update.effective_user.id):
            await update.message.reply_text("アクセスが許可されていません。")
            return

        args = context.args
        if len(args) < 2:
            await update.message.reply_text("使い方: /ask [agent_id] [メッセージ]")
            return

        agent_id = args[0]
        message = " ".join(args[1:])

        agent = self.agents.get(agent_id)
        if not agent:
            await update.message.reply_text(f"エージェント '{agent_id}' が見つかりません。")
            return

        await update.message.reply_text(f"'{agent.name}' に問い合わせ中...")

        try:
            result = await agent.run(trigger="telegram_ask", user_message=message)
            if len(result) > 3800:
                result = result[:3800] + "\n...(以下省略)..."
            await update.message.reply_text(result)
        except Exception as e:
            await update.message.reply_text(f"エラー: {e}")

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """通常メッセージをデフォルトエージェントに転送する"""
        if not self._is_allowed(update.effective_user.id):
            return

        if not self._default_agent_id:
            await update.message.reply_text("稼働中のエージェントがありません。")
            return

        agent = self.agents.get(self._default_agent_id)
        if not agent:
            return

        user_message = update.message.text
        await update.message.reply_text(f"'{agent.name}' が処理中...")

        try:
            result = await agent.run(trigger="telegram_message", user_message=user_message)
            if len(result) > 3800:
                result = result[:3800] + "\n...(以下省略)..."
            await update.message.reply_text(result)
        except Exception as e:
            await update.message.reply_text(f"エラー: {e}")

    async def start(self):
        """Telegram Botを起動する"""
        if not self.config.token:
            logger.warning("Telegram tokenが設定されていないため、Telegramチャンネルをスキップします")
            return

        self.app = Application.builder().token(self.config.token).build()

        # コマンドハンドラー登録
        self.app.add_handler(CommandHandler("start", self._start))
        self.app.add_handler(CommandHandler("status", self._status))
        self.app.add_handler(CommandHandler("run", self._run_agent))
        self.app.add_handler(CommandHandler("ask", self._ask_agent))
        self.app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
        )

        logger.info("Telegram Bot を開始します...")
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(drop_pending_updates=True)
        logger.info("Telegram Bot 稼働中")

    async def stop(self):
        """Telegram Botを停止する"""
        if self.app:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
            logger.info("Telegram Bot 停止")
