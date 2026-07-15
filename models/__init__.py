# models/__init__.py
# Exporta los modelos principales para facilitar los imports

from .whatsapp_models import WhatsAppMessage, ErpResponse, ConversationContext

__all__ = [
    "WhatsAppMessage",
    "ErpResponse",
    "ConversationContext"
]