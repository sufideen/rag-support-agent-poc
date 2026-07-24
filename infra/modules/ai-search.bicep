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
