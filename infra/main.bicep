targetScope = 'resourceGroup'

@allowed(['staging', 'production'])
param env string
@description('Digest (sha256:...) of the image in the shared registry: images are promoted by digest, never rebuilt.')
param digest string
@description('Client id of the folium-<env> app registration that signs users in.')
param authClientId string
@description('Suffix of the revision this deployment creates, unique per run.')
param revisionSuffix string
@description('Revision serving traffic before this deployment; empty on the first one.')
param stableRevision string = ''
@minValue(1)
@maxValue(3)
param maxReplicas int
@description('Monthly budget of the resource group, in euros.')
param budget int
@secure()
@description('Address that receives the budget and alert e-mails.')
param alertEmail string
param location string = resourceGroup().location
@description('First month of the budgets, fixed so that a redeployment never changes it.')
param budgetStartDate string = '2026-11-01'
param sharedResourceGroup string = 'rg-aiplatform-shared-swc'
param registryName string = 'craiplatformshared'
param foundryName string = 'fdry-aiplatform-shared-swc'
param projectName string = 'proj-aiplatform-shared'
param workspaceName string = 'log-aiplatform-shared-swc'
param model string = 'gpt-5-mini'

var short = env == 'staging' ? 'stg' : 'prod'
var tags = { project: 'product-finance-folium', environment: env, owner: 'Rodrigo-GomezdelMoral' }
var shared = resourceGroup(sharedResourceGroup)

resource registry 'Microsoft.ContainerRegistry/registries@2025-11-01' existing = { name: registryName, scope: shared }
resource foundry 'Microsoft.CognitiveServices/accounts@2026-07-01' existing = { name: foundryName, scope: shared }
resource project 'Microsoft.CognitiveServices/accounts/projects@2026-07-01' existing = { parent: foundry, name: projectName }
resource workspace 'Microsoft.OperationalInsights/workspaces@2026-03-01' existing = { name: workspaceName, scope: shared }
resource appIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = { name: 'id-folium-${short}', location: location, tags: tags }
resource scaleIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2024-11-30' = { name: 'id-folium-${short}-scale', location: location, tags: tags }

module sharedAccess 'modules/shared.bicep' = {
  scope: shared
  params: { principalId: appIdentity.properties.principalId, registryName: registryName, foundryName: foundryName, projectName: projectName }
}

module data 'modules/data.bicep' = {
  params: { location: location, tags: tags, short: short, appPrincipalId: appIdentity.properties.principalId, scalePrincipalId: scaleIdentity.properties.principalId }
}

module monitor 'modules/monitor.bicep' = {
  params: {
    location: location, tags: tags, short: short, production: env == 'production', workspaceId: workspace.id, principalId: appIdentity.properties.principalId
    budget: budget, budgetStartDate: budgetStartDate, alertEmail: alertEmail, busId: data.outputs.busId
  }
}

module app 'modules/app.bicep' = {
  dependsOn: [sharedAccess]
  params: {
    location: location, tags: tags, short: short, maxReplicas: maxReplicas, workspaceId: workspace.id, busName: data.outputs.busName
    image: '${registry.properties.loginServer}/product-finance-folium@${digest}', registryServer: registry.properties.loginServer
    revisionSuffix: revisionSuffix, stableRevision: stableRevision, authClientId: authClientId, appIdentityId: appIdentity.id, scaleIdentityId: scaleIdentity.id
    settings: {
      ENVIRONMENT: env
      AZURE_CLIENT_ID: appIdentity.properties.clientId
      COSMOS_ENDPOINT: data.outputs.cosmosEndpoint
      STORAGE: data.outputs.blobEndpoint
      SERVICEBUS: data.outputs.busNamespace
      FOUNDRY_ACCOUNT_ENDPOINT: foundry.properties.endpoint
      FOUNDRY_PROJECT_ENDPOINT: project.properties.endpoints['AI Foundry API']
      FOUNDRY_MODEL: model
      APPLICATIONINSIGHTS_CONNECTION_STRING: monitor.outputs.connectionString
    }
  }
}

output app string = app.outputs.name
output revision string = app.outputs.revision
