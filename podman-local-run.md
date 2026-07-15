# Ejecutar Azure Functions en local con Podman

## Objetivo
Esta guia explica:
1. Como levantar la Function App localmente con Podman.
2. Como probar que esta respondiendo.
3. Como funciona la "publicacion" del codigo en Podman.

## Requisitos
- Podman instalado.
- Archivo `local.settings.json` completo con las variables del proyecto.
- Estar en la raiz del repositorio.

## Ejecucion local (Bash)
```bash
cd "/home/federico/Proyectos/Trabajos extra/codigowhatsappv1"

python3 -c "import json; d=json.load(open('local.settings.json')); print('\n'.join(f'{k}={v}' for k,v in d.get('Values',{}).items()))" > .env.podman

podman run -d \
  --name whatsapp-func-local \
  -p 7071:80 \
  --env-file .env.podman \
  -v "$PWD:/home/site/wwwroot:Z" \
  mcr.microsoft.com/azure-functions/python:4-python3.11

podman logs -f whatsapp-func-local
```

## Ejecucion local (fish)
```fish
cd "/home/federico/Proyectos/Trabajos extra/codigowhatsappv1"

python3 -c "import json; d=json.load(open('local.settings.json')); print('\\n'.join(f'{k}={v}' for k,v in d.get('Values',{}).items()))" > .env.podman

podman run -d \
  --name whatsapp-func-local \
  -p 7071:80 \
  --env-file .env.podman \
  -v "$PWD:/home/site/wwwroot:Z" \
  mcr.microsoft.com/azure-functions/python:4-python3.11

podman logs -f whatsapp-func-local
```

## Verificacion rapida
```bash
curl -i http://localhost:7071/
```

## Probar endpoints
### Webhook
```bash
curl -i -X POST http://localhost:7071/api/whatsapp/webhook \
  -H "Content-Type: application/json" \
  -d '{"value":[{"from":"573000000000","id":"wamid.test","text":{"body":"hola"}}]}'
```

### Send
```bash
curl -i -X POST http://localhost:7071/api/whatsapp/send \
  -H "Content-Type: application/json" \
  -d '{"to":"+573000000000","message":"mensaje de prueba"}'
```

## Detener y limpiar
```bash
podman rm -f whatsapp-func-local
rm -f .env.podman
```

## Como se "publica" el codigo en Podman
Hay dos formas:

### 1) Desarrollo local (sin build de imagen)
En este proyecto se esta usando:
```bash
-v "$PWD:/home/site/wwwroot:Z"
```
Eso monta tu carpeta local dentro del contenedor. Significa que:
- El codigo NO se copia a una imagen nueva.
- Cualquier cambio en archivos locales se refleja en el contenedor montado.
- Es ideal para desarrollo y pruebas rapidas.

### 2) Publicacion real (build de imagen)
Para "publicar" codigo de forma reproducible, se construye una imagen que ya incluye el codigo.

Este repositorio ahora incluye `Containerfile` en la raiz.

Ejemplo de flujo:
```bash
# Construir imagen propia con el codigo
podman build -f Containerfile -t codigowhatsappv1-func:local .

# Ejecutar imagen propia
podman run -d --name whatsapp-func-local \
  -p 7071:80 \
  --env-file .env.podman \
  codigowhatsappv1-func:local
```

Flujo para subir la imagen a un registry:
```bash
# Ejemplo con GitHub Container Registry
podman tag codigowhatsappv1-func:local ghcr.io/<tu-usuario>/codigowhatsappv1-func:latest
podman login ghcr.io
podman push ghcr.io/<tu-usuario>/codigowhatsappv1-func:latest
```

En este modo, el codigo queda versionado dentro de la imagen y luego puedes:
- Etiquetar (`podman tag`)
- Subir a un registry (`podman push`)
- Desplegar esa imagen en otro entorno.

## Nota de seguridad
`local.settings.json` y `.env.podman` pueden contener secretos. No subirlos al repositorio.

## Publicar en Azure Functions usando GitHub Actions
Se agrego el workflow [/.github/workflows/deploy-function-container.yml](.github/workflows/deploy-function-container.yml).

### Que hace el workflow
1. Hace login en Azure con un Service Principal (`AZURE_CREDENTIALS`).
2. Hace login en ACR.
3. Construye la imagen desde `Containerfile`.
4. Publica tags `latest` y `${{ github.sha }}` en ACR.
5. Actualiza la Function App para usar la imagen publicada.
6. Reinicia la Function App.

### Secrets que debes crear en GitHub
En `Settings > Secrets and variables > Actions` del repo, agrega:
- `AZURE_CREDENTIALS`: JSON de credenciales del Service Principal.
- `ACR_NAME`: nombre del Azure Container Registry (sin `.azurecr.io`).
- `FUNCTION_APP_NAME`: nombre de la Azure Function App.
- `RESOURCE_GROUP`: Resource Group donde vive la Function App.

### Permisos minimos recomendados
El Service Principal de `AZURE_CREDENTIALS` debe tener:
- `Contributor` sobre la Function App (o sobre el Resource Group).
- `AcrPush` sobre el ACR.

### Flujo de despliegue
1. Haces push a `master` o `main`.
2. GitHub Actions ejecuta `deploy-function-container.yml`.
3. La Function App queda apuntando a la nueva imagen.
