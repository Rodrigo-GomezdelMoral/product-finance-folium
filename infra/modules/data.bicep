import { roles, roleId, uuid } from 'roles.bicep'

param location string
param tags object
param short string
param appPrincipalId string
@description('Principal id of id-folium-<env>-scale, which only the queue scale rule uses.')
param scalePrincipalId string

var partitions = { invoices: '/id', audit: '/invoice_id', vendors: '/tax_id', exports: '/id', conversations: '/session_id', checkpoints: '/workflow_name' }
var queueGrants = [
  { principalId: appPrincipalId, role: roles.serviceBusDataSender }
  { principalId: appPrincipalId, role: roles.serviceBusDataReceiver }
  { principalId: scalePrincipalId, role: roles.serviceBusDataOwner }
]

resource cosmos 'Microsoft.DocumentDB/databaseAccounts@2026-03-15' = {
  name: 'cosmos-folium-${short}-swc'
  location: location
  tags: tags
  kind: 'GlobalDocumentDB'
  properties: {
    databaseAccountOfferType: 'Standard', capabilities: [{ name: 'EnableServerless' }], consistencyPolicy: { defaultConsistencyLevel: 'Session' }
    locations: [{ locationName: location, failoverPriority: 0, isZoneRedundant: false }]
    backupPolicy: { type: 'Continuous', continuousModeProperties: { tier: 'Continuous7Days' } }
    disableLocalAuth: true, disableKeyBasedMetadataWriteAccess: true, minimalTlsVersion: 'Tls12'
  }
}

resource database 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases@2026-03-15' = {
  parent: cosmos
  name: 'folium'
  properties: { resource: { id: 'folium' } }
}

resource containers 'Microsoft.DocumentDB/databaseAccounts/sqlDatabases/containers@2026-03-15' = [
  for item in items(partitions): { parent: database, name: item.key, properties: { resource: { id: item.key, partitionKey: { paths: [item.value], kind: 'Hash' } } } }
]

resource cosmosAccess 'Microsoft.DocumentDB/databaseAccounts/sqlRoleAssignments@2026-03-15' = {
  parent: cosmos
  name: guid(cosmos.id, appPrincipalId, roles.cosmosDataContributor)
  properties: {
    roleDefinitionId: '${cosmos.id}/sqlRoleDefinitions/${uuid(roles.cosmosDataContributor)}', principalId: appPrincipalId, scope: '${cosmos.id}/dbs/${database.name}'
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2026-06-01' = {
  name: 'stfolium${short}swc'
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: { name: 'Standard_LRS' }
  properties: {
    accessTier: 'Hot', allowBlobPublicAccess: false, allowSharedKeyAccess: false, defaultToOAuthAuthentication: true
    minimumTlsVersion: 'TLS1_2', supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2026-06-01' = {
  parent: storage
  name: 'default'
  properties: {
    isVersioningEnabled: true, deleteRetentionPolicy: { enabled: true, days: 7 }, containerDeleteRetentionPolicy: { enabled: true, days: 7 }
  }
}

resource blobContainers 'Microsoft.Storage/storageAccounts/blobServices/containers@2026-06-01' = [
  for name in ['originals', 'exports']: { parent: blobService, name: name, properties: { publicAccess: 'None' } }
]

resource lifecycle 'Microsoft.Storage/storageAccounts/managementPolicies@2026-06-01' = {
  parent: storage
  name: 'default'
  properties: {
    policy: {
      rules: [
        {
          name: 'cool-after-30-days-and-expire-previous-versions', enabled: true, type: 'Lifecycle'
          definition: {
            filters: { blobTypes: ['blockBlob'] }
            actions: { baseBlob: { tierToCool: { daysAfterModificationGreaterThan: 30 } }, version: { delete: { daysAfterCreationGreaterThan: 7 } } }
          }
        }
        {
          name: 'expire-exports-after-a-year', enabled: true, type: 'Lifecycle'
          definition: {
            filters: { blobTypes: ['blockBlob'], prefixMatch: ['exports/'] }
            actions: { baseBlob: { delete: { daysAfterModificationGreaterThan: 365 } } }
          }
        }
      ]
    }
  }
}

resource blobAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, appPrincipalId, roles.storageBlobDataContributor)
  scope: storage
  properties: { roleDefinitionId: roleId(roles.storageBlobDataContributor), principalId: appPrincipalId, principalType: 'ServicePrincipal' }
}

resource bus 'Microsoft.ServiceBus/namespaces@2026-01-01' = {
  name: 'sb-folium-${short}-swc'
  location: location
  tags: tags
  sku: { name: 'Basic', tier: 'Basic' }
  properties: { disableLocalAuth: true, minimumTlsVersion: '1.2' }
}

resource queue 'Microsoft.ServiceBus/namespaces/queues@2026-01-01' = {
  parent: bus
  name: 'invoices'
  properties: { lockDuration: 'PT1M', maxDeliveryCount: 5, deadLetteringOnMessageExpiration: true, defaultMessageTimeToLive: 'P14D' }
}

resource queueAccess 'Microsoft.Authorization/roleAssignments@2022-04-01' = [
  for grant in queueGrants: {
    name: guid(queue.id, grant.principalId, grant.role)
    scope: queue
    properties: { roleDefinitionId: roleId(grant.role), principalId: grant.principalId, principalType: 'ServicePrincipal' }
  }
]

output cosmosEndpoint string = cosmos.properties.documentEndpoint
output blobEndpoint string = storage.properties.primaryEndpoints.blob
output busName string = bus.name
output busNamespace string = split(split(bus.properties.serviceBusEndpoint, '/')[2], ':')[0]
output busId string = bus.id
