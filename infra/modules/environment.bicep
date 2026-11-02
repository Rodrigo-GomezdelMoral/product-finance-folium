@description('The one Container Apps environment of Folium, shared by staging and production and owned by production (ADR-013).')
param name string
param location string
param tags object
param workspaceId string

resource managedEnvironment 'Microsoft.App/managedEnvironments@2026-07-01' = {
  name: name
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: { destination: 'azure-monitor' }, workloadProfiles: [{ name: 'Consumption', workloadProfileType: 'Consumption' }], zoneRedundant: false
  }
}

#disable-next-line use-recent-api-versions
resource logs 'Microsoft.Insights/diagnosticSettings@2021-05-01-preview' = {
  name: 'to-shared-workspace'
  scope: managedEnvironment
  properties: { workspaceId: workspaceId, logs: [{ categoryGroup: 'allLogs', enabled: true }] }
}
