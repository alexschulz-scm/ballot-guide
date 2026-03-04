// Web Container App — Next.js, external ingress, proxies to API
param location string
param environmentId string
param registryLoginServer string
param registryName string
@secure()
param registryPassword string
param webImageTag string
param apiInternalFqdn string

resource webApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ballot-guide-web'
  location: location
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      ingress: {
        external: true
        targetPort: 3000
        transport: 'auto'
      }
      registries: [
        {
          server: registryLoginServer
          username: registryName
          passwordSecretRef: 'acr-password'
        }
      ]
      secrets: [
        { name: 'acr-password', value: registryPassword }
      ]
    }
    template: {
      containers: [
        {
          name: 'web'
          image: '${registryLoginServer}/ballot-guide-web:${webImageTag}'
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            { name: 'API_URL', value: 'http://${apiInternalFqdn}' }
            { name: 'HOSTNAME', value: '0.0.0.0' }
          ]
          probes: [
            {
              type: 'Startup'
              httpGet: {
                port: 3000
                path: '/'
              }
              periodSeconds: 5
              failureThreshold: 12
            }
            {
              type: 'Liveness'
              httpGet: {
                port: 3000
                path: '/'
              }
              periodSeconds: 30
              failureThreshold: 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 2
        rules: [
          {
            name: 'http-scaler'
            http: {
              metadata: {
                concurrentRequests: '10'
              }
            }
          }
        ]
      }
    }
  }
}

output fqdn string = webApp.properties.configuration.ingress.fqdn
output name string = webApp.name
