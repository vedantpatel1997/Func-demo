# Func-demo — Deployment Fix & Analysis

**App:** `Func-demo` (Azure Functions, **Flex Consumption**, Python **3.13**, region westus2)
**Resource group:** `Temp_RG`
**Repo:** https://github.com/vedantpatel1997/Func-demo
**Default host:** `func-demo-gmhhhvh0gcghc6b2.westus2-01.azurewebsites.net`

---

## 1. Symptom

Every HTTP call to the app returned an error and no functions were reachable:

```
GET  /                       -> HTTP 502
GET  /api/whatsapp/webhook   -> HTTP 503  "Function host is not running."
POST /api/whatsapp/send      -> HTTP 503  "Function host is not running."
```

The runtime log showed the real cause:

```
Microsoft.Azure.WebJobs.Script: Error building configuration in an external startup class.
ModuleNotFoundError: No module named 'azure.communication'
  File "/home/site/wwwroot/services/acs_service.py", line 5, in <module>
    from azure.communication.messages import NotificationMessagesClient
sys.path: /home/site/wwwroot/.python_packages/lib/site-packages  ...
```

The Python worker could not import `azure.communication`, so indexing the function app
failed, the host never started, and **0 functions** were registered.

---

## 2. Root cause

**The deployed package contained no dependencies.** `.python_packages/lib/site-packages`
(where Azure looks for Python packages) shipped effectively empty.

The GitHub Actions workflow was building the package incorrectly for a **Flex Consumption**
app:

1. It created a virtual environment and ran `pip install` **in a separate `run:` step**.
   Each `run:` step is a fresh shell, so the `source venv/bin/activate` from the previous
   step was already gone — `pip install` installed into the runner's system Python, not the
   venv, and **not** into the deployment package.
2. It then zipped `./*`, which captured a `venv/` folder that contained **only pip**
   (confirmed in the deploy log: `venv/lib64/python3.13/site-packages/pip-26.1.2...` and
   nothing else). Azure does not load packages from `venv/` anyway — it loads them from
   `.python_packages/lib/site-packages`.
3. The deploy step ran with **`remote-build: false`**, so Azure did **not** run a build
   (Oryx `pip install`) on the platform either.

Net effect: source code was deployed with no usable dependencies → `import azure.communication`
fails → host down.

### Why `remote-build` matters on Flex Consumption
On the **Flex Consumption** plan the correct pattern is to let the platform build the
dependencies remotely. Per Microsoft's docs for `Azure/functions-action`:

> **remote-build** — Set this to `true` to enable a build action from Kudu when the package is
> deployed to a Flex Consumption app. Oryx build is always performed during a remote build in
> Flex Consumption; **don't set `scm-do-build-during-deployment` or `enable-oryx-build`.**

With `remote-build: true`, Azure receives the source + `requirements.txt`, runs
`pip install -r requirements.txt` on the real Python 3.13 Linux target (correct manylinux
wheels for native packages like `cryptography`/`cffi`), and populates
`.python_packages/lib/site-packages`.

---

## 3. Secondary issues found

| # | Issue | Impact | Fix |
|---|-------|--------|-----|
| A | `models/__init__.py` imported `ErpResponse` and `ConversationContext`, which don't exist in `whatsapp_models.py`. | `ImportError` **if** anything imports `models`. Not the production failure (nothing imports it today) but a latent landmine. | Export only `WhatsAppMessage`. |
| B | Test/dev packages (`pytest`, `hypothesis`) were in `requirements.txt`. | Installed onto the Function App at runtime — slower cold start, larger build, unnecessary. | Split into `requirements-dev.txt`; keep runtime deps lean. |
| C | `azure-communication-chat` was in `requirements.txt` but never imported. | Dead dependency. | Removed (verified no `azure.communication.chat` usage). |
| D | No `.funcignore`. | venv/tests/docs could be shipped to Azure. | Added `.funcignore` + `respect-funcignore: true`. |
| E | Missing runtime **app settings** (secrets). | Host starts and all 3 functions load, but real WhatsApp send/verify won't work until set. See §6. | Documented; user supplies secret values. |

---

## 4. What was changed

Commit `Fix Flex Consumption deployment: enable Oryx remote build`:

- **`.github/workflows/main_func-demo.yml`** — rewritten:
  - Removed the broken venv/pip/zip build.
  - Deploy step now uses **`remote-build: true`** and **`respect-funcignore: true`**
    (kept `sku: flexconsumption`, correct `app-name: Func-demo`, and the existing
    publish-profile secret).
  - Added a CI pre-flight that installs deps and runs `pytest` + `import function_app`
    so a broken build fails in CI **before** it can take the app down.
- **`models/__init__.py`** — export only `WhatsAppMessage` (fixes the `ImportError`).
- **`requirements.txt`** — runtime-only, trimmed dead deps.
- **`requirements-dev.txt`** — `pytest`, `hypothesis` (+ `-r requirements.txt`).
- **`.funcignore`** — excludes `venv/`, `tests/`, docs, local settings from the package.
- **`.gitignore`** — standard Python/Azure ignores.

---

## 5. Verification

**Local (Python 3.13):**
- `pip install -r requirements.txt` → all deps resolve on 3.13. ✅
- `python -c "import function_app"` → imports cleanly (reproduces the exact Azure import
  chain that was failing). ✅
- `python -c "import models"` → now imports (was `ImportError`). ✅
- `pytest -q` → **5 passed**. ✅

**Live deployment** (deployed directly to Azure with remote build —
`az functionapp deployment source config-zip ... --build-remote true`):

Before the fix:
```
GET /api/whatsapp/webhook  -> HTTP 503  "Function host is not running."
az functionapp function list -> (empty, 0 functions)
```

After the fix:
```
az functionapp function list ->
    Func-demo/verify_webhook
    Func-demo/receive_message
    Func-demo/send_message                     # all 3 functions indexed ✅

GET  /api/whatsapp/webhook  (no key)           -> HTTP 401  (host up, auth enforced) ✅
GET  /api/whatsapp/webhook?...&code=<key>      -> function logic runs (403 for bad token) ✅
POST /api/whatsapp/send?code=<key>  {"to":"abc"} ->
     HTTP 400 {"error":"Field 'to' must be E.164","correlationId":"<uuid>"}   ✅
```

The 503 "Function host is not running" is gone and the deployed function code executes
end-to-end — proving `azure.communication`, `httpx`, and all dependencies are now present
in `.python_packages/lib/site-packages`. App **state: Running**.

---

## 6. Required app settings (to complete WhatsApp functionality)

The host starts without these, but the WhatsApp flows need them. Set with:

```bash
az functionapp config appsettings set -g Temp_RG -n Func-demo --settings \
  ACS_CONNECTION_STRING="endpoint=https://<your-acs>.communication.azure.com/;accesskey=<KEY>" \
  ACS_CHANNEL_ID="<channel-registration-guid>" \
  META_VERIFY_TOKEN="<your-webhook-verify-token>" \
  LOGIC_APP_ENDPOINT="https://<your-logic-app-trigger-url>" \
  TENANT_ID="<int>" \
  GS_APP_ID="<guid>"
```

Optional tunables (have safe code defaults): `LOGIC_APP_TIMEOUT_SECONDS`,
`LOGIC_APP_RETRY_ATTEMPTS`, `LOGIC_APP_RETRY_BACKOFF_SECONDS`,
`WEBHOOK_MAX_BODY_BYTES`, `OUTBOUND_MAX_MESSAGE_LENGTH`.
`APPLICATIONINSIGHTS_CONNECTION_STRING` and `AzureWebJobsStorage` are already set.

---

## 7. Pushing the fix through GitHub (CD pipeline)

The fix is committed locally. Pushing it updates `.github/workflows/`, which GitHub blocks
for credentials without the **`workflow`** scope. To push from your machine:

```bash
# grant the workflow scope once (interactive), then push:
gh auth refresh -h github.com -s workflow
git push origin main
```

Pushing triggers the corrected workflow, which redeploys with remote build. (The app was
also deployed directly to Azure — see §5 — so it is already working regardless.)

> ⚠️ **Regression risk:** `origin/main` on GitHub still has the **old, broken** workflow
> (`remote-build: false`). The corrected workflow lives only in the local, unpushed commit
> `c03c8ec`. The live app is fine now, but if the old workflow is ever re-run (e.g. a
> "Re-run jobs" in the Actions tab, or a push that doesn't include the fix), it will
> redeploy the dependency-less package and break the app again. **Push `c03c8ec` to make
> GitHub's pipeline correct.** Until then, don't re-run the old workflow.

---

## 8. Endpoints (after fix)

| Method | Route | Purpose |
|--------|-------|---------|
| GET  | `/api/whatsapp/webhook` | Meta webhook verification (needs `META_VERIFY_TOKEN`). |
| POST | `/api/whatsapp/webhook` | Inbound WhatsApp messages → forwarded to Logic App. |
| POST | `/api/whatsapp/send`    | Outbound send via ACS (needs `ACS_*`). Function-key auth. |

All routes are `AuthLevel.FUNCTION` and prefixed with `/api` (from `host.json`).
