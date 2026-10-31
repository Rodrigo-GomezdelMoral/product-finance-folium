import { roles, roleId } from 'roles.bicep'

@description('Principal id of the app identity, id-folium-<env>.')
param principalId string
param registryName string
param foundryName string
param projectName string

resource registry 'Microsoft.ContainerRegistry/registries@2025-11-01' existing = { name: registryName }
resource foundry 'Microsoft.CognitiveServices/accounts@2026-07-01' existing = { name: foundryName }
resource project 'Microsoft.CognitiveServices/accounts/projects@2026-07-01' existing = { parent: foundry, name: projectName }

resource pull 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, principalId, roles.acrPull)
  scope: registry
  properties: { roleDefinitionId: roleId(roles.acrPull), principalId: principalId, principalType: 'ServicePrincipal' }
}

resource services 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundry.id, principalId, roles.cognitiveServicesUser)
  scope: foundry
  properties: { roleDefinitionId: roleId(roles.cognitiveServicesUser), principalId: principalId, principalType: 'ServicePrincipal' }
}

resource agents 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(project.id, principalId, roles.foundryUser)
  scope: project
  properties: { roleDefinitionId: roleId(roles.foundryUser), principalId: principalId, principalType: 'ServicePrincipal' }
}
