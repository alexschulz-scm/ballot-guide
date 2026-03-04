// Azure Storage Account + File Share for SQLite persistence
param location string
param envName string

var storageAccountName = 'ballotguide${envName}sa'
var fileShareName = 'ballotdata'

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
}

resource fileShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: fileService
  name: fileShareName
  properties: {
    shareQuota: 1
  }
}

output accountName string = storageAccount.name
output accountKey string = storageAccount.listKeys().keys[0].value
output shareName string = fileShareName
