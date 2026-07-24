# Run from: C:\Users\sufyandg\source\repos\rag-support-agent-poc\infra
# Step 1 of the two-phase fix: strip model deployments out of azure-openai.bicep
# so it only creates the account + private endpoint + RBAC + diagnostics.
# Step 2 creates a new standalone file that deploys the model deployments
# separately, run AFTER the account is confirmed Succeeded.

# --- infra\modules\azure-openai.bicep (account only, no model deployments) ---
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
output openAiName string = openAi.name
'@ | Set-Content -Path "modules\azure-openai.bicep" -Encoding utf8

# --- infra\openai-model-deployments.bicep (NEW — run as a separate, later deployment) ---
@'
@description('Name of the already-existing, fully-provisioned Azure OpenAI account')
param openAiAccountName string

resource openAi 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: openAiAccountName
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
'@ | Set-Content -Path "openai-model-deployments.bicep" -Encoding utf8

Write-Host "Done. azure-openai.bicep now creates the account only; openai-model-deployments.bicep deploys the models separately." -ForegroundColor Green
