import os
import logging
from typing import Optional

from azure.communication.messages import NotificationMessagesClient
from azure.communication.messages.models import TextNotificationContent

logger = logging.getLogger(__name__)


def _get_client() -> NotificationMessagesClient:
    return NotificationMessagesClient.from_connection_string(
        os.environ["ACS_CONNECTION_STRING"]
    )


def _get_channel_id() -> str:
    return os.environ["ACS_CHANNEL_ID"]


def send_text_result(
    to_number: str,
    message: str,
    correlation_id: Optional[str] = None,
) -> dict:
    try:
        client = _get_client()
        channel_id = _get_channel_id()

        content = TextNotificationContent(
            channel_registration_id=channel_id,
            to=[to_number],
            content=message,
        )

        client.send(content)
        logger.info(
            "WhatsApp message sent successfully | correlation_id=%s",
            correlation_id,
        )
        return {"success": True}

    except Exception:
        logger.error(
            "Error sending WhatsApp message via ACS | correlation_id=%s",
            correlation_id,
            exc_info=True,
        )
        return {"success": False, "reason": "acs_send_failed"}


def send_text(to_number: str, message: str) -> bool:
    return send_text_result(to_number, message).get("success", False)


def safe_send_text(to_number: str, message: str) -> bool:
    try:
        return send_text(to_number, message)
    except Exception:
        logger.warning("Silent failure sending WhatsApp message", exc_info=True)
        return False
