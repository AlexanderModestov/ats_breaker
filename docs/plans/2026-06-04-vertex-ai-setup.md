# Vertex AI (Agent Platform) Setup Plan

**Goal:** Provision a GCP project with Vertex AI enabled so HR-Breaker can call Gemini models via the `google-vertex:` pydantic-ai provider.

**Architecture:** HR-Breaker uses pydantic-ai with `google-vertex:gemini-*` model strings. Authentication is via Application Default Credentials (ADC) locally and a service account JSON on Railway/production. No API key is used — billing and IAM replace it.

**Note on naming:** Google's Cloud Console now surfaces Vertex AI under the **"Agent Platform"** section in the left nav. The underlying API (`aiplatform.googleapis.com`) and SDK are unchanged — just follow the "Agent Platform" label in the UI where noted below.

---

## Task 1: Create or select a GCP project

**Where:** [console.cloud.google.com](https://console.cloud.google.com)

**Step 1: Create the project**

1. Click the project picker in the top bar → **New Project**
2. Project name: `hr-breaker-prod` (or similar)
3. Note the **Project ID** (auto-generated, e.g. `hr-breaker-prod-123456`) — this is what goes in `GOOGLE_CLOUD_PROJECT`, not the display name
4. Click **Create**

**Step 2: Confirm you're in the right project**

The project picker in the top bar should now show your new project name. All following steps must be done inside this project.

---

## Task 2: Enable billing

**Where:** Google Cloud Console → Billing

**Step 1: Open billing**

Left nav → **Billing** (or search "Billing" in the top search bar)

**Step 2: Link a billing account**

Click **Link a billing account** → select or create a billing account → **Set account**.

Vertex AI has no free tier. Requests return `RESOURCE_EXHAUSTED` or `PERMISSION_DENIED` without an active billing account.

**Step 3: Set up a budget alert (recommended)**

Billing → **Budgets & alerts** → **Create budget**

| Field | Value |
|---|---|
| Scope | This project only |
| Amount | Set a monthly cap you're comfortable with |
| Alert thresholds | 50%, 90%, 100% |
| Notifications | Your email |

---

## Task 3: Enable the Vertex AI API

**Where:** Google Cloud Console → APIs & Services → Enabled APIs

**Step 1: Open API library**

Left nav → **APIs & Services** → **Library** (or search "Vertex AI API" in the top search bar)

**Step 2: Enable the API**

Search `Vertex AI API` → click result → **Enable**

Alternatively via CLI:

```bash
gcloud services enable aiplatform.googleapis.com --project=YOUR_PROJECT_ID
```

**Step 3: Verify**

APIs & Services → **Enabled APIs and services** → confirm `Vertex AI API` appears in the list.

---

## Task 4: Set up authentication

### Option A — Local development (your own Google account)

Run once on your machine:

```bash
gcloud auth application-default login
```

A browser window opens. Sign in with the Google account that has access to the GCP project. ADC credentials are saved to `~/.config/gcloud/application_default_credentials.json`. No env vars needed locally beyond `GOOGLE_CLOUD_PROJECT`.

### Option B — Production / Railway (service account)

**Step 1: Create a service account**

Google Cloud Console → **IAM & Admin** → **Service Accounts** → **Create Service Account**

| Field | Value |
|---|---|
| Name | `hr-breaker-api` |
| Description | Used by HR-Breaker Railway service |

**Step 2: Grant the required role**

On the same creation screen (or IAM → Grant Access later):

| Role | Why |
|---|---|
| **Vertex AI User** (`roles/aiplatform.user`) | Call Gemini models via Vertex AI API |

**Step 3: Create a JSON key**

Service Accounts list → click `hr-breaker-api` → **Keys** tab → **Add Key** → **Create new key** → **JSON** → Download.

Keep this file secret — it grants API access. Do not commit it to git.

**Step 4: Set it on Railway**

Railway dashboard → your service → **Variables** → add:

```
GOOGLE_APPLICATION_CREDENTIALS_JSON=<paste entire contents of the downloaded JSON file>
```

Then in your app startup (or a Railway build command), write it to disk:

```bash
echo "$GOOGLE_APPLICATION_CREDENTIALS_JSON" > /tmp/gcp-key.json
export GOOGLE_APPLICATION_CREDENTIALS=/tmp/gcp-key.json
```

Or load it directly in Python at app startup (before any Vertex AI calls):

```python
import json, os, google.auth
from google.oauth2 import service_account

if creds_json := os.getenv("GOOGLE_APPLICATION_CREDENTIALS_JSON"):
    info = json.loads(creds_json)
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    import google.auth.transport.requests  # noqa
```

---

## Task 5: Set environment variables

**Local `.env`:**

```env
GOOGLE_CLOUD_PROJECT=hr-breaker-prod-123456
# GOOGLE_CLOUD_LOCATION=us-central1   # default, omit unless changing region
```

**Railway Variables:**

| Variable | Value |
|---|---|
| `GOOGLE_CLOUD_PROJECT` | Your Project ID |
| `GOOGLE_CLOUD_LOCATION` | `us-central1` (or your chosen region) |
| `GOOGLE_APPLICATION_CREDENTIALS_JSON` | Contents of service account JSON key |

---

## Task 6: Choose a region

| Region | Notes |
|---|---|
| `us-central1` | Default, all Gemini models available, cheapest egress |
| `europe-west4` | Netherlands, EU data residency, check model availability |
| `asia-northeast1` | Tokyo, for APAC latency |

Set via `GOOGLE_CLOUD_LOCATION`. If omitted, pydantic-ai defaults to `us-central1`.

To check which Gemini models are available in a region:

Google Cloud Console → **Agent Platform** (left nav) → **Model Garden** → filter by region.

---

## Task 7: Verify the connection

```bash
uv run python - <<'EOF'
import vertexai
import os

project = os.environ["GOOGLE_CLOUD_PROJECT"]
location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
vertexai.init(project=project, location=location)
print(f"OK — project={project} location={location}")
EOF
```

Expected output: `OK — project=hr-breaker-prod-123456 location=us-central1`

If you see `DefaultCredentialsError` → run `gcloud auth application-default login` (local) or check `GOOGLE_APPLICATION_CREDENTIALS` (production).

If you see `PERMISSION_DENIED` → billing is not linked or the Vertex AI API is not enabled.

---

## Task 8: Smoke-test with pydantic-ai

```bash
uv run python - <<'EOF'
import asyncio
from pydantic_ai import Agent

agent = Agent("google-vertex:gemini-2.0-flash")

async def main():
    result = await agent.run("Reply with just: OK")
    print(result.output)

asyncio.run(main())
EOF
```

Expected output: `OK`

---

## Where to find things in the new Console UI

Google renamed several sections. If a step says "Vertex AI" but you don't see it, look for:

| Old label | New label in Console |
|---|---|
| Vertex AI → Model Garden | **Agent Platform** → Model Garden |
| Vertex AI → Online predictions | **Agent Platform** → Online Predictions |
| Vertex AI → Pipelines | **Agent Platform** → Pipelines |
| Vertex AI API (in API Library) | Still listed as **Vertex AI API** (`aiplatform.googleapis.com`) |
| IAM role "Vertex AI User" | Still named **Vertex AI User** in IAM |

The underlying API name, SDK package (`google-cloud-aiplatform`), and pydantic-ai provider string (`google-vertex:`) are unchanged — only the Console navigation label has been updated.

---

## Summary

| Task | Effort | Blocker if skipped |
|---|---|---|
| 1 — Create project | 2 min | All other tasks fail |
| 2 — Enable billing | 2 min | All API calls return 403 |
| 3 — Enable Vertex AI API | 1 min | All API calls return 403 |
| 4A — ADC login (local) | 1 min | Local dev fails |
| 4B — Service account (prod) | 5 min | Railway deployment fails |
| 5 — Set env vars | 1 min | pydantic-ai can't find project |
| 6 — Choose region | 0 min | Default `us-central1` is fine |
| 7 — Verify connection | 1 min | — |
| 8 — Smoke test | 1 min | — |
