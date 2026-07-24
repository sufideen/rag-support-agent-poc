# Run from: C:\Users\sufyandg\source\repos\rag-support-agent-poc
# Rewrites main-rag-poc.bicep, ai-search.bicep, and azure-openai.bicep
# to fix: (1) hardcoded ServicePrincipal -> parameterized principal type,
#         (2) confirms governance-RG scope for Key Vault / Log Analytics.

# --- main-rag-poc.bicep ---
@'
targetScope = 'resourceGroup'

@description('Environment tag, e.g. poc, dev, prod')
param environment string = 'poc'

@description('Short project prefix, keeps resource names under length limits')
param projectPrefix string = 'ragcs'

@description('Azure region — match your landing zone region for data residency')
param location string = resourceGroup().location

@description('Name of the existing Key Vault deployed by ztr-entra-lz')
param existingKeyVaultName string

@description('Name of the existing Log Analytics workspace deployed by ztr-entra-lz')
param existingLogAnalyticsName string

@description('Resource ID of the existing subnet for private endpoints (from ztr-entra-lz VNet)')
param existingPrivateEndpointSubnetId string

@description('Object ID of the principal that needs data-plane access')
param dataPlaneAccessPrincipalId string

@description('Type of the principal above — User for interactive testing, ServicePrincipal for CI/CD identities')
@allowed(['User', 'ServicePrincipal', 'Group'])
param dataPlaneAccessPrincipalType string = 'User'

@description('Resource group name where the Key Vault and Log Analytics workspace actually live')
param governanceResourceGroupName string = 'rg-ictlabs-governance-dev-uksouth'

var namePrefix = '${projectPrefix}-${environment}'

resource existingKeyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: existingKeyVaultName
  scope: resourceGroup(governanceResourceGroupName)
}

resource existingLogAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: existingLogAnalyticsName
  scope: resourceGroup(governanceResourceGroupName)
}

module aiSearch 'modules/ai-search.bicep' = {
  name: 'deploy-ai-search'
  params: {
    name: '${namePrefix}-search'
    location: location
    logAnalyticsWorkspaceId: existingLogAnalytics.id
    privateEndpointSubnetId: existingPrivateEndpointSubnetId
    keyVaultName: existingKeyVault.name
    dataPlaneAccessPrincipalId: dataPlaneAccessPrincipalId
    dataPlaneAccessPrincipalType: dataPlaneAccessPrincipalType
  }
}

module azureOpenAi 'modules/azure-openai.bicep' = {
  name: 'deploy-azure-openai'
  params: {
    name: '${namePrefix}-aoai'
    location: location
    logAnalyticsWorkspaceId: existingLogAnalytics.id
    privateEndpointSubnetId: existingPrivateEndpointSubnetId
    keyVaultName: existingKeyVault.name
    dataPlaneAccessPrincipalId: dataPlaneAccessPrincipalId
    dataPlaneAccessPrincipalType: dataPlaneAccessPrincipalType
  }
}

module contentSafety 'modules/content-safety.bicep' = {
  name: 'deploy-content-safety'
  params: {
    name: '${namePrefix}-safety'
    location: location
    logAnalyticsWorkspaceId: existingLogAnalytics.id
    privateEndpointSubnetId: existingPrivateEndpointSubnetId
    keyVaultName: existingKeyVault.name
  }
}

output searchEndpoint string = aiSearch.outputs.endpoint
output openAiEndpoint string = azureOpenAi.outputs.endpoint
output contentSafetyEndpoint string = contentSafety.outputs.endpoint
'@ | Set-Content -Path "infra\main-rag-poc.bicep" -Encoding utf8

# --- infra\modules\ai-search.bicep ---
@'
param name string
param location string
param logAnalyticsWorkspaceId string
param privateEndpointSubnetId string
param keyVaultName string
param dataPlaneAccessPrincipalId string
param dataPlaneAccessPrincipalType string = 'User'

resource search 'Microsoft.Search/searchServices@2024-06-01-preview' = {
  name: name
  location: location
  sku: {
    name: 'basic'
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    publicNetworkAccess: 'disabled'
    disableLocalAuth: true
  }
  identity: {
    type: 'SystemAssigned'
  }
}

resource searchDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: search
  name: 'diag-${name}'
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [
      { categoryGroup: 'audit', enabled: true }
      { categoryGroup: 'allLogs', enabled: true }
    ]
    metrics: [
      { category: 'AllMetrics', enabled: true }
    ]
  }
}

resource searchPrivateEndpoint 'Microsoft.Network/privateEndpoints@2023-09-01' = {
  name: 'pe-${name}'
  location: location
  properties: {
    subnet: { id: privateEndpointSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'plsc-${name}'
        properties: {
          privateLinkServiceId: search.id
          groupIds: ['searchService']
        }
      }
    ]
  }
}

resource searchRbac 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, dataPlaneAccessPrincipalId, 'search-index-data-contributor')
  scope: search
  properties: {
    principalId: dataPlaneAccessPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '8ebe5a00-799e-43f5-93ac-243d3dce84a7')
    principalType: dataPlaneAccessPrincipalType
  }
}

output endpoint string = 'https://${search.name}.search.windows.net'
output searchServiceId string = search.id
'@ | Set-Content -Path "infra\modules\ai-search.bicep" -Encoding utf8

# --- infra\modules\azure-openai.bicep ---
@'
param name string
param location string
param logAnalyticsWorkspaceId string
param privateEndpointSubnetId string
param keyVaultName string
param dataPlaneAccessPrincipalId string
param dataPlaneAccessPrincipalType string = 'User'

resource openAi 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: name
  location: location
  kind: 'OpenAI'
  sku: { name: 'S0' }
  properties: {
    publicNetworkAccess: 'Disabled'
    disableLocalAuth: true
    customSubDomainName: name
  }
  identity: { type: 'SystemAssigned' }
}

resource chatDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openAi
  name: 'gpt-5-mini'
  sku: {
    name: 'GlobalStandard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5-mini'
      version: '2025-08-07'
    }
  }
}

resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: openAi
  name: 'text-embedding-3-small'
  sku: {
    name: 'GlobalStandard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'text-embedding-3-small'
    }
  }
  dependsOn: [ chatDeployment ]
}

resource openAiDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: openAi
  name: 'diag-${name}'
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [ { categoryGroup: 'allLogs', enabled: true } ]
    metrics: [ { category: 'AllMetrics', enabled: true } ]
  }
}

resource openAiPrivateEndpoint 'Microsoft.Network/privateEndpoints@2023-09-01' = {
  name: 'pe-${name}'
  location: location
  properties: {
    subnet: { id: privateEndpointSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'plsc-${name}'
        properties: {
          privateLinkServiceId: openAi.id
          groupIds: ['account']
        }
      }
    ]
  }
}

resource openAiRbac 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openAi.id, dataPlaneAccessPrincipalId, 'cognitive-services-openai-user')
  scope: openAi
  properties: {
    principalId: dataPlaneAccessPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd')
    principalType: dataPlaneAccessPrincipalType
  }
}

output endpoint string = openAi.properties.endpoint
output openAiId string = openAi.id
'@ | Set-Content -Path "infra\modules\azure-openai.bicep" -Encoding utf8

Write-Host "All three files rewritten. Run 'git status' and 'git diff' to verify before committing." -ForegroundColor Green
