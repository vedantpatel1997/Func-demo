import os
import logging
import time
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)

_LOGIC_APP_ENDPOINT = os.environ.get("LOGIC_APP_ENDPOINT", "")
_LOGIC_APP_TIMEOUT = int(os.environ.get("LOGIC_APP_TIMEOUT_SECONDS", "10"))
_LOGIC_APP_RETRY_ATTEMPTS = int(os.environ.get("LOGIC_APP_RETRY_ATTEMPTS", "1"))
_LOGIC_APP_RETRY_BACKOFF_SECONDS = float(
    os.environ.get("LOGIC_APP_RETRY_BACKOFF_SECONDS", "0.2")
)
_TENANT_ID = int(os.environ.get("TENANT_ID", "0"))
_GS_APP_ID = os.environ.get("GS_APP_ID", "")


def _now_iso() -> str:
    dt = datetime.now(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def _is_retriable_status(status_code: int) -> bool:
    return status_code == 429 or status_code >= 500


def build_inbound_event(
    msg: dict,
    sender_name: str,
    display_phone_number: str,
    correlation_id: str,
) -> dict:
    msg_type = msg.get("type", "text")
    wa_message_id = msg.get("id", "")
    sender_number = msg.get("from", "")
    now = _now_iso()

    text_message = ""
    media_url = None
    media_mime_type = None
    media_filename = None

    if msg_type == "text":
        text_message = msg.get("text", {}).get("body", "")
    else:
        media_info = msg.get(msg_type, {})
        media_url = media_info.get("url") or media_info.get("id")
        media_mime_type = media_info.get("mime_type")
        media_filename = media_info.get("filename")

    return {
        "event": "inbound.message",
        "timestamp": now,
        "correlationId": correlation_id,
        "data": {
            "senderNumber": sender_number,
            "senderName": sender_name,
            "textMessage": text_message,
            "originalText": text_message,
            "messageType": msg_type,
            "waMessageId": wa_message_id,
            "receivedAt": now,
            "mediaUrl": media_url,
            "mediaMimeType": media_mime_type,
            "mediaFilename": media_filename,
            "wasTranscribed": False,
            "tenantId": _TENANT_ID,
            "gsAppId": _GS_APP_ID,
            "displayPhoneNumber": display_phone_number,
        },
    }


def _post_with_retry(body: dict, wa_message_id: str, correlation_id: str) -> None:
    if not _LOGIC_APP_ENDPOINT:
        logger.error(
            "Logic App endpoint missing | correlation_id=%s | wamid=%s",
            correlation_id,
            wa_message_id,
        )
        return

    max_attempts = max(1, min(_LOGIC_APP_RETRY_ATTEMPTS + 1, 3))
    for attempt in range(1, max_attempts + 1):
        start = time.perf_counter()
        try:
            resp = httpx.post(
                _LOGIC_APP_ENDPOINT,
                json=body,
                timeout=_LOGIC_APP_TIMEOUT,
                headers={"x-correlation-id": correlation_id},
            )
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.info(
                "Inbound event forwarded | correlation_id=%s | wamid=%s | status=%d | attempt=%d | latency_ms=%d",
                correlation_id,
                wa_message_id,
                resp.status_code,
                attempt,
                latency_ms,
            )

            if resp.is_success:
                return

            if not _is_retriable_status(resp.status_code):
                return
        except Exception:
            latency_ms = int((time.perf_counter() - start) * 1000)
            logger.error(
                "Forwarding failed | correlation_id=%s | wamid=%s | attempt=%d | latency_ms=%d",
                correlation_id,
                wa_message_id,
                attempt,
                latency_ms,
                exc_info=True,
            )

        if attempt < max_attempts:
            time.sleep(_LOGIC_APP_RETRY_BACKOFF_SECONDS)


def forward_inbound_messages(value: dict, correlation_id: str = "") -> None:
    messages = value.get("messages", [])
    contacts = value.get("contacts", [])
    metadata = value.get("metadata", {})

    display_phone_number = metadata.get("display_phone_number", "")
    sender_name = contacts[0]["profile"]["name"] if contacts else ""

    for msg in messages:
        wa_message_id = msg.get("id", "")
        body = build_inbound_event(msg, sender_name, display_phone_number, correlation_id)
        _post_with_retry(body, wa_message_id, correlation_id)
