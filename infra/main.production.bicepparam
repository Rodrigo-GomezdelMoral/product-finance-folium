using 'main.bicep'

param env = 'production'
param maxReplicas = 3
param budget = 20
param digest = readEnvironmentVariable('IMAGE_DIGEST')
param authClientId = readEnvironmentVariable('AUTH_CLIENT_ID')
param revisionSuffix = readEnvironmentVariable('REVISION_SUFFIX')
param stableRevision = readEnvironmentVariable('STABLE_REVISION', '')
param alertEmail = readEnvironmentVariable('ALERT_EMAIL_ADDRESS')
