from hypothesis import given, strategies as st

from services import logic_app_service


@given(
    msg_type=st.sampled_from(["text", "image", "document"]),
    message_id=st.text(min_size=1, max_size=40),
    sender=st.text(min_size=1, max_size=16),
    text=st.text(max_size=80),
)
def test_build_inbound_event_invariants(msg_type, message_id, sender, text):
    msg = {"id": message_id, "from": sender, "type": msg_type}
    if msg_type == "text":
        msg["text"] = {"body": text}
    else:
        msg[msg_type] = {"id": "media-id", "mime_type": "application/octet-stream"}

    event = logic_app_service.build_inbound_event(
        msg,
        sender_name="Tester",
        display_phone_number="+573114447490",
        correlation_id="corr-1",
    )

    assert event["event"] == "inbound.message"
    assert event["correlationId"] == "corr-1"
    assert event["data"]["waMessageId"] == message_id
    assert event["data"]["senderNumber"] == sender
    assert event["data"]["messageType"] == msg_type
    assert "receivedAt" in event["data"]
