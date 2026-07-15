Mapa completo de parámetros

AzureWebJobsStorage
Para local rápido: deja UseDevelopmentStorage=true
Requisito: tener Azurite levantado
Alternativa: usar connection string real de una cuenta de Storage
Dónde obtenerla en Azure: Storage Account > Access keys > Connection string
FUNCTIONS_WORKER_RUNTIME
Valor esperado: python
No se obtiene de Azure, es fijo para este proyecto
FUNCTIONS_WORKER_RUNTIME_VERSION
Valor recomendado aquí: 3.11
Debe coincidir con el runtime que usas local/container
ACS_CONNECTION_STRING
Dónde obtenerla: Azure Communication Services > Keys > Connection string
Debe verse como endpoint más accesskey
ACS_CHANNEL_ID
Dónde obtenerlo: en el canal de WhatsApp configurado dentro de Azure Communication Services (Messaging/Channels)
Es el identificador del registro de canal que usa el envío
META_VERIFY_TOKEN
Este lo defines tú
Debe ser exactamente el mismo que configuras en Meta Developer (Webhook verify token)
LOGIC_APP_ENDPOINT
Dónde obtenerlo: Logic App > Trigger HTTP Request > URL del trigger
Es la URL completa con firma
LOGIC_APP_TIMEOUT_SECONDS
Valor sugerido inicial: 10
Ajuste operativo según latencia esperada
LOGIC_APP_RETRY_ATTEMPTS
Valor sugerido inicial: 1
Puedes subirlo si tu Logic App tiene picos de error temporal
LOGIC_APP_RETRY_BACKOFF_SECONDS
Valor sugerido inicial: 0.2
Tiempo entre reintentos
TENANT_ID
En este proyecto se usa como dato de negocio que se envía al payload hacia Logic App
No viene automáticamente de Azure AD
Debes poner el ID interno de tu tenant de negocio (según tu integración)
GS_APP_ID
También es dato de negocio/integración, se envía al payload
Debes usar el identificador de tu aplicación en el sistema destino
WEBHOOK_MAX_BODY_BYTES
Límite de tamaño del body de entrada
Sugerido: 1048576 (1 MB)
OUTBOUND_MAX_MESSAGE_LENGTH
Límite de caracteres para mensajes salientes
Sugerido: 4096
APPLICATIONINSIGHTS_CONNECTION_STRING
Dónde obtenerla: Application Insights > Overview > Connection string
Útil para telemetría cuando quieras observabilidad real
Variables que realmente usa el código

Se leen en function_app.py, acs_service.py, logic_app_service.py
Si faltan ACS_CONNECTION_STRING o ACS_CHANNEL_ID, fallará el envío
Si falta LOGIC_APP_ENDPOINT, fallará el reenvío a Logic App
META_VERIFY_TOKEN se usa para validar el webhook GET de Meta
Checklist mínimo para arrancar local

ACS_CONNECTION_STRING correcto
ACS_CHANNEL_ID correcto
META_VERIFY_TOKEN igual al de Meta
LOGIC_APP_ENDPOINT válido
local.settings.json presente
Si usas UseDevelopmentStorage=true, Azurite activo