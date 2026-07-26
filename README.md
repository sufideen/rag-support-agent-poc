# rag-support-agent-poc

[![Deploy infrastructure](https://github.com/sufideen/rag-support-agent-poc/actions/workflows/deploy.yml/badge.svg)](https://github.com/sufideen/rag-support-agent-poc/actions/workflows/deploy.yml)
[![Security scan](https://github.com/sufideen/rag-support-agent-poc/actions/workflows/security-scan.yml/badge.svg)](https://github.com/sufideen/rag-support-agent-poc/actions/workflows/security-scan.yml)
[![Python CI](https://github.com/sufideen/rag-support-agent-poc/actions/workflows/python-ci.yml/badge.svg)](https://github.com/sufideen/rag-support-agent-poc/actions/workflows/python-ci.yml)

RAG-powered customer support AI agent POC built on Azure AI Foundry
(Azure AI Search, Azure OpenAI, Azure AI Content Safety).

## Can I run this myself?

Not standalone. This repo deploys **into** an existing Zero Trust landing
zone ([ztr-entra-lz](https://github.com/sufideen/ztr-entra-lz)) rather than
provisioning its own network, Key Vault, and Log Analytics workspace — see
"Landing zone dependency" below. To deploy and run the pipeline end to end
you need that landing zone deployed in your own Azure subscription first.
Without it, you can still read through `app/` and `infra/` and run the unit
tests (`pytest` — see "Testing" below), which don't touch Azure at all.

## Prerequisites

- Python 3.9+ (`app/` uses `list[str]`-style built-in generics)
- Azure CLI, logged in (`az login`) with access to the target subscription
- The [ztr-entra-lz](https://github.com/sufideen/ztr-entra-lz) landing zone
  already deployed (see "Can I run this myself?" above)

## Landing zone dependency

This POC deploys **into** the existing [ztr-entra-lz](https://github.com/sufideen/ztr-entra-lz)
Zero Trust landing zone rather than standing up parallel infrastructure. It reuses:

- The landing zone's Key Vault
- The landing zone's Log Analytics workspace
- The landing zone's private endpoint subnet

These are passed in as deployment parameters (`existingKeyVaultName`,
`existingLogAnalyticsName`, `existingPrivateEndpointSubnetId`) — never hardcoded.

## Structure

```
infra/
  main-rag-poc.bicep              # orchestrator
  test-vm.bicep                   # disposable Ubuntu VM for connectivity testing / running app/
  openai-model-deployments.bicep
  modules/
    ai-search.bicep
    azure-openai.bicep
    content-safety.bicep
  scripts/
    provision-test-vm-python.sh   # installs venv + requirements.txt on vm-rag-test
    provision-test-vm-python.ps1  # wrapper: drives the above via `az vm run-command invoke`
app/
  config.py                       # env-var driven config, see .env.example
  create_index.py                 # one-time: (re)creates the AI Search index — run before ingest.py
  ingest.py                       # chunks data/*.md, embeds, upserts into AI Search
  query.py                        # RAG query CLI (retrieve + generate)
  api.py                          # FastAPI wrapper around query.py's logic (HTTP + minimal HTML UI)
tests/                            # unit tests for app/ — no Azure access required
data/
  *.md                            # sample GridPulse Energy support knowledge base
docs/
  architecture.md
.github/workflows/
  deploy.yml
  security-scan.yml
  python-ci.yml
```

See `docs/architecture.md` for how these fit together, including why `app/`
runs from inside the VNet rather than a local dev machine.

## Deploy

Deployment is two phases — the OpenAI account first, then its model
deployments as a separate step. Doing both in one template intermittently
fails with `AccountProvisioningStateInvalid` (see "Build log" below), so
`infra/openai-model-deployments.bicep` is deployed only after the account
from `main-rag-poc.bicep` is confirmed `Succeeded` (this is exactly what
`.github/workflows/deploy.yml`'s `deploy` → `deploy-model-deployments` jobs
automate).

**Step 1 — core infrastructure (Search, OpenAI account, Content Safety):**

```powershell
az deployment group what-if `
  --resource-group "<your-rg>" `
  --template-file "infra\main-rag-poc.bicep" `
  --parameters existingKeyVaultName="<kv-name>" `
               existingLogAnalyticsName="<law-name>" `
               existingPrivateEndpointSubnetId="<subnet-id>" `
               dataPlaneAccessPrincipalId="<principal-id>"
```

Review the `what-if` output, then run with `az deployment group create --name deploy-rag-poc` (same parameters).

**Step 2 — OpenAI model deployments** (run once step 1 shows `Succeeded`):

```powershell
az deployment group create `
  --resource-group "<your-rg>" `
  --template-file "infra\openai-model-deployments.bicep" `
  --parameters openAiAccountName="<name from step 1's openAiName output>"
```

## Running the RAG pipeline

All three data-plane services are private-endpoint-only, so `app/ingest.py` and
`app/query.py` need to run from inside the VNet — in practice, from
`vm-rag-test` (see `infra/scripts/provision-test-vm-python.ps1` to provision
Python there). From wherever you run them:

```bash
az login   # DefaultAzureCredential needs a credential source
cp .env.example .env   # fill in SEARCH_ENDPOINT / OPENAI_ENDPOINT / CONTENT_SAFETY_ENDPOINT from the deployment outputs
export $(grep -v '^#' .env | xargs)

python app/create_index.py                    # one-time: creates the Search index
python app/ingest.py                          # embeds data/*.md into it
python app/query.py "How do I report an outage?"
```

Example output, grounded in `data/outage-reporting.md`:

```
$ python app/query.py "How do I report an outage?"
You can report a power outage in three ways: online via the GridPulse
account portal (fastest, gives a restoration estimate), by calling the
24/7 outage line on 0800 555 0199, or by texting OUTAGE to 60555 with
your postcode. Before reporting, check whether a neighbour has power
(a tripped fuse may be the cause) and the live outage map for known
faults in your area.

$ python app/query.py "What's your refund policy for a broken toaster?"
I don't have that information — please contact GridPulse Energy support
directly for help with that.
```

The second example shows the grounding working as intended: nothing in the
knowledge base covers toaster refunds, so `gpt-5-mini` declines per
`SYSTEM_PROMPT` instead of guessing. Separately, if either the question or
the generated answer is flagged by Content Safety (severity ≥
`SEVERITY_BLOCK_THRESHOLD`), `query.py` short-circuits with a fixed refusal
message instead of ever printing model output.

No API keys are used anywhere — all three services have `disableLocalAuth:
true`, so auth is Entra ID / RBAC only via `DefaultAzureCredential`. Both the
incoming question and the generated answer are also checked against Azure AI
Content Safety before a response is returned.

## Running the web API

Same pipeline, same VNet requirement, same `.env` — just an HTTP front end
(`app/api.py`) instead of a one-shot CLI command:

```bash
uvicorn app.api:app --host 0.0.0.0 --port 8000
```

- `GET /` — a minimal HTML page with a text box, for quick interactive testing.
- `POST /query` — `{"question": "...", "top_k": 3}` → `{"answer": "..."}`.
- `GET /healthz` — liveness check.

This is the natural integration point for anything that needs to call the
agent over HTTP instead of a CLI — a Teams bot, a Copilot Studio custom
connector, or any other M365-side client (see "What's next" below).

## Testing

`app/`'s pure logic and Azure client calls are unit tested with mocks — no
Azure access or deployed infrastructure required:

```bash
pip install -r requirements-dev.txt
ruff check app tests
pytest
```

Runs automatically in CI on every push/PR touching `app/**` or `tests/**`
(`.github/workflows/python-ci.yml`).

## What's next: Microsoft 365 (Teams / Copilot) integration

Since most target customers here are M365 tenants, `app/api.py`'s
`POST /query` is deliberately a plain, stateless HTTP endpoint — the seam
either of these integration paths would call:

- **Teams bot** via the [Teams AI Library](https://microsoft.github.io/teams-ai/)
  or Azure Bot Framework: a bot registered in Entra ID, deployed as an Azure
  Bot resource, whose message handler calls `POST /query` and relays the
  answer back into the Teams conversation. Most control over UX (adaptive
  cards, citations, follow-up prompts).
- **Copilot Studio custom connector / plugin**: wrap `POST /query` as an
  OpenAPI-described action Copilot Studio (or M365 Copilot) can invoke
  directly from a conversation, no separate bot app to host. Faster to stand
  up, less control over the interaction.

Either path needs its own Entra ID app registration and — since the API
still only listens inside the VNet — a way for the bot/connector to reach it
(private endpoint + VNet integration on whatever hosts the bot, or an
internal Application Gateway). Neither is wired up in this repo; picking one
is a tenant/hosting decision for whoever deploys this for real.

## Deployment Evidence

### Infrastructure deployed

All resources deployed into `rg-ictlabs-workload-dev-uksouth`, reusing the [ztr-entra-lz](https://github.com/sufideen/ztr-entra-lz) landing zone's Key Vault (governance RG) and Log Analytics workspace (connectivity RG).

| Resource | Type | Status |
|---|---|---|
| `ragcs-poc-search` | Azure AI Search (basic) | ✅ Succeeded |
| `ragcs-poc-aoai` | Azure OpenAI (gpt-5-mini, text-embedding-3-small) | ✅ Succeeded |
| `ragcs-poc-safety` | Azure AI Content Safety | ✅ Succeeded |

All three deployed with `publicNetworkAccess: 'Disabled'`, private endpoints into `snet-private-links`, and `disableLocalAuth: true` — Entra ID / RBAC only, no API keys.

### Connectivity validation

Private endpoint reachability was validated from inside the VNet using a disposable test VM (`vm-rag-test`, no public IP, deleted after testing) via `az vm run-command invoke` — no Bastion, VPN, or Portal access required:

```
--- AI Search ---
HTTP 401
--- Azure OpenAI ---
HTTP 200
--- Content Safety ---
HTTP 200
```

A `401` on AI Search is expected — it confirms the private endpoint is reachable and the service responded; the request just carried no auth token. All three results confirm DNS resolution, private endpoint routing, and network connectivity are correctly wired end to end, and — just as importantly — that these endpoints are *not* reachable from outside the VNet, per the Zero Trust design.

### Build log — issues hit and fixed

Deploying this wasn't a single clean run. Worth documenting the real issues, since debugging them is as much the point of this POC as the final result:

1. **Cross-resource-group references** — the landing zone splits Key Vault (governance RG) and Log Analytics (connectivity RG) across different resource groups from the workload RG this deploys into. Fixed with explicit `scope: resourceGroup(...)` on the `existing` resource references in Bicep, using two separate RG parameters rather than assuming both lived in one place.

2. **Model deprecation mid-build** — Azure began blocking new deployments of `gpt-4o-mini` (2024-07-18) ahead of its official retirement date. Switched the chat deployment to `gpt-5-mini` (2025-08-07), the current GA successor.

3. **Principal type mismatch** — RBAC role assignments were hardcoded to `principalType: 'ServicePrincipal'`, but testing used a user account. Parameterized `dataPlaneAccessPrincipalType` so the same template supports both interactive testing (`User`) and CI/CD service principals later.

4. **OpenAI account provisioning race** — deploying the Cognitive Services account and its model deployments in the same Bicep template intermittently failed with `AccountProvisioningStateInvalid`, because ARM's implicit dependency ordering doesn't wait for the account to fully settle before deploying child resources. Fixed by splitting into two separate deployments: the account first, confirmed `Succeeded`, then the model deployments against the existing account.

### Security scanning

IaC security scanning via [PSRule for Azure](https://azure.github.io/PSRule.Rules.Azure/) and [Checkov](https://www.checkov.io/) runs on every push to `infra/**` — see `.github/workflows/security-scan.yml`. Findings surface in the repo's [Security tab](../../security/code-scanning).

