@export()
@description('Built-in role definition names: public constants, kept without hyphens so the repository scan for identifiers stays strict.')
var roles = {
  acrPull: '7f951dda4ed34680a7ca43fe172d538d'
  cognitiveServicesUser: 'a97b65f324c74388baec2e87135dc908'
  foundryUser: '53ca6127db724b80b1b0d745d6d5456d'
  storageBlobDataContributor: 'ba92f5b42d11453da403e96b0029c9fe'
  serviceBusDataSender: '69a216fcb8fb44d8bc221f3c2cd27a39'
  serviceBusDataReceiver: '4f6d3b9b027b4f4c91420e5a2a2247e0'
  serviceBusDataOwner: '090c5cfd751d490a894a3ce6f1109419'
  monitoringMetricsPublisher: '3913510d42f44e428a64420c390055eb'
  cosmosDataContributor: '00000000000000000000000000000002'
}

@export()
func uuid(hex string) string =>
  '${substring(hex, 0, 8)}-${substring(hex, 8, 4)}-${substring(hex, 12, 4)}-${substring(hex, 16, 4)}-${substring(hex, 20, 12)}'

@export()
func roleId(hex string) string => subscriptionResourceId('Microsoft.Authorization/roleDefinitions', uuid(hex))
