"""Telegram channel handler — connects to Telegram Bot API and publishes to bus.

Supports:
    - Text messages
    - Media messages (photo, document, audio, voice, video) with file download
    - Commands (/start, /clear)
"""

import time
from pathlib import Path

from loguru import logger
from telegram import Bot, Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from merobot.config import get_config
from merobot.constants import DEFAULT_MEDIA_DIR
from merobot.handler.message_bus import MessageBus
from merobot.handler.messages import OutboundMessage

from .base import BaseChannelHandler

# Media type mapping for Telegram message attributes
_MEDIA_ATTRS = ["photo", "document", "video", "audio", "voice"]


class TelegramChannelHandler(BaseChannelHandler):
    """Telegram channel handler using polling.

    Responsibilities:
        - Connect / disconnect to Telegram (polling mode)
        - Send an OutboundMessage via Bot API
        - Receive incoming text & media messages, convert to InboundMessage, publish to bus
        - Handle bot commands (/start, /clear)
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

        # Media download directory
        workspace = get_config().agent.resolved_workspace
        self._media_dir = workspace / DEFAULT_MEDIA_DIR

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

        # --- Command handlers ---
        self._app.add_handler(CommandHandler("start", self._handle_start))
        self._app.add_handler(CommandHandler("clear", self._handle_clear))

        # --- Text messages (not commands) ---
        self._app.add_handler(
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self._handle_text,
            )
        )

        # --- Media messages ---
        self._app.add_handler(
            MessageHandler(
                filters.PHOTO | filters.Document.ALL | filters.AUDIO
                | filters.VIDEO | filters.VOICE,
                self._handle_media,
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
    # Command handlers
    # ------------------------------------------------------------------

    async def _handle_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command — send welcome message."""
        if update.message is None:
            return

        await update.message.reply_text(
            "👋 Hey! I'm MeroBot, your personal AI assistant.\n\n"
            "Send me a message, photo, document, or voice note and I'll help you out.\n\n"
            "Commands:\n"
            "/start — Show this message\n"
            "/clear — Clear conversation history"
        )

    async def _handle_clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /clear command — publish a special inbound message to clear session."""
        if update.message is None:
            return

        msg = update.message
        await self._publish_inbound(
            channel=self.CHANNEL_NAME,
            content="/clear",
            sender_id=str(msg.from_user.id) if msg.from_user else "unknown",
            chat_id=str(msg.chat_id),
            timestamp=msg.date.timestamp() if msg.date else time.time(),
            metadata={"command": "clear"},
        )

    # ------------------------------------------------------------------
    # Text message handler
    # ------------------------------------------------------------------

    async def _handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Convert an incoming text message into an InboundMessage and publish to bus."""
        if update.message is None or update.message.text is None:
            return

        msg = update.message
        await self._publish_inbound(
            channel=self.CHANNEL_NAME,
            content=msg.text,
            sender_id=str(msg.from_user.id) if msg.from_user else "unknown",
            chat_id=str(msg.chat_id),
            timestamp=msg.date.timestamp() if msg.date else time.time(),
            media=self._extract_media(msg),
            metadata=self._build_metadata(msg),
        )
        logger.debug(
            f"Received text from "
            f"{msg.from_user.id if msg.from_user else 'unknown'} "
            f"in chat {msg.chat_id}"
        )

    # ------------------------------------------------------------------
    # Media message handler
    # ------------------------------------------------------------------

    async def _handle_media(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Download media file, convert to InboundMessage with local path, publish to bus."""
        if update.message is None:
            return

        msg = update.message
        media_type = self._detect_media_type(msg)

        # Download the file
        local_path = await self._download_media(msg, media_type)

        # Build content: caption + media description
        parts = []
        if msg.caption:
            parts.append(msg.caption)
        if local_path:
            parts.append(f"[Attached {media_type}: {local_path}]")
        else:
            parts.append(f"[Attached {media_type}: download failed]")

        content = "\n".join(parts)
        media_paths = [str(local_path)] if local_path else []

        await self._publish_inbound(
            channel=self.CHANNEL_NAME,
            content=content,
            sender_id=str(msg.from_user.id) if msg.from_user else "unknown",
            chat_id=str(msg.chat_id),
            timestamp=msg.date.timestamp() if msg.date else time.time(),
            media=media_paths,
            metadata={
                **self._build_metadata(msg),
                "media_type": media_type,
            },
        )
        logger.debug(
            f"Received {media_type} from "
            f"{msg.from_user.id if msg.from_user else 'unknown'} "
            f"in chat {msg.chat_id}"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _download_media(self, msg, media_type: str) -> Path | None:
        """Download a media file from Telegram to the workspace media directory."""
        try:
            file_id = self._get_file_id(msg, media_type)
            if not file_id:
                return None

            # Create chat-specific media directory
            chat_dir = self._media_dir / str(msg.chat_id)
            chat_dir.mkdir(parents=True, exist_ok=True)

            # Get file info from Telegram
            tg_file = await self._bot.get_file(file_id)
            file_ext = Path(tg_file.file_path).suffix if tg_file.file_path else ""
            if not file_ext:
                file_ext = self._default_extension(media_type)

            filename = f"{media_type}_{int(time.time())}_{msg.message_id}{file_ext}"
            local_path = chat_dir / filename

            await tg_file.download_to_drive(str(local_path))
            logger.info(f"Downloaded {media_type} to {local_path}")
            return local_path

        except Exception as exc:
            logger.error(f"Failed to download {media_type}: {exc}")
            return None

    @staticmethod
    def _detect_media_type(msg) -> str:
        """Determine the type of media in a Telegram message."""
        if msg.photo:
            return "photo"
        if msg.document:
            return "document"
        if msg.video:
            return "video"
        if msg.audio:
            return "audio"
        if msg.voice:
            return "voice"
        return "unknown"

    @staticmethod
    def _get_file_id(msg, media_type: str) -> str | None:
        """Extract the file_id for the given media type."""
        if media_type == "photo" and msg.photo:
            return msg.photo[-1].file_id  # largest resolution
        if media_type == "document" and msg.document:
            return msg.document.file_id
        if media_type == "video" and msg.video:
            return msg.video.file_id
        if media_type == "audio" and msg.audio:
            return msg.audio.file_id
        if media_type == "voice" and msg.voice:
            return msg.voice.file_id
        return None

    @staticmethod
    def _default_extension(media_type: str) -> str:
        """Fallback file extension when Telegram doesn't provide one."""
        return {
            "photo": ".jpg",
            "voice": ".ogg",
            "audio": ".mp3",
            "video": ".mp4",
            "document": ".bin",
        }.get(media_type, ".bin")

    @staticmethod
    def _extract_media(msg) -> list[str]:
        """Pull media file-IDs from a Telegram Message, if any."""
        media: list[str] = []
        if msg.photo:
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

    @staticmethod
    def _build_metadata(msg) -> dict:
        """Build common metadata dict from a Telegram message."""
        return {
            "message_id": msg.message_id,
            "chat_type": msg.chat.type if msg.chat else None,
            "first_name": (msg.from_user.first_name if msg.from_user else None),
            "username": (msg.from_user.username if msg.from_user else None),
        }
