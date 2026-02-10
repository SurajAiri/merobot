# channel: connect/disconnect, send, receive, (start and stop) typing, etc.

from abc import ABC, abstractmethod

from merobot.handler.messages import InboundMessage, OutboundMessage


class BaseChannelHandler(ABC):
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
    async def receive_message(self) -> InboundMessage:
        """Receive a message from the channel."""
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
