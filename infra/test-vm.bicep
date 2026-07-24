@description('Name of the VM')
param vmName string = 'vm-rag-test'

@description('Azure region — match the VNet region')
param location string = 'uksouth'

@description('Resource ID of the subnet to deploy into (e.g. snet-devops-agents)')
param subnetId string

@description('Admin username for the VM')
param adminUsername string = 'azureuser'

@description('Admin password — pass via --parameters at deploy time, never commit a real value')
@secure()
param adminPassword string

resource nic 'Microsoft.Network/networkInterfaces@2023-09-01' = {
  name: '${vmName}-nic'
  location: location
  properties: {
    ipConfigurations: [
      {
        name: 'ipconfig1'
        properties: {
          subnet: { id: subnetId }
          privateIPAllocationMethod: 'Dynamic'
        }
      }
    ]
  }
}

resource vm 'Microsoft.Compute/virtualMachines@2024-07-01' = {
  name: vmName
  location: location
  properties: {
    hardwareProfile: {
      vmSize: 'Standard_B1s'
    }
    osProfile: {
      computerName: vmName
      adminUsername: adminUsername
      adminPassword: adminPassword
    }
    storageProfile: {
      imageReference: {
        publisher: 'Canonical'
        offer: 'ubuntu-24_04-lts'
        sku: 'server'
        version: 'latest'
      }
      osDisk: {
        createOption: 'FromImage'
        managedDisk: {
          storageAccountType: 'Standard_LRS'
        }
      }
    }
    networkProfile: {
      networkInterfaces: [
        { id: nic.id }
      ]
    }
  }
}

output vmName string = vm.name
output privateIp string = nic.properties.ipConfigurations[0].properties.privateIPAddress
