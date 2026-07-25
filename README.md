# rag-support-agent-poc

RAG-powered customer support AI agent POC built on Azure AI Foundry
(Azure AI Search, Azure OpenAI, Azure AI Content Safety).

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
data/
  *.md                            # sample GridPulse Energy support knowledge base
docs/
  architecture.md
.github/workflows/
  deploy.yml
  security-scan.yml
```

See `docs/architecture.md` for how these fit together, including why `app/`
runs from inside the VNet rather than a local dev machine.

## Deploy

```powershell
az deployment group what-if `
  --resource-group "<your-rg>" `
  --template-file "infra\main-rag-poc.bicep" `
  --parameters existingKeyVaultName="<kv-name>" `
               existingLogAnalyticsName="<law-name>" `
               existingPrivateEndpointSubnetId="<subnet-id>" `
               dataPlaneAccessPrincipalId="<principal-id>"
```

Review the `what-if` output, then run `az deployment group create` with the same parameters.

## Running the RAG pipeline

All three data-plane services are private-endpoint-only, so `app/ingest.py` and
`app/query.py` need to run from inside the VNet — in practice, from
`vm-rag-test` (see `infra/scripts/provision-test-vm-python.ps1` to provision
Python there). From wherever you run them:

```bash
az login   # DefaultAzureCredential needs a credential source
cp .env.example .env   # fill in SEARCH_ENDPOINT / OPENAI_ENDPOINT from the deployment outputs
export $(grep -v '^#' .env | xargs)

python app/create_index.py                    # one-time: creates the Search index
python app/ingest.py                          # embeds data/*.md into it
python app/query.py "How do I report an outage?"
```

No API keys are used anywhere — both services have `disableLocalAuth: true`,
so auth is Entra ID / RBAC only via `DefaultAzureCredential`.

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




