import json
from types import SimpleNamespace

import function_app


class FakeRequest:
    def __init__(self, body: bytes, json_payload=None, params=None, headers=None):
        self._body = body
        self._json_payload = json_payload
        self.params = params or {}
        self.headers = headers or {}

    def get_body(self):
        return self._body

    def get_json(self):
        if isinstance(self._json_payload, Exception):
            raise self._json_payload
        return self._json_payload


def test_send_message_rejects_invalid_json():
    req = FakeRequest(body=b"not-json", json_payload=ValueError("bad"))
    resp = function_app.send_message(req)
    assert resp.status_code == 400


def test_send_message_rejects_invalid_phone():
    req = FakeRequest(
        body=b"{}",
        json_payload={"to": "abc", "message": "hola"},
        headers={"x-correlation-id": "cid-1"},
    )
    resp = function_app.send_message(req)
    payload = json.loads(resp.get_body())
    assert resp.status_code == 400
    assert payload["correlationId"] == "cid-1"


def test_send_message_success(monkeypatch):
    monkeypatch.setattr(
        function_app.acs_service,
        "send_text_result",
        lambda *_args, **_kwargs: {"success": True},
    )
    req = FakeRequest(body=b"{}", json_payload={"to": "+573001112233", "message": "ok"})
    resp = function_app.send_message(req)
    assert resp.status_code == 200


def test_receive_message_ignores_oversized_payload(monkeypatch):
    monkeypatch.setattr(function_app, "WEBHOOK_MAX_BODY_BYTES", 3)
    called = {"value": False}

    def _never_called(*_args, **_kwargs):
        called["value"] = True

    monkeypatch.setattr(function_app.logic_app_service, "forward_inbound_messages", _never_called)

    req = FakeRequest(body=b"12345", json_payload={"object": "whatsapp_business_account"})
    resp = function_app.receive_message(req)

    assert resp.status_code == 200
    assert called["value"] is False
