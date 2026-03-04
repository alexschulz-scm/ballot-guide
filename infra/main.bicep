// Ballot Guide — Azure Container Apps deployment
// Deploy: az deployment group create -g ballot-guide-rg -f infra/main.bicep
//         --parameters envName=dev location=eastus
//         --parameters anthropicApiKey=<val> googleCivicApiKey=<val> ...

targetScope = 'resourceGroup'

// ── Parameters ────────────────────────────────
param location string = resourceGroup().location
param envName string = 'dev'
param apiImageTag string = 'latest'
param webImageTag string = 'latest'

@secure()
param anthropicApiKey string
@secure()
param googleCivicApiKey string
@secure()
param newsapiKey string
@secure()
param openfecApiKey string

// ── Modules ───────────────────────────────────

module registry 'modules/registry.bicep' = {
  name: 'registry'
  params: {
    location: location
    envName: envName
  }
}

module environment 'modules/environment.bicep' = {
  name: 'environment'
  params: {
    location: location
    envName: envName
  }
}

module api 'modules/api.bicep' = {
  name: 'api'
  params: {
    location: location
    environmentId: environment.outputs.environmentId
    registryLoginServer: registry.outputs.loginServer
    registryName: registry.outputs.name
    registryPassword: registry.outputs.password
    apiImageTag: apiImageTag
    anthropicApiKey: anthropicApiKey
    googleCivicApiKey: googleCivicApiKey
    newsapiKey: newsapiKey
    openfecApiKey: openfecApiKey
  }
}

module web 'modules/web.bicep' = {
  name: 'web'
  params: {
    location: location
    environmentId: environment.outputs.environmentId
    registryLoginServer: registry.outputs.loginServer
    registryName: registry.outputs.name
    registryPassword: registry.outputs.password
    webImageTag: webImageTag
    apiInternalFqdn: api.outputs.fqdn
  }
}

// ── Outputs ───────────────────────────────────

output acrLoginServer string = registry.outputs.loginServer
output webUrl string = 'https://${web.outputs.fqdn}'
output apiInternalUrl string = 'http://${api.outputs.fqdn}'
