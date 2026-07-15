from dataclasses import dataclass
from typing import Optional


@dataclass
class WhatsAppMessage:
    message_id: str
    from_number: str
    sender_name: str
    text: str
    message_type: str
    timestamp: str
    phone_number_id: str
    display_phone_number: str
    wa_app_id: Optional[str] = None

    def is_text(self) -> bool:
        return self.message_type == "text"

    def is_media(self) -> bool:
        return self.message_type in ["image", "document", "audio", "video"]
