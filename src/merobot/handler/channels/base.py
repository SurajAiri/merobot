# channel: connect/disconnect, send, receive, (start and stop) typing, etc.

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from merobot.handler.message_bus import MessageBus

from merobot.handler.messages import InboundMessage, OutboundMessage


class BaseChannelHandler(ABC):
    name: str = "base"

    def __init__(
        self,
        bus: MessageBus,
        config: dict | None = None,
    ):
        self._running = False
        self._bus = bus
        self._config = config

    @abstractmethod
    async def connect(self):
        """Establish connection to the channel."""
        pass

    @abstractmethod
    async def disconnect(self):
        """Terminate connection to the channel."""
        pass

    @abstractmethod
    async def send_message(self, message: OutboundMessage):
        """Send a message to the channel."""
        pass

    @abstractmethod
    async def start_typing(self, chat_id: str):
        """Indicate that the bot is typing in a chat."""
        pass

    @abstractmethod
    async def stop_typing(self, chat_id: str):
        """Indicate that the bot has stopped typing in a chat."""
        pass

    async def __del__(self):
        """Ensure resources are cleaned up when the handler is destroyed."""
        await self.disconnect()

    async def _publish_inbound(
        self,
        channel: str,
        content: str,
        sender_id: str,
        chat_id: str,
        timestamp: float,
        media: list[str] = [],
        metadata: dict = {},
    ):
        """Publish an inbound message to the bus."""
        message = InboundMessage(
            channel=channel,
            content=content,
            sender_id=sender_id,
            chat_id=chat_id,
            timestamp=timestamp,
            media=media,
            metadata=metadata,
        )
        await self._bus.publish_inbound(message)

    @property
    def is_running(self) -> bool:
        """Return True if the handler is running, False otherwise."""
        return self._running
