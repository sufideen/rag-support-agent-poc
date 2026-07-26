param name string
param location string
param logAnalyticsWorkspaceId string
param privateEndpointSubnetId string
param keyVaultName string
param dataPlaneAccessPrincipalId string
param dataPlaneAccessPrincipalType string = 'User'

resource contentSafety 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: name
  location: location
  kind: 'ContentSafety'
  sku: { name: 'S0' }
  properties: {
    publicNetworkAccess: 'Disabled'
    disableLocalAuth: true
    customSubDomainName: name
  }
  identity: { type: 'SystemAssigned' }
}

resource contentSafetyDiagnostics 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  scope: contentSafety
  name: 'diag-${name}'
  properties: {
    workspaceId: logAnalyticsWorkspaceId
    logs: [ { categoryGroup: 'allLogs', enabled: true } ]
    metrics: [ { category: 'AllMetrics', enabled: true } ]
  }
}

resource contentSafetyPrivateEndpoint 'Microsoft.Network/privateEndpoints@2023-09-01' = {
  name: 'pe-${name}'
  location: location
  properties: {
    subnet: { id: privateEndpointSubnetId }
    privateLinkServiceConnections: [
      {
        name: 'plsc-${name}'
        properties: {
          privateLinkServiceId: contentSafety.id
          groupIds: ['account']
        }
      }
    ]
  }
}

resource contentSafetyRbac 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(contentSafety.id, dataPlaneAccessPrincipalId, 'cognitive-services-user')
  scope: contentSafety
  properties: {
    principalId: dataPlaneAccessPrincipalId
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908')
    principalType: dataPlaneAccessPrincipalType
  }
}

output endpoint string = contentSafety.properties.endpoint
output contentSafetyId string = contentSafety.id
