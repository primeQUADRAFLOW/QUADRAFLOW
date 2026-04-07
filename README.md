# QUADRAFLOW

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=flat-square&logo=python" alt="Python">
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" alt="License">
  <img src="https://img.shields.io/badge/LLM-Ollama%20%7C%20Groq%20%7C%20OpenAI%20%7C%20Gemini-orange?style=flat-square" alt="LLM">
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?style=flat-square&logo=docker" alt="Docker">
  <img src="https://img.shields.io/github/stars/primeQUADRAFLOW/quadraflow?style=flat-square" alt="Stars">
</p>

<p align="center">
  <strong>Self-autonomous AI agent system that runs from a single YAML file.</strong><br>
  No complex setup. No cloud required. Runs locally with Ollama or in the cloud with any OpenAI-compatible API.
</p>

---

> **"I just want my AI agents to work — not spend days configuring them."**
>
> QUADRAFLOW is the answer.

---

## Why QUADRAFLOW?

| Feature | AutoGPT | CrewAI | OpenClaw | **QUADRAFLOW** |
|---------|---------|--------|----------|----------------|
| Setup time | 30+ min | 20+ min | 15+ min | **< 2 min** |
| Config | Python code | Python code | JSON | **Single YAML** |
| Local LLM | Partial | Partial | No | **Full Ollama support** |
| Heartbeat (autonomous) | No | No | Yes | **Yes** |
| Agent-to-agent messaging | No | Yes | Yes | **Yes** |
| Web Dashboard | No | No | Yes | **Yes** |
| Telegram control | No | No | Yes | **Yes** |

---

## 30-Second Quickstart

```bash
# 1. Clone and install
git clone https://github.com/primeQUADRAFLOW/quadraflow.git
cd quadraflow
pip install -r requirements.txt

# 2. Generate config
python main.py init

# 3. Edit quadraflow.yaml (set your LLM provider and API key)

# 4. Start
python main.py start
```

Open **http://localhost:8765** — your agents are running.

---

## The KILLER FEATURE: One YAML to Rule Them All

```yaml
# quadraflow.yaml — this is ALL you need

llm:
  provider: ollama          # ollama | groq | openai | anthropic | gemini
  model: gemma2:2b
  base_url: http://localhost:11434/v1

agents:
  - id: researcher
    name: "AI Researcher"
    heartbeat: 60m          # runs every 60 minutes, autonomously
    tools: [web_search, file_write]
    prompt: "Research the latest AI news and write a report"

  - id: writer
    name: "Content Writer"
    heartbeat: 120m
    tools: [file_read, file_write, send_message]
    prompt: "Read researcher's reports and write blog articles"

channels:
  telegram:
    token: "${TELEGRAM_BOT_TOKEN}"
    allowed_users: [123456789]
```

That's it. **Agents run on their own schedule, communicate with each other, and you can monitor everything from the web dashboard.**

---

## Architecture

```
quadraflow.yaml
      │
      ▼
┌─────────────────────────────────────────────────┐
│                  QUADRAFLOW Core                 │
│                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐   │
│  │  Agent A │◄──►│ Message  │◄──►│  Agent B │   │
│  │(60m beat)│    │   Bus    │    │(120m beat)│  │
│  └────┬─────┘    └──────────┘    └────┬─────┘   │
│       │                               │          │
│  ┌────▼──────────────────────────────▼─────┐    │
│  │             LLM Abstraction Layer        │    │
│  │   Ollama │ Groq │ OpenAI │ Anthropic     │    │
│  └──────────────────────────────────────────┘   │
│                                                  │
│  ┌───────────┐  ┌──────────┐  ┌──────────────┐  │
│  │ Scheduler │  │  Memory  │  │    Tools     │  │
│  │(APSched.) │  │  (JSON)  │  │shell│web│file│  │
│  └───────────┘  └──────────┘  └──────────────┘  │
└──────────────────────────┬──────────────────────┘
                           │
            ┌──────────────┼──────────────┐
            ▼              ▼              ▼
     ┌─────────────┐ ┌──────────┐ ┌────────────┐
     │Web Dashboard│ │ REST API │ │  Telegram  │
     │  port:8765  │ │  /api/v1 │ │    Bot     │
     └─────────────┘ └──────────┘ └────────────┘
```

---

## Features

### Autonomous Heartbeat
Agents wake up on their own schedule — every 30 minutes, every hour, daily — and do their work without any human intervention.

### Agent-to-Agent Messaging
Agents communicate via an inbox/outbox system. A researcher can hand off findings to a writer, which hands off to a publisher.

### Universal LLM Support
Switch between providers by changing two lines in YAML. Ollama (local, private), Groq (fast, free tier), OpenAI, Anthropic, Gemini, OpenRouter — all supported via the OpenAI-compatible API.

### Built-in Tools
| Tool | Description |
|------|-------------|
| `shell` | Execute shell commands (with 30s timeout) |
| `file_read` | Read any file |
| `file_write` | Write files (auto-create directories) |
| `web_fetch` | Fetch and extract text from URLs |
| `web_search` | Google search results |
| `send_message` | Send messages to other agents |

### Web Dashboard
Real-time monitoring of all agents — status, last run, next scheduled run, execution logs, and agent memory. Dark theme. No JavaScript frameworks.

### Telegram Control
`/status`, `/run [agent_id]`, `/ask [agent_id] [message]` — control your agents from anywhere.

### Agent Memory
Each agent has persistent JSON-based memory. Past work is automatically included in each heartbeat's system prompt, so agents remember what they've done.

---

## Docker Quickstart

```bash
# Copy the example config
cp examples/quadraflow.yaml ./quadraflow.yaml
# Edit the config with your settings

# Start with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f quadraflow
```

---

## REST API

```bash
# List all agents
GET /api/v1/agents

# Run an agent immediately
POST /api/v1/agents/{agent_id}/trigger

# Send a message to an agent (synchronous response)
POST /api/v1/agents/{agent_id}/message
{"content": "What have you been working on?"}

# Get execution logs
GET /api/v1/agents/{agent_id}/logs

# Get agent memory
GET /api/v1/agents/{agent_id}/memory

# Health check
GET /api/v1/health
```

Full API docs: **http://localhost:8765/docs**

---

## Local LLM with Ollama

```bash
# Install Ollama: https://ollama.com
ollama pull gemma2:2b       # lightweight, 1.6GB
ollama pull llama3.1:8b     # powerful, 4.7GB
ollama pull qwen2.5:14b     # multilingual, 9GB

# Use in quadraflow.yaml:
# llm:
#   provider: ollama
#   model: gemma2:2b
#   base_url: http://localhost:11434/v1
```

Your data never leaves your machine.

---

## Configuration Reference

```yaml
llm:
  provider: ollama | groq | openai | anthropic | gemini | openrouter
  model: model-name
  base_url: http://...          # optional, auto-detected per provider
  api_key: ${ENV_VAR}           # env var expansion supported
  temperature: 0.7
  max_tokens: 4096
  timeout: 120

agents:
  - id: unique-id               # required
    name: "Display Name"
    heartbeat: 60m              # 30s | 5m | 2h | 1d
    tools: [shell, file_read, file_write, web_fetch, web_search, send_message]
    prompt: "What this agent does..."
    enabled: true
    workspace: ./workspace      # agent's working directory
    llm:                        # optional: override global LLM per agent
      provider: openai
      model: gpt-4o-mini

channels:
  telegram:
    token: ${TELEGRAM_BOT_TOKEN}
    allowed_users: [user_id_1, user_id_2]

web:
  host: "0.0.0.0"
  port: 8765
  enabled: true

data_dir: ./data
log_level: INFO | DEBUG | WARNING
```

---

## Roadmap

- [ ] **v0.2** — Plugin system (custom tools as Python files)
- [ ] **v0.3** — Multi-agent orchestration (agent pipelines)
- [ ] **v0.4** — Vector memory (semantic search over past work)
- [ ] **v0.5** — Web UI agent editor (no YAML needed)
- [ ] **v1.0** — Stable release, Windows GUI installer

---

## Contributing

Contributions are welcome! This project is in active development.

```bash
# Fork and clone
git clone https://github.com/YOUR_USERNAME/quadraflow.git
cd quadraflow

# Create a virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run
python main.py start --config examples/quadraflow_local.yaml
```

**Ways to contribute:**
- Add new tools (PRs welcome)
- Report bugs via GitHub Issues
- Share your agent configurations in Discussions
- Star the repo if you find it useful

---

## License

MIT License — free to use, modify, and distribute.

---

## Acknowledgments

Inspired by [OpenClaw](https://github.com/openclaw/openclaw), AutoGPT, and the open-source AI agent community.

Built with: FastAPI, APScheduler, OpenAI Python SDK, python-telegram-bot, BeautifulSoup4, Rich

---

<p align="center">
  <strong>If QUADRAFLOW saved you time, please give it a star!</strong>
</p>
