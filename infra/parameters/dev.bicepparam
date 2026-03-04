using '../main.bicep'

param envName = 'dev'
param location = 'eastus'

// Image tags default to 'latest' — overridden by CI/CD with git SHA.
// Secrets are passed via CLI --parameters flag, NEVER in this file.
