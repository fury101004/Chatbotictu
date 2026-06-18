# Azure deployment guide

This project is currently a single FastAPI app that also renders the Jinja
frontend from `views/frontend`. Deploy it as one Azure App Service for the demo.
Do not deploy `views/frontend` to Azure Static Web Apps unless the UI is later
refactored into a standalone SPA build.

## Verified local commands

```powershell
.\venv\Scripts\python.exe -m pip check
.\venv\Scripts\python.exe -c "import main; print(type(main.app).__name__); print(main.app.title)"
.\venv\Scripts\python.exe -m pytest tests\test_chat_api_endpoints.py tests\test_runtime_config.py tests\test_rag_upload_flow.py
.\venv\Scripts\python.exe -m uvicorn config.asgi:app --host 0.0.0.0 --port 8000 --workers 1
```

Health check:

```powershell
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/v1/health" -UseBasicParsing
```

## Required Azure App Settings (all deploy modes)

On Azure App Service Linux, `/home/site` is **read-only**. Never point HuggingFace
cache or ChromaDB persistence there. Use `/home/data/...` (persistent storage).

```text
VECTORSTORE_DIR=/home/data/vectorstore
HF_HOME=/home/data/hf-cache
HUGGINGFACE_HUB_CACHE=/home/data/hf-cache/hub
TRANSFORMERS_CACHE=/home/data/transformers
SENTENCE_TRANSFORMERS_HOME=/home/data/sentence-transformers
TORCH_HOME=/home/data/.cache/torch
XDG_CACHE_HOME=/home/data/.cache
```

`startup.sh` and `config.settings` also redirect bad `/home/site` paths automatically,
but setting the values above in App Settings makes Log stream debugging easier.

After deployment, the production app auto-syncs the seed corpus on startup when
`ENVIRONMENT=production`, so handbook edits are picked up without a manual re-index.
Keep the demo App Service on one instance because SQLite and ChromaDB are local
persistent files in this mode.

## Web App for Containers from GHCR (recommended)

Use this path when the Docker image has already been built by GitHub Actions.
The image pre-downloads `paraphrase-multilingual-MiniLM-L12-v2` at build time and
starts through `startup.sh`.

### Example: `ictu-chatbot-xuanluc`

```powershell
$RG="rg-ictu-chatbot"
$LOC="southeastasia"
$PLAN="asp-ictu-chatbot"
$APP="ictu-chatbot-xuanluc"
$IMAGE="ghcr.io/fury101004/chatbotictu:latest"

az group create --name $RG --location $LOC
az appservice plan create --name $PLAN --resource-group $RG --location $LOC --is-linux --sku B2
az webapp create `
  --resource-group $RG `
  --plan $PLAN `
  --name $APP `
  --deployment-container-image-name $IMAGE

az webapp config appsettings set --resource-group $RG --name $APP --settings `
  WEBSITES_PORT=8000 `
  PORT=8000 `
  ENVIRONMENT=production `
  WEB_CONCURRENCY=1 `
  DATA_DIR=/home/site/data `
  LOG_DIR=/home/LogFiles `
  UPLOAD_DIR=/home/site/data/uploads `
  RAG_UPLOAD_ROOT=/home/site/data/rag_uploads `
  DB_PATH=/home/site/data/bot_config.db `
  VECTORSTORE_DIR=/home/data/vectorstore `
  API_LOG_PATH=/home/LogFiles/api.log `
  HF_HOME=/home/data/hf-cache `
  HUGGINGFACE_HUB_CACHE=/home/data/hf-cache/hub `
  TRANSFORMERS_CACHE=/home/data/transformers `
  SENTENCE_TRANSFORMERS_HOME=/home/data/sentence-transformers `
  TORCH_HOME=/home/data/.cache/torch `
  XDG_CACHE_HOME=/home/data/.cache `
  CORS_ALLOW_ORIGINS=https://$APP.azurewebsites.net `
  LLM_PROVIDER_ORDER=groq `
  GROQ_API_BASE_URL=https://api.groq.com/openai/v1 `
  PARTNER_API_KEY="<REDACTED_SECRET>" `
  JWT_SECRET="<REDACTED_SECRET>" `
  SESSION_SECRET="<REDACTED_SECRET>" `
  ADMIN_USERNAME="admin@ictu.edu.vn" `
  ADMIN_PASSWORD="<REDACTED_SECRET>" `
  USER_USERNAME="student" `
  USER_PASSWORD="<REDACTED_SECRET>" `
  GROQ_API_KEY="<REDACTED_SECRET>"
```

If the GHCR package is private, configure registry credentials separately or
make the package public from GitHub Packages before creating the web app.

Smoke check:

```powershell
Invoke-WebRequest -Uri "https://$APP.azurewebsites.net/api/v1/health" -UseBasicParsing
```

### After updating the container image

Push a new image tag to GHCR (GitHub Actions workflow `docker-image.yml` on
`main`), then restart the web app:

```powershell
az webapp restart --resource-group $RG --name $APP
```

## Azure App Service zip deploy

Replace all placeholder values before running these commands.
Prerequisites: Azure CLI installed, `az login` completed, and an active
subscription selected with `az account set --subscription "<subscription-id>"`.

```powershell
$RG="rg-ictu-chatbot"
$LOC="southeastasia"
$PLAN="asp-ictu-chatbot"
$APP="ictu-chatbot-api"

az group create --name $RG --location $LOC
az appservice plan create --name $PLAN --resource-group $RG --location $LOC --is-linux --sku B2
az webapp create --name $APP --resource-group $RG --plan $PLAN --runtime "PYTHON:3.11"

az webapp config set `
  --resource-group $RG `
  --name $APP `
  --startup-file 'sh startup.sh'
```

Set application settings. Keep real secret values outside the repository.

```powershell
az webapp config appsettings set --resource-group $RG --name $APP --settings `
  SCM_DO_BUILD_DURING_DEPLOYMENT=true `
  ENVIRONMENT=production `
  PORT=8000 `
  WEB_CONCURRENCY=1 `
  DATA_DIR=/home/site/data `
  LOG_DIR=/home/LogFiles `
  UPLOAD_DIR=/home/site/data/uploads `
  RAG_UPLOAD_ROOT=/home/site/data/rag_uploads `
  DB_PATH=/home/site/data/bot_config.db `
  VECTORSTORE_DIR=/home/data/vectorstore `
  API_LOG_PATH=/home/LogFiles/api.log `
  HF_HOME=/home/data/hf-cache `
  HUGGINGFACE_HUB_CACHE=/home/data/hf-cache/hub `
  TRANSFORMERS_CACHE=/home/data/transformers `
  SENTENCE_TRANSFORMERS_HOME=/home/data/sentence-transformers `
  TORCH_HOME=/home/data/.cache/torch `
  XDG_CACHE_HOME=/home/data/.cache `
  CORS_ALLOW_ORIGINS=https://$APP.azurewebsites.net `
  LLM_PROVIDER_ORDER=groq `
  GROQ_API_BASE_URL=https://api.groq.com/openai/v1 `
  PARTNER_API_KEY="<REDACTED_SECRET>" `
  JWT_SECRET="<REDACTED_SECRET>" `
  SESSION_SECRET="<REDACTED_SECRET>" `
  ADMIN_USERNAME="admin@ictu.edu.vn" `
  ADMIN_PASSWORD="<REDACTED_SECRET>" `
  USER_USERNAME="student" `
  USER_PASSWORD="<REDACTED_SECRET>" `
  GROQ_API_KEY="<REDACTED_SECRET>"
```

Create a zip package from tracked source only. This keeps `.env`, local SQLite,
logs, uploads, model cache, and local vector stores out of the deployment.

```powershell
git archive --format zip -o app.zip HEAD
az webapp deploy --resource-group $RG --name $APP --src-path app.zip
```

## GitHub Actions deploy

The workflow is in `.github/workflows/azure-app-service.yml`.

Add these GitHub repository secrets:

```text
AZURE_WEBAPP_NAME=<your-app-service-name>
AZURE_WEBAPP_PUBLISH_PROFILE=<downloaded publish profile XML>
```

The workflow runs smoke tests, builds `release.zip`, and deploys it to App
Service. Configure Azure App Settings separately with the values shown above.

## Docker container deploy (ACR)

The Docker image starts through `startup.sh`, so App Service can pass `PORT`.

```powershell
$ACR="ictuchatbotacr"
az acr create --resource-group $RG --name $ACR --sku Basic
az acr build --registry $ACR --image ictu-chatbot:latest .

az webapp create `
  --resource-group $RG `
  --plan $PLAN `
  --name $APP `
  --deployment-container-image-name "$ACR.azurecr.io/ictu-chatbot:latest"

az webapp config appsettings set --resource-group $RG --name $APP --settings `
  WEBSITES_PORT=8000 `
  PORT=8000 `
  VECTORSTORE_DIR=/home/data/vectorstore `
  HF_HOME=/home/data/hf-cache `
  HUGGINGFACE_HUB_CACHE=/home/data/hf-cache/hub `
  TRANSFORMERS_CACHE=/home/data/transformers `
  SENTENCE_TRANSFORMERS_HOME=/home/data/sentence-transformers `
  TORCH_HOME=/home/data/.cache/torch `
  XDG_CACHE_HOME=/home/data/.cache
```

## Troubleshooting embedding PermissionError

Symptom on Knowledge Base dashboard:

```text
Vector store is temporarily unavailable: PermissionError at /home/site when downloading sentence-transformers/...
```

Checklist:

1. Confirm App Settings use `/home/data/...` paths (see section above), not `/home/site/vectorstore`.
2. Open **Log stream** and verify startup lines:
   - `=== Azure Startup Paths (before Python boot) ===`
   - `[CACHE] Bootstrapping Azure App Service paths...`
   - `[EMBEDDING] Cache state (before_load):` with `writable` status
3. For container deploy, pull a fresh `ghcr.io/fury101004/chatbotictu:latest` image
   (model is baked in at build time).
4. If a download was interrupted, remove lock files via SSH/Kudu:

```bash
find /home/data/hf-cache -name "*.lock" -delete
find /tmp/huggingface -name "*.lock" -delete 2>/dev/null || true
```

5. Restart the web app after changing settings.

## Bundled data deploy (vectorstore / knowledge base)

The Docker image must include bundled artifacts from git:

- `vectorstore/` (ChromaDB + `chroma.sqlite3`)
- `clean_data/`, `datapdf/` (source corpus)
- `data/rag_uploads/` (approved upload snapshots)
- `data/bot_config.db` (chat Q&A / review state)

On first Azure boot, `startup.sh` seeds persistent storage:

| Image path | Azure persistent path | Condition |
|------------|----------------------|-----------|
| `/app/vectorstore` | `/home/data/vectorstore` | no `chroma.sqlite3` yet |
| `/app/data/rag_uploads` | `$RAG_UPLOAD_ROOT` | dest empty |
| `/app/data/bot_config.db` | `$DB_PATH` | file missing |

Redeploys do **not** overwrite existing `/home/data/vectorstore` (data survives).

Debug endpoint (admin login required):

```text
GET /admin/vectorstore-status
```

Log stream on boot should show:

```text
[BOOT] VECTORSTORE_DIR=/home/data/vectorstore
[BOOT] chroma.sqlite3 exists=True
[BOOT] collections=1
[BOOT] chunks=2541
```

## Production work still required

- Move SQLite data in `config/db.py` to Azure Database for PostgreSQL.
- Move uploads and approved knowledge files to Azure Blob Storage.
- Move ChromaDB local vector data to Azure AI Search or PostgreSQL pgvector.
- Move in-memory rate limiting and job state to Azure Cache for Redis.
- Add database migrations with Alembic.
- Add Azure Application Insights or structured stdout logging.
