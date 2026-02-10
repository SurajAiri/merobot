import asyncio
from asyncio import Queue
from collections.abc import Awaitable, Callable

from loguru import logger

from .messages import InboundMessage, OutboundMessage


class MessageBus:
    def __init__(self, config: dict | None = None):
        self.inbound: Queue[InboundMessage] = Queue()
        self.outbound: Queue[OutboundMessage] = Queue()
        self._outbound_subscribers: dict[
            str, list[Callable[[OutboundMessage], Awaitable[None]]]
        ] = {}
        self._running = False

    async def publish_inbound(self, message: InboundMessage):
        """Publish an inbound message to the bus."""
        await self.inbound.put(message)

    async def consume_inbound(self) -> InboundMessage:
        """Consume an inbound message from the bus."""
        return await self.inbound.get()

    async def publish_outbound(self, message: OutboundMessage):
        """Publish an outbound message to the bus and notify subscribers."""
        await self.outbound.put(message)

    # not used directly, rather dispatch_outbound is used to send messages to channels
    async def consume_outbound(self) -> OutboundMessage:
        """Consume an outbound message from the bus."""
        return await self.outbound.get()

    async def subscribe_outbound(
        self, channel: str, callback: Callable[[OutboundMessage], Awaitable[None]]
    ):
        """Subscribe to outbound messages for a specific channel."""
        if channel not in self._outbound_subscribers:
            self._outbound_subscribers[channel] = []
        self._outbound_subscribers[channel].append(callback)

    async def dispatch_outbound(self) -> None:
        """
        Dispatch outbound messages to subscribed channels.
        Run this as a background task.
        """
        self._running = True
        while self._running:
            try:
                msg = await asyncio.wait_for(self.outbound.get(), timeout=1.0)
                subscribers = self._outbound_subscribers.get(msg.channel, [])
                for callback in subscribers:
                    try:
                        await callback(msg)
                    except Exception as e:
                        logger.error(f"Error dispatching to {msg.channel}: {e}")

            except asyncio.TimeoutError:
                continue

    def stop(self):
        """Stop the message bus."""
        self._running = False

    @property
    def inbound_size(self) -> int:
        """Return the number of messages in the inbound queue."""
        return self.inbound.qsize()

    @property
    def outbound_size(self) -> int:
        """Return the number of messages in the outbound queue."""
        return self.outbound.qsize()
