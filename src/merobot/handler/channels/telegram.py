"""Telegram channel handler — bridges Telegram Bot API ↔ MessageBus."""

import asyncio
import time

from loguru import logger
from telegram import Bot, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    ContextTypes,
    MessageHandler,
    filters,
)

from merobot.handler.messages import InboundMessage, OutboundMessage

from .base import BaseChannelHandler


class TelegramChannelHandler(BaseChannelHandler):
    """Concrete channel handler that connects to Telegram via polling."""

    CHANNEL_NAME = "telegram"

    def __init__(self, token: str, message_bus=None):
        """
        Args:
            token: Telegram Bot API token from @BotFather.
            message_bus: Optional MessageBus instance. When provided the
                handler will publish inbound messages to the bus and
                subscribe for outbound messages automatically.
        """
        self._token = token
        self._message_bus = message_bus
        self._app: Application | None = None
        self._bot: Bot | None = None
        self._inbound_queue: asyncio.Queue[InboundMessage] = asyncio.Queue()
        self._connected = False

    # ------------------------------------------------------------------
    # BaseChannelHandler interface
    # ------------------------------------------------------------------

    async def connect(self):
        """Build the Telegram Application, register handlers, start polling."""
        if self._connected:
            logger.warning(
                "TelegramChannelHandler.connect() called while already connected"
            )
            return

        self._app = Application.builder().token(self._token).build()
        self._bot = self._app.bot

        # Register a handler for all text (& caption) messages
        self._app.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self._handle_update,
            )
        )

        # Subscribe to outbound messages on the bus so replies flow back
        if self._message_bus is not None:
            await self._message_bus.subscribe_outbound(
                self.CHANNEL_NAME,
                self._on_outbound,
            )

        # Initialize and start polling (non-blocking)
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

        self._connected = True
        logger.info("Telegram channel connected (polling)")

    async def disconnect(self):
        """Stop polling, shut down the Application gracefully."""
        if not self._connected or self._app is None:
            return

        try:
            if self._app.updater and self._app.updater.running:
                await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        except Exception as exc:
            logger.error(f"Error during Telegram disconnect: {exc}")
        finally:
            self._connected = False
            logger.info("Telegram channel disconnected")

    async def send_message(self, message: OutboundMessage):
        """Send a text message to a Telegram chat."""
        if self._bot is None:
            raise RuntimeError("Cannot send message: handler is not connected")

        await self._bot.send_message(
            chat_id=message.chat_id,
            text=message.content,
        )
        logger.debug(f"Sent message to chat {message.chat_id}")

    async def receive_message(self) -> InboundMessage:
        """Block until the next inbound message arrives and return it."""
        return await self._inbound_queue.get()

    async def start_typing(self, chat_id: str):
        """Send a 'typing…' indicator to the given chat."""
        if self._bot is None:
            raise RuntimeError("Cannot send typing indicator: handler is not connected")

        await self._bot.send_chat_action(
            chat_id=chat_id,
            action=ChatAction.TYPING,
        )

    async def stop_typing(self, chat_id: str):
        """No-op — Telegram auto-clears typing after ~5 s or on next message."""
        pass

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _handle_update(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Convert an incoming Telegram Update into an InboundMessage."""
        if update.message is None or update.message.text is None:
            return

        msg = update.message

        inbound = InboundMessage(
            channel=self.CHANNEL_NAME,
            content=msg.text,
            sender_id=str(msg.from_user.id) if msg.from_user else "unknown",
            chat_id=str(msg.chat_id),
            timestamp=msg.date.timestamp() if msg.date else time.time(),
            media=self._extract_media(msg),
            metadata={
                "message_id": msg.message_id,
                "chat_type": msg.chat.type if msg.chat else None,
                "first_name": (msg.from_user.first_name if msg.from_user else None),
                "username": (msg.from_user.username if msg.from_user else None),
            },
        )

        # Enqueue for receive_message()
        await self._inbound_queue.put(inbound)

        # Publish to bus if available
        if self._message_bus is not None:
            await self._message_bus.publish_inbound(inbound)

        logger.debug(
            f"Received message from {inbound.sender_id} in chat {inbound.chat_id}"
        )

    async def _on_outbound(self, message: OutboundMessage):
        """Callback registered on the MessageBus for outbound dispatch."""
        await self.send_message(message)

    @staticmethod
    def _extract_media(msg) -> list[str]:
        """Pull media file-IDs from a Telegram Message, if any."""
        media: list[str] = []
        if msg.photo:
            # Largest resolution is the last item
            media.append(msg.photo[-1].file_id)
        if msg.document:
            media.append(msg.document.file_id)
        if msg.video:
            media.append(msg.video.file_id)
        if msg.audio:
            media.append(msg.audio.file_id)
        if msg.voice:
            media.append(msg.voice.file_id)
        return media
