"""Telegram channel handler — connects to Telegram Bot API and publishes to bus."""

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

from merobot.handler.message_bus import MessageBus
from merobot.handler.messages import OutboundMessage

from .base import BaseChannelHandler


class TelegramChannelHandler(BaseChannelHandler):
    """Telegram channel handler using polling.

    Responsibilities:
        - Connect / disconnect to Telegram (polling mode)
        - Send an OutboundMessage via Bot API
        - Receive incoming messages, convert to InboundMessage, and publish to bus
    """

    name = "telegram"
    CHANNEL_NAME = "telegram"

    def __init__(self, bus: MessageBus, token: str, config: dict | None = None):
        """
        Args:
            bus: MessageBus instance for publishing inbound messages.
            token: Telegram Bot API token from @BotFather.
            config: Optional channel-specific config dict.
        """
        super().__init__(bus, config)
        self._token = token
        self._app: Application | None = None
        self._bot: Bot | None = None

    # ------------------------------------------------------------------
    # BaseChannelHandler interface
    # ------------------------------------------------------------------

    async def connect(self):
        """Build the Telegram Application, register handlers, start polling."""
        if self._running:
            logger.warning(
                "TelegramChannelHandler.connect() called while already connected"
            )
            return

        self._app = Application.builder().token(self._token).build()
        self._bot = self._app.bot

        # Register a handler for all text (& caption) messages
        self._app.add_handler(
            MessageHandler(
                filters.TEXT
                & ~filters.COMMAND,  # todo: support all media types (image, text, audio, voice and documents)
                self._handle_update,
            )
        )

        # Initialize and start polling (non-blocking)
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(drop_pending_updates=True)

        self._running = True
        logger.info("Telegram channel connected (polling)")

    async def disconnect(self):
        """Stop polling, shut down the Application gracefully."""
        if not self._running or self._app is None:
            return

        try:
            if self._app.updater and self._app.updater.running:
                await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
        except Exception as exc:
            logger.error(f"Error during Telegram disconnect: {exc}")
        finally:
            self._running = False
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
        """Convert an incoming Telegram Update into an InboundMessage and publish to bus."""
        if update.message is None or update.message.text is None:
            return

        msg = update.message

        # Use the base class helper to create InboundMessage and publish to bus
        await self._publish_inbound(
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

        logger.debug(
            f"Received message from "
            f"{msg.from_user.id if msg.from_user else 'unknown'} "
            f"in chat {msg.chat_id}"
        )

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
