@description('Name of the Bastion resource')
param bastionName string = 'bas-rag-test-dev'

@description('Azure region — match the VNet region')
param location string = 'uksouth'

@description('Resource ID of the existing VNet that vm-rag-test lives in (not a subnet — Developer SKU attaches to the VNet directly, no dedicated AzureBastionSubnet or public IP required)')
param existingVnetId string

resource bastion 'Microsoft.Network/bastionHosts@2024-05-01' = {
  name: bastionName
  location: location
  sku: {
    name: 'Developer'
  }
  properties: {
    virtualNetwork: {
      id: existingVnetId
    }
  }
}

output bastionName string = bastion.name
