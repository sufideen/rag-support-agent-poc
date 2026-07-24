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

@description('Object ID of the managed identity or user that needs data-plane access, e.g. your CI/CD OIDC identity or the Agent Service identity')
param dataPlaneAccessPrincipalId string

var namePrefix = '${projectPrefix}-${environment}'

resource existingKeyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: existingKeyVaultName
}

resource existingLogAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: existingLogAnalyticsName
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
