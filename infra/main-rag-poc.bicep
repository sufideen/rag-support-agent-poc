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

@description('Resource group name where the Key Vault lives')
param governanceResourceGroupName string = 'rg-ictlabs-governance-dev-uksouth'

@description('Resource group name where the Log Analytics workspace lives (different RG than the Key Vault in this landing zone)')
param connectivityResourceGroupName string = 'rg-ictlabs-connectivity-dev-uksouth'

var namePrefix = '${projectPrefix}-${environment}'

resource existingKeyVault 'Microsoft.KeyVault/vaults@2023-07-01' existing = {
  name: existingKeyVaultName
  scope: resourceGroup(governanceResourceGroupName)
}

resource existingLogAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' existing = {
  name: existingLogAnalyticsName
  scope: resourceGroup(connectivityResourceGroupName)
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
    dataPlaneAccessPrincipalId: dataPlaneAccessPrincipalId
    dataPlaneAccessPrincipalType: dataPlaneAccessPrincipalType
  }
}

output searchEndpoint string = aiSearch.outputs.endpoint
output openAiEndpoint string = azureOpenAi.outputs.endpoint
output openAiName string = azureOpenAi.outputs.openAiName
output contentSafetyEndpoint string = contentSafety.outputs.endpoint
