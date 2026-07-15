import os
import json
import logging
import re
import uuid
import azure.functions as func

from services import acs_service, logic_app_service

logger = logging.getLogger(__name__)
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

META_VERIFY_TOKEN = os.environ.get("META_VERIFY_TOKEN", "")
WEBHOOK_MAX_BODY_BYTES = int(os.environ.get("WEBHOOK_MAX_BODY_BYTES", "1048576"))
OUTBOUND_MAX_MESSAGE_LENGTH = int(os.environ.get("OUTBOUND_MAX_MESSAGE_LENGTH", "4096"))

_E164_PATTERN = re.compile(r"^\+?[1-9]\d{7,14}$")


def _get_correlation_id(req: func.HttpRequest) -> str:
    header_value = (req.headers.get("x-correlation-id") or "").strip()
    return header_value or str(uuid.uuid4())


def _json_response(payload: dict, status_code: int) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload),
        status_code=status_code,
        mimetype="application/json",
    )


def _is_valid_e164(value: str) -> bool:
    return bool(_E164_PATTERN.fullmatch(value))


# =============================================================================
# 1. WEBHOOK META – VERIFICACIÓN (GET)
# =============================================================================
@app.route(route="whatsapp/webhook", methods=["GET"])
def verify_webhook(req: func.HttpRequest) -> func.HttpResponse:
    correlation_id = _get_correlation_id(req)
    mode = req.params.get("hub.mode")
    token = req.params.get("hub.verify_token")
    challenge = req.params.get("hub.challenge")

    if mode == "subscribe" and token == META_VERIFY_TOKEN:
        logger.info(
            "Webhook Meta verificado correctamente | correlation_id=%s",
            correlation_id,
        )
        return func.HttpResponse(challenge, status_code=200)

    logger.warning("Verificacion Meta fallida | correlation_id=%s", correlation_id)
    return func.HttpResponse("Forbidden", status_code=403)


# =============================================================================
# 2. WEBHOOK META – RECEPCIÓN DE MENSAJES ENTRANTES (POST)
# =============================================================================
@app.route(route="whatsapp/webhook", methods=["POST"])
def receive_message(req: func.HttpRequest) -> func.HttpResponse:
    correlation_id = _get_correlation_id(req)
    body_size = len(req.get_body() or b"")

    if body_size > WEBHOOK_MAX_BODY_BYTES:
        logger.warning(
            "Webhook body exceeds limit | correlation_id=%s | size=%d",
            correlation_id,
            body_size,
        )
        return func.HttpResponse("OK", status_code=200)

    try:
        payload = req.get_json()
    except ValueError:
        logger.warning(
            "Webhook recibido con cuerpo no-JSON, ignorando | correlation_id=%s",
            correlation_id,
        )
        return func.HttpResponse("OK", status_code=200)

    if not isinstance(payload, dict):
        logger.warning(
            "Webhook payload no es objeto JSON | correlation_id=%s",
            correlation_id,
        )
        return func.HttpResponse("OK", status_code=200)

    if payload.get("object") != "whatsapp_business_account":
        logger.info(
            "Webhook object no soportado | correlation_id=%s | object=%s",
            correlation_id,
            payload.get("object"),
        )
        return func.HttpResponse("OK", status_code=200)

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            if change.get("field") != "messages":
                continue
            logic_app_service.forward_inbound_messages(
                change.get("value", {}),
                correlation_id=correlation_id,
            )

    # Meta exige siempre HTTP 200
    return func.HttpResponse("OK", status_code=200)


# =============================================================================
# 3. ENVÍO SALIENTE – LLAMADO DESDE LOGIC APP (POST)
# =============================================================================
@app.route(route="whatsapp/send", methods=["POST"])
def send_message(req: func.HttpRequest) -> func.HttpResponse:
    correlation_id = _get_correlation_id(req)

    try:
        body = req.get_json()
    except ValueError:
        return _json_response(
            {"error": "Invalid JSON body", "correlationId": correlation_id},
            status_code=400,
        )

    if not isinstance(body, dict):
        return _json_response(
            {"error": "Invalid JSON object", "correlationId": correlation_id},
            status_code=400,
        )

    to_number = (body.get("to") or "").strip()
    message = (body.get("message") or "").strip()

    if not to_number or not message:
        return _json_response(
            {
                "error": "Fields 'to' and 'message' are required",
                "correlationId": correlation_id,
            },
            status_code=400,
        )

    if not _is_valid_e164(to_number):
        return _json_response(
            {"error": "Field 'to' must be E.164", "correlationId": correlation_id},
            status_code=400,
        )

    if len(message) > OUTBOUND_MAX_MESSAGE_LENGTH:
        return _json_response(
            {
                "error": "Field 'message' exceeds max length",
                "correlationId": correlation_id,
            },
            status_code=400,
        )

    send_result = acs_service.send_text_result(
        to_number,
        message,
        correlation_id=correlation_id,
    )

    if send_result["success"]:
        return _json_response(
            {"status": "sent", "correlationId": correlation_id},
            status_code=200,
        )

    return _json_response(
        {
            "error": "Failed to send message via ACS",
            "reason": send_result.get("reason"),
            "correlationId": correlation_id,
        },
        status_code=502,
    )

