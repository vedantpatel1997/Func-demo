# Func-demo — Root Cause Analysis & Complete Fix

**Date:** 2026-07-16
**App:** `Func-demo` (Resource group `Temp_RG`, subscription `6a3bb170-...`)
**Plan:** Azure Functions **Flex Consumption**, Python **3.13** (Linux)
**Host:** `func-demo-gmhhhvh0gcghc6b2.westus2-01.azurewebsites.net`

---

## 1. Symptom

Every request to the app returned:

```
HTTP 503 – "Function host is not running"
```

and the app had **0 functions** registered. The Azure log showed:

```
ModuleNotFoundError: No module named 'azure.communication'
File "/home/site/wwwroot/services/acs_service.py", line 5, in <module>
    from azure.communication.messages import NotificationMessagesClient
sys.path: /home/site/wwwroot/.python_packages/lib/site-packages  ← this folder was EMPTY
```

The Python worker could not import its dependencies, so the host failed to index
`function_app.py` and never started.

---

## 2. Root cause

The **GitHub Actions workflow never installed the dependencies into the deployment
package, and remote build was disabled.**

The generated workflow (`.github/workflows/main_func-demo.yml`) did this:

```yaml
- name: Create and start virtual environment
  run: |
    python -m venv venv
    source venv/bin/activate      # ← activation is lost when this step ends

- name: Install dependencies
  run: pip install -r requirements.txt   # ← runs in a NEW shell → installs into
                                          #    system Python, NOT the venv, and NOT
                                          #    into the deployment package
- name: Zip artifact for deployment
  run: zip release.zip ./* -r     # ← zips source + an empty venv (only pip inside)
...
- uses: Azure/functions-action@v1
  with:
    remote-build: false           # ← DEFAULT. No platform build happened either.
```

Two independent problems combined:

1. **Each `run:` step is a fresh shell.** `source venv/bin/activate` in one step does
   not carry to the next step, so `pip install` installed nothing useful into the
   package. The deploy log confirmed the zip only contained `venv/.../pip-26.1.2`.
2. **`remote-build` was `false`.** On the **Flex Consumption** plan, dependencies are
   meant to be built on the platform by **Oryx**. With remote build off *and* no
   `.python_packages` in the zip, the app shipped with **zero dependencies**.

Result: `/home/site/wwwroot/.python_packages/lib/site-packages` was empty →
`import azure.communication...` failed → host down.

> Note: an earlier broken workflow (`main_asdasd.yml`) also existed, targeting a
> non-existent app name `asdasd`. It was already replaced by `main_func-demo.yml`
> (which correctly targets `Func-demo`), so the app-name was **not** the issue — the
> build/dependency handling was.

### Why not just build locally and ship `.python_packages`?
Several dependencies have **native/binary wheels** (`cryptography`, `cffi`, `psutil`).
Building them on a Windows or generic runner and shipping them to Azure's Linux host
produces incompatible binaries. The correct approach for Flex Consumption is a
**remote (Oryx) build on the platform**, which produces Linux-native wheels.

---

## 3. The fix

### 3.1 Workflow — `.github/workflows/main_func-demo.yml`
Rewritten to the supported Flex Consumption pattern:

- Removed the broken venv/local-install/zip steps.
- Runs the test suite on the runner (gate), then deploys with:

```yaml
- uses: Azure/functions-action@v1
  with:
    app-name: 'Func-demo'
    package: '.'
    publish-profile: ${{ secrets.AZUREAPPSERVICE_PUBLISHPROFILE_5A43E5BCCA7245779EACA83912784B91 }}
    sku: 'flexconsumption'
    remote-build: true          # Oryx runs `pip install -r requirements.txt` on Azure
    respect-funcignore: true    # honor .funcignore
```

Per Microsoft docs, on Flex Consumption you set **`remote-build: true`** and must
**not** set `scm-do-build-during-deployment` / `enable-oryx-build`.

### 3.2 `.funcignore` (new)
Excludes `tests/`, `.venv/`, `.github/`, docs, and local settings from the package so
only runtime code is deployed.

### 3.3 `requirements.txt` / `requirements-dev.txt`
- `requirements.txt` now contains **runtime** deps only.
- Test-only deps (`pytest`, `hypothesis`) moved to `requirements-dev.txt` so they are
  not installed on the Function App (faster cold starts, smaller package).

### 3.4 `models/__init__.py` (latent bug)
It imported `ErpResponse` and `ConversationContext`, which **do not exist** in
`models/whatsapp_models.py`. Importing the `models` package raised `ImportError`.
Fixed to export only `WhatsAppMessage`. (The app didn't import `models`, so this
wasn't the outage cause, but it was a real bug.)

### 3.5 `.gitignore` (new)
Prevents committing `.venv/`, `__pycache__/`, and `local.settings.json`.

---

## 4. Verification

**Local (mirrors what Azure's remote build does):**
- Created a Python 3.13 venv, `pip install -r requirements-dev.txt` → clean install.
- `pytest` → **5 passed**.
- Imported `function_app` and indexed routes → **3 functions** discovered.

**Live on Azure (after deploying with remote build):**
- Host status: **Running**; Oryx build step completed; 3 functions registered.
- `GET /api/whatsapp/webhook` (bad token) → **403 Forbidden** (function code ran).
- `POST /api/whatsapp/send` `{}` → **400** `{"error":"Fields 'to' and 'message' are required",...}`.
- `POST /api/whatsapp/send` `{"to":"abc",...}` → **400** `{"error":"Field 'to' must be E.164",...}`.

The app was redeployed directly with `func azure functionapp publish Func-demo --build remote`
to fix the running instance immediately.

---

## 5. Remaining action items (need your input)

### 5.1 Application settings (secrets) — required for full functionality
The host runs, but these env vars are **not set**, so message send / webhook
verification / Logic App forwarding won't work until you add them:

| Setting | Used by | Notes |
|---|---|---|
| `ACS_CONNECTION_STRING` | `services/acs_service.py` | ACS resource connection string |
| `ACS_CHANNEL_ID` | `services/acs_service.py` | WhatsApp channel registration id |
| `META_VERIFY_TOKEN` | `verify_webhook` | Must match the token you set in Meta |
| `LOGIC_APP_ENDPOINT` | `services/logic_app_service.py` | Logic App HTTP trigger URL |
| `GS_APP_ID`, `TENANT_ID` | `logic_app_service.py` | Metadata (optional) |

Set them with:

```bash
az functionapp config appsettings set -g Temp_RG -n Func-demo --settings \
  ACS_CONNECTION_STRING="endpoint=https://<your-acs>.communication.azure.com/;accesskey=<key>" \
  ACS_CHANNEL_ID="<channel-guid>" \
  META_VERIFY_TOKEN="<your-meta-verify-token>" \
  LOGIC_APP_ENDPOINT="<logic-app-url>" \
  GS_APP_ID="<guid>" TENANT_ID="0"
```

Already present: `AzureWebJobsStorage`, `DEPLOYMENT_STORAGE_CONNECTION_STRING`,
`APPLICATIONINSIGHTS_CONNECTION_STRING`.

### 5.2 Push the workflow fix to GitHub
The corrected files are committed locally but the push was blocked because the
GitHub CLI token lacks the **`workflow`** scope (GitHub refuses to update
`.github/workflows/*` without it). One-time grant, then push:

```bash
gh auth refresh -h github.com -s workflow
git push origin main
```

Until this lands, **avoid pushing to `main`** — the old workflow in the repo still has
`remote-build: false` and would redeploy the broken (dependency-less) package.
