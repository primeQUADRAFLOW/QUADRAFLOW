"""
YAML設定パーサー
quadraflow.yaml を読み込んでシステム設定に変換する
"""

import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class LLMConfig:
    provider: str = "ollama"
    model: str = "gemma2:2b"
    base_url: str = "http://localhost:11434/v1"
    api_key: str = "ollama"
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 120


@dataclass
class AgentConfig:
    id: str = ""
    name: str = ""
    heartbeat: str = "60m"
    tools: list = field(default_factory=list)
    prompt: str = ""
    llm: Optional[LLMConfig] = None  # エージェント個別LLM設定（省略時はグローバル設定を使用）
    enabled: bool = True
    workspace: str = "./workspace"


@dataclass
class TelegramConfig:
    token: str = ""
    allowed_users: list = field(default_factory=list)
    enabled: bool = False


@dataclass
class WebConfig:
    host: str = "0.0.0.0"
    port: int = 8765
    enabled: bool = True


@dataclass
class QuadraflowConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    agents: list = field(default_factory=list)
    telegram: Optional[TelegramConfig] = None
    web: WebConfig = field(default_factory=WebConfig)
    data_dir: str = "./data"
    log_level: str = "INFO"


def parse_heartbeat(heartbeat_str: str) -> int:
    """heartbeat文字列を秒数に変換する (例: '60m' -> 3600, '2h' -> 7200, '30s' -> 30)"""
    heartbeat_str = heartbeat_str.strip().lower()
    if heartbeat_str.endswith("s"):
        return int(heartbeat_str[:-1])
    elif heartbeat_str.endswith("m"):
        return int(heartbeat_str[:-1]) * 60
    elif heartbeat_str.endswith("h"):
        return int(heartbeat_str[:-1]) * 3600
    elif heartbeat_str.endswith("d"):
        return int(heartbeat_str[:-1]) * 86400
    else:
        return int(heartbeat_str) * 60  # デフォルトは分


def _resolve_env(value: str) -> str:
    """${ENV_VAR} 形式の環境変数を展開する"""
    if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
        env_key = value[2:-1]
        return os.environ.get(env_key, value)
    return value


def load_config(config_path: str = "quadraflow.yaml") -> QuadraflowConfig:
    """YAMLファイルを読み込んで QuadraflowConfig を返す"""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"設定ファイルが見つかりません: {config_path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    config = QuadraflowConfig()

    # LLM設定
    if "llm" in raw:
        llm_raw = raw["llm"]
        config.llm = LLMConfig(
            provider=llm_raw.get("provider", "ollama"),
            model=llm_raw.get("model", "gemma2:2b"),
            base_url=_resolve_env(llm_raw.get("base_url", "http://localhost:11434/v1")),
            api_key=_resolve_env(llm_raw.get("api_key", "ollama")),
            temperature=llm_raw.get("temperature", 0.7),
            max_tokens=llm_raw.get("max_tokens", 4096),
            timeout=llm_raw.get("timeout", 120),
        )
        # プロバイダー別のデフォルトbase_url
        if "base_url" not in llm_raw:
            config.llm.base_url = _get_default_base_url(config.llm.provider)

    # エージェント設定
    if "agents" in raw:
        for agent_raw in raw["agents"]:
            agent_llm = None
            if "llm" in agent_raw:
                al = agent_raw["llm"]
                agent_llm = LLMConfig(
                    provider=al.get("provider", config.llm.provider),
                    model=al.get("model", config.llm.model),
                    base_url=_resolve_env(al.get("base_url", config.llm.base_url)),
                    api_key=_resolve_env(al.get("api_key", config.llm.api_key)),
                    temperature=al.get("temperature", config.llm.temperature),
                    max_tokens=al.get("max_tokens", config.llm.max_tokens),
                )

            agent = AgentConfig(
                id=agent_raw.get("id", ""),
                name=agent_raw.get("name", agent_raw.get("id", "")),
                heartbeat=agent_raw.get("heartbeat", "60m"),
                tools=agent_raw.get("tools", []),
                prompt=agent_raw.get("prompt", ""),
                llm=agent_llm,
                enabled=agent_raw.get("enabled", True),
                workspace=agent_raw.get("workspace", "./workspace"),
            )
            config.agents.append(agent)

    # Telegram設定
    if "channels" in raw and "telegram" in raw["channels"]:
        tg_raw = raw["channels"]["telegram"]
        config.telegram = TelegramConfig(
            token=_resolve_env(tg_raw.get("token", "")),
            allowed_users=tg_raw.get("allowed_users", []),
            enabled=bool(tg_raw.get("token", "")),
        )

    # Web設定
    if "web" in raw:
        web_raw = raw["web"]
        config.web = WebConfig(
            host=web_raw.get("host", "0.0.0.0"),
            port=web_raw.get("port", 8765),
            enabled=web_raw.get("enabled", True),
        )

    # その他
    config.data_dir = raw.get("data_dir", "./data")
    config.log_level = raw.get("log_level", "INFO")

    return config


def _get_default_base_url(provider: str) -> str:
    """プロバイダー別デフォルトbase_url"""
    defaults = {
        "ollama": "http://localhost:11434/v1",
        "groq": "https://api.groq.com/openai/v1",
        "openai": "https://api.openai.com/v1",
        "anthropic": "https://api.anthropic.com/v1",
        "openrouter": "https://openrouter.ai/api/v1",
        "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    }
    return defaults.get(provider, "http://localhost:11434/v1")
