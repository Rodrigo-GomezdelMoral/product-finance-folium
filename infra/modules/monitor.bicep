import { roles, roleId } from 'roles.bicep'

param location string
param tags object
param short string
@description('Alerts and their action group exist in production only: each log alert rule bills.')
param production bool
param workspaceId string
param principalId string
param budget int
param budgetStartDate string
@secure()
param alertEmail string
param busId string

var businessHours = 'extend local = datetime_utc_to_local(timestamp, "Europe/Madrid") | where dayofweek(local) between (1d .. 5d) and hourofday(local) between (8 .. 18)'
var availability = 'requests | ${businessHours} | summarize total = count(), failed = countif(toint(resultCode) >= 500) | extend availability_pct = round(100.0 * (total - failed) / total, 3)'
var ready = 'customEvents | where name == "invoice_ready" and tobool(customDimensions.standard) | summarize invoices = count(), p95_seconds = percentile(todouble(customDimensions.seconds), 95)'
var errors = 'requests | summarize total = count(), failed = countif(toint(resultCode) >= 500) | extend error_pct = round(100.0 * failed / total, 2)'
var approved = 'customEvents | where name == "invoice_approved" | summarize approved = count()'
var tiles = [
  { title: 'Handling time: median seconds on approval (target 120)', query: '${approved}, median_seconds = percentile(todouble(customDimensions.review_seconds), 50) | extend target = 120' }
  { title: 'Touchless rate: % approved with no correction (target 70)', query: '${approved}, touchless_pct = round(100.0 * countif(toint(customDimensions.corrections) == 0) / count(), 1) | extend target = 70' }
  {
    title: 'Field correction rate: % of extracted fields corrected (target 5)'
    query: 'customEvents | where name in ("field_corrected", "invoice_ready") | summarize corrected = countif(name == "field_corrected"), fields = sumif(toint(customDimensions.fields), name == "invoice_ready") | extend correction_pct = round(100.0 * corrected / fields, 2), target = 5'
  }
  { title: 'Feedback: % helpful (target 80)', query: 'customEvents | where name == "feedback" | summarize votes = count(), helpful_pct = round(100.0 * countif(tobool(customDimensions.helpful)) / count(), 1) | extend target = 80' }
  { title: 'Availability in business hours, % (SLO 99.7, SLA 99.5, REQ-10)', query: '${availability} | extend slo = 99.7, sla = 99.5' }
  { title: 'Ready for review: p95 seconds of standard invoices (SLO 25, SLA 30, REQ-11)', query: '${ready} | extend slo = 25, sla = 30' }
  { title: 'Health model: dependencies', query: 'dependencies | summarize calls = count(), failed = countif(success == false), p95_ms = round(percentile(duration, 95)) by target, type | order by failed desc' }
  {
    title: 'Health model: requests, server errors and latency by hour'
    query: 'requests | summarize requests = count(), error_pct = round(100.0 * countif(toint(resultCode) >= 500) / count(), 2), p95_ms = round(percentile(duration, 95)) by bin(timestamp, 1h) | render timechart'
  }
  { title: 'KPI events arriving', query: 'customEvents | summarize events = count() by name' }
]
var items = [
  for (tile, i) in tiles: {
    type: 3, name: 'tile-${i}'
    content: { version: 'KqlItem/1.0', title: tile.title, query: tile.query, size: 4, queryType: 0, resourceType: 'microsoft.insights/components', timeContext: { durationMs: 2592000000 } }
  }
]
var alerts = [
  { name: 'availability', description: 'Availability in business hours below the 99.7 % SLO', query: '${availability} | where total >= 20 and availability_pct < 99.7' }
  { name: 'ready-p95', description: 'p95 time to ready above the 25 s SLO', query: '${ready} | where invoices >= 5 and p95_seconds > 25' }
  { name: 'errors', description: 'Server errors above 1 % of requests', query: '${errors} | where total >= 20 and error_pct > 1' }
]

resource insights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-folium-${short}-swc'
  location: location
  tags: tags
  kind: 'web'
  properties: { Application_Type: 'web', WorkspaceResourceId: workspaceId, DisableLocalAuth: true, IngestionMode: 'LogAnalytics' }
}

resource publisher 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(insights.id, principalId, roles.monitoringMetricsPublisher)
  scope: insights
  properties: { roleDefinitionId: roleId(roles.monitoringMetricsPublisher), principalId: principalId, principalType: 'ServicePrincipal' }
}

resource workbook 'Microsoft.Insights/workbooks@2023-06-01' = {
  name: guid(insights.id, 'kpi-workbook')
  location: location
  tags: tags
  kind: 'shared'
  properties: {
    displayName: 'Folium KPIs, SLAs and health (${short})', category: 'workbook', sourceId: insights.id
    serializedData: string({ version: 'Notebook/1.0', items: items, fallbackResourceIds: [insights.id] })
  }
}

resource costBudget 'Microsoft.Consumption/budgets@2026-06-01' = {
  name: 'budget-folium-${short}'
  properties: {
    category: 'Cost', amount: budget, timeGrain: 'Monthly', timePeriod: { startDate: budgetStartDate }
    notifications: toObject([50, 80, 100], level => 'actual-${level}', level => {
      enabled: true, operator: 'GreaterThanOrEqualTo', threshold: level, thresholdType: 'Actual', contactEmails: [alertEmail]
    })
  }
}

resource group 'Microsoft.Insights/actionGroups@2023-01-01' = if (production) {
  name: 'ag-folium-${short}-swc'
  location: 'global'
  tags: tags
  properties: { groupShortName: 'folium', enabled: true, emailReceivers: [{ name: 'author', emailAddress: alertEmail, useCommonAlertSchema: true }] }
}

resource logAlerts 'Microsoft.Insights/scheduledQueryRules@2026-03-01' = [
  for alert in alerts: if (production) {
    name: 'alert-folium-${alert.name}'
    location: location
    tags: tags
    properties: {
      description: alert.description, severity: 2, enabled: true, scopes: [insights.id], evaluationFrequency: 'PT15M', windowSize: 'PT1H', autoMitigate: true
      criteria: {
        allOf: [
          { query: alert.query, timeAggregation: 'Count', operator: 'GreaterThan', threshold: 0, failingPeriods: { numberOfEvaluationPeriods: 1, minFailingPeriodsToAlert: 1 } }
        ]
      }
      actions: { actionGroups: [group.id] }
    }
  }
]

resource deadLetters 'Microsoft.Insights/metricAlerts@2026-01-01' = if (production) {
  name: 'alert-folium-dead-letters'
  location: 'global'
  tags: tags
  properties: {
    description: 'Invoices dead-lettered after five deliveries', severity: 2, enabled: true, scopes: [busId], evaluationFrequency: 'PT15M', windowSize: 'PT1H'
    autoMitigate: true, actions: [{ actionGroupId: group.id }]
    criteria: {
      'odata.type': 'Microsoft.Azure.Monitor.SingleResourceMultipleMetricCriteria'
      allOf: [
        {
          criterionType: 'StaticThresholdCriterion', name: 'dead-lettered', metricNamespace: 'Microsoft.ServiceBus/namespaces', metricName: 'DeadletteredMessages'
          operator: 'GreaterThan', threshold: 0, timeAggregation: 'Maximum'
        }
      ]
    }
  }
}

output connectionString string = insights.properties.ConnectionString
