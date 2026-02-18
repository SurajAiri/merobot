# MeroBot — Architecture

> **Source of truth**: This document is derived from the actual implemented code.
> If the code and this document diverge, the code is correct.

---

## High-Level Overview

MeroBot is an async-first personal AI assistant that connects communication channels (currently Telegram) to large-language-model backends via a message-bus architecture. The agent loop consumes inbound user messages, runs an iterative LLM + tool-calling cycle, and publishes responses back through the same bus.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Application (app.py)                        │
│                                                                     │
│   ┌──────────────┐      ┌────────────┐      ┌──────────────────┐   │
│   │  Channels    │      │            │      │   Agent Loop     │   │
│   │ ┌──────────┐ │ push │  Message   │ pull │ ┌──────────────┐ │   │
│   │ │ Telegram │─┼─────►│    Bus     │─────►│ │ LLM Provider │ │   │
│   │ └──────────┘ │      │            │      │ └──────┬───────┘ │   │
│   │              │◄─────│ inbound /  │◄─────│        │         │   │
│   │ (future:     │ recv │ outbound   │ pub  │ ┌──────▼───────┐ │   │
│   │  Discord,    │      │  queues    │      │ │ Tool Registry│ │   │
│   │  WhatsApp,   │      └────────────┘      │ │ (8 tools)    │ │   │
│   │  CLI …)      │                          │ └──────────────┘ │   │
│   └──────────────┘                          └──────────────────┘   │
│                                                                     │
│   ┌──────────────┐      ┌────────────────┐                         │
│   │ Config       │      │ Session Mgr    │                         │
│   │ (config.json │      │ (in-memory     │                         │
│   │  + .env)     │      │  per-chat      │                         │
│   └──────────────┘      │  history)      │                         │
│                          └────────────────┘                         │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Project Structure (Actual)

```
merobot/
├── main.py                        # Entrypoint — calls Application.run()
├── pyproject.toml                 # Project metadata & dependencies (uv/pip)
├── ruff.toml                      # Linting & formatting rules
├── configs/
│   └── config.json                # Runtime config (providers, channels, agent defaults)
├── .env.example                   # Template for environment secrets
│
├── src/merobot/
│   ├── __init__.py                # Package root — exposes main()
│   ├── __main__.py                # `python -m merobot` support
│   ├── app.py                     # Application bootstrap & lifecycle
│   ├── config.py                  # Typed config loader with secret resolution
│   ├── constants.py               # Compile-time constants (limits, defaults)
│   │
│   ├── agents/                    # ── Agent Layer ──
│   │   ├── loop.py                # Core agent loop (message → LLM → tools → response)
│   │   ├── context.py             # System prompt + history assembly
│   │   ├── tools.py               # ToolRegistry (register / validate / execute)
│   │   └── memory.py              # (placeholder — future persistent memory)
│   │
│   ├── handler/                   # ── Communication Layer ──
│   │   ├── handler.py             # CommunicationHandler singleton (orchestrator)
│   │   ├── message_bus.py         # Async inbound/outbound queues + dispatch
│   │   ├── messages.py            # InboundMessage / OutboundMessage dataclasses
│   │   ├── channels/
│   │   │   ├── base.py            # BaseChannelHandler ABC
│   │   │   └── telegram.py        # Telegram polling handler (text + media + commands)
│   │   └── session/
│   │       └── session.py         # In-memory per-chat history (SessionManager)
│   │
│   ├── providers/                 # ── LLM Provider Layer ──
│   │   ├── llm/
│   │   │   ├── base.py            # BaseLLMProvider ABC + LLMResponse / ToolCallRequests
│   │   │   ├── llmapi_provider.py # Direct HTTP (OpenAI-compatible) provider (active)
│   │   │   └── litellm_provider.py# LiteLLM multi-provider backend (available)
│   │   └── asr/                   # (placeholder — future ASR providers)
│   │
│   ├── tools/                     # ── Tool Layer ──
│   │   ├── base.py                # BaseTool ABC + JSON Schema validation
│   │   ├── date_time.py           # get_current_datetime
│   │   ├── file_ops.py            # file_read / file_write (sandboxed)
│   │   ├── web_search.py          # web_search (DuckDuckGo HTML)
│   │   ├── web_scrape.py          # web_scrape (httpx + BeautifulSoup)
│   │   ├── code_executor.py       # code_executor (subprocess sandbox)
│   │   ├── query_db.py            # sqlite_query (persistent SQLite in workspace)
│   │   └── sub_agent.py           # sub_agent (delegates to a child LLM loop)
│   │
│   └── utils/                     # Shared utilities (currently empty)
│
├── tests/
│   ├── test_agent_loop.py         # Agent loop unit tests
│   ├── test_telegram_handler.py   # Telegram handler unit tests
│   └── test_tools_registory.py    # Tool registry tests
│
├── scripts/                       # Automation scripts
├── docs/
│   └── architecture.md            # This file
└── logs/                          # Runtime log output
```

---

## Component Deep-Dive

### 1. Application Bootstrap — `app.py`

`Application` is the top-level wiring class. It:

1. Loads the singleton `AppConfig` via `get_config()`.
2. Creates a shared `MessageBus`.
3. Creates a `SessionManager` (in-memory, 50-message window per chat).
4. Instantiates `CommunicationHandler` (singleton) with the bus.
5. Instantiates the active `LlmApiProvider` from the configured provider.
6. Creates `AgentLoop` with bus, session manager, and LLM provider.
7. Starts everything concurrently under `asyncio.run()`.
8. Handles `SIGINT` / `SIGTERM` for graceful shutdown.

### 2. Configuration — `config.py` + `constants.py`

| Concern | File | Description |
|---------|------|-------------|
| **Runtime config** | `configs/config.json` | Providers, channels, agent defaults. Loaded once; cached as singleton `AppConfig`. |
| **Secrets** | `.env` → `os.environ` | API keys are stored as `UPPER_SNAKE_CASE` refs in config.json and resolved from env vars at load time. Single hook `resolve_secret()` for future vault integration. |
| **Compile-time constants** | `constants.py` | File size limits, timeouts, default model, DB filename, etc. Change only on code updates. |

**Config dataclasses** (all frozen):
- `AppConfig` → `AgentConfig` + `dict[str, ProviderConfig]` + `dict[str, ChannelConfig]`
- `AgentDefaults` — provider, model, temperature, max_tokens

### 3. Communication Handler — `handler/`

#### Message Flow

```
Telegram ──► TelegramChannelHandler._handle_text/media()
                  │
                  ▼
             BaseChannelHandler._publish_inbound()
                  │
                  ▼
             MessageBus.inbound queue  ◄─── (consumed by AgentLoop.run())
                  │
                  ▼
             AgentLoop._process_message()
                  │
                  ▼
             AgentLoop._send_response()
                  │
                  ▼
             MessageBus.outbound queue
                  │
                  ▼
             MessageBus.dispatch_outbound() ──► subscriber callbacks
                  │
                  ▼
             TelegramChannelHandler.send_message()
```

#### Key Classes

| Class | Role |
|-------|------|
| `MessageBus` | Two async queues (inbound + outbound) + subscriber-based outbound dispatch. |
| `InboundMessage` / `OutboundMessage` | Dataclasses carrying channel-agnostic message data (content, sender, chat_id, media, metadata). |
| `CommunicationHandler` | Singleton orchestrator — instantiates channel handlers, wires them to the bus, manages lifecycle. |
| `BaseChannelHandler` | ABC defining `connect`, `disconnect`, `send_message`, `start_typing`, `stop_typing`, and the `_publish_inbound` helper. |
| `TelegramChannelHandler` | Concrete handler — uses `python-telegram-bot` in polling mode. Handles text, media (photo/document/audio/voice/video download to workspace), and commands (`/start`, `/clear`). |
| `SessionManager` | In-memory per-chat message history with FIFO trimming (configurable `max_history`). Stores OpenAI-format message dicts. |

### 4. Agent Loop — `agents/loop.py`

The heart of the system. For each inbound message:

1. **Context assembly** — `AgentContextBuilder.build()` prepends a system prompt and appends session history.
2. **LLM call loop** (up to `MAX_TOOL_ITERATIONS = 10`):
   - Call `llm.generate_response()` with messages + tool schemas.
   - If response has no tool calls → done, return text.
   - Otherwise execute each tool via `ToolRegistry.execute()`, append results as `tool` messages, and loop.
3. **Session bookkeeping** — all messages (user, assistant, tool) are persisted in `SessionManager`.
4. **Response publishing** — wraps the final text in an `OutboundMessage` and publishes to the bus.

Special handling: `/clear` command bypasses LLM and resets the chat session.

### 5. Tool System — `tools/`

#### BaseTool Contract

Every tool extends `BaseTool` (ABC) and must provide:
- `name` — unique string identifier used in LLM function-calling
- `description` — human-readable, shown to the LLM
- `parameters` — JSON Schema (Draft 7) for parameter validation
- `execute(**kwargs) → str` — async execution returning a string result

`BaseTool` provides:
- `validate_params()` — recursive JSON Schema validation
- `to_schema()` — converts to OpenAI-compatible function-calling format

#### ToolRegistry

Central registry (`agents/tools.py`) that manages tool lifecycle:
- `register(tool)` / `unregister(name)`
- `get_definitions()` — returns schemas for all registered tools
- `execute(name, params)` — validates params, runs tool, catches exceptions

#### Registered Tools

| Tool | Function Name | Description |
|------|--------------|-------------|
| `DateTimeTool` | `get_current_datetime` | Current date/time with IANA timezone + strftime format support |
| `FileReadTool` | `file_read` | Read files within the sandboxed workspace (1 MB limit). Falls back to directory listing. |
| `FileWriteTool` | `file_write` | Write/append files within the workspace (5 MB limit). Auto-creates directories. |
| `WebSearchTool` | `web_search` | DuckDuckGo HTML scraping — no API key needed. Returns titles, URLs, snippets. |
| `WebScrapeTool` | `web_scrape` | Fetch & extract readable text from any URL (httpx + BeautifulSoup). CSS selector support. |
| `CodeExecutorTool` | `code_executor` | Run Python code in a subprocess with timeout (30s default) and output limits. |
| `SQLiteQueryTool` | `sqlite_query` | Execute SQL against a persistent SQLite database in the workspace. Formatted table output. |
| `SubAgentTool` | `sub_agent` | Spawn a child LLM loop (5 iterations max) for delegated tasks. Has access to all tools except itself (prevents recursion). |

#### Sandbox Security

File operations (`file_read`, `file_write`) are sandboxed to the configured workspace directory (`~/.merobot/workspace` by default). Path traversal is blocked via `Path.resolve().relative_to(sandbox)`.

### 6. LLM Providers — `providers/llm/`

#### BaseLLMProvider

Abstract interface with a single method:
```python
async def generate_response(
    model, messages, tools, max_tokens, temperature
) → LLMResponse
```

**Response types:**
- `LLMResponse` — content (text), tool_calls, usage stats, raw_response
- `ToolCallRequests` — id, name, arguments (parsed dict)

#### Implemented Providers

| Provider | Class | How it works |
|----------|-------|-------------|
| **LlmApiProvider** (active) | `llmapi_provider.py` | Direct HTTP POST to any OpenAI-compatible `/chat/completions` endpoint via `httpx`. Works with Groq, OpenRouter, NVIDIA NIM, vLLM, etc. |
| **LiteLLMProvider** (available) | `litellm_provider.py` | Uses the `litellm` library's `acompletion()` for 100+ provider support. Currently commented out in imports but fully implemented. |

Both providers normalize responses into the same `LLMResponse` format, making them interchangeable.

---

## Data Flow Summary

```
User (Telegram)
    │
    ▼
TelegramChannelHandler     ←── python-telegram-bot polling
    │ _publish_inbound()
    ▼
MessageBus.inbound         ←── asyncio.Queue
    │ consume_inbound()
    ▼
AgentLoop.run()
    │
    ├─► AgentContextBuilder.build()  →  [system_prompt, ...history]
    │
    ├─► LLM.generate_response()      →  LLMResponse
    │       │
    │       ├── has text only?  →  return as final answer
    │       │
    │       └── has tool_calls?
    │               │
    │               ▼
    │           ToolRegistry.execute(name, args)
    │               │
    │               ▼
    │           append tool results → loop back to LLM
    │
    ▼
MessageBus.outbound        ←── asyncio.Queue
    │ dispatch_outbound()
    ▼
TelegramChannelHandler.send_message()
    │
    ▼
User (Telegram)
```

---

## Key Design Decisions

1. **Message Bus decoupling** — Channels and the agent loop never directly reference each other. Everything flows through `MessageBus`, making it trivial to add new channels.

2. **Iterative tool loop** — The agent loop supports multi-step reasoning. The LLM can chain tool calls (up to 10 iterations) before producing a final answer.

3. **Sub-agent delegation** — Complex tasks can be delegated to a child LLM loop (`SubAgentTool`), which runs with its own message thread and a reduced iteration cap (5). Recursion is prevented by excluding `sub_agent` from the child's tool set.

4. **Provider abstraction** — `BaseLLMProvider` ensures any OpenAI-compatible backend can be swapped in via config, with zero code changes to the agent loop.

5. **Workspace sandbox** — All file and code operations are confined to `~/.merobot/workspace`. Path escapes are rejected.

6. **In-memory sessions** — Chat history lives in `SessionManager` with a configurable FIFO window (`max_history=50`). No persistence across restarts (by design for now).

7. **Secret resolution hook** — `config.py` has a single `resolve_secret()` function that currently reads env vars but is designed as the one place to swap in a vault (HashiCorp, AWS Secrets Manager, etc.).

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `python-telegram-bot[ext]` ≥21.0 | Telegram Bot API integration |
| `httpx` ≥0.27 | Async HTTP client (LLM API calls, web scrape/search) |
| `beautifulsoup4` ≥4.12 | HTML parsing for web scraping |
| `litellm` ≥1.81 | Multi-provider LLM abstraction (optional backend) |
| `loguru` | Structured logging |
| `python-dotenv` ≥1.2 | `.env` file loading |
| `jsonschema` ≥4.0 | Tool parameter validation |
| `tzdata` ≥2025.3 | Timezone database for `DateTimeTool` |

Dev: `ruff` for linting/formatting.

---

## Future Considerations

- **Persistent memory** — `agents/memory.py` is a placeholder for future long-term memory (vector DB, knowledge graphs).
- **ASR providers** — `providers/asr/` directory exists for future speech-to-text integration.
- **Additional channels** — The architecture supports Discord, WhatsApp, CLI, etc. via new `BaseChannelHandler` subclasses.
- **Cron / scheduling** — `tools/cron.py` and `tools/email.py` exist as empty placeholders.
- **Streaming responses** — Current flow is request-response; streaming can be layered onto the bus.

> **Note**: The agent flow, tool set, and overall architecture are actively evolving and may change as requirements develop.