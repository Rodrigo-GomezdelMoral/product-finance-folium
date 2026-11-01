param location string
param tags object
param short string
param image string
param registryServer string
param revisionSuffix string
@description('Revision that keeps all traffic while the new one starts at 0 % behind the canary label; empty on the first deployment.')
param stableRevision string
param maxReplicas int
param authClientId string
param appIdentityId string
@description('Identity of the queue scale rule only: lifecycle None, so the code can never obtain its tokens.')
param scaleIdentityId string
param busName string
param workspaceId string
@description('Environment variables of the container.')
param settings object

var canary = { revisionName: 'ca-folium-${short}--${revisionSuffix}', weight: empty(stableRevision) ? 100 : 0, label: 'canary' }
var regionCodes = { swedencentral: 'swc', spaincentral: 'spc' }
@description('Production only (ADR-011): one warm replica Monday to Friday, 08:00 to 19:00 Madrid time.')
var businessHours = { name: 'business-hours', custom: { type: 'cron', metadata: { timezone: 'Europe/Madrid', start: '0 8 * * 1-5', end: '0 19 * * 1-5', desiredReplicas: '1' } } }
var issuer = '${az.environment().authentication.loginEndpoint}${tenant().tenantId}/v2.0'

resource managedEnvironment 'Microsoft.App/managedEnvironments@2026-07-01' = {
  name: 'cae-folium-${short}-${regionCodes[location]}'
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

resource app 'Microsoft.App/containerApps@2026-07-01' = {
  name: 'ca-folium-${short}'
  location: location
  tags: tags
  identity: { type: 'UserAssigned', userAssignedIdentities: { '${appIdentityId}': {}, '${scaleIdentityId}': {} } }
  properties: {
    environmentId: managedEnvironment.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Multiple'
      maxInactiveRevisions: 5
      ingress: {
        external: true, targetPort: 8000, transport: 'auto', allowInsecure: false
        traffic: empty(stableRevision) ? [canary] : [{ revisionName: stableRevision, weight: 100 }, canary]
      }
      registries: [{ server: registryServer, identity: appIdentityId }]
      identitySettings: [{ identity: appIdentityId, lifecycle: 'Main' }, { identity: scaleIdentityId, lifecycle: 'None' }]
    }
    template: {
      revisionSuffix: revisionSuffix
      containers: [
        {
          name: 'folium'
          image: image
          resources: { cpu: json('0.5'), memory: '1Gi' }
          env: [for item in items(settings): { name: item.key, value: item.value }]
          probes: [
            for kind in ['Startup', 'Liveness', 'Readiness']: {
              type: kind, httpGet: { path: '/healthz', port: 8000 }, periodSeconds: kind == 'Startup' ? 12 : 10, failureThreshold: kind == 'Startup' ? 10 : 3
            }
          ]
        }
      ]
      scale: {
        minReplicas: 0
        maxReplicas: maxReplicas
        rules: concat([
          { name: 'http', http: { metadata: { concurrentRequests: '20' } } }
          {
            name: 'queue'
            custom: { type: 'azure-servicebus', metadata: { queueName: 'invoices', namespace: busName, messageCount: '10' }, identity: scaleIdentityId }
          }
        ], short == 'prod' ? [businessHours] : [])
      }
    }
  }
}

resource auth 'Microsoft.App/containerApps/authConfigs@2026-07-01' = {
  parent: app
  name: 'current'
  properties: {
    platform: { enabled: true }
    globalValidation: { unauthenticatedClientAction: 'RedirectToLoginPage', redirectToProvider: 'azureactivedirectory', excludedPaths: ['/healthz'] }
    identityProviders: {
      azureActiveDirectory: {
        enabled: true, registration: { clientId: authClientId, openIdIssuer: issuer }, validation: { allowedAudiences: ['api://${authClientId}', authClientId] }
      }
    }
    httpSettings: { requireHttps: true }
  }
}

output name string = app.name
output revision string = '${app.name}--${revisionSuffix}'
