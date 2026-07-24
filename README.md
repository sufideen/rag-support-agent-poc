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
  main-rag-poc.bicep       # orchestrator
  modules/
    ai-search.bicep
    azure-openai.bicep
    content-safety.bicep
docs/
  architecture.md
.github/workflows/
  deploy.yml
```

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
