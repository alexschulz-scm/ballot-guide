// Azure Container Registry — Basic SKU for MVP
param location string
param envName string

var registryName = 'ballotguide${envName}acr'

resource acr 'Microsoft.ContainerRegistry/registries@2023-07-01' = {
  name: registryName
  location: location
  sku: {
    name: 'Basic'
  }
  properties: {
    adminUserEnabled: true
  }
}

output loginServer string = acr.properties.loginServer
output name string = acr.name
output password string = acr.listCredentials().passwords[0].value
