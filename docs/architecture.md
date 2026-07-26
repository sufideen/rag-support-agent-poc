# Architecture

## Overview

A RAG-powered customer support agent for a fictional utility ("GridPulse Energy"),
built on Azure AI Foundry components, deployed into the existing
[ztr-entra-lz](https://github.com/sufideen/ztr-entra-lz) Zero Trust landing zone
rather than standing up parallel infrastructure.

```
data/*.md  --ingest.py-->  Azure AI Search index (vector + keyword)
                                     ^
                                     | retrieve top-k chunks
                                     |
customer question --query.py--> [Content Safety: question] --> Azure OpenAI (gpt-5-mini)
                                     ^                                    |
                                     | embed question / chunks           v
                                     |                    [Content Safety: answer] --> grounded answer
                          Azure OpenAI (text-embedding-3-small)
```

## Components

| Component | Bicep module | Purpose |
|---|---|---|
| Azure AI Search (basic) | `infra/modules/ai-search.bicep` | Vector + keyword index over the support knowledge base |
| Azure OpenAI | `infra/modules/azure-openai.bicep`, `infra/openai-model-deployments.bicep` | `gpt-5-mini` for answer generation, `text-embedding-3-small` for embeddings |
| Azure AI Content Safety | `infra/modules/content-safety.bicep` | Moderates both the incoming question and the generated answer in `app/query.py` before either reaches the customer |
| Test VM | `infra/test-vm.bicep` | Disposable Ubuntu 24.04 VM inside the VNet, used to validate private-endpoint connectivity and to run `app/` scripts (see below) |

All three data-plane services are deployed with `publicNetworkAccess: 'Disabled'`,
private endpoints into `snet-private-links`, and `disableLocalAuth: true` — Entra ID
/ RBAC only, no API keys, not reachable from outside the VNet.

## Why `app/` runs from the test VM, not the dev machine

Because the services above have no public network access, a Windows dev machine
outside the VNet cannot call them directly. `app/ingest.py` and `app/query.py` are
written to run from inside the VNet — in practice, from `vm-rag-test` — using
`infra/scripts/provision-test-vm-python.sh` (installs the venv and
`requirements.txt`) via `az vm run-command invoke`, since the VM has no public IP
and no SSH/Bastion access.

## RAG pipeline (`app/`)

- `app/config.py` — reads endpoints/deployment names from environment variables
  (see `.env.example`); no secrets, since auth is Entra ID only.
- `app/create_index.py` — **run once, before `ingest.py`.** Defines and
  (re)creates the `gridpulse-support-docs` index: `content` (searchable text),
  `content_vector` (HNSW vector field), plus `source`/`category`/`chunk_index`
  for filtering and facets. Deletes and recreates the index if it already
  exists, so the schema can be iterated on during development.
- `app/ingest.py` — chunks `data/*.md` on `##` section boundaries, embeds each
  chunk with `text-embedding-3-small`, and upserts into the index created by
  `create_index.py` (fails with a clear error if that index doesn't exist
  yet).
- `app/query.py` — moderates the incoming question with Content Safety first
  (refuses without calling Search/OpenAI if flagged), embeds it, retrieves the
  top-k chunks via Search's vector query, asks `gpt-5-mini` to answer using
  only that context, then moderates the generated answer before printing it.
  Both moderation checks use `SEVERITY_BLOCK_THRESHOLD = 4` — Azure's own
  recommended "medium" default on Content Safety's 0/2/4/6 severity scale.

All three authenticate via `DefaultAzureCredential` against the RBAC roles the
Bicep already grants to `dataPlaneAccessPrincipalId` (`Search Index Data
Contributor`, `Cognitive Services OpenAI User`, `Cognitive Services User`).

## Known gap: auth from inside the VM

`DefaultAzureCredential` needs a credential source it can actually use. Two
options, neither wired up yet:

1. **Interactive `az login` on the VM** (device-code flow) — works only if the
   Zero Trust firewall allows outbound to the Entra ID login endpoints even
   though general internet (e.g. PyPI) may be blocked. Simplest for one-off
   testing.
2. **System-assigned managed identity on the VM**, granted the same
   `Search Index Data Contributor` / `Cognitive Services OpenAI User` roles as
   `dataPlaneAccessPrincipalId` in `infra/test-vm.bicep` — more appropriate if
   the VM becomes a longer-lived execution environment, but not yet
   implemented since it grants a disposable VM standing data-plane access and
   should be a deliberate decision, not a default.

## CI/CD

- `.github/workflows/deploy.yml` — `az deployment group what-if` then
  `az deployment group create` against `infra/main-rag-poc.bicep`, followed
  by a `deploy-model-deployments` job that deploys
  `infra/openai-model-deployments.bicep` against the now-`Succeeded` OpenAI
  account — via OIDC federated login (no stored secrets beyond
  client/tenant/subscription IDs).
- `.github/workflows/security-scan.yml` — PSRule for Azure + Checkov against
  `infra/**` on every push/PR touching it.
- `.github/workflows/python-ci.yml` — `ruff check` + `pytest` against `app/**`
  and `tests/**` on every push/PR touching them.

## Not yet done

- No web/API front end — `app/query.py` is a CLI only.
