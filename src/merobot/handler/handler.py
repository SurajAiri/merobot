# roles: connection with channels, message transport, session with message history management. # noqa:E501

import asyncio

from loguru import logger

from merobot.config import get_config
from merobot.handler.channels.base import BaseChannelHandler
from merobot.handler.channels.telegram import TelegramChannelHandler
from merobot.handler.message_bus import MessageBus


class CommunicationHandler:
    """Singleton orchestrator that owns channels, the MessageBus, and sessions.

    Responsibilities:
        1. **Channel connections** — instantiate and connect/disconnect channels.
        2. **Message transport** — owns the MessageBus and passes it to channels
           so they can publish inbound messages directly. Subscribes each
           channel's send_message for outbound dispatch.
        3. **Session management** — maintain per-chat session state (TBD).
    """

    _instance: "CommunicationHandler | None" = None

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    @classmethod
    def get_instance(
        cls, message_bus: MessageBus | None = None
    ) -> "CommunicationHandler":
        """Return the singleton CommunicationHandler, creating it on first call."""
        if cls._instance is None:
            cls._instance = cls(message_bus=message_bus)
        return cls._instance

    @classmethod
    def reset(cls):
        """Reset the singleton (useful for testing)."""
        cls._instance = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def __init__(self, message_bus: MessageBus | None = None):
        self._config = get_config()
        self.message_bus = message_bus or MessageBus()
        self.channels: dict[str, BaseChannelHandler] = {}
        self.sessions: dict[str, dict] = {}
        self._dispatch_task: asyncio.Task | None = None

        self._register_channels()

    def _register_channels(self):
        """Parse enabled channels from config and instantiate handlers.

        Each channel receives the shared MessageBus so it can publish
        inbound messages directly via ``_publish_inbound()``.
        """
        for name, channel_cfg in self._config.get_enabled_channels().items():
            if channel_cfg.type == "telegram":
                if not channel_cfg.token:
                    logger.warning(
                        f"Telegram token not resolved for channel '{name}'. "
                        f"Check your .env file. Skipping."
                    )
                    continue
                handler = TelegramChannelHandler(
                    bus=self.message_bus,
                    token=channel_cfg.token,
                    config=channel_cfg.extra,
                )
                self.channels[name] = handler
                logger.info(f"Registered channel: {name} (type={channel_cfg.type})")
            else:
                logger.warning(f"Unknown channel type: {channel_cfg.type}")

    async def start(self):
        """Connect all channels and start outbound dispatch."""
        for name, channel in self.channels.items():
            await channel.connect()
            logger.info(f"Channel '{name}' connected")

            await self.message_bus.subscribe_outbound(
                name,
                channel.send_message,
            )

        self._dispatch_task = asyncio.create_task(
            self.message_bus.dispatch_outbound(),
            name="bus-outbound-dispatch",
        )

        logger.info("CommunicationHandler started")

    async def stop(self):
        """Disconnect channels, cancel background tasks, stop bus."""
        self.message_bus.stop()
        if self._dispatch_task is not None:
            self._dispatch_task.cancel()
            self._dispatch_task = None

        for name, channel in self.channels.items():
            await channel.disconnect()
            logger.info(f"Channel '{name}' disconnected")

        logger.info("CommunicationHandler stopped")
