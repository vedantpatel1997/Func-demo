# models/__init__.py
# Exporta los modelos principales para facilitar los imports.
# Nota: solo se exporta lo que realmente existe en whatsapp_models.py.
# (Antes se importaban ErpResponse y ConversationContext, que no existen,
#  lo que provocaba un ImportError al importar el paquete `models`.)

from .whatsapp_models import WhatsAppMessage

__all__ = [
    "WhatsAppMessage",
]
