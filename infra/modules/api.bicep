// API Container App — FastAPI, external ingress, SQLite on File Share
param location string
param environmentId string
param registryLoginServer string
param registryName string
@secure()
param registryPassword string
param apiImageTag string
param corsOrigins string = '["https://ballot-guide.azurecontainerapps.io"]'

// Secrets
@secure()
param geminiApiKey string
@secure()
param googleCivicApiKey string
@secure()
param newsapiKey string
@secure()
param openfecApiKey string

resource apiApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: 'ballot-guide-api'
  location: location
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
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
        { name: 'gemini-api-key', value: geminiApiKey }
        { name: 'google-civic-api-key', value: googleCivicApiKey }
        { name: 'newsapi-key', value: newsapiKey }
        { name: 'openfec-api-key', value: openfecApiKey }
      ]
    }
    template: {
      containers: [
        {
          name: 'api'
          image: '${registryLoginServer}/ballot-guide-api:${apiImageTag}'
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            { name: 'DB_PATH', value: '/data/ballot-guide.db' }
            { name: 'LOG_LEVEL', value: 'INFO' }
            { name: 'APP_VERSION', value: '1.0.0' }
            { name: 'MOCK_EXTERNAL_APIS', value: 'false' }
            { name: 'MOCK_LLM', value: 'false' }
            { name: 'MOCK_CIVIC_API', value: 'true' }
            { name: 'CORS_ORIGINS', value: corsOrigins }
            { name: 'GEMINI_API_KEY', secretRef: 'gemini-api-key' }
            { name: 'GOOGLE_CIVIC_API_KEY', secretRef: 'google-civic-api-key' }
            { name: 'NEWSAPI_KEY', secretRef: 'newsapi-key' }
            { name: 'OPENFEC_API_KEY', secretRef: 'openfec-api-key' }
          ]
          volumeMounts: [
            {
              volumeName: 'data-volume'
              mountPath: '/data'
            }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: {
                port: 8000
                path: '/health'
              }
              periodSeconds: 30
              failureThreshold: 3
            }
            {
              type: 'Startup'
              httpGet: {
                port: 8000
                path: '/health'
              }
              periodSeconds: 10
              failureThreshold: 12
            }
          ]
        }
      ]
      volumes: [
        {
          name: 'data-volume'
          storageType: 'EmptyDir'
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: 3
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

output fqdn string = apiApp.properties.configuration.ingress.fqdn
output name string = apiApp.name
