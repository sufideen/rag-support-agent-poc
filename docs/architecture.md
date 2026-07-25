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
customer question --query.py--> Azure OpenAI (gpt-5-mini) --> grounded answer
                                     ^
                                     | embed question / chunks
                                     |
                          Azure OpenAI (text-embedding-3-small)
```

## Components

| Component | Bicep module | Purpose |
|---|---|---|
| Azure AI Search (basic) | `infra/modules/ai-search.bicep` | Vector + keyword index over the support knowledge base |
| Azure OpenAI | `infra/modules/azure-openai.bicep`, `infra/openai-model-deployments.bicep` | `gpt-5-mini` for answer generation, `text-embedding-3-small` for embeddings |
| Azure AI Content Safety | `infra/modules/content-safety.bicep` | Provisioned for future input/output moderation — not yet wired into `app/` |
| Test VM | `infra/test-vm.bicep` | Disposable Ubuntu 24.04 VM inside the VNet, used to validate private-endpoint connectivity and to run `app/` scripts (see below) |

All three data-plane services are deployed with `publicNetworkAccess: 'Disabled'`,
private endpoints into `snet-private-links`, and `disableLocalAuth: true` — Entra ID
/ RBAC only, no API keys, not reachable from outside the VNet.

## Why `app/` runs from the test VM, not the dev machine

Because the services above have no public network access, a Windows dev machine
outside the VNet cannot call them directly. `app/ingest.py` and `app/query.py` are
written to run from inside the VNet — in practice, from `vm-rag-test` — using
`infra/scripts/provision-test-vm-python.sh` (installs the venv and
`requirements.txt`) via `az vm run-command invoke`, since the VM has no public IP.
For anything interactive (`az login`, ad hoc debugging), `infra/bastion-dev.bicep`
(Bastion Developer SKU) gives a browser-based SSH session — see the README's
"Connecting to vm-rag-test interactively" section.

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
- `app/query.py` — embeds the incoming question, retrieves the top-k chunks via
  Search's vector query, and asks `gpt-5-mini` to answer using only that
  context.

Both authenticate via `AzureCliCredential` against the RBAC roles the Bicep
already grants to `dataPlaneAccessPrincipalId` (`Search Index Data Contributor`,
`Cognitive Services OpenAI User`) — auth on the VM is interactive `az login`
(device-code flow via a Bastion session; see "Connecting to vm-rag-test
interactively" in the README).

## Resolved gap: DefaultAzureCredential picked the wrong identity

The scripts originally used `DefaultAzureCredential`, which tries a fixed chain
— `EnvironmentCredential`, then `ManagedIdentityCredential`, and only *then*
`AzureCliCredential`. In practice on `vm-rag-test`, one of the earlier
credential types silently won and authenticated as an unintended identity that
lacked the RBAC roles, even though `az login` had been completed correctly and
the actual signed-in user did have the right roles assigned. The fix: pin all
three scripts to `AzureCliCredential` explicitly, so they always use the
`az login` session on the VM specifically rather than letting
`DefaultAzureCredential` guess. A system-assigned managed identity on the VM
(granted the same roles as `dataPlaneAccessPrincipalId`) remains a possible
alternative for a longer-lived execution environment, but isn't used —
deliberately, since it would grant a disposable VM standing data-plane access.

## CI/CD

- `.github/workflows/deploy.yml` — `az deployment group what-if` then
  `az deployment group create` against `infra/main-rag-poc.bicep`, via OIDC
  federated login (no stored secrets beyond client/tenant/subscription IDs).
- `.github/workflows/security-scan.yml` — PSRule for Azure + Checkov against
  `infra/**` on every push/PR touching it.

## Not yet done

- Content Safety is deployed but not called from `app/query.py`.
- No automated tests for `app/`.
- No web/API front end — `app/query.py` is a CLI only.
