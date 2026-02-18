# MeroBot

A personal AI assistant built from scratch — an opinionated take on the [OpenClaw](https://github.com/) personal-assistant concept. MeroBot connects to Telegram (and future channels), talks to any OpenAI-compatible LLM, and can use tools like web search, code execution, file I/O, and more to get things done.

> **⚠️ Active Development** — The agent flow, tool set, and overall architecture are evolving and may change as requirements develop. Treat the current implementation as a working foundation, not a stable API.

---

## Features

- **Telegram integration** — Text messages, media (photo/document/audio/voice/video) with automatic download, and commands (`/start`, `/clear`).
- **Iterative tool-calling loop** — The LLM can chain up to 10 tool calls per message before replying, enabling multi-step reasoning.
- **8 built-in tools** — Date/time, file read/write (sandboxed), web search (DuckDuckGo), web scrape, Python code execution, SQLite database, and sub-agent delegation.
- **Pluggable LLM providers** — Swap between any OpenAI-compatible API (Groq, NVIDIA NIM, OpenRouter, vLLM, etc.) or LiteLLM (100+ providers) via config.
- **Message-bus architecture** — Channels and the agent loop are decoupled through async queues, making it easy to add new channels.
- **Workspace sandbox** — All file and code operations are confined to `~/.merobot/workspace` by default.

---

## Quick Start

### Prerequisites

- **Python ≥ 3.12**
- **[uv](https://docs.astral.sh/uv/)** (recommended) or pip
- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- At least one LLM provider API key (Groq, OpenAI, NVIDIA, etc.)

### Installation

```bash
# Clone the repository
git clone https://github.com/SurajAiri/merobot.git
cd merobot

# Install dependencies (uv)
uv sync

# Or with pip
pip install -e .
```

### Configuration

1. **Environment variables** — Copy the example and fill in your keys:

   ```bash
   cp .env.example .env
   ```

   ```env
   TELEGRAM_BOT_TOKEN=your_telegram_bot_token
   TELEGRAM_USER_ID=your_telegram_user_id
   GROQ_API_KEY=your_groq_api_key
   # OPENAI_API_KEY=your_openai_api_key    # optional
   ```

2. **Config file** — Edit `configs/config.json` to set your default provider, model, and enable/disable providers and channels:

   ```jsonc
   {
     "agent": {
       "workspace_path": "~/.merobot/workspace",
       "default": {
         "provider": "groq",
         "model": "openai/gpt-oss-120b",
         "temperature": 0.7,
         "max_tokens": 2048
       }
     },
     "providers": {
       "groq": { "enabled": true, "api_key": "GROQ_API_KEY", ... }
     },
     "channels": {
       "telegram": { "enabled": true, "env_token": "TELEGRAM_BOT_TOKEN", ... }
     }
   }
   ```

   > API keys in `config.json` are stored as `UPPER_SNAKE_CASE` env-var references (e.g. `"GROQ_API_KEY"`) and resolved automatically from `.env` / environment at runtime.

### Run

```bash
# Using uv
uv run python main.py

# Or directly
python main.py

# Or as a module
python -m merobot
```

MeroBot will connect to Telegram and start polling for messages. Send it a message to start chatting!

---

## Project Structure

```
merobot/
├── main.py                     # Entry point
├── configs/config.json         # Runtime configuration
├── .env.example                # Secret template
├── src/merobot/
│   ├── app.py                  # Application bootstrap & lifecycle
│   ├── config.py               # Typed config loader + secret resolution
│   ├── constants.py            # Compile-time constants
│   ├── agents/                 # Agent loop, context builder, tool registry
│   ├── handler/                # Communication handler, message bus, channels
│   ├── providers/llm/          # LLM provider abstraction + implementations
│   └── tools/                  # 8 built-in tools (file, web, code, db, etc.)
├── tests/                      # Unit tests
└── docs/architecture.md        # Detailed architecture documentation
```

For a detailed component breakdown, see [docs/architecture.md](docs/architecture.md).

---

## Tools

| Tool | What it does |
|------|-------------|
| `get_current_datetime` | Current date/time with timezone & format support |
| `file_read` | Read files from the sandboxed workspace |
| `file_write` | Write/append files in the workspace |
| `web_search` | Search the web via DuckDuckGo (no API key needed) |
| `web_scrape` | Fetch & extract text from any URL |
| `code_executor` | Run Python code in a subprocess sandbox |
| `sqlite_query` | Query a persistent SQLite database |
| `sub_agent` | Delegate tasks to a child LLM loop |

---

## Architecture Overview

```
User (Telegram)
  │
  ▼
TelegramChannelHandler ──► MessageBus (inbound queue)
                                  │
                                  ▼
                            AgentLoop
                              ├── Context Builder (system prompt + history)
                              ├── LLM Provider (Groq / OpenAI / LiteLLM / ...)
                              └── Tool Registry (8 tools)
                                  │
                                  ▼
                            MessageBus (outbound queue) ──► Telegram
```

See [docs/architecture.md](docs/architecture.md) for the full deep-dive.

---

## Development

```bash
# Install dev dependencies
uv sync --group dev

# Lint & format
uv run ruff check .
uv run ruff format .

# Run tests
uv run pytest tests/
```

---

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Make your changes
4. Run linting and tests
5. Submit a pull request

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

**Author**: [Suraj Airi](mailto:surajairi.ml@gmail.com)