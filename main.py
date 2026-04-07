"""
QUADRAFLOW エントリーポイント
"""

import asyncio
import logging
import signal
import sys
from pathlib import Path

import click
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.table import Table

from quadraflow.config import load_config
from quadraflow.core.agent import Agent
from quadraflow.core.messaging import MessageBus
from quadraflow.core.scheduler import HeartbeatScheduler
from quadraflow.channels.api import router as api_router
from quadraflow.channels.api import setup as setup_api
from quadraflow.web.dashboard import create_dashboard_router, setup_dashboard

console = Console()


def setup_logging(log_level: str = "INFO"):
    """ロギングを設定する"""
    logging.basicConfig(
        level=getattr(logging, log_level.upper(), logging.INFO),
        format="%(message)s",
        handlers=[
            RichHandler(
                console=console,
                rich_tracebacks=True,
                show_path=False,
                markup=True,
            )
        ],
    )
    # uvicornのログを抑制
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


async def run_system(config_path: str, host: str, port: int):
    """メインシステムを起動する"""
    # 設定読み込み
    try:
        config = load_config(config_path)
    except FileNotFoundError as e:
        console.print(f"[red]設定ファイルエラー: {e}[/red]")
        sys.exit(1)

    setup_logging(config.log_level)
    logger = logging.getLogger(__name__)

    # バナー表示
    console.print(Panel.fit(
        "[bold cyan]QUADRAFLOW[/bold cyan] [purple]v0.1.0[/purple]\n"
        "[dim]Self-Autonomous AI Agent System[/dim]",
        border_style="cyan",
    ))

    # データディレクトリ作成
    data_dir = Path(config.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    # メッセージバス初期化
    message_bus = MessageBus(data_dir=str(data_dir))

    # エージェント初期化
    agents: dict[str, Agent] = {}
    for agent_config in config.agents:
        agent = Agent(
            config=agent_config,
            global_llm_config=config.llm,
            message_bus=message_bus,
            data_dir=str(data_dir),
        )
        agents[agent_config.id] = agent
        logger.info(f"エージェント初期化: {agent_config.id} ({agent_config.name})")

    # エージェント一覧表示
    table = Table(title="稼働エージェント", show_header=True, header_style="bold cyan")
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("名前")
    table.add_column("ハートビート")
    table.add_column("ツール")
    table.add_column("LLM")

    for agent in agents.values():
        llm = agent.config.llm or config.llm
        table.add_row(
            agent.id,
            agent.name,
            agent.config.heartbeat,
            ", ".join(agent.config.tools),
            f"{llm.provider}/{llm.model}",
        )

    console.print(table)

    # スケジューラー初期化
    scheduler = HeartbeatScheduler()
    for agent in agents.values():
        scheduler.register_agent(agent)
    scheduler.start()

    # FastAPIアプリ構築
    app = FastAPI(
        title="QUADRAFLOW API",
        version="0.1.0",
        description="Self-Autonomous AI Agent System",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # APIルーター登録
    setup_api(agents, scheduler)
    app.include_router(api_router)

    # ダッシュボード登録
    setup_dashboard(app, agents, scheduler)
    dashboard_router = create_dashboard_router()
    app.include_router(dashboard_router)

    # Telegram Bot 起動
    telegram_channel = None
    if config.telegram and config.telegram.enabled:
        from quadraflow.channels.telegram import TelegramChannel
        telegram_channel = TelegramChannel(config.telegram, agents)
        await telegram_channel.start()
        logger.info("Telegram Bot 起動完了")

    # uvicorn サーバー設定
    web_host = host or config.web.host
    web_port = port or config.web.port

    uvicorn_config = uvicorn.Config(
        app=app,
        host=web_host,
        port=web_port,
        log_level="warning",
        loop="asyncio",
    )
    server = uvicorn.Server(uvicorn_config)

    console.print(
        f"\n[bold green]システム起動完了![/bold green]\n"
        f"  Webダッシュボード: [cyan]http://{web_host}:{web_port}[/cyan]\n"
        f"  REST API:          [cyan]http://{web_host}:{web_port}/api/v1[/cyan]\n"
        f"  API docs:          [cyan]http://{web_host}:{web_port}/docs[/cyan]\n"
    )

    # シグナルハンドラ
    loop = asyncio.get_event_loop()

    def shutdown():
        scheduler.stop()
        if telegram_channel:
            asyncio.create_task(telegram_channel.stop())
        server.should_exit = True
        logger.info("シャットダウン完了")

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, shutdown)
        except (NotImplementedError, RuntimeError):
            # Windowsではシグナルハンドラが制限されるためスキップ
            pass

    await server.serve()


@click.group()
def cli():
    """QUADRAFLOW - Self-Autonomous AI Agent System"""
    pass


@cli.command()
@click.option("--config", "-c", default="quadraflow.yaml", help="設定ファイルのパス")
@click.option("--host", "-h", default="", help="サーバーホスト（デフォルト: 設定ファイルに従う）")
@click.option("--port", "-p", default=0, type=int, help="サーバーポート（デフォルト: 設定ファイルに従う）")
def start(config: str, host: str, port: int):
    """QUADRAFLOWシステムを起動する"""
    asyncio.run(run_system(config, host or None, port or None))


@cli.command()
@click.option("--config", "-c", default="quadraflow.yaml", help="設定ファイルのパス")
def validate(config: str):
    """設定ファイルを検証する"""
    try:
        cfg = load_config(config)
        console.print(f"[green]設定ファイル '{config}' は有効です[/green]")
        console.print(f"  LLM: {cfg.llm.provider}/{cfg.llm.model}")
        console.print(f"  エージェント数: {len(cfg.agents)}")
        for agent in cfg.agents:
            console.print(f"  - {agent.id}: {agent.name} (heartbeat: {agent.heartbeat})")
    except Exception as e:
        console.print(f"[red]設定エラー: {e}[/red]")
        sys.exit(1)


@cli.command()
def init():
    """サンプル設定ファイルを生成する"""
    sample = """# quadraflow.yaml - QUADRAFLOW設定ファイル

llm:
  provider: ollama
  model: gemma2:2b
  base_url: http://localhost:11434/v1

agents:
  - id: researcher
    name: "AI Researcher"
    heartbeat: 60m
    tools: [web_search, file_write]
    prompt: "最新のAI技術ニュースをリサーチして日本語でレポートを書く"

  - id: writer
    name: "Content Writer"
    heartbeat: 120m
    tools: [file_read, file_write, send_message]
    prompt: "researcherのレポートを読んでわかりやすいブログ記事を書く"

channels:
  telegram:
    token: "${TELEGRAM_BOT_TOKEN}"
    allowed_users: [123456789]

web:
  host: "0.0.0.0"
  port: 8765

data_dir: "./data"
log_level: "INFO"
"""
    path = Path("quadraflow.yaml")
    if path.exists():
        console.print("[yellow]quadraflow.yaml は既に存在します。上書きしませんでした。[/yellow]")
    else:
        path.write_text(sample, encoding="utf-8")
        console.print("[green]quadraflow.yaml を生成しました。設定を編集して `python main.py start` で起動してください。[/green]")


if __name__ == "__main__":
    cli()
