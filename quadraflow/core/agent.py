"""
Agentクラス
ハートビート実行・ツール呼び出し・メモリ管理・メッセージ処理を担う
"""

import json
import logging
import re
import asyncio
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from quadraflow.config import AgentConfig, LLMConfig
from quadraflow.core.llm import LLMClient
from quadraflow.core.memory import Memory
from quadraflow.core.tools import ToolRegistry, ToolResult

if TYPE_CHECKING:
    from quadraflow.core.messaging import MessageBus

logger = logging.getLogger(__name__)

# ツール呼び出しのJSONを抽出するパターン
TOOL_CALL_PATTERN = re.compile(
    r'\{[^{}]*"tool"\s*:\s*"([^"]+)"[^{}]*"params"\s*:\s*(\{[^{}]*\})[^{}]*\}',
    re.DOTALL,
)

SYSTEM_PROMPT_TEMPLATE = """あなたは自律AIエージェントです。

## アイデンティティ
- ID: {agent_id}
- 名前: {agent_name}
- 役割: {agent_prompt}

## 利用可能なツール
ツールを使う場合は以下のJSON形式で記述してください。1メッセージに複数のツール呼び出しが可能です。

```json
{{"tool": "ツール名", "params": {{"パラメータ名": "値"}}}}
```

利用可能なツール:
{tool_descriptions}

## 過去のメモリ（最近の記録）
{memory_summary}

## ルール
- ツールを使って実際に作業を完了させてください
- 結果をメモリに記録するためのサマリーを最後に書いてください（「[記録]」で始める）
- 日本語で回答してください
"""


class AgentStatus:
    IDLE = "idle"
    RUNNING = "running"
    ERROR = "error"
    DISABLED = "disabled"


class ExecutionLog:
    """エージェント実行ログの1エントリ"""

    def __init__(self, trigger: str, agent_id: str):
        self.agent_id = agent_id
        self.trigger = trigger
        self.started_at = datetime.now().isoformat()
        self.finished_at: Optional[str] = None
        self.success: Optional[bool] = None
        self.summary: str = ""
        self.tool_calls: list[dict] = []
        self.error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "agent_id": self.agent_id,
            "trigger": self.trigger,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "success": self.success,
            "summary": self.summary,
            "tool_calls": self.tool_calls,
            "error": self.error,
        }


class Agent:
    """自律AIエージェント"""

    def __init__(
        self,
        config: AgentConfig,
        global_llm_config: LLMConfig,
        message_bus: "MessageBus",
        data_dir: str = "./data",
    ):
        self.config = config
        self.id = config.id
        self.name = config.name

        # エージェント個別LLM設定があればそれを使用、なければグローバル設定
        llm_config = config.llm if config.llm else global_llm_config
        self.llm = LLMClient(llm_config)

        self.message_bus = message_bus
        self.memory = Memory(agent_id=self.id, data_dir=data_dir)
        self.tools = ToolRegistry(
            workspace=config.workspace,
            message_bus=message_bus,
            agent_id=self.id,
        )

        self.status = AgentStatus.IDLE if config.enabled else AgentStatus.DISABLED
        self.last_run: Optional[str] = None
        self.next_run: Optional[str] = None
        self.execution_logs: list[ExecutionLog] = []

        # 外部通知コールバック（WebSocketやTelegramへの通知用）
        self._on_log_callbacks: list = []

    def add_log_callback(self, callback):
        """実行ログ完了時に呼ばれるコールバックを登録する"""
        self._on_log_callbacks.append(callback)

    async def _build_system_prompt(self) -> str:
        """システムプロンプトを構築する"""
        memory_summary = await self.memory.get_summary()
        tool_descriptions = self.tools.get_tool_descriptions(self.config.tools)

        return SYSTEM_PROMPT_TEMPLATE.format(
            agent_id=self.id,
            agent_name=self.name,
            agent_prompt=self.config.prompt,
            tool_descriptions=tool_descriptions,
            memory_summary=memory_summary,
        )

    async def _parse_and_execute_tools(
        self, response_text: str, log: ExecutionLog, allowed_tools: list[str]
    ) -> str:
        """レスポンスからツール呼び出しを抽出して実行する"""
        # コードブロック内のJSONを探す
        tool_calls = []

        # ```json ... ``` パターン
        code_block_pattern = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
        for match in code_block_pattern.finditer(response_text):
            try:
                data = json.loads(match.group(1))
                if "tool" in data and "params" in data:
                    tool_calls.append(data)
            except json.JSONDecodeError:
                pass

        # インラインJSONパターン
        if not tool_calls:
            for match in TOOL_CALL_PATTERN.finditer(response_text):
                try:
                    full_json = match.group(0)
                    data = json.loads(full_json)
                    if "tool" in data and "params" in data:
                        tool_calls.append(data)
                except json.JSONDecodeError:
                    pass

        if not tool_calls:
            return response_text

        tool_results = []
        for call in tool_calls:
            tool_name = call.get("tool", "")
            params = call.get("params", {})

            logger.info(f"ツール実行 ({self.id}): {tool_name}({params})")
            result = await self.tools.execute(tool_name, params, allowed_tools)

            log.tool_calls.append({
                "tool": tool_name,
                "params": params,
                "success": result.success,
                "output": result.output[:500],
            })

            tool_results.append(f"[{tool_name}の結果]\n{result}")

        # ツール結果をLLMに渡してまとめさせる
        return "\n\n".join(tool_results)

    async def run(self, trigger: str = "heartbeat", user_message: Optional[str] = None) -> str:
        """エージェントを実行する"""
        if self.status == AgentStatus.DISABLED:
            return "エージェントは無効です"

        self.status = AgentStatus.RUNNING
        log = ExecutionLog(trigger=trigger, agent_id=self.id)
        self.execution_logs.append(log)
        # 最大100件
        if len(self.execution_logs) > 100:
            self.execution_logs = self.execution_logs[-100:]

        try:
            system_prompt = await self._build_system_prompt()

            # 未読メッセージを確認
            unread_messages = await self.message_bus.get_unread(self.id)
            inbox_context = ""
            if unread_messages:
                inbox_context = "\n\n## 未読メッセージ\n"
                for msg in unread_messages:
                    inbox_context += f"[{msg.from_agent}から]: {msg.content}\n"

            # ユーザーメッセージまたはハートビートプロンプトを設定
            if user_message:
                human_message = user_message + inbox_context
            else:
                human_message = (
                    f"ハートビート実行時刻: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                    f"{inbox_context}\n"
                    f"あなたの役割に従って自律的に作業を実行してください。"
                )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": human_message},
            ]

            # LLM呼び出し（最大3ラウンドのツール実行ループ）
            final_response = ""
            for round_num in range(3):
                response = await self.llm.complete(messages)

                # ツール実行
                tool_output = await self._parse_and_execute_tools(
                    response, log, self.config.tools
                )

                if tool_output == response:
                    # ツールが実行されなかった場合はループ終了
                    final_response = response
                    break
                else:
                    # ツール結果をメッセージに追加して再度LLMに渡す
                    messages.append({"role": "assistant", "content": response})
                    messages.append({"role": "user", "content": f"ツール実行結果:\n{tool_output}\n\n上記の結果を元に作業を完了させてください。"})
                    final_response = tool_output

            # [記録]で始まる部分をメモリに保存
            if "[記録]" in final_response:
                memory_content = final_response.split("[記録]", 1)[1].strip()
                await self.memory.add(memory_content, source=trigger)
            elif final_response:
                # 記録タグがなくても要約をメモリに保存
                summary = final_response[:500]
                await self.memory.add(summary, source=trigger)

            log.success = True
            log.summary = final_response[:300]
            log.finished_at = datetime.now().isoformat()
            self.last_run = log.finished_at

            logger.info(f"エージェント実行完了 ({self.id}): {log.summary[:100]}")

        except Exception as e:
            logger.exception(f"エージェント実行エラー ({self.id}): {e}")
            log.success = False
            log.error = str(e)
            log.finished_at = datetime.now().isoformat()
            final_response = f"エラーが発生しました: {e}"
            self.status = AgentStatus.ERROR

        finally:
            if self.status == AgentStatus.RUNNING:
                self.status = AgentStatus.IDLE

            # コールバック通知
            for callback in self._on_log_callbacks:
                try:
                    await callback(log)
                except Exception:
                    pass

        return final_response

    def get_status_dict(self) -> dict:
        """ダッシュボード用ステータス情報を返す"""
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "heartbeat": self.config.heartbeat,
            "tools": self.config.tools,
            "last_run": self.last_run,
            "next_run": self.next_run,
            "enabled": self.config.enabled,
            "recent_logs": [log.to_dict() for log in self.execution_logs[-5:]],
        }
