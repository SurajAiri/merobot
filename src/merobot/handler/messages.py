# inbound and outbound messages

from dataclasses import dataclass, field


@dataclass
class InboundMessage:
    channel: str
    content: str
    sender_id: str
    chat_id: str
    timestamp: float
    media: list[str] = field(default_factory=list)  # Local file paths or media IDs
    media_type: str | None = None  # "photo", "document", "audio", "voice", "video"
    metadata: dict = field(
        default_factory=dict
    )  # Additional info like attachments, reactions, etc.


@dataclass
class OutboundMessage:
    channel: str
    content: str
    recipient_id: str
    chat_id: str
    media: list[str] = field(default_factory=list)  # URLs or media identifiers
    metadata: dict = field(
        default_factory=dict
    )  # Additional info like attachments, reactions, etc.
