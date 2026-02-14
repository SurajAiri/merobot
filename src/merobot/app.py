"""Application bootstrap — creates shared components and runs everything.

This is the single place that wires the CommunicationHandler and AgentLoop
together through a shared MessageBus, then runs them concurrently.
"""

from __future__ import annotations

import asyncio
import signal

from loguru import logger

from merobot.agents.loop import AgentLoop
from merobot.config import get_config
from merobot.handler.handler import CommunicationHandler
from merobot.handler.message_bus import MessageBus
from merobot.handler.session.session import SessionManager


class Application:
    """Top-level application that owns all major components.

    Architecture:
        MessageBus (shared)
            ├── CommunicationHandler  (channels → inbound queue, outbound queue → channels)
            └── AgentLoop             (inbound queue → LLM + tools → outbound queue)
    """

    def __init__(self) -> None:
        self._config = get_config()

        # Shared message bus — the single bridge between handler and agent
        self.message_bus = MessageBus()

        # Session manager — conversation history per chat
        self.session_manager = SessionManager(max_history=50)

        # Communication handler — owns channels, publishes inbound, dispatches outbound
        CommunicationHandler.reset()  # ensure clean state
        self.handler = CommunicationHandler.get_instance(
            message_bus=self.message_bus
        )

        # Agent loop — consumes inbound, calls LLM, publishes outbound
        self.agent_loop = AgentLoop(
            message_bus=self.message_bus,
            session_manager=self.session_manager,
        )

        self._shutdown_event = asyncio.Event()

    async def start(self) -> None:
        """Start all components and run until shutdown signal."""
        logger.info("MeroBot starting up...")

        # Install signal handlers for graceful shutdown
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._signal_handler)

        # Start communication handler (connects channels + starts outbound dispatch)
        await self.handler.start()

        # Run the agent loop concurrently
        agent_task = asyncio.create_task(
            self.agent_loop.run(),
            name="agent-loop",
        )

        logger.info("MeroBot is running. Press Ctrl+C to stop.")

        # Wait for shutdown signal
        await self._shutdown_event.wait()

        # Graceful shutdown
        logger.info("Shutting down...")
        agent_task.cancel()
        try:
            await agent_task
        except asyncio.CancelledError:
            pass

        await self.handler.stop()
        logger.info("MeroBot stopped.")

    def _signal_handler(self) -> None:
        """Handle SIGINT/SIGTERM by setting the shutdown event."""
        logger.info("Shutdown signal received")
        self._shutdown_event.set()

    def run(self) -> None:
        """Synchronous entry point — creates event loop and runs the app."""
        asyncio.run(self.start())
