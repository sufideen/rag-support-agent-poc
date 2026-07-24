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
