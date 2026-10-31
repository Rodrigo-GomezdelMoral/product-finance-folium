using 'main.bicep'

param env = 'staging'
param maxReplicas = 2
param budget = 10
param digest = readEnvironmentVariable('IMAGE_DIGEST')
param authClientId = readEnvironmentVariable('AUTH_CLIENT_ID')
param revisionSuffix = readEnvironmentVariable('REVISION_SUFFIX')
param stableRevision = readEnvironmentVariable('STABLE_REVISION', '')
param alertEmail = readEnvironmentVariable('ALERT_EMAIL_ADDRESS')
